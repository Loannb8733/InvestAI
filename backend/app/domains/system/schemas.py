from pydantic import BaseModel


class SystemStatusResponse(BaseModel):
    email_enabled: bool
    smtp_host: str
    smtp_port: int
    smtp_from: str
    celery_tasks: list[str]
