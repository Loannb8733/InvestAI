from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ScheduledTaskStatus(BaseModel):
    """Rythme, dernière exécution et dernière issue d'une tâche planifiée."""

    name: str
    task: str
    schedule: str
    last_run_at: datetime | None
    last_success_at: datetime | None
    last_error_at: datetime | None
    last_error: str | None
    last_duration_s: float | None
    last_result: str | None
    running: bool
    next_run_at: datetime | None


class SystemStatusResponse(BaseModel):
    """Configuration e-mail, exécutant des tâches planifiées (API ou worker Celery) et état de chacune."""

    email_enabled: bool
    smtp_host: str
    smtp_port: int
    smtp_from: str
    scheduler: Literal["api", "celery"]
    tasks: list[ScheduledTaskStatus]
