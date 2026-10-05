import redis.asyncio as redis
import asyncio
from datetime import datetime, timezone
import json
import ast
import random 

async def save_services_to_redis(r: redis.Redis, office_id: int, groups_of_services: dict):
    key = f"office_services:{office_id}"
    groups_of_services_json = json.dumps(groups_of_services)
    await r.set(key, groups_of_services_json, ex=3600)

async def get_services_from_redis(r: redis.Redis, office_id: int) -> dict | None:
    """
    Retrieves the grouped services for a specific office from the Redis cache.

    Returns:
        dict | None: A dictionary containing the grouped services if found in the cache, 
        otherwise None.
    """
    key = f"office_services:{office_id}"
    groups_of_services = await r.get(key)
    if groups_of_services:
        return json.loads(groups_of_services)

async def save_form_params_to_redis(r: redis.Redis, service_id: int, form_params: dict):
    """
    Saves the parameters used to fetch the right form for a specific service in Redis
    """
    key = f"form_params:{service_id}"
    form_params_json = json.dumps(form_params)
    await r.set(key, form_params_json, ex=3600)

async def get_form_params_from_redis(r: redis.Redis, service_id) -> dict | None:
    key = f"form_params:{service_id}"
    form_params = await r.get(key)
    if form_params:
        return json.loads(form_params)

async def save_form_elements_to_redis(r: redis.Redis, service_id: int, form_elements: list):
    """
    Saves the form elements for a specific service in Redis
    """
    key = f"form_elements:{service_id}"
    form_elements_json = json.dumps(form_elements)
    await r.set(key, form_elements_json, ex=3600)

async def get_form_elements_from_redis(r: redis.Redis, service_id) -> list:
    key = f"form_elements:{service_id}"
    form_elements = await r.get(key)
    if form_elements:
        return json.loads(form_elements)

async def remove_task_from_redis(r: redis.Redis, session_id:str, service_id: int):
    session_key = f"session:{session_id}:service:{service_id}"
    queue_key = f"service:{service_id}:queue"

    async with r.pipeline(transaction=True) as pipe:
        pipe.delete(session_key)
        pipe.zrem(queue_key, session_id)
        await pipe.execute()

async def delete_service_from_schedule(r: redis.Redis, service_id: int|str) -> int:
    """
    Deletes the service from global:service_schedule
    """
    return await r.zrem("global:services_schedule", service_id)

async def get_service_score_from_schedule(r: redis.Redis, service_id: int) -> float:
    """
    Returns the score of a specific service in global:services_schedule
    """
    score = await r.zscore("global:services_schedule", service_id)
    return score


async def add_user_to_service_queue(r: redis.Redis, session_id: str, service_id: int, started_at: float):
    """
    Adds the session to the service's waiting queue (Sorted Set) using the start time as the score.
    """
    queue_key = f"service:{service_id}:queue"
    await r.zadd(queue_key, {session_id: started_at})

async def get_queue_length(r: redis.Redis, service_id: int) -> int:
    """
    Returns the number of active session in queue of a specific service (service:{service_id}:queue)
    """
    queue_key = f"service:{service_id}:queue"
    queue_length = await r.zcard(queue_key)
    return queue_length

async def get_schedule_length(r: redis.Redis) -> int:
    """
    Returns the number of the active services in global:services_schedule
    """
    return await r.zcard("global:services_schedule")

async def get_services_for_session(r: redis.Redis, session_id: str) -> list:
    """
    Retrieves a list of all active service IDs associated with a specific user session.
    """
    services = []
    pattern = f"session:{session_id}:service:*"
    async for key in r.scan_iter(match=pattern, count=10):
        service_id = key.split(":")[3]
        services.append(int(service_id))
    return services

async def save_session_details_to_redis(r: redis.Redis, session_id: str, service_id: int, details: dict):
    """
    Converts all values in the details dictionary to strings to ensure compatibility with Redis and stores the session 
    details in a Redis Hash.
    """
    key = f"session:{session_id}:service:{service_id}"
    #the dictionary can contain boolian and None values and the redis understands only strings
    stringified_details = {}
    for k, v in details.items():
        if isinstance(v, dict):
            stringified_details[str(k)] = json.dumps(v)
        else:
            stringified_details[str(k)] = str(v)
            
    await r.hset(key, mapping=stringified_details)

async def get_task_details(r: redis.Redis, session_id: str, service_id: int) -> dict:
    details = await r.hgetall(f"session:{session_id}:service:{service_id}")
    
    if "user_data" in details:
        try:
            details["user_data"] = json.loads(details["user_data"])
        except json.JSONDecodeError:
            details["user_data"] = ast.literal_eval(details["user_data"])
            
    if "random_time" in details:
        details["random_time"] = details["random_time"] == "True"
        
    return details
            

async def get_tasks(r: redis.Redis, session_id: str) -> dict:
    """
    Retrieves all tasks or active services for a specific session and returns a dict
    where the keys are the service_id the values are the task details
    """
    pattern = f"session:{session_id}:service:*"
    data = {}
    async for key in r.scan_iter(match=pattern):
        raw_data = await r.hgetall(key)
        if raw_data:
            service_id = raw_data["service_id"]
            data[service_id] = raw_data
    return data


async def save_settings_to_redis(r: redis.Redis, service_id: int, settings: dict):
    key = f"settings:{service_id}"
    settings_json = json.dumps(settings)
    await r.set(key, settings_json, ex=3600)

async def get_settings_from_redis(r: redis.Redis, service_id: int) -> dict | None:
    key = f"settings:{service_id}"
    json_string = await r.get(key)
    if json_string:
        return json.loads(json_string)
    return None

async def set_fail_message(r: redis.Redis, session_id: str, service_id: int):
    fail_key = f"fail:{session_id}:{service_id}"
    fail_message = "you reached your limit!"
    await r.set(fail_key, fail_message, ex=3600)

async def get_fail_message(r: redis.Redis, session_id: str, service_id: int):
    fail_key = f"fail:{session_id}:{service_id}"
    return await r.get(fail_key)

async def get_sessions_by_service_id(r: redis.Redis, service_id: int) -> list | None:
    """
    Retrieves all active sessions with their scores that are waiting for an appointment by a specific service
    """
    queue_key = f"service:{service_id}:queue"
    result = await r.zrange(queue_key, 0, -1, withscores=True)
    if not result:
        return None
    return result  #[(), (), ... etc]

async def save_booking_details(r: redis.Redis, session_id: str, service_id: int, data: dict):
    key = f"book:{session_id}:{service_id}"
    data_json = json.dumps(data)
    await r.set(key, data_json)

async def get_booking_details(r: redis.Redis, session_id: str, service_id: int) -> dict | None:
    key = f"book:{session_id}:{service_id}"
    details_json = await r.get(key)
    if details_json:
        return json.loads(details_json)

async def save_dates(r: redis.Redis, session_id: str, service_id: int, dates: list):
    key = f"dates:{session_id}:{service_id}"
    dates_json = json.dumps(dates)
    await r.set(key, dates_json, ex=1800)

async def get_dates(r: redis.Redis, session_id: str, service_id: int)-> list | None:
    key = f"dates:{session_id}:{service_id}"
    dates_json = await r.get(key)
    if dates_json:
        return json.loads(dates_json)

async def get_next_check(r: redis.Redis, session_id: str, service_id: int) -> dict:
    """
    Primary function: Returns the timestamp for the next scheduled check.
    
    Conditional behavior: If the background task has found appointments, 
    it dynamically returns either the booking confirmation (if auto-book is set) 
    or the available dates/slots. Includes a fallback wait loop if the service is currently processing.
    """
    start_time = datetime.now(timezone.utc).timestamp()
    max_wait_time = 25
    schedule_key = f"global:services_schedule"
    # The service might still be in processing by check_appointments function.
    # This happens when the service has many sessions waiting and appointments are found,
    # causing the next check time to temporarily be None in Redis, because it will be removed from "global:services_schedule"
    # and re-added when the check_appointments finish.
    # Therefore, a while True loop is used to wait for the processing to finish, avoiding a None response being returned to the user. 
    while True:
        book_data = await get_booking_details(r, session_id, service_id)
        if book_data:
            return book_data
        
        dates = await get_dates(r, session_id, service_id)
        if dates:
            return {
                "dates": dates
            }
        fail_message = await get_fail_message(r, session_id, service_id)
        if fail_message:
            return {
                "message": fail_message,
                "is_fatal": True
            }
        next_check = await r.zscore(schedule_key, service_id)
        if next_check is not None:
            return {
                "next_check": next_check
            }
        session_services = await get_services_for_session(r, session_id)
        if service_id not in session_services:
            print(f"Service {service_id} was deleted for session {session_id}. Stopping early.")
            return {
                "message": "Die Suche wurde beendet oder die Aufgabe wurde gelöscht.",
                "is_fatal": True
            }
        current_time = datetime.now(timezone.utc).timestamp()
        elapsed_time = current_time - start_time
        if elapsed_time >= max_wait_time:
            print(f"Service {service_id} check timed out. Alerting user.")
            return {
                "message": "Das System ist derzeit stark ausgelastet. Bitte versuche es in ein paar Minuten erneut."
            }
        await asyncio.sleep(3)


async def lock_and_alter_schedule(r: redis.Redis, service_id: int, is_new: bool = False) -> float:
    """
    Safely calculates and schedules the next execution time for a service using a Redis lock.
    
    This function prevents race conditions by locking the scheduling process. It checks the 
    latest scheduled time for the services in the global services queue and appends the new service with a random 
    time delay 30 seconds plus a jitter between 10 to 20 seconds to prevent execution spikes. If the schedule 
    is empty and the service is new, it schedules it for immediate execution. Finally, it 
    publishes a signal to wake up the background worker.
    
    Returns:
        float: The calculated timestamp for the next execution.
    """
    async with r.lock("schedule_lock", timeout=5.0):
        current_time = datetime.now(timezone.utc).timestamp()
        last_entry = await r.zrange("global:services_schedule", 0, 0, desc=True, withscores=True) # returns a list with one tuple [(service_id, score)]
        if last_entry:
            latest_score = last_entry[0][1]

            # Fail-safe: Ensures the base time is never in the past. 
            # This protects against edge cases like server restarts, downtime, or unexpected event loop spikes.
            base_time = max(current_time, latest_score)  
            jitter = random.uniform(10, 20)
            next_run_time = base_time + 30 + jitter
        else:
            if is_new:
                next_run_time = current_time
            else:
                jitter = random.uniform(10, 20)
                next_run_time = current_time + 30 + jitter

        await r.zadd("global:services_schedule", {service_id: next_run_time}) # store the next check time as a timestamp
        await r.publish("wakeup_execution_worker", "wake_up!")
        return next_run_time
    