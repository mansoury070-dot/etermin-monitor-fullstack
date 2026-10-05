from pydantic import BaseModel, model_validator
from typing import Optional, Dict, Any

class TaskData(BaseModel):
    office: str
    webid: str
    office_id: int
    group: str
    service: str
    service_id: int
    action: str
    desired_time: Optional[str] = None
    random_time: Optional[bool] = False
    chat_id: Optional[int] = None
    user_data: Optional[Dict[str, Any]] = None

    @model_validator(mode='after')
    def check_action_requirements(self):
        if self.action == "Telegram Benachrichtigung" and self.chat_id is None:
            raise ValueError("Aktiviere bitte die Telegram-benachrichtigung und versuche es erneut!")
        if self.action == "Reservieren" and self.user_data is None:
            raise ValueError('user_data is required when action is booking')
        return self
