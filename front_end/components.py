import streamlit as st
import server_requests as sr
import datetime
import utils
from constants import MY_BOT_USERNAME
from fragments import generic_flash_message, next_check_time_fragment
import phonenumbers
from pydantic import ValidationError
from models import SelectionState, TaskData
import time
################################################# Home Page #############################################

def render_homepage():
    st.title("Terminjäger in Duisburg 📅", text_alignment="center")
    st.subheader("Ich helfe dir, einen Termin zu finden!", text_alignment="center")
    
def office_change_callback():
    st.session_state.selection.office = st.session_state.ui_selected_office # I got problem with redendering the right value without using the key ui_selected_office/group .. etc
    selected_office = st.session_state.selection.office
    if selected_office != "--Bitte wählen--":
        office_id = st.session_state.office_collection[selected_office][1]
        services_data = sr.request_services_and_groups(office_id)
        if not services_data:
            return
        st.session_state["current_services"] = services_data
    else:
        st.session_state["current_services"] = {}
    st.session_state.selection.group = None
    st.session_state.selection.service = None


def group_change_callback():
    st.session_state.selection.group = st.session_state.ui_selected_group
    st.session_state.selection.service = None

def service_change_callback(services_dict):
    service_name = st.session_state.ui_selected_service
    st.session_state.selection.service = service_name
    st.session_state.selection.service_id = services_dict.get(service_name, None)

def render_office(options):
    prev_selected_office = st.session_state.selection.office
    current_index = options.index(prev_selected_office) if prev_selected_office else None
    st.selectbox("Behörde auswählen", options=options, index=current_index, 
                 key='ui_selected_office', on_change=office_change_callback,
                 placeholder="Bitte wählen")

def render_groups_of_services(options):
    prev_group = st.session_state.selection.group
    current_index = options.index(prev_group) if prev_group in options else None
    st.selectbox("Dienstleistungsgruppe auswählen", options=options, index=current_index, 
                 key='ui_selected_group', on_change=group_change_callback,
                 placeholder="Bitte wählen")

def render_services(services_dict):
    options = list(services_dict.keys())
    prev_service = st.session_state.selection.service
    current_index = options.index(prev_service) if prev_service in options else None
    st.selectbox("Dienstleistung auswählen", options=options, index=current_index, 
                 key='ui_selected_service', on_change=service_change_callback, args=[services_dict], placeholder="Bitte wählen")


def render_continue_button(is_continue_disabled):
    st.button("weiter", disabled=is_continue_disabled, use_container_width=True, 
              on_click= lambda: st.session_state.update({"current_page": "work_page"}))
#########################################################################################################

########################################### Bot Control Buttons #########################################
def start_bot_callback(session_id):
    try:
        task = utils.create_task_data()
    except ValidationError as e:
        errors = e.errors()
        for error in errors:
            error_msg = error.get("msg", "")
            if "user_data" in error_msg :
                utils.set_flash_message(4, "Fülle bitte deine persönlichen Daten aus!")
            elif "chat_id" in error_msg:
                utils.set_flash_message(4, "Aktiviere bitte die Telegram-benachrichtigung und versuche es erneut!")
        return

    if task.service_id in st.session_state.get("tasks", {}):
        msg_text ="Du hast schon diesen Service ausgewählt!"
        utils.set_flash_message(4, msg_text)
        return
    
    if len(st.session_state.get("tasks", {})) >= 2:
        msg_text = "Du kannst maximal für 2 Services gleichzeitig nach Termine suchen"
        utils.set_flash_message(4, msg_text)
        return
    
    if task.action == "Verfügbare Termine angucken":
        one_time_task = SelectionState(
            service=task.service,
            office=task.office,
            group=task.group,
            service_id=task.service_id
        )
        st.session_state["one_time_selection"] = one_time_task
        st.session_state.clicked["one_time_appointment_clicked"] = True
        dates_response = sr.request_one_time_appointment(one_time_task.service_id)
        if not dates_response:
            return
        st.session_state["dates"] = dates_response.get("dates", [])
        return
    
    st.session_state.one_time_appointment_clicked = False
    task_payload = task.model_dump(exclude_none=True)

    response = sr.add_task(session_id, task.service_id, task_payload)
    if st.session_state.get("api_error"):
        utils.set_flash_message(4, st.session_state["api_error"])
        st.session_state["api_error"] = None
        return
    
    if response:
        st.toast("Task wurde erfolgreich hinzugefügt!", icon="✅")
        if "tasks" not in st.session_state:
            st.session_state.tasks = {}
        st.session_state.tasks[task.service_id] = task
        st.session_state.tasks[task.service_id].next_check = response

def render_bot_control(session_id):
    with st.container():      
        st.button("🚀 Bot starten", use_container_width=True, on_click=start_bot_callback, args=[session_id])
        if 4 in st.session_state.flash_messages:
            generic_flash_message(4)

#########################################################################################################

############################################# Bot Settings ##############################################
    
def telegram_activation_callback(session_id):
    if st.session_state.get("chat_id", None):
        msg_text = "Du bist bereits verizifiert. Du brauchst nicht mehr hier zu klicken"
        utils.set_flash_message(1, msg_text)
    else:
        chat_dict = sr.check_telegram_chat_id(session_id)
        if not chat_dict:
            return
        if chat_dict.get("chat_id", None):
            st.session_state.chat_id = chat_dict["chat_id"]
            utils.set_flash_message(1, chat_dict["message"])
        else:
            utils.set_flash_message(2, chat_dict["message"])

def action_callback():
    st.session_state.action = st.session_state.ui_action

def desired_time_change_callback():
    st.session_state.desired_time = st.session_state.ui_desired_time

def random_time_change_callback():
    if st.session_state.ui_random_time == "Ja":
        st.session_state.random_time = True
    else:
        st.session_state.random_time = False

def enter_user_data_callback(webid, service_id):
    form_fields = sr.request_form(webid, service_id)
    if not form_fields:
        return
    render_form(form_fields)

def one_time_result_callback():
    st.session_state.clicked = {key: (key == "one_time_appointment_clicked") for key in st.session_state.get("clicked",{})}
    if "state_date_key" in st.session_state:
        st.session_state.state_date_key = {}

def render_radio():  
    st.markdown("##### Bot-Einstellungen")
    options = ["Telegram Benachrichtigung", "Reservieren", "Verfügbare Termine angucken"]
    prev_selected_method = st.session_state.get("action", "Telegram Benachrichtigung")
    current_index = options.index(prev_selected_method) if prev_selected_method in options else 0
    st.radio("Möchtest du den Termin direkt reservieren oder per Benachrichtigung informiert werden?", 
            options=options, index=current_index, horizontal=True,
            key='ui_action', on_change=action_callback)



def render_reservation_options(webid, service_id):
    time_options = ["08:00 - 10:00", "10:00 - 12:00", "12:00 - 14:00", "14:00 - 16:00"]
    prev_desired_time = st.session_state.get("desired_time", "08:00 - 10:00")
    current_index = time_options.index(prev_desired_time) 
    st.radio("Wähle deine gewünschte Uhrzeit aus", options=time_options, 
             index=current_index, key='ui_desired_time', on_change=desired_time_change_callback)

    decision_options = ["Ja", "Nein"]
    prev_random_time = st.session_state.get("decision", "Nein")
    current_index = 0 if prev_random_time else 1
    st.radio("Ich versuche, den passenden Termin für Sie zu finden. Falls es keinen gibt, möchtest du" \
            "trotzdem irgendeinen verfügbaren Termin reservieren lassen?", options= decision_options, 
            key='ui_random_time', on_change=random_time_change_callback)
    st.button("Daten Eingeben", on_click=enter_user_data_callback, args=[webid, service_id])

def render_telegram_options(session_id):
    telegram_link = f"https://t.me/{MY_BOT_USERNAME}?start={st.session_state.session_id}"
    st.write("Um Benachrichtigungen zu erhalten, klicke bitte auf den folgenden Link und starte eine Unterhaltung mit dem Bot:", )
    st.link_button("Telegram Bot aktivieren", telegram_link)
    st.caption("Nachdem du den Bot aktiviert hast, klicke auf die Schaltfläche unten, um die Verifizierung abzuschließen.")
    st.button("Ich habe den Bot aktiviert", on_click=telegram_activation_callback, args=[session_id])
    if 1 in st.session_state.flash_messages:
        generic_flash_message(1)
    elif 2 in st.session_state.flash_messages:
        generic_flash_message(2)

def render_one_time_button():
    st.button("Ergebnisse anzeigen", on_click=one_time_result_callback)
#########################################################################################################

# ################################################# Form ##################################################

@st.dialog("Reservierungsdaten")
def render_form(form_fields):
    user_data = {}
    with st.form("Gib deine Daten ein"):
        with st.container(horizontal=True, horizontal_alignment="center", vertical_alignment="bottom"):
            for field in form_fields:
                if field["type"] == "select":
                    options = field["options"]
                    prev_title = st.session_state.get("user_data", {}).get(field["for"])
                    selected_value = st.selectbox(f'{field["label"]} {"*" if field["mandatory"] else ""}', options=options, 
                                                index=(options.index(prev_title) if prev_title in options else 0))
                    user_data[field["for"]] = selected_value

                if field["type"] == "input":
                    if field['for'] == "Birthday":
                        value = st.session_state.get("user_data", {}).get(field["for"], None)
                        if value:
                            value = datetime.datetime.strptime(value, "%d.%m.%Y")
                        entered_value = st.date_input(f'{field["label"]} {"*" if field["mandatory"] else ""}',
                                                    min_value=datetime.date(1900, 1, 1), max_value=datetime.date.today(), 
                                                    value=value)
                        if entered_value:
                            entered_value = entered_value.strftime("%d.%m.%Y")
                        user_data[field["for"]] = entered_value
                        continue #stop executing the next logic when the field is birthday

                    entered_value = st.text_input(f'{field["label"]} {"*" if field["mandatory"] else ""}', 
                                                    placeholder=field['label'],
                                                    value=st.session_state.get("user_data", {}).get(field["for"], ""))
                    if entered_value and field["for"] == "Phone":
                        parsed_local_number = phonenumbers.parse(entered_value, "DE")
                        international_number = phonenumbers.format_number(parsed_local_number, phonenumbers.PhoneNumberFormat.E164)
                        entered_value = international_number

                    user_data[field["for"]] = entered_value

                if field["type"] == "textarea":
                    written_string = st.text_area(f'{field["label"]} {"*" if field["mandatory"] else ""}',
                                                value=st.session_state.get("user_data", {}).get(field["for"], ""))
                    user_data[field["for"]] = written_string
            st.info("""
            **Hinweis zum Datenschutz:**
            Ihre Daten werden nur für die Terminsuche verwendet und direkt nach der erfolgreichen Buchung restlos gelöscht. 
            Es werden keine persönlichen Daten dauerhaft in unserer Datenbank gespeichert.
            """)
            submit_data = st.form_submit_button("Daten speichern")
            if submit_data:
                if utils.validate_user_input(form_fields, user_data):
                    st.session_state["user_data"] = user_data
                    st.rerun()
            
# #########################################################################################################

# ################################################# Status and Results ####################################

def fetch_slots_callback(state_key, date, service_id):
    current_state_key = st.session_state.state_date_key[state_key]
    for key in st.session_state.state_date_key:
        st.session_state.state_date_key[key] = False
    st.session_state.state_date_key[state_key] = not current_state_key

    if service_id not in st.session_state.found_slots:
        st.session_state.found_slots[service_id] = {}
 
    if date not in st.session_state.found_slots[service_id]:
        result = sr.request_one_time_appointment(service_id, date)
        st.session_state.found_slots[service_id][date] = result

def stop_bot_callback(session_id, service_id):
    response = sr.delete_task(session_id, service_id)
    if response:
        st.session_state.tasks.pop(service_id, None)
        st.session_state.clicked.pop(service_id, None)
    else:
        msg_txt = "Fehler aufgetreten. Versuche es erneut"
        utils.set_flash_message(3, msg_txt)

def retry_bot_callback(session_id, service_id):
    st.session_state.tasks[service_id].fail_message = {}
    st.session_state["api_error"] = None
    sr.get_next_check_time(service_id, session_id)

def show_results_callback(service_id):
    st.session_state.clicked = {key: (key == service_id) for key in st.session_state.get("clicked",{})}
    if "state_date_key" in st.session_state:
        st.session_state.state_date_key = {}

def close_task_callback(service_id):
    del st.session_state.tasks[service_id]
    del st.session_state.clicked[service_id]

def status_card(tasks: dict, session_id: str):
    if not tasks:
        return
    with st.container(horizontal=True, horizontal_alignment="left"):
        for service_id, task in tasks.items():
            with st.container(border=True, height=300):
                with st.container(horizontal=True, horizontal_alignment="distribute"):
                    st.write("Nach Termine im Hintergrund gesucht für:")
                    if task.dates is not None or task.book_data is not None or task.fail_message.get("is_fatal"):
                        st.button("x", key=f"close_{service_id}", on_click=close_task_callback, args=[task.service_id])
                st.info(f"**Behörde**: {task.office}"
                        +"\n\n" + f"**Service**: {task.service}"
                        +"\n\n" + f"**Methode**: {task.action}")
                next_check_time_fragment(task, st.session_state.session_id)
                with st.container(horizontal=True, horizontal_alignment="distribute"):
                    if task.dates is None and task.book_data is None and not task.fail_message.get("is_fatal") and not st.session_state.get("api_error"):
                        st.button("🛑 Bot stoppen", key=f"stop_{service_id}", disabled=(task.dates is not None or task.book_data is not None or task.fail_message.get("is_fatal", False)), on_click=stop_bot_callback, args=[session_id, service_id])
                    if st.session_state.get("api_error") or (task.fail_message and not task.fail_message.get("is_fatal", False)):
                        st.button("🔄 Erneut versuchen", key=f"retry_{service_id}", on_click=retry_bot_callback, args=[session_id, service_id])
                    st.button("Ergebnisse anzeigen ", key=f"show_{service_id}", on_click=show_results_callback, args=[service_id])
                if 3 in st.session_state.flash_messages:
                    generic_flash_message(3)

def render_one_time_appointment(selection: SelectionState, dates: list):
    if not dates:
        st.info("Leider gibt es derzeit keine verfügbare Termine für:"
                +"\n\n" + f"**Service**: {selection.service}"
                +"\n\n" + f"**Behörde**: {selection.office}"
                +"\n\n" + "**Methode**: Verfügbare Termine angucken")
        return
    render_dates(selection, "Verfügbare Termine angucken", dates)

def render_telegram_results(task: TaskData, dates: list):
        if not dates:
            return
        render_dates(task, task.action, dates)

def render_dates(task: TaskData, method: str, dates: list):
    task_dict = task.model_dump()
    with st.spinner():
        time.sleep(1)
    st.success("🎯 Löttchen Termine! 🕒")
    st.write("📅 **Verfügbare Termine für:**")
    cols = st.columns([1.5, 2.5])
    for key, value in task_dict.items():
        if key == "office":
            with cols[0]:
                st.write("**Amt 🏫**")
            with cols[1]:
                st.write(f"{value}")
        if key == "group":
            with cols[0]:
                st.write("**Gruppe 📋**")
            with cols[1]:
                st.write(f"{value}")
        if key == "service":
            with cols[0]:
                st.write("**Service 🛠️**")
            with cols[1]:
                st.write(f"{value}")
    with cols[0]:
        st.write("**Methode 🛠️**")
    with cols[1]:
        st.write(f"{method}")
    if "state_date_key" not in st.session_state:
        st.session_state.state_date_key = {}
    cols = st.columns([1, 1, 1, 1, 1])
    num_cols = len(cols)
    for index, date in enumerate(dates):
        state_key = f"expanded_{date}"
        if state_key not in st.session_state.state_date_key:
            st.session_state.state_date_key[state_key] = False
        arrow_icon = "🔼" if st.session_state.state_date_key[state_key] else "🔽"
        col = cols[index % num_cols]
        with col:
            st.button(f"{arrow_icon} {date} ✅", type=("primary" if st.session_state.state_date_key[state_key] else "secondary"), 
                      on_click=fetch_slots_callback, args=[state_key, date, task.service_id])
    st.divider()

def render_book_details(details: dict):
            st.success("Whoooopa!! der Termin wurde erfolgreich gebucht. Es wurde dir eine Email geschickt. Bitte bestätige den Termin über den Link in deiner Email.")
            st.subheader("Termin Details")
            for key, value in details.items():
                col1, col2 = st.columns([1, 3])
                with col1:
                    st.write(f"**{key}**")
                with col2:
                    st.write(f"{value}")

def render_slots(service_id: int):
    cols = st.columns([1, 1, 1, 1])
    num_cols = len(cols)
    date_with_expand = next((k for k, v in st.session_state.state_date_key.items() if v), None)
    if date_with_expand:
        date = date_with_expand.split("_")[1]
        slots = st.session_state.found_slots[service_id][date]
        for index, (_, value) in enumerate(slots.items()):
            col = cols[index % num_cols]
            with col:
                st.write(f"von {value['start'].split(' ')[1]} bis {value['end'].split(' ')[1]} ✅")