from pydantic import BaseModel
from typing import Optional, Dict, Any

class ScheduleRequest(BaseModel):
    """Modelo para requisições de agendamento."""
    code: str
    trigger_type: str  # 'date', 'interval', ou 'cron'
    trigger_args: Dict[str, Any]
    contexto: Optional[str] = None
    job_id: Optional[str] = None