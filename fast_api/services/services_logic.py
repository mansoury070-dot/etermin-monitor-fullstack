from __future__ import annotations
import core.constants as c
import database.postgres_queries as pg
import database.redis_queries as rq
import services.etermin_api.request_handler as rh
import services.etermin_api.utils as utils
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from fastapi import Request
    import redis
    from sqlalchemy.ext.asyncio import AsyncSession
    from schemas.pydantic_schemas import TaskData

async def initialize_session(r:redis.Redis, session: AsyncSession, session_id: str):
    """
    Bootstraps the frontend state when the application initializes.
    
    This function handles both new and returning users based on the provided session_id:
    - If the session is new, it registers it in the database.
    - If the session exists and has active monitoring tasks, it retrieves the tasks from Redis 
      and restores the user's previous selection state to populate the UI.
    - It also performs state reconciliation: if the database indicates the user is searching 
      but no active tasks exist in Redis, it safely resets the database status to False.
    """
    session_record = await pg.get_or_create_session(session_id, session)
    last_service_key = None
    tasks = {}
    groups_of_services = {}
    if session_record["is_searching"]:
        tasks = await rq.get_tasks(r, session_id)
        # If there are active tasks in the session take the last task and send it to the user to populate the session state
        if tasks:
            dict_keys = list(tasks.keys())
            last_service_key = tasks[dict_keys[-1]]
            office_id = last_service_key.get("office_id")
            groups_of_services = await retrieve_services_logic(r, office_id, session=session)
        else:
            await pg.update_searching_status_in_db(session, session_id, False)
            session_record["is_searching"] = False

    return {
        "current_page": "work_page" if session_record["is_searching"] else "home_page",
        "office_collection": c.OFFICE_COLLECTION,
        "session_id": session_record["session_id"],
        "chat_id": session_record["telegram_chat_id"],
        "action": last_service_key["action"] if session_record["is_searching"] else "Telegram Benachrichtigung",
        "selection": {
            "office": last_service_key["office"] if session_record["is_searching"] else None,
            "group": last_service_key["group"] if session_record["is_searching"] else None,
            "service": last_service_key["service"] if session_record["is_searching"] else None,
            "service_id": last_service_key["service_id"] if session_record["is_searching"] else None
        },
        "desired_time": last_service_key["desired_time"] if session_record["is_searching"] and last_service_key["action"] == "Reservieren" else "08:00 - 10:00",
        "random_time": last_service_key["random_time"] if session_record["is_searching"] and last_service_key["action"] == "Reservieren" else True,
        "tasks": tasks if session_record["is_searching"] else {},
        "current_services": groups_of_services if session_record["is_searching"] else {}
    }    

async def retrieve_services_logic(r: redis.Redis, office_id: int, session_factory: Optional[Callable[[], AsyncSession]] = None,
                                session: Optional[AsyncSession] = None) -> dict:
    """
    Retrieves and caches services for a specific office, grouped by category.

    It first attempts to fetch the grouped services from the Redis cache. If not found, 
    it retrieves the data from the database using either the provided session or the 
    session factory. During the database processing, it also extracts and caches the 
    form parameters for each individual service to optimize future requests. Finally, 
    it groups the services by their group name, caches the result, and returns it.

    Returns:
        dict: A dictionary where the keys are group names, and the values are dictionaries 
        containing the services and their details (id, annotation, price) within that group.
    """
    
    groups_of_services = await rq.get_services_from_redis(r, office_id)
    if groups_of_services:
        print(f"Data for office_id {office_id} retrieved from REDIS!")
        return groups_of_services
        
    print(f"Data for office_id {office_id} retrieved from DATABASE!")

    if session:
        db_records = await pg.get_services_from_db(office_id, session)
    elif session_factory:
        async with session_factory() as new_session:
            db_records = await pg.get_services_from_db(office_id, new_session)
    else:
        raise ValueError("You must provide either 'session' or 'session_factory'")
            
    grouped_services = {}
    
    for row in db_records:
        group_name = row[0]
        service_id = row[1]
        service_name = row[2]
        annotation = row[3]
        price = row[4]
        language = row[5]
        vfields = row[6]
        
        form_params = {
            "serviceid": service_id,
            "language": language,
            "vfields": vfields
        }
        # Cache the form parameters in Redis to avoid separate database queries
        await rq.save_form_params_to_redis(r, service_id, form_params)
        
        if group_name not in grouped_services:
            grouped_services[group_name] = {}
            
        grouped_services[group_name][service_name] = {
            "id": service_id,
            "annotation": annotation,
            "price": price
        }
        
    await rq.save_services_to_redis(r, office_id, grouped_services)
    return grouped_services

