from fastapi import FastAPI, Request, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import uvicorn
from core.exceptions import register_exception_handlers
import core.config as cfg
import database.postgres_queries as pg
import database.redis_queries as rq
import services.services_logic as ser
from typing import Optional
from schemas.pydantic_schemas import TaskData

app = FastAPI()

register_exception_handlers(app)

@app.post("/sessions/{session_id}")
async def root_init(session_id: str, session: AsyncSession = Depends(cfg.get_db)):
    """
    Initialize a new user session.
    
    Registers or retrieves the session context for the given session_id 
    using the provided database connection.
    """
    return await ser.initialize_session(cfg.r, session, session_id)

@app.get("/offices/{office_id}/services")
async def retrieve_services(office_id: int):
    """
    Retrieve available services for a specific municipal office.
    
    Returns a dictionary of services provided by the office identified by office_id, 
    grouped by their respective categories. Fetches from the database or cache.
    """
    return await ser.retrieve_services_logic(cfg.r, office_id, cfg.AsyncSessionLocal)

@app.post("/telegram-webhook")
async def telegram_webhook(request: Request):
    """
    Handle incoming Telegram webhook updates.
    
    Listens for the '/start {user_uuid}' command sent by users on Telegram, 
    extracts the chat_id, and links it to the corresponding user session in the PostgreSQL database.
    """
    return await ser.telegram_webhook_logic(request, cfg.AsyncSessionLocal)

@app.get("/verify-telegram/{session_id}")
async def verify_telegram(session_id: str, session: AsyncSession = Depends(cfg.get_db)):
    """
    Retrieve the linked Telegram chat ID for the user session.
    
    Queries the database using the provided session_id and returns the 
    associated Telegram chat ID to the client. This allows the frontend 
    to confirm the connection and utilize the chat ID for further logic.
    """
    return await pg.check_telegram_id(session_id, session)

@app.get("/form/{webid}/{service_id}")
async def retrieve_form(webid: str, service_id: int):
    """
    Retrieve the appointment booking form details.
    
    Fetches the necessary form structure and parameters required to book 
    an appointment for a specific webid and service_id.
    """
    return await ser.retrieve_form_logic(cfg.r, cfg.AsyncSessionLocal, webid, service_id)

@app.post("/task/{session_id}/{service_id}")
async def create_task(data: TaskData, session_id: str, service_id: int):
    """
    Create a new background monitoring task.
    
    Registers a new task for the given session and service to continuously 
    monitor for available appointments based on the provided payload data.
    """
    return await ser.create_task_logic(cfg.r, cfg.AsyncSessionLocal,session_id, service_id, data)

@app.delete("/delete-task/{session_id}/{service_id}")
async def delete_task_endpoint(session_id: str, service_id: int):
    """
    Delete an existing monitoring task.
    
    Removes the user's appointment monitoring task from the queue 
    and stops further checks for this specific service.
    """
    await ser.delete_task_logic(cfg.r, cfg.AsyncSessionLocal, session_id, service_id)

#one time appointment request
@app.get("/appointment/{service_id}")
async def retrieve_appointment_one_time(service_id: int, date: Optional[str] = Query(None)):
    """
    Perform a one-time check for available appointments or dates.
    
    The behavior of this endpoint changes based on the 'date' query parameter:
    - If 'date' is NOT provided: Returns a list of all dates that currently have available appointments.
    - If 'date' IS provided: Returns the specific available appointment time slots for that exact date.
    """
    return await ser.fetch_appointment_one_time_logic(cfg.r, cfg.AsyncSessionLocal, service_id, date)

@app.get("/next-check/{service_id}/{session_id}")
async def get_next_check_time(service_id: int, session_id: str):
    """
    Get the next scheduled check time for a task.
    
    Retrieves the timestamp from Redis indicating when the background worker 
    will next poll the external API for available appointments.
    """
    return await rq.get_next_check(cfg.r, session_id, service_id)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)