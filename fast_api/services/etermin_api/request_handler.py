import asyncio
from curl_cffi import requests
import services.etermin_api.parameters as p
from bs4 import BeautifulSoup
import json
import services.etermin_api.utils as utils
from typing import Optional

ETERMIN_BASE_URL = "https://www.etermin.net"

def error_handling_decorator(max_retries=3, sleep_interval=5, default_return=None):
    """
    A decorator to handle network errors, JSON parsing errors, and other exceptions for async functions.
    It retries the function execution up to 'max_retries' times before returning a default value.

    Args:
        max_retries (int, optional): Maximum number of retry attempts. Defaults to 3.
        sleep_interval (int, optional): Delay in seconds between retries. Defaults to 5.
        default_return (any, optional): The value to return if all retries fail. Defaults to None.

    Returns:
        function: The wrapped asynchronous function with error handling and retry logic.
    """
  
    def decorator(base_func):
        async def wrapper(*args, **kwargs):
            for attempt in range(max_retries): 
                try:
                    result = await base_func(*args, **kwargs)
                    return result

                except requests.errors.RequestsError as req_err:
                    print(f"Network or request error on attempt {attempt + 1}: {req_err}")
                    await asyncio.sleep(sleep_interval)

                except json.JSONDecodeError:
                    print(f"Data parsing error on attempt {attempt + 1}")
                    await asyncio.sleep(sleep_interval)
                
                except Exception as e:
                    print(f"Unexpected error occurred in {base_func.__name__}: {e}")
                    if hasattr(e, 'response') and e.response is not None:
                        if 400 <= e.response.status_code < 500:
                            print(f"Client error ({e.response.status_code}) - No retry.")
                            return default_return
                    await asyncio.sleep(sleep_interval)
            print(f"{base_func.__name__}: All retries failed!")
            return default_return
        return wrapper
    return decorator

###############################################################################################################################

##################################### Fetch general and service-specific parameters ###########################################
@error_handling_decorator(default_return={})
async def get_office_params(webid: str) -> dict:
    """
    Fetches the general settings and configuration for the target website or office.

    Args:
        webid (str): The unique identifier for the web service (the office in which the user want an appointment).
            Used to construct the headers.

    Returns:
        dict: A dictionary containing the general settings (e.g., caching rules, timezone, deadlines).
              Returns an empty dictionary if the request fails.
    """
    headers= p.construct_headers(webid)
    url_settings = f"{ETERMIN_BASE_URL}/api/settingbs?t="
    async with requests.AsyncSession(impersonate="chrome110") as session:
        settings_response = await session.get(url_settings, headers=headers, timeout=10)
        settings_response.raise_for_status()

        if not settings_response.json():
            print("No settings fetched!")
            return {}
        settings_json = settings_response.json()[0]  # because the server returns a json array with only one element
    settings_dict = {}
    settings_dict["webid"] = headers["webid"]
    settings_dict["language"] = settings_json.get("defaultlanguage", "de")
    settings_dict["appfuture"] = settings_json.get("appfuture", 0)
    settings_dict["appdeadline"] = settings_json.get("appdeadline", 0)
    settings_dict["appdeadlinewm"] = settings_json.get("appdeadlinewm", 0)
    settings_dict["msdcm"] = settings_json.get("msdcm", 0)
    settings_dict["caching"] = settings_json.get("caching", False)
    settings_dict["cluster"] = settings_json.get("cluster", False)
    settings_dict["limitappointments"] = settings_json.get("limitappointments", 0)
    settings_dict["limitappointmentstype"] = settings_json.get("limitappointmentstype", 0)
    settings_dict["onetimebooking"] = settings_json.get("onetimebooking", False)
    settings_dict["latf"] = settings_json.get("latf", 0)
    settings_dict["z"] = settings_json.get("z")
    settings_dict["agb"] = settings_json.get("agb", False)
    settings_dict["agblink"] = settings_json.get("agblink", "")
    settings_dict["dp"] = settings_json.get("dp", False)
    settings_dict["dplink"] = settings_json.get("dplink", False)
    settings_dict["nea"] = settings_json.get("nea", 0)
    settings_dict["enablefeedback"] = settings_json.get("enablefeedback", False)
    settings_dict["street"] = settings_json.get("street", "")
    settings_dict["zip"] = settings_json.get("zip", "")
    settings_dict["city"] = settings_json.get("city", "")
    settings_dict["timezone"] = settings_json.get("timezone", "")
    settings_dict["canceldeadline_settings"] = settings_json.get("canceldeadline")
    settings_dict['appointmentreminderhours'] = settings_json.get("appointmentreminderhours")
    settings_dict['appointmentreminderhours2'] = settings_json.get("appointmentreminderhours2")
    settings_dict['customerconfirm'] = settings_json.get("customerconfirm")
    settings_dict['customerconfirmtime'] = settings_json.get("customerconfirmtime")
    settings_dict['bl'] = settings_json.get("bl")
    settings_dict['storeip'] = settings_json.get("storeip")
    settings_dict['apw'] = settings_json.get('apw')
    settings_dict['showreminder'] = settings_json.get('showreminder')
    settings_dict['vfields'] = settings_json.get('vfields')
    settings_dict['vservices'] = settings_json.get('vservices')
    settings_dict['fillcalendarstrategy'] = settings_json.get('fillcalendarstrategy', 0)
    settings_dict['settings_showavcap'] = settings_json.get('showavcap')
    print("General settings fetched successfully")

    return settings_dict
        

@error_handling_decorator(default_return={})
async def get_services(webid: str, office: str) -> dict:
    """
    Retrieves the service-specific parameters based on the office and general settings.

    Args:
        webid (str): The unique identifier for the web service (the office in which the user want an appointment).
            Used to construct the headers.
        office (str): The name of the office to check if specific rules (like Hamborn) apply.

    Returns:
        dict: A nested dictionary where the first key is the service group name, 
              and the value is another dictionary of services containing their specific settings.
    """
    
    settings = await get_office_params(webid)
    if not settings:
        print("Aborting get_services because get_office_params failed!")
        return {}
    
    headers = p.construct_headers(webid)
    service_params = p.construct_services_params(webid, settings, hamborn=True if office == 'Ausländerbehörde Hamborn' else False)
    url_services = f"{ETERMIN_BASE_URL}/api/servicegroupservice"
    async with requests.AsyncSession(impersonate="chrome110") as session:
        services_response = await session.get(url_services, headers=headers, params=service_params, timeout=10)
        services_response.raise_for_status()
        services_json = services_response.json()
    groups_dict = {}

    for item in services_json:
        raw_group_name = item.get('sg') or ""
        raw_service_name = item.get('s') or ""

        raw_service_annotation = item.get('sa') or ""
        service_id = item.get('sid') 
        duration = item.get('duration') if item.get("showduration") else 0
        capacity = item.get('nrappsel') or item.get('capacitynonsel') or 1
        captype = item.get('captype')
        enablecapacity = item.get('enablecapacity', False)
        canceldeadline = item.get('canceldeadline')
        rh = item.get('rh')
        rh2 = item.get('rh2')
        cc = item.get('cc')
        cct = item.get('cct')
        abb = item.get('abb')
        lb = item.get('lb')
        limitappointments = item.get('la') if lb == 1 else settings['limitappointments']
        limitappointmentstype = item.get('lat') if lb == 1 else settings['limitappointmentstype']
        limitservice = service_id if item.get('ls') == 1 else 0
        msdcm = settings['msdcm'] if item.get('msdcm') == -1 else item.get('msdcm')
        price = item.get('price')
        addapphours = item.get('addapphours')
        fcs = item.get('fcs')
        service_showavcap = item.get('showavcap')

        if not raw_service_name or not service_id:
            print(f"warning in get_services function: Skipping an entry due to missing data in {webid}")
            continue # some entries are just to diaplay the groups without containig services, so we dont want them

        group_name = BeautifulSoup(raw_group_name, "html.parser").get_text().strip()
        service_name = BeautifulSoup(raw_service_name, "html.parser").get_text().strip()

        if group_name not in groups_dict:
            groups_dict[group_name] = {}
        if service_name not in groups_dict[group_name]:
            groups_dict[group_name][service_name] = {}
        groups_dict[group_name][service_name].update({
            **settings,
            'serviceid': service_id,
            'servicetext': service_name,
            'serviceannotation': raw_service_annotation,
            'servicegroup': group_name,
            'raw_group_name': raw_group_name,
            'duration': duration,
            'capacity': capacity,
            'captype': captype,
            'enablecapacity': enablecapacity,
            'canceldeadline_service': canceldeadline,
            'rh': rh,
            'rh2': rh2,
            'cc': cc,
            'cct': cct,
            'abb': abb,
            'limitappointments': limitappointments,
            'limitappointmentstype': limitappointmentstype,
            'limitservice': limitservice,
            'msdcm': msdcm,
            'price': price,
            'addapphours': addapphours,
            'fcs': fcs,
            'service_showavcap': service_showavcap
        })
    return groups_dict
        
###############################################################################################################################

######################################################## Fetch form ###########################################################
@error_handling_decorator(default_return="")
async def fetch_form_fields(webid: str, part_of_form_params: dict) -> str:
    """
    Fetches the HTML form fields required to collect user information for booking.

    Args:
        webid (str): The unique identifier for the web service (the office in which the user want an appointment).
            Used to construct the headers.
        part_of_form_params (dict): part of The URL parameters for fetching the correct form.
            The wohle parameters are created in this function

    Returns:
        str: The raw HTML content of the form. Returns an empty string if it fails.
    """

    url = f"{ETERMIN_BASE_URL}/api/field"

    headers = p.construct_headers(webid)
    params = p.form_params(part_of_form_params)

    async with requests.AsyncSession(impersonate="chrome110") as session:
        response = await session.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()

        print("Form fetched successfully")
        return response.text

###############################################################################################################################

################################################ request appointment ##########################################################
@error_handling_decorator(default_return={})
async def fetch_date_or_time_slots(settings: dict, target_date: Optional[str] = None) -> dict:
    """
    Retrieves available appointment dates or specific time slots based on the input.
    If `target_date` is passed, it returns the available time slots inside that specific date.
    If `target_date` is not passed (None), it returns a list of dates that currently have available appointments.

    Args:
        settings (dict): The settings dictionary containing 'webid' and other config rules.
        target_date (Optional[str]): The specific date to fetch time slots for. Defaults to None.

    Returns:
        dict: A dictionary containing available dates ({"dates": [...]}) 
              or a dictionary of time slots mapped by their start time.
    """
    webid = settings["webid"]
    headers = p.construct_headers(webid)
    params = p.date_or_time_slot_params(settings, target_date=target_date)

    url = f"{ETERMIN_BASE_URL}/api/timeslots"

    async with requests.AsyncSession(impersonate="chrome110") as session:
        response = await session.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    if not data:
        print("No available dates or time slots")
        if "rangesearch" in params:
            return {"dates": []}
        return {}
    
    if "rangesearch" in params: # if range search activated, it scans a range of dates for appointments like from 01.06 to 01.07
        dates = {"dates": []} # I adjusted the dates variable to match the default return in the decorator. the older version was just dates = [], so I had two default returns in this function
        for date in data:
            dates["dates"].append(date["start"].split("T")[0]) #start:"2026-05-29T00:00:00" --> 2026-05-29
        return dates
    slots = {} # if range search is not activated, it retrieves the available appointments in a specific date
    for slot in data:
        id_and_timeslot = slot["idandtimeslot"].split("|") # example: idandtimeslot:"90709|2026-05-29 08:50|2026-05-29 09:00|Fahrzeugzulassung|0"
        start_time = id_and_timeslot[1] # --> 2026-05-29 08:50
        end_time = id_and_timeslot[2] # --> 2026-05-29 09:00
        dict_key = start_time.split(" ")[1] # I made the start time the dict key to access the time slot 2026-05-29 08:50 --> 08:50
        slots[dict_key] = {
            'start': start_time,
            'end': end_time,
            'calendarid': id_and_timeslot[0], # --> 90709
            'calendarname': id_and_timeslot[3], #--> Fahrzeugzulassung
            'hash': slot['hv'],
            'ecap': slot['ecap'],
            'capmax': slot['capmax']
        }
    return slots

###############################################################################################################################

#################################################### Telegram #################################################################
@error_handling_decorator()
async def send_telegram_notification(token: str, chat_id: str | int, message: str):
    """
    Sends a notification message to a specific Telegram chat using a bot token.

    Args:
        token (str): The Telegram Bot API token.
        chat_id (str | int): The ID of the Telegram chat or user to send the message to.
        message (str): The text message to be sent.

    Returns:
        None
    """
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message
    }

    async with requests.AsyncSession() as session:
        response = await session.post(url, json=payload, timeout=10)
        response.raise_for_status()
    return
        
###############################################################################################################################

################################################ Booking request ##############################################################
@error_handling_decorator(default_return=False)
async def limit_reached_request(webid: str, date: str, settings: dict, user_data: dict) -> bool:
    """
    Sends a request to the server to check if the user has reached their maximum allowed bookings.

    Args:
        webid (str): The unique identifier for the web service.
        date (str): The target date passed to construct the limit check parameters.
        settings (dict): The service settings used to build the limit check parameters.
        user_data (dict): The user's personal information used to build the limit check parameters.

    Returns:
        bool: True if the user is allowed to book (limit not reached), False otherwise.
    """

    url = f"{ETERMIN_BASE_URL}/limitreached"
    headers = p.construct_headers(webid)
    params = p.limit_reached_params(date, settings, user_data)
    async with requests.AsyncSession(impersonate="chrome110") as session:
        response = await session.get(url, headers=headers, params=params)
        response.raise_for_status()
        print("limit reached request processed successfully")
        result = response.json()
    if result == 0:
        print(f"Limit check passed ({result}). Ready to book")
        return True
    else:
        print(f"Limit reached! ({result}). you cannot book more appointments")
        return False

@error_handling_decorator(default_return={})  
async def book_appointment(webid: str, settings: dict, user_data: dict, appointment_details: dict, 
                           is_second_request: Optional[bool] = False, addapphours: Optional[int] = 0) -> dict:
    """
    Submits the final request to book an appointment with the selected service.

    Args:
        webid (str): The unique identifier for the web service. 
            It is used to construct the HTTP headers (via `p.construct_headers`) 
            and the main booking payload (via `p.construct_book_data`).
        settings (dict): Configuration settings. 
            It is used to check reminder preferences for the booker info (via `utils.create_bookerinfo`) 
            and to build the main booking payload (via `p.construct_book_data`).
        user_data (dict): The user's personal information. 
            It is used to generate the formatted booker info string (via `utils.create_bookerinfo`) 
            and to construct the main booking payload (via `p.construct_book_data`).
        appointment_details (dict): Details about the chosen appointment (time, service, hash, etc.). 
            It is used to populate the required time and service fields in the booking payload (via `p.construct_book_data`).
        is_second_request (Optional[bool]): A flag used to correctly format the final URL-encoded body 
            (via `utils.construct_encoded_body`) depending on whether this is a primary or a follow-up booking request. 
            Defaults to False.
        addapphours (Optional[int]): Additional hours, used to adjust the appointment time parameters when formatting the final 
            encoded body (via `utils.construct_encoded_body`). Defaults to 0.


    Returns:
        dict: The JSON response from the server indicating the booking status.
    """
    url = f"{ETERMIN_BASE_URL}/api/appointment"

    bookerinfo = utils.create_bookerinfo(user_data, settings["showreminder"])
    body = p.construct_book_data(webid, settings, user_data, appointment_details, bookerinfo)
    encoded_body = utils.construct_encoded_body(body, is_second_request, addapphours)

    headers = p.construct_headers(webid, booking=True)

    async with requests.AsyncSession(impersonate="chrome110") as session:
        response = await session.post(url, headers=headers, data=encoded_body)
        response.raise_for_status()
        print("congrats, appointment booked successfully, please confirm it from your email!")
        result = response.json()
        return result

###############################################################################################################################