async def retrieve_form_logic(r: redis.Redis, session_factory: Callable[[], AsyncSession], webid: str, service_id: int) -> list:
    """
    Retrieves and caches parsed form elements for a specific service.

    It first checks Redis for cached form elements. If missing, it fetches the 
    required parameters (from Redis or PostgreSQL), retrieves the form HTML 
    from the API, parses it, caches the resulting list in Redis, and returns it.

    Returns a list of dictionaries, each containing the elements of a specific form field.
    """
    form_elements = await rq.get_form_elements_from_redis(r, service_id)
    if form_elements:
        return form_elements

    part_of_form_params = await rq.get_form_params_from_redis(r, service_id)
    if not part_of_form_params:
        async with session_factory() as session:
            part_of_form_params = await pg.fetch_form_params_from_db(service_id, session)
        await rq.save_form_params_to_redis(r, service_id, part_of_form_params)

    form_html = await rh.fetch_form_fields(webid, part_of_form_params)
    form_elements = utils.form_parser(form_html) # it is a list
    await rq.save_form_elements_to_redis(r, service_id, form_elements)
    
    return form_elements

async def fetch_appointment_one_time_logic(r: redis.Redis, session_factory: Callable[[], AsyncSession], 
                                           service_id: int, date: Optional[str] = None) -> dict:
    """
    Orchestrates the retrieval of appointment data by managing settings and delegating the API call.

    This function is responsible for retrieving the necessary service settings from the Redis 
    cache (or PostgreSQL if not cached). It then delegates the parameter construction and 
    the actual API request to the underlying helper functions to fetch either available dates 
    or time slots.

    Returns:
        dict: A dictionary containing the available dates or time slots returned by the API.
    """
    cached_settings = await rq.get_settings_from_redis(r, service_id)
    if not cached_settings:
        async with session_factory() as session:
            cached_settings = await pg.fetch_all_settings(service_id, session)
        await rq.save_settings_to_redis(r, service_id, cached_settings)

    result = await rh.fetch_date_or_time_slots(cached_settings, target_date=date)
    return result

async def create_task_logic(r: redis.Redis, session_factory: Callable[[], AsyncSession], 
                       session_id: str, service_id: int, data: TaskData) -> float:
    
    """
    Creates a new tracking task for a user and adds them to the service queue.

    Process flow:
    1. Validates that the session has not exceeded the limit of 2 concurrent services.
    2. Ensures the requested service is not already being tracked by the session.
    3. Prepares task data and assigns a UTC start timestamp.
    4. Updates the relational database (Postgres) to set the session status to actively searching
       if this is the first service for the session.
    5. Saves session details and adds the user to the Redis service queue.
    6. Checks the global schedule: returns the existing scheduled time if active, otherwise
       calculates and assigns a new check time.

    Returns:
        float: The timestamp indicating when the service will be checked next. 
    """
    session_services_list = await rq.get_services_for_session(r, session_id)
    
    if len(session_services_list) >= 2:
        raise ValueError("Du kannst maximal für 2 Services gleichzeitig nach Termine suchen")
    
    if service_id in session_services_list:
        raise ValueError("Du hast schon diesen Service ausgewählt!")
    
    task_dict = data.model_dump(exclude_none=True)
    current_time = datetime.now(timezone.utc).timestamp()
    task_dict["started_at"] = datetime.fromtimestamp(current_time, timezone.utc).isoformat()

    # Update the searching status in Postgres if the session has no active services
    is_first_service = len(session_services_list) == 0
    if is_first_service:
        async with session_factory() as session:
            await pg.update_searching_status_in_db(session, session_id, True)
            await rq.add_user_to_service_queue(r, session_id, service_id, current_time)
            await session.commit()
    else:
        await rq.add_user_to_service_queue(r, session_id, service_id, current_time)

    queue_length = await rq.get_queue_length(r, service_id)
    is_first_user = (queue_length == 1)

    next_check = None
    # If the service is already scheduled, return the score to the user
    service_score = await rq.get_service_score_from_schedule(r, service_id)
    if service_score:
        next_check = service_score
    else:
        # Pass the is_first_user flag to lock_and_alter_schedule to handle empty schedule scenarios.
        # If the global schedule is empty and the user is new, it schedules for immediate execution
        next_check = await rq.lock_and_alter_schedule(r, service_id, is_new=is_first_user)

    task_dict["next_check"] = next_check
    await rq.save_session_details_to_redis(r, session_id, service_id, task_dict)

    return next_check

