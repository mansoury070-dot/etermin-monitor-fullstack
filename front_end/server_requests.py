import os
import streamlit as st
import requests

BASE_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")

def error_handling_decorator(default_return=None):
    def decorator(base_func):
        def wrapper(*args, **kwargs):
            st.session_state["api_error"] = None
            try:
                result = base_func(*args, **kwargs)
                return result
            
            except requests.exceptions.HTTPError as http_err:
                error_data = http_err.response.json()
                error_message = error_data.get("detail")
                st.session_state.api_error = error_message            
                print(f"HTTP Error: {error_message}")
                return default_return

            except requests.exceptions.ConnectionError as conn_err:
                st.session_state.api_error = "Keine Verbindung zum Server. Bitte versuchen Sie es später erneut."
                print(f"Server is offline - No retry: {conn_err}")
                return default_return

            except requests.exceptions.RequestException as req_err:
                st.session_state.api_error = "Ein Netzwerkfehler ist aufgetreten."
                print(f"Network error: {req_err}")
                return default_return
            
            except Exception as e:
                print(f"Unexpected error occurred: {e}")
                st.session_state.api_error = "Ein unerwarteter Systemfehler ist aufgetreten."
                return default_return
        return wrapper
    return decorator

@error_handling_decorator(default_return={})
def init(session_id):
    api_url = f"{BASE_URL}/sessions/{session_id}"   
    response = requests.post(api_url, timeout=5)
    response.raise_for_status()
    init_data = response.json()
    return init_data

@error_handling_decorator(default_return={})
@st.cache_data(ttl=1800)
def request_services_and_groups(office_id):
    api_url = f"{BASE_URL}/offices/{office_id}/services"
    response = requests.get(api_url, timeout=5)
    response.raise_for_status()
    services = response.json()
    return services

@error_handling_decorator(default_return={})
def check_telegram_chat_id(session_id):
    api_url =f"{BASE_URL}/verify-telegram/{session_id}"
    response = requests.get(api_url, timeout=5)
    return response.json()

@error_handling_decorator(default_return=[])
def request_form(webid, service_id):
    api_url = f"{BASE_URL}/form/{webid}/{service_id}"
    response = requests.get(api_url, timeout=5)
    return response.json()

@error_handling_decorator(default_return=None)
def add_task(session_id, service_id, task_data):
    api_url = f"{BASE_URL}/task/{session_id}/{service_id}"
    response = requests.post(api_url, json=task_data, timeout=5)
    response.raise_for_status()
    return response.json()

@error_handling_decorator(default_return={})
def request_one_time_appointment(service_id, date=None):
    api_url = f"{BASE_URL}/appointment/{service_id}"
    response = requests.get(api_url, params={"date": date}, timeout=5)
    response.raise_for_status()
    return response.json()

@error_handling_decorator(default_return=None)
def get_next_check_time(service_id, session_id):
    api_url = f"{BASE_URL}/next-check/{service_id}/{session_id}"
    response = requests.get(api_url, timeout=5)
    response.raise_for_status()
    return response.json()

@error_handling_decorator(default_return=False)
def delete_task(session_id, service_id):
    api_url = f"{BASE_URL}/delete-task/{session_id}/{service_id}"
    response = requests.delete(api_url, timeout=5)
    response.raise_for_status()
    return True

    