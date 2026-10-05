import os
from dotenv import load_dotenv

load_dotenv()

def get_secret_value(key):
    return os.getenv(key)


MY_BOT_TOKEN = get_secret_value("MY_TELEGRAM_BOT_TOKEN")
MY_BOT_USERNAME = "my_appointment_app_bot"
ENCRYPT_KEY = get_secret_value("ENCRYPT_KEY")


OFFICE_COLLECTION = {
    "Ausländerbehörde Süd": ("qtermin-stadt-duisburg-abh-sued", 71400),
    "Ausländerbehörde Hamborn": ("stadt-duisburg-abh-homberg", 53036),
    "Ausländerbehörde Homberg": ("stadt-duisburg-abh-homberg", 53036),
    "Straßenverkehrsamt": ("stadt-duisburg-zul", 51901),
    "Fahrerlaubnisbehörde": ("qterminstadtduisburgstva", 41433),
    "Bürgerservice": ("stadt-duisburg", 39575) 
    }


