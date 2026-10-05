import streamlit as st
import time
import datetime
import re 
import server_requests as sr
import uuid
from models import SelectionState, TaskData
import extra_streamlit_components as stx

############################################ Session State Intialization ######################################################
def initialize_state(cookie: stx.CookieManager):
    # init is initialized by stx.CookieManager() in the session state. 
    # it remains None for a few milliseconds before the actual data loads.
    if "init" not in st.session_state or st.session_state["init"] is None:
        st.stop()
    if "current_page" in st.session_state:
        return
    
    is_new_session = False
    session_id = st.session_state.init.get("session_id", None)
    if not session_id:
        is_new_session = True
        session_id = str(uuid.uuid4())
        print("session_id generated!")
    else:
        print("session_id retrieved from cookies!")

    init_data = sr.init(session_id)
    if not init_data:
        return
    st.session_state["current_page"] = init_data["current_page"]
    st.session_state["office_collection"] = init_data["office_collection"]
    st.session_state["selection"] = SelectionState(**init_data.get("selection", {}))
    st.session_state["session_id"] = init_data["session_id"]
    st.session_state["chat_id"] = init_data["chat_id"]
    st.session_state["action"] = init_data["action"]
    st.session_state["tasks"] = {int(service_id): TaskData(**task) for service_id, task in init_data.get("tasks", {}).items()}
    st.session_state["current_services"] = init_data["current_services"]
    st.session_state["desired_time"] = init_data.get("desired_time")
    st.session_state["random_time"] = init_data.get("random_time")

    # These are UI-specific states; they don't come from the server
    default_states = {
        "flash_messages": {},
        "found_slots": {},
        "clicked": {}
    }
    for key, default_value in default_states.items():
        st.session_state[key] = default_value
    # set_cookie does not block the flow of the code causes streamlit to rerun again when the cookie is set in the browser.
    # Therefore, we prevent the code from sending 2 get requests to the server with the same session_id 
    # if the session is newly created, by moving the set command to the end of the function
    if is_new_session:
        expiration_date = datetime.datetime.now() + datetime.timedelta(days=3)
        cookie.set(cookie="session_id", val=session_id, expires_at=expiration_date)
        print("cookie set successfully")
###############################################################################################################################

#################################################### Check Next Request #######################################################

def should_wait_cooldown(next_check_time: float) -> bool:
    """ 
    This function checks if the bot should wait before making the next request
    to avoid hitting the server too frequently
    """
    
    now = time.time()
    remaining = int(next_check_time - now)
    if remaining > 0:
        st.caption(f"Bot läuft... Nächster Check in {remaining} Sekunden.")
        return True
    return False

###############################################################################################################################

#################################################### Form Utils ###############################################################

def validate_user_input(form_fields, user_data):
    """ This function validates the user input data."""
    
    validated_data = {}
    for index, (key, value) in enumerate(user_data.items()):
        if form_fields[index].get("Regex"):
            if value is None: #when the user leaves the birthady out, the returned value is None and the matching throws an error
                value = ""
            is_match = re.fullmatch(form_fields[index]["Regex"], value, re.IGNORECASE)
            validated_data[key] = True if is_match else False
            continue
        if form_fields[index].get("mandatory"): # there are mandatory fields withaout regex, I want the user to fill it in.
            if isinstance(value, str):
                value = value.strip()
            if not value:
                validated_data[key] = False

    if not all(validated_data.values()):
        string = "\n - ".join([f"{key} ungültig" for key, value in validated_data.items() if not value])
        st.error("Bitte prüfen Sie Ihre Eingaben\n"+ string)
        return False
    else:
        st.success("Daten erfolgreich gespeichert!")
        return True

###############################################################################################################################

def create_task_data():
    selection = st.session_state.selection
    office_array = st.session_state.get("office_collection", {}).get(selection.office)
    webid = office_array[0] if office_array else None
    office_id = office_array[1] if office_array else -1
    services_dict = st.session_state.get("current_services", {}).get(selection.group, {}).get(selection.service, {})
    service_id = services_dict.get("id")

    return TaskData(
        office= selection.office,
        webid= webid,
        office_id= office_id,
        group= selection.group,
        service= selection.service,
        service_id= service_id,
        action= st.session_state.get("action"),
        desired_time=st.session_state.get("desired_time"),
        random_time=st.session_state.get("random_time"),
        chat_id= st.session_state.get("chat_id", None),
        user_data=st.session_state.get("user_data", None)
    )
############################################# Variables And Reset #############################################################

def reset_session_keys(keys_to_reset=None):
    if keys_to_reset is not None:
        for key in keys_to_reset:
            if key in st.session_state:
                if isinstance(st.session_state[key], dict):
                    st.session_state[key] = {}
                elif isinstance(st.session_state[key], list):
                    st.session_state[key] = []
                elif isinstance(st.session_state[key], bool):
                    st.session_state[key] = False
                else:
                    st.session_state[key] = None
    
###############################################################################################################################

################################################## UI Helpers #################################################################
def set_flash_message(msg_id, msg_text):
    """Sets a flash messages in the session_state, that will disappear after a period of time"""

    if msg_id not in st.session_state.flash_messages:
        st.session_state.flash_messages[msg_id] = {
            "message": msg_text,
            "message_time": time.time()
        }


def style_annotation(html_snippet):
    """Mimics the st.info() styling in streamlit and removes unwanted HTML snippets"""

    # remove the following phrase, because the website uses it as a description to the appointment
    unimportant_html = r'<b><u>Hier klicken</u> und damit die Dienstleistung auswählen, dann \\*"weiter zur Terminwahl\\*"\.*</b><br><br>\n*'
    html_snippet = re.sub(unimportant_html, "", html_snippet, flags=re.IGNORECASE)
    
    # the responses from the server are not consistent, sometimes the href attribute comes with a "" or '' or even without quotation marks
    # add quotation marks "" to the href attribute in all cases to display it properly in the st.markdown() in app.py
    refined_html = re.sub(r'href=["\']?([^\s>"\']+)["\']?', r'href="\1"', html_snippet)

    styled_snippet = f"""
    <div style="
        background-color: #1c83ff1a; 
        color: #0054a3; 
        padding: 16px; 
        border-radius: 8px; 
        border: 1px solid #cce5ff;
        font-family: sans-serif;
        font-size: 16px;
        margin-bottom: 15px;
">
    {refined_html}
</div>
"""
    return styled_snippet


def should_disable_button(*conditions):
    return not all(conditions)

###############################################################################################################################