async def delete_task_logic(r: redis.Redis, session_factory: Callable[[], AsyncSession], session_id: str, service_id: int):
    """
    Removes a user session from a service queue and dynamically optimizes the global execution schedule.

    This function implements a self-healing, resource-efficient scheduling logic:
    
    1. Session Cleanup: Removes the user from the specific service queue in Redis.
    2. Global State Sync: If the user has no remaining active tasks, updates their searching status 
       to False in the PostgreSQL database.
    3. Lazy Deletion (Guard Clauses): If the service queue is not empty, it exits early. 
       Otherwise, it removes the empty service from the global schedule.
    4. Worker Sleep Management: If the global schedule becomes completely empty, it notifies 
       the execution worker via PubSub to enter a deep sleep state.
    5. Cascading Time-Shift (Slot Inheritance): If removing the service creates a time gap, 
       it calculates the difference between the deleted service and the next scheduled one. 
       If this gap exceeds the optimization threshold (10 seconds), it pulls all future 
       services forward by that exact duration.
    6. Targeted Wake-ups: Wakes up the background worker only when a significant schedule 
       compaction occurs, preventing unnecessary CPU cycles and busy-waiting.
    """
    session_services = await rq.get_services_for_session(r, session_id)
    # if the user(session) has no more services running (searching for appointments) update the searching status in Postgres
    is_last_service = len(session_services) == 1
    if is_last_service:
        async with session_factory() as session:
            await pg.update_searching_status_in_db(session, session_id, False)
            await rq.remove_task_from_redis(r, session_id, service_id)
            await session.commit()
    else:
        await rq.remove_task_from_redis(r, session_id, service_id)

    # get the length of the queue for the specific service in order to remove it from the global schedule if it is empty.
    queue_length = await rq.get_queue_length(r, service_id)
    if queue_length > 0:
        return

    # Remove the service from the global schedule in order not to create a backround task for an empty service
    # by the execution worker and get the score of the deleted service in order to apply the shift on other services in 
    # the schedule if the schedule is not empty
    deleted_score = await rq.get_service_score_from_schedule(r, service_id)
    await rq.delete_service_from_schedule(r, service_id)
    # Note: The Redis delete immediatly the empty queue "services:{service_id}:queue". There is no need to delete it here.

    # Guard clause: Prevents TypeError in a race condition where the worker
    # wakes up and pops the service from the schedule at the exact same millisecond the user stops the bot
    if not deleted_score:
        return
    
    remaining_services_count = await rq.get_schedule_length(r)
    # If the schedule is completely empty after deletion,
    # wake the worker to cancel its active timer and enter deep sleep.
    if remaining_services_count == 0:
        await r.publish("wakeup_execution_worker", "schedule_empty")
        return

    # Implement the shift to all services after the deleted services if the schedule is not empty
    future_services = await r.zrange(
        "global:services_schedule", 
        deleted_score, 
        float('inf'), 
        byscore=True, 
        withscores=True
    )
    # Guard clause: If the deleted service was the last one in the schedule,
    # there are no future services to shift. Exits early to prevent IndexError.
    if not future_services:
        return

    # Calculate the gap between the deleted and the next scheduled service.
    # And shift the other services by this amount of time.
    next_score = future_services[0][1]
    time_shift = next_score - deleted_score
    # I think 10 seconds are a reasonable threshold to avoid unnecessary shifting
    if time_shift <= 10.0: 
        return
    shifted_mapping = {srv_id: old_score - time_shift for srv_id, old_score in future_services}
    
    await r.zadd("global:services_schedule", shifted_mapping)
    # Wake up the worker to calculate the new sleeping time and correct the time gap
    await r.publish("wakeup_execution_worker", "schedule_shifted")

async def telegram_webhook_logic(request: Request, session_factory: Callable[[], AsyncSession]):
    data = await request.json()
    message = data.get("message", {})
    text = message.get('text', "")
    if text.startswith("/start"):
        parts = text.split(" ")
        if len(parts) == 2:
            user_uuid = parts[1]
            chat_id = message.get("chat", {}).get("id")
            if chat_id:
                async with session_factory() as db:
                    await pg.save_telegram_chat_id(user_uuid, chat_id, db)
                print(f"success: session {user_uuid} linked to chat {chat_id}")
    return {"status": "ok"}