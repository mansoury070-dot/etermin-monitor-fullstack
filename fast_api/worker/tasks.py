from __future__ import annotations
from typing import TYPE_CHECKING, Callable
import services.services_logic as ser
import services.etermin_api.request_handler as rh
import database.redis_queries as rq
import services.etermin_api.utils as utils
from core.constants import MY_BOT_TOKEN
import asyncio
import random

if TYPE_CHECKING:
    import redis.asyncio as redis
    from sqlalchemy.ext.asyncio import AsyncSession


async def check_appointments(r: redis.Redis, session_factory: Callable[[], AsyncSession], service_id):
    """
    Checks for available appointments for a given service and processes user tasks.

    This function fetches the currently available dates for a specific service.
    If dates are found, it retrieves all active user sessions waiting for this service.
    It splits the tasks into two categories: automated reservations and Telegram notifications.
    
    To prevent false positive alerts, it prioritizes reservation tasks first. 
    If appointments are still available after all reservation attempts are completed, 
    it fetches the updated dates and sends Telegram notifications to the remaining users.
    """

    # with range search, the returned list contains several dates. Note that a single date can hold multiple appointmnets
    available_dates_response = await ser.fetch_appointment_one_time_logic(r, session_factory, service_id)
    available_dates = available_dates_response.get("dates", [])
    if not available_dates:
        print(f"no available appointments for service: {service_id}")
        return
    
    # retrieve all sessions for a certain service
    session_ids = await rq.get_sessions_by_service_id(r, service_id)
    if not session_ids:
        return
    # I seperate the reservation tasks from telegram tasks and handle firstly the reservation tasks.
    # This avoids sending false telegram notifications when the appoinntment is already booked
    sessions_dicts_reservation = []
    sessions_dicts_telegram = []
    for (session_id, _) in session_ids:
        try:
            session_dict = await rq.get_task_details(r, session_id, service_id)
            session_dict["session_id"] = session_id 
            action = session_dict["action"]
            if action == "Reservieren":
                sessions_dicts_reservation.append(session_dict)
            if action == "Telegram Benachrichtigung":
                sessions_dicts_telegram.append(session_dict)
        except Exception as e:
            print(f"Error fetching details for session {session_id}: {e}")

    if sessions_dicts_reservation:
        total_reservations = len(sessions_dicts_reservation)
        for index, session_dict_reservation in enumerate(sessions_dicts_reservation):
            try:
                total_found_slots = await handle_reservation(r, session_factory, service_id, session_dict_reservation, available_dates)
                # Stop processing if no slots are left server-wide
                if total_found_slots == 0:
                    print(f"No slots left. Breaking the session loop for service {service_id}")
                    break
                # Apply delay only if this is not the last reservation task
                if index < total_reservations - 1:
                    delay = random.uniform(10, 20)
                    await asyncio.sleep(delay)
            except Exception as e:
                print(f"Reservation failed for session: {e}")

    if sessions_dicts_telegram:
        try:
            fresh_dates_response = await ser.fetch_appointment_one_time_logic(r, session_factory, service_id)
            available_dates = fresh_dates_response.get("dates", [])
            if available_dates:
                for session_dict_telegram in sessions_dicts_telegram:
                    await handle_telegram(r, session_factory, session_dict_telegram, available_dates)
        except Exception as e:
            print(f"Error handling Telegram notifications: {e}")

async def handle_reservation(r: redis.Redis, session_factory: Callable[[], AsyncSession], 
                             service_id: int, session_details, available_dates) -> int:   
    """
    Attempts to book a suitable appointment for a user based on their preferences.

    This function iterates over the provided available dates, fetching specific time slots 
    for each date and accumulating the total number of available slots. If a slot matches 
    the user's desired time criteria, it proceeds to book it. Before booking, it verifies 
    that the user hasn't exceeded their booking limits. Upon a successful booking, it saves 
    the confirmation details to Redis and deletes the completed task.

    Returns:
        int: The total number of time slots found across the checked dates (total_found_slots). 
        Returning 0 signals to the calling function that no slots are left server-wide.
    """

    webid = session_details["webid"]
    session_id = session_details["session_id"]
    desired_date = None
    appointment_details = {}
    # Accumulates the total available slots for the current service. If no slots are found (total_found_slots == 0), 
    # it signals the caller (check_appointments) to stop processing remaining reservation tasks, 
    # thereby optimizing performance and reducing overhead.
    total_found_slots = 0
    # Loop over the available dates and fetch the slots in each date io order to find the right appointmnet for the user
    for date in available_dates:
        available_slots = await ser.fetch_appointment_one_time_logic(r, session_factory, service_id, date=date)
        if available_slots:
            total_found_slots += len(available_slots)

        desired_appointment = utils.desired_time_request(desired_time=session_details["desired_time"], 
                                                time_slots=available_slots, random_time=session_details["random_time"])
        if desired_appointment:
            appointment_details = desired_appointment
            desired_date = date
            # Do not loop over the rest of the dates if you find the desired appointment or slot given by the user
            break
        
    if not appointment_details:
        print(f"no appropriate appointment found for session: {session_id} for the service {service_id}")
        return total_found_slots

    #To Do: I must ensure that the settings key is still in Redis and is not expired (I have set ex=3600)
    settings = await rq.get_settings_from_redis(r, service_id) 

    user_data = session_details["user_data"]
    can_book = await rh.limit_reached_request(webid, desired_date, settings, user_data)
    if not can_book:
        print(f"limit reached for this session: {session_id}, you can not book right now")
        await rq.set_fail_message(r, session_id, service_id)
        await ser.delete_task_logic(r, session_factory, session_id, service_id)
        return total_found_slots
    
    book_response_data = await rh.book_appointment(webid, settings, user_data, appointment_details)
    addapphours = settings.get('addapphours', 0)
    if addapphours > 0:
        await rh.book_appointment(webid, settings, user_data, appointment_details, is_second_request=True, addapphours=addapphours)
    # I only want the book reference from the booking-request respone 
    if book_response_data and "AdditionalInformation" in book_response_data: 
        book_data = utils.construct_appointment_details(appointment_details, user_data, settings, session_details,
                                                        book_response_data["AdditionalInformation"])
        
        await rq.save_booking_details(r, session_id, service_id, book_data)
        await ser.delete_task_logic(r, session_factory, session_id, service_id)
    return total_found_slots

async def handle_telegram(r: redis.Redis, session_factory: Callable[[], AsyncSession], session_details: dict, dates: list):
    """
    Sends a Telegram notification to the user and cleans up the task.

    This function constructs and sends a Telegram message containing the available 
    appointment dates. After the notification is successfully sent, it saves the 
    found dates to Redis for the specific session and deletes the task from the queue 
    since it has been fully processed.
    """
    await rh.send_telegram_notification(MY_BOT_TOKEN, session_details["chat_id"],
                            f"🎯 Löttchen Termine für {session_details['service']} gefunden! 🕒\n\n📅 Verfügbare Termine:\n"
                            + "\n".join(dates))
    await rq.save_dates(r, session_details["session_id"], session_details["service_id"], dates)
    await ser.delete_task_logic(r, session_factory, session_details["session_id"], session_details["service_id"])