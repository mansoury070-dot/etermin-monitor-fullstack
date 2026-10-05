from __future__ import annotations
from typing import TYPE_CHECKING, Callable
import core.config as cfg
import tasks
import database.redis_queries as rq
import asyncio
from datetime import datetime, timezone

if TYPE_CHECKING:
    import redis.asyncio as redis
    from sqlalchemy.ext.asyncio import AsyncSession


async def execution_worker(r: redis.Redis, session_factory: Callable[[], AsyncSession]):
    """
    Background worker that processes scheduled services from a Redis Sorted Set.
    
    Lifecycle and Architecture:
    1. Lifecycle & Sleeping: Continuously monitors `global:services_schedule`. 
       - Deep Sleep: If the schedule is empty, it enters a standby state using a PubSub 
         channel (`wakeup_execution_worker`), waking up instantly when a new service is added.
       - Smart Nap: If the next service is scheduled in the future, it sleeps for the exact 
         time difference, avoiding unnecessary CPU cycles (busy-waiting).
         
    2. Connection Management: Uses a 20-second timeout on PubSub listens to act as a heartbeat. 
       This prevents Docker or network proxies from killing the idle connection (TimeoutError).
       
    3. Task Delegation: Pops the service from the schedule using `zrem` to exclusively claim it.
       Then, it delegates the actual external API polling to an asynchronous background task 
       (`process_service_background`). This prevents head-of-line blocking and allows concurrent execution.
    """

    # Publish/Subscribe: Configure the connection to Redis to create pubsub channel, and then subscribe to this channel
    pubsub = r.pubsub()
    await pubsub.subscribe("wakeup_execution_worker")

    background_tasks = set()

    # Main event loop: Continuously checks the schedule for services to process.
    # It handles its own sleep/wake cycles internally to avoid CPU overloading.
    while True:
        try:
            current_time = datetime.now(timezone.utc).timestamp()
            # Fetch the earliest scheduled service from the sorted set (index 0 to 0).
            # withscores=True returns both the service_id and its scheduled timestamp.
            first_service = await r.zrange("global:services_schedule", 0, 0, withscores=True)
            if not first_service: 
                print("Schedule is empty. Sleeping deeply until a new service is added...")
                # The schedule is empty. Enter a standby loop where the worker sleeps 
                # and waits for a wake-up signal, pinging every 20 seconds to keep the connection alive.
                # This prevents Docker from dropping the inactive connection, which would cause a TimeoutError.
                while True: 
                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=20.0)
                    if message:
                        break
                # Go up to the first while loop after the second while loop is broken(message received).
                # It will recalculate the current time at the time the second loop is broken and get the first service in the schedule.
                continue 
            # first service is returned as a list containing one tuple: [(service_id_str, score)]
            service_id_str, schedule_time = first_service[0] 
            time_to_wait = schedule_time - current_time

            # if the time to wait greater than zero, the code will sleep for the required amount of time,
            # and then execute again from the beginning of the first while loop
            if time_to_wait > 0:
                wait_time = min(time_to_wait, 20.0)
                print(f"Sleeping for {time_to_wait:.2f} seconds...")
                await pubsub.get_message(ignore_subscribe_messages=True, timeout=wait_time)
                continue # Go to the first while true loop if the time has not come
            removed = await rq.delete_service_from_schedule(r, service_id_str) # delete it from the schedule
            if removed == 0: # if the deletion fails, execute the loop again
                continue

            # Architectural Note:
            # Previously, services were processed sequentially (one by one) to avoid overwhelming the eTermin API with concurrent requests.
            # We migrated to background tasks using asyncio.create_task to prevent head-of-line blocking and speed up processing.
            # Keep in mind: This concurrent approach might pressure or overwhelm the eTermin API with requests 
            # ONLY IF the application scales up significantly (a massive increase in active users, services, and sessions).
            
            service_id = int(service_id_str) # service_id is returned from redis as a string , so we cast it to an int.
            task = asyncio.create_task(process_service_background(r, session_factory, service_id))

            # ​In modern Python versions, background tasks created with asyncio.create_task must be stored in a collection
            #  to maintain a strong reference. Otherwise, the garbage collector might silently destroy the task
            #  while it is still executing in the background. We use a set to keep these references alive 
            # and attach a callback to automatically remove the task from the set once it completes, which prevents memory leaks.
            background_tasks.add(task)
            task.add_done_callback(background_tasks.discard)
        except Exception as e:
            print(f"Error in execution_worker loop: {e}")
            await asyncio.sleep(1)
            continue

async def process_service_background(r: redis.Redis, session_factory: Callable[[], AsyncSession], service_id: int):
    """
    Asynchronously processes a specific service and handles its scheduling lifecycle.
    This function isolates the processing of a single service to run concurrently without
    blocking the main execution loop. It fast-fails if the queue is empty. Otherwise, it 
    delegates the actual checking of appointments and guarantees that the service is 
    rescheduled if there are still users pending, even in the event of an error.
    """

    should_reschedule = False
    try:
        queue_length = await rq.get_queue_length(r, service_id)

        # Fail-Fast: If the queue is empty, don't ping eTermin. Just let it die.
        if queue_length == 0:
            print(f"Skipping API call and reschedule for {service_id} because its queue is empty.")
            return
        
        # if there are users, check appointments and reschedule
        await tasks.check_appointments(r, session_factory, service_id)
        current_queue_length = await rq.get_queue_length(r, service_id)
        if current_queue_length > 0:
            should_reschedule = True
        else:
            should_reschedule = False
    except Exception as e:
        print(f"Error processing background task for service {service_id}: {e}")
        current_queue_length = await rq.get_queue_length(r, service_id)
        if current_queue_length > 0:
            should_reschedule = True
    finally:
        if should_reschedule:
            # Check queue length again in finally to ensure we don't reschedule an empty queue, 
            # but ALWAYS reschedule if there are still users waiting, even if an error occurred.
            try:
                next_run_time = await rq.lock_and_alter_schedule(r, service_id)
                print(f"Rescheduled service {service_id} at {next_run_time}")
            except Exception as inner_e:
                print(f"Critical error while rescheduling service {service_id}: {inner_e}")
        else:
            print(f"All sessions_processed for service {service_id} no need to reschedule")

async def main():
    print("Starting execution worker...")    
    await execution_worker(cfg.r, cfg.AsyncSessionLocal)

if __name__ == "__main__":
    asyncio.run(main())

