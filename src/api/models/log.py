from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class LogEntry(BaseModel):
    """Modelo para entradas de log."""
    status: str
    log_texto: str
    data_criacao: Optional[datetime] = None