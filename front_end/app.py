import streamlit as st
import extra_streamlit_components as stx
import components as comp
import utils
import server_requests as sr
cookie = stx.CookieManager()

st.set_page_config(page_title="Duisburg Termin Bot", page_icon="📅", layout="wide")

utils.initialize_state(cookie)

if "current_page" not in st.session_state or "office_collection" not in st.session_state:
    if st.session_state.get("api_error"):
        st.error(st.session_state.api_error)
    else:
        st.warning("Es fehlen Daten zum Laden der Seite.")
        
    if st.button("🔄 Erneut versuchen", key="retry_top"):
        st.session_state.api_error = None
        st.rerun()
    st.stop()


selection = st.session_state.get("selection", {})
session_id = st.session_state.get("session_id")
office_collection = st.session_state.get("office_collection", {})
current_services = st.session_state.get("current_services", {})

office_name = selection.office if selection else None
group_name = selection.group if selection else None
service_name = selection.service if selection else None
service_id = selection.service_id if selection else None

office_array = office_collection.get(office_name) if office_name else None
webid = office_array[0] if office_array else None

############################################### Home Page ############################################################
if st.session_state.get("current_page") == "home_page":
    comp.render_homepage()
    col_left, col_center, col_right = st.columns([1, 2, 1])

    with col_center:
        st.markdown("##### Suchfilter")
        st.info("Bitte wähle das Amt, die Gruppe, in der sich der gewünschte Service befindet, und den Service, in dem du einen Termin buchen möchtest.") 
    
        comp.render_office(list(office_collection.keys()))
        comp.render_groups_of_services(list(current_services.keys()))
        services = current_services.get(group_name, {}) if group_name else {}
        services_dict = {key: value["id"] for key, value in services.items()}
        comp.render_services(services_dict)

        is_continue_disabled = utils.should_disable_button(office_name, group_name, service_name)
        comp.render_continue_button(is_continue_disabled)
        annontation = services.get(service_name, {}).get("annotation", "") if service_name else ""
        if annontation:
            styled_annotation = utils.style_annotation(annontation)
            st.markdown(styled_annotation, unsafe_allow_html=True)

        if st.session_state.get("api_error"):
            st.error(st.session_state.api_error)
            if st.button("🔄 Erneut versuchen", key="retry_api_error_home"):
                st.session_state.api_error = None
                if office_name and office_name != "--Bitte wählen--":
                    if office_array:
                        o_id = office_array[1]
                        services_data = sr.request_services_and_groups(o_id)
                        st.session_state["current_services"] = services_data or {}
                
                st.rerun()


        st.write(st.session_state)
######################################################################################################################

######################################################### Work Page ##################################################

if st.session_state.get("current_page") == "work_page":
    col1, col2 = st.columns([1, 3], gap="medium")

######################################################### Bot control ################################################
    with col1:
        with st.container(border=True):
            with st.container():
                st.button("⏪ zurück", use_container_width=True,
                          on_click= lambda: st.session_state.update({"current_page": "home_page"}))
            comp.render_bot_control(session_id)
        with st.container(border=True, horizontal=True, horizontal_alignment="distribute"):
            comp.render_radio()

        action = st.session_state.get("action")
        if action == 'Reservieren':
            with st.container(border=True):
                price = current_services.get(group_name, {}).get(service_name, {}).get("price", 0) if (group_name and service_name) else 0
                if price and price > 0:
                    st.warning("Der ausgewählte Service ist kostenpflichtig, und muss online bezahlt werden. Reserviere bitte den Termin über die Website" \
                    "oder wähle Telegram Benachrichtigung aus, um eine Nachricht über verfügbaren Termine zu bekommen!")
                comp.render_reservation_options(webid, service_id)
        if action == "Telegram Benachrichtigung":
            with st.container(border=True):
                comp.render_telegram_options(session_id)
        clicked_dict = st.session_state.get("clicked", {})
        if "one_time_appointment_clicked" in clicked_dict:
            comp.render_one_time_button()
    st.write(st.session_state)
#####################################################################################################################

######################################################## Column 2 : Status & Results ################################
    with col2:
        st.header("Status & Ergebnisse", text_alignment="center")
        tasks_dict = st.session_state.get("tasks", {})
        comp.status_card(tasks_dict, session_id)
        if st.session_state.get("api_error"):
            st.error(st.session_state.api_error)
    
        if clicked_dict.get("one_time_appointment_clicked", False):
            dates = st.session_state.get("dates", [])
            one_time_selection = st.session_state.get("one_time_selection")
            comp.render_one_time_appointment(one_time_selection, dates)
            if dates and one_time_selection:
                ot_service_id = one_time_selection.service_id if one_time_selection else None
                if ot_service_id:
                    comp.render_slots(ot_service_id)

        for s_id, value in clicked_dict.items():
            if s_id != "one_time_appointment_clicked" and value:
                task = tasks_dict.get(s_id)
                if task:
                    if task.action == "Telegram Benachrichtigung":
                        comp.render_telegram_results(task, task.dates)
                        comp.render_slots(s_id)
                    if task.action == "Reservieren":
                        comp.render_book_details(task.book_data)
# ######################################################################################################################

        


