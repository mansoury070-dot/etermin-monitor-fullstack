from bs4 import BeautifulSoup
import urllib.parse
import datetime
from typing import Optional

def form_parser(html_text):
    """Extract the form fields from the form fetched as HTML"""

    soup = BeautifulSoup(html_text, "html.parser")
    divs = soup.find_all("div")
    extracted_fields = []

    for div in divs:
        field_info = {}
        retrieved_tag = div.find(["input", "select", "textarea"]) # only these tags are relevant
        if not retrieved_tag:
            continue
        # mandatoriness can either be as a class or as a tag
        mandatory_label = div.find("span", class_="mandatory")
        mandatory_tag = retrieved_tag.get("data-required") in ["true", "True"]

        # the form comes as follows: <div> <label for="..."></label> <input or select or.. ...> </div>
        label_tag = div.find("label")
        if label_tag:
            label_text = label_tag.get_text().strip()
            # remove the mandatory sign * to ensure clean extraction of the field names, 
            #and add it dynamically in the form in components.py using field['mandatory']
            label = label_text[:-1].strip() if label_text.endswith('*') else label_text
            # the english name of the field, will be used as a key in user_data dictionary
            field_info["for"] = label_tag.get("for", "") 
        else:
            # it is not the case but to ensure more robustness
            label = retrieved_tag.get("placeholder") or retrieved_tag.get("name")
            field_info["for"] = ""

        field_info["label"] = label
        field_info['mandatory'] = bool(mandatory_label or mandatory_tag)
        field_info["type"] = retrieved_tag.name

        # some regex fetched have a function called at the end after the $ sign.
        regex = retrieved_tag.get("data-regex", "")
        for i in range(-1, -len(regex) -1, -1):
            if regex[i] == "$":
                if i != -1:
                    regex = regex[:i+1]
                break
        field_info["Regex"] = regex

        if retrieved_tag.name == "select":
            options = retrieved_tag.find_all("option")
            field_info["options"] = [option.get('value') for option in options]
        extracted_fields.append(field_info)

    return extracted_fields

def create_bookerinfo(user_data: dict, show_reminder: bool) -> str:
    """
    Constructs a formatted string of the booker's information using German labels.

    This exact string is strictly required to be included in the body of the HTTP 
    request when you want to book an appointment. It extracts the available values 
    from the dictionary and formats them into a single string separated by tabs 
    and newlines

    Returns:
        str: A formatted string containing the mapped booker information, 
            ready to be used in the booking payload.
    """
    german_to_english_map = {
        'Anrede': 'Salutation',
        'Vorname': 'FirstName',
        'Name': 'LastName',
        'Strasse': 'Street',
        'PLZ': 'ZIP',
        'Ort': 'City',
        'Telefon': 'Phone',
        'E-Mail': 'Email',
        'Geburtsdatum': 'Birthday',
        'Bemerkungen': 'Notes'
    }

    entries = ['Anrede', 'Vorname', 'Name', 'Strasse', 'PLZ', 'Ort', 'Telefon', 'E-Mail', 'Geburtsdatum', 'Bemerkungen']
    
    final_entries = []

    for german_label in entries:
        english_key = german_to_english_map.get(german_label)
        if english_key and english_key in user_data:
            final_entries.append(f'{german_label}\t{user_data[english_key]}\r\n')
    
    bookerinfo = "".join(final_entries)
    bookerinfo += "\t\r\n"
    # if the office has a reminder in their settings
    if show_reminder:
        bookerinfo += "Terminerinnerung\t12 Stunden vor Termin\r\n"
    return bookerinfo

def construct_encoded_body(body: dict, is_second_request: Optional[bool] = False, addapphours: Optional[int] = 0) -> str:
    """
    Constructs the URL-encoded body for the booking request manually.
    
    We perform this manual encoding instead of passing the dictionary directly to `curl_cffi` 
    because we need strict control over the encoding process to mimic the target's JavaScript logic. 
    `curl_cffi` would encode everything uniformly, but we specifically need to leave 
    certain parameters unencoded and conditionally remove or add parameters for the second request.
    """
    separate_parts = []
    for key, value in body.items():
        # ignore the parameter "checkexist" if it is the second request!
        if is_second_request and addapphours > 0 and key == 'checkexist':
            continue

        # the following parameters are not URL-encoded in the body (simulating what the JavaScript code does)
        elif key in ["start", "end", "tzaccount", 'servicescapacity']:
            separate_parts.append(f"{key}={value}")
        
        else:
            separate_parts.append(urllib.parse.urlencode({key: value}, quote_via=urllib.parse.quote, safe='()'))

    # in the second request we must add the parameter "addapphours" without URL-encoding and remove "checkexist"
    if is_second_request and addapphours > 0:
        separate_parts.append(f'addapphours={addapphours}')
    encoded_body = "&".join(separate_parts)
    return encoded_body

def desired_time_request(desired_time: str, time_slots: dict, random_time: bool) -> dict:
    """Search for the desired appointment time entered by the user. If it fails to find one, it takes the first available
    appointment, if the user wants to."""

    user_start, user_end = desired_time.split(" - ") # desired_time like 08:00 - 10:00
    user_start_obj = datetime.datetime.strptime(user_start, "%H:%M").time()
    user_end_obj = datetime.datetime.strptime(user_end, "%H:%M").time()
    first_available_time = None

    for time, appointment_details in time_slots.items():
        if not first_available_time: # take the first available time it encounters
            first_available_time = appointment_details
        time_obj = datetime.datetime.strptime(time, "%H:%M").time()
        if user_start_obj <= time_obj <= user_end_obj:
            print("I have found your desired time")
            return appointment_details
    if random_time:
        return first_available_time
    else:
        print("No available time slots found according to your desire")
        return {}
    
def construct_appointment_details(appointment_data: dict, user_data: dict, settings: dict, session_data: dict,
                                  AdditionalInformation: str): 
    """Constructs the conclusion shown to the user after successfully booking an appointment"""

    start_date_obj = datetime.datetime.strptime(appointment_data['start'], "%Y-%m-%d %H:%M") # example: 2026-06-03 08:00 
    end_date_obj = datetime.datetime.strptime(appointment_data['end'], "%Y-%m-%d %H:%M") # example: 2026-06-03 08:20 

    return {
        'Amt 🏫': session_data["office"],
        'Gruppe 📋': session_data["group"],
        'Service 🛠️': session_data["service"],
        'Datum 📅': start_date_obj.strftime("%Y-%m-%d"), # --> 2026-06-03
        'Terminbeginn ​🏃‍♂️': start_date_obj.strftime("%H:%M"), # --> 08:00
        'Terminende 💃🏼': end_date_obj.strftime("%H:%M"), # --> 08:20
        'Terminort 🏢': f"{settings['street']}, {settings['zip']} {settings['city']}", #the place where you must attend to the appointment
        'Buchungsreferenz 🔢': AdditionalInformation,
        'Name ​🪪': f"{user_data['Salutation']} {user_data['FirstName']} {user_data['LastName']}", # Herr John Doe
        'Adresse 🏡': f"{user_data['Street']}, {user_data['ZIP']} {user_data['City']}", # some street 45433, New York
        'Telefonnummer ☎️': user_data['Phone'],
        'Email 📧': user_data['Email']
    }
