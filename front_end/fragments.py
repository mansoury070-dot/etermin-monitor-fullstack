import streamlit as st
import time
import utils
import server_requests as sr
from models import TaskData
import datetime


@st.fragment(run_every=1)
def generic_flash_message(msg_id):
    """
    Generic function takes the message key which is usually saved in the session_state and checks if it should disapear
    """
    if msg_id in st.session_state.flash_messages:
        msg_data = st.session_state.flash_messages[msg_id]
        time_passed = time.time() - msg_data["message_time"]
        
        if time_passed >= 3:
            del st.session_state.flash_messages[msg_id]
            st.rerun()
        else:
            st.error(msg_data["message"]) if msg_id == 2 else st.info(msg_data["message"])


@st.fragment(run_every=1)
def next_check_time_fragment(task: TaskData, session_id: str):
    if task.fail_message:
        st.error(f"🚫 {task.fail_message['message']}")
        return

    msg = st.session_state.get("api_error")
    if msg:
        return
    
    if task.next_check is None:
        return

    if utils.should_wait_cooldown(task.next_check):
        return

    result = sr.get_next_check_time(task.service_id, session_id)
    if st.session_state.get("api_error"):
        st.rerun()
        return
    
    if result is None:
        return
    
    had_error = bool(st.session_state.get("api_error"))
    st.session_state["api_error"] = None 

    if "next_check" in result:
        task.next_check = result["next_check"]
        if had_error:
            st.rerun() 
        return
    elif "message" in result:
        task.fail_message = result
        task.next_check = None
        st.rerun()
        return
    
    if "dates" in result:
        task.dates = result["dates"]
    else:
        task.book_data = result

    task.next_check = None
    clicked_dict = st.session_state.get("clicked", {})
    clicked_dict[task.service_id] = True
    st.session_state.clicked = {key: (key == task.service_id) for key in clicked_dict}

    st.rerun()