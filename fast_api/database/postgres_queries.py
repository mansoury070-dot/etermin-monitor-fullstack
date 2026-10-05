from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from models.db_models import Service, UserSession

async def get_services_from_db(target_id: int, session: AsyncSession):
    stmt = select(Service.servicegroup, Service.serviceid, Service.servicetext, Service.serviceannotation, Service.price, 
                  Service.language, Service.vfields).where(Service.z == target_id)
    result = await session.execute(stmt)
    return result.all()

async def get_or_create_session(session_id: str, session: AsyncSession):
    stmt = select(UserSession).where(UserSession.session_id == session_id)
    result = await session.execute(stmt)
    db_session = result.scalar_one_or_none()

    if not db_session:
        db_session = UserSession(session_id= session_id)
        session.add(db_session)
        await session.commit()
        await session.refresh(db_session)

    session_dict = {c.name: getattr(db_session, c.name) for c in db_session.__table__.columns}
    return session_dict

async def save_telegram_chat_id(session_id: str, chat_id: int, session: AsyncSession):
    stmt = update(UserSession).where(UserSession.session_id == session_id).values(telegram_chat_id = chat_id)
    await session.execute(stmt)
    await session.commit()
    return True

async def fetch_all_settings(service_id: int, session: AsyncSession):
    stmt = select(Service.__table__).where(Service.serviceid == service_id)
    result = await session.execute(stmt)
    settings = result.mappings().one_or_none()
    return dict(settings) if settings else None

async def check_telegram_id(session_id: str, session: AsyncSession):
    stmt = select(UserSession.telegram_chat_id).where(UserSession.session_id == session_id)
    result = await session.execute(stmt)
    chat_id = result.scalar_one_or_none()
    return {"chat_id": chat_id, 
            "message": "Telegram-Verifizierung erfolgreich! Du erhältst eine Benachrichtigung, \
            sobald ein Termin gefunden wird." if chat_id else "Telegram-Verifizierung fehlgeschlagen.\
            Bitte stelle sicher, dass du den Bot gestartet hast und versuche es erneut."}

async def fetch_form_params_from_db(service_id: int, session: AsyncSession):
    stmt = select(Service.serviceid, Service.language, Service.vfields).where(Service.serviceid == service_id)
    result = await session.execute(stmt)
    form_params = result.mappings().one_or_none()
    return dict(form_params) if form_params else None


async def update_searching_status_in_db(session: AsyncSession, session_id: str, is_seacrching: bool):
    stmt = update(UserSession).where(UserSession.session_id == session_id).values(is_searching=is_seacrching)
    await session.execute(stmt)
    await session.commit()
