from pydantic import Field
from pydantic import BaseModel
from typing import Optional
class ReminderExtraction(BaseModel):
    message: Optional[str] = Field(..., description="El mensaje que se enviará como recordatorio")
    schedule_time: Optional[str] = Field(..., description="La fecha y hora en la que se programará el recordatorio en el formato 'YYYY-MM-DD HH:MM'")