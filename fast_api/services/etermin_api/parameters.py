from datetime import date
import uuid
from typing import Optional


def construct_services_params(webid: str, settings: dict, hamborn: bool) -> dict:
    """
    Constructs the URL parameters required to fetch services for a specific office.

    Args:
        webid (str): The unique identifier for the web service.
        settings (dict): A dictionary containing service configurations such as 'vservices' and 'language'.
        hamborn (bool): A flag indicating whether to include the specific service group ID for Hamborn.

    Returns:
        dict: A dictionary containing the constructed parameters for the URL.
    """
    return {
        'cache': 1,
        'w': webid,
        'v': settings['vservices'],
        'lang': settings['language'],
        **({'servicegroupid': 117957} if hamborn else {})
    }

def construct_headers(webid: str, booking: Optional[bool] = False) -> dict:
    """
    Constructs the HTTP headers required for making requests, ensuring they mimic an XHR request.

    Args:
        webid (str): The unique identifier used in the Referer and webid headers.
        booking (bool, optional): A flag indicating whether the headers are for a booking request. Defaults to False.

    Returns:
        dict: A dictionary representing the HTTP headers.
    """
    headers = {
        #These headers are to ensure that the request comes from JS code using XHR, not from the navigation
        'Accept': 'application/json, text/plain',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        #disable the headers that are automatically added when requesting from the navigation. This is necessary because of 
        #the impersonation feature in the curl_cffi library.
        'Sec-Fetch-User': None,
        'Upgrade-Insecure-Requests': None,
        #etermin-specific headers
        'Cache-Control': 'no-cache',
        'content-type': 'application/json',
        'Pragma': 'no-cache',
        'priority': 'u=1, i',
        'Referer': f'https://www.etermin.net/{webid}',
        'webid': webid,
    }
    if booking:
        headers['origin'] = 'https://www.etermin.net'

    return headers


def date_or_time_slot_params(settings: dict, target_date: Optional[str] = None) -> dict:
    """
    Constructs the parameters required to fetch available dates or time slots.

    Args:
        settings (dict): A dictionary containing service configurations and calendar settings.
        target_date (str, optional): The specific date to check for time slots in ISO format (YYYY-MM-DD). 
                                     If None, it fetches available dates from today onwards. Defaults to None.

    Returns:
        dict: A dictionary containing the query parameters for the API request.
    """
  
    showavcap = None
    if settings["service_showavcap"] == -1:
        showavcap = settings["settings_showavcap"]
    elif settings["service_showavcap"] == 0:
        showavcap = 'false'
    elif settings["service_showavcap"] == 1:
        showavcap = 'true'

    return {
        'date': (target_date if target_date else date.today().isoformat()),
        'serviceid': settings['serviceid'],
        'capacity': 1,
        **({'rangesearch': 1} if not target_date else {}),
        'caching': settings['caching'],
        'duration': 0 if settings['captype'] == -1 else settings['duration'],
        'cluster': settings['cluster'],
        'slottype': 0,
        'fillcalendarstrategy': settings['fillcalendarstrategy'] if settings['fcs'] in [-1, "-1", None, ""] else settings['fcs'], 
        'showavcap': showavcap,
        'appfuture': settings['appfuture'],
        'appdeadline': settings['appdeadline'],
        'appdeadlinewm': settings['appdeadlinewm'],
        'oneoff': 'null', 
        'msdcm': settings['msdcm'],
        **(
            {
                'tz': 'W. Europe Standard Time',
                'tzaccount': 'W. Europe Standard Time'
            } if target_date else {}),
        'calendarid': '' 
    }

def form_params(settings: dict) -> dict:
    """
    Constructs the parameters required to fetch the booking form data.

    Returns:
        dict: A dictionary containing the parameters for the form request.
    """
   
    return {
        'output': 'html',
        'serviceid': settings['serviceid'],
        'lang': settings['language'],
        'v': settings['vfields'],
        'requestaccess': False,
        'cache': 1,
    }

def limit_reached_params(date: str, settings: dict, user_data: dict) -> dict:
    """
    Constructs the parameters to check if the user has reached their appointment booking limit.

    Returns:
        dict: A dictionary containing the parameters to validate booking limits.
    """
    return {
        'startdate': date,
        'limitappointments': settings['limitappointments'],
        'latf': settings['latf'],
        'limitappointmentstype': settings['limitappointmentstype'],
        'onetimebooking': settings['onetimebooking'],
        'z': settings['z'],
        'email': user_data['Email'],
        'phone': user_data['Phone'],
        'lastname': user_data['LastName'],
        'birthday': user_data.get('Birthday', 'undefined'),
        'limitservice': settings['limitservice'],
        'company': user_data.get('Company', 'undefined'),
        'additional1': user_data.get('additional1', 'undefined'),
        'firstname': user_data['FirstName'],
    }

def get_customer_confirm(service_cc: int, setting_cc: bool) -> bool:
    """
    Determines whether customer confirmation is required based on service and general settings.

    Args:
        service_cc (int): The service-specific customer confirmation setting (-1, 0, or 1).
        setting_cc (bool): The general customer confirmation fallback setting.

    Returns:
        bool: True if customer confirmation is required, False otherwise.
    """
    if service_cc == -1:
        return setting_cc # in the general setting "customerconfirm": True or False
    elif service_cc == 0:
        return False
    else:
        return True

def construct_book_data(webid: str, settings: dict, user_data: dict, appointment_data: dict, booker_info: str) -> dict:
    """
    Constructs the final payload data required to book an appointment.

    Args:
        webid (str): The unique identifier for the web office.
        settings (dict): A dictionary containing comprehensive service configurations.
        user_data (dict): A dictionary containing the user's personal and contact details.
        appointment_data (dict): A dictionary containing the selected appointment slot details.
        booker_info (str): An encoded string containing the booker's information.

    Returns:
        dict: A dictionary containing the complete payload to be sent via POST request to finalize the booking.
    """
    cap_suffix = " (1)" if settings['captype'] == 0 else ""
    service_text_dynamic = f"{settings['servicetext']}{cap_suffix}"
    
    
    location = f"{settings['street']}, {settings['zip']} {settings['city']}"
    return {
        'language': settings['language'],
        'bookingtype': 'Internet',
        'bookingurl': f'https://www.etermin.net/{webid}',
        'agbaccepted': str(settings['agb']).lower(),
        'dataprivacyaccepted': str(settings['dp']).lower(),
        **({'nea': 1} if settings['nea'] != 0 else {}),
        'feedbackpermissionaccepted': 0, # they will send you an email to ask you about how was you appointment give us a feedback, I do not think that public offices in Germany care about your feedback
        'newsletter': 'false',
        'senddoimsg': 1,
        'services': f"{settings['serviceid']}",
        'servicestext': service_text_dynamic,
        'servicesinclsgtext': f"{settings['raw_group_name']}<br>{service_text_dynamic}",
        'FirstName': user_data['FirstName'],
        'LastName': user_data['LastName'],
        'Email': user_data['Email'],
        **({'Birthday': user_data['Birthday']} if user_data.get('Birthday', None) else {}),
        'Street': user_data['Street'],
        'ZIP': user_data['ZIP'],
        'City': user_data['City'],
        'Phone': user_data['Phone'],
        'Salutation': user_data['Salutation'],
        **({'Notes': user_data['Notes']} if "Notes" in user_data else {}),
        'bookerinfo': booker_info,
        'calendarname': appointment_data['calendarname'],
        'start': appointment_data['start'],
        'end': appointment_data['end'],
        'calendarid': appointment_data['calendarid'],
        'calname': appointment_data['calendarname'],
        'hash': appointment_data['hash'],
        'location': location,
        'tzaccount': settings['timezone'],
        'checkexist': 1,
        'pricegross': 0,
        'appgroup': str(uuid.uuid4()),
        'capacity': 1, # we want to book an appointment just for one person
        'servicescapacity': f'{{"{settings["serviceid"]}":"1"}}' if settings['enablecapacity'] else "",
        'servicescapacitydetails': f'{settings["servicetext"]}\t{1 if settings["enablecapacity"] else ""}\r\n',
        'canceldeadline': settings['canceldeadline_settings'] if settings['canceldeadline_service'] == -1 else settings['canceldeadline_service'],
        'sync': 1,
        'sendemail': 1,
        'appointmentreminderhours': settings['rh'] if settings['rh'] != 1 else settings['appointmentreminderhours'],
        'appointmentreminderhours2': settings['rh2'] if settings['rh2'] != 1 else settings['appointmentreminderhours2'],
        **(
            {
                'confirmappointment': 1,
                'confirmtime': settings['customerconfirmtime'] if settings['cc'] == -1 else settings['cct']
            } if get_customer_confirm(settings['cc'], settings['customerconfirm']) else {}
            ),
        **({'servicesabb': settings['abb']} if settings['abb'] else {}),
        'sendinvoice': 1,
        'nrappbooked': 1,
        'capused': str(appointment_data["ecap"]).lower(),
        'capmaxused': appointment_data['capmax'],
        **({'blacklist': 1} if settings['bl'] else {}),
        'customerconfirm': str(get_customer_confirm(settings['cc'], settings['customerconfirm'])).lower(),
        'calselid': -1,
        'lnm': 1,
        'emailm': 1,
        'storeip': str(settings['storeip']).lower(),
        'apw': str(settings['apw']).lower(),
        **({'addapphours': settings['addapphours']} if settings['addapphours'] > 0 else {})
    }

