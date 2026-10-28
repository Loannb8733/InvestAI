import hmac
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.core.config import settings
from app.core.db.session import session_factory
from app.core.errors import DomainError, NotFoundError
from app.domains.identity.dependencies import CurrentAdmin
from app.domains.planning.goals.sync import sync_active_goals
from app.domains.system.invariants import check_invariants
from app.domains.system.scheduler import api_scheduler
from app.domains.system.schemas import ScheduledTaskStatus, SystemStatusResponse

logger = logging.getLogger(__name__)


async def verify_cron_token(x_cron_token: Annotated[str, Header()] = "") -> None:
    """Refuse la requête sans le secret cron ; sans secret configuré, les routes cron sont désactivées (503)."""
    if not settings.CRON_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cron endpoints are disabled (CRON_SECRET not configured).",
        )
    if not hmac.compare_digest(x_cron_token, settings.CRON_SECRET):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid cron token.")


class JobRunningError(DomainError):
    status_code = 409


class JobFailedError(DomainError):
    status_code = 502


cron_router = APIRouter(dependencies=[Depends(verify_cron_token)])
status_router = APIRouter()


def _ran(task: str, result: Any) -> dict[str, Any]:
    return {"task": task, "result": result}


@cron_router.post("/sync-goals")
async def cron_sync_goals() -> dict[str, Any]:
    """Recale les jauges des objectifs actifs de tous les utilisateurs sur leur portefeuille."""
    logger.info("Cron: sync-goals started")
    async with session_factory() as db:
        users, goals = await sync_active_goals(db)
    return _ran("sync-goals", {"users": users, "goals_synced": goals})


@cron_router.post("/invariants-check")
async def cron_invariants_check() -> dict[str, Any]:
    """Contrôle les invariants financiers de toute la base, pour le watchdog hebdomadaire."""
    return _ran("invariants-check", await check_invariants())


@cron_router.post("/jobs/{name}", response_model=ScheduledTaskStatus)
async def cron_run_job(name: str) -> ScheduledTaskStatus:
    """Lance maintenant une tâche planifiée (nom de la planification Celery) et rend son état ; 502 si elle échoue."""
    if name not in api_scheduler.entries:
        raise NotFoundError(f"Tâche planifiée inconnue : {name}")
    if api_scheduler.state(name).running:
        raise JobRunningError(f"La tâche {name} est déjà en cours")
    state = await api_scheduler.run(name)
    if state.failed:
        raise JobFailedError(f"{name} : {state.last_error}")
    return _task_status(name)


def _task_status(name: str) -> ScheduledTaskStatus:
    state = api_scheduler.state(name)
    entry = api_scheduler.entries[name]
    return ScheduledTaskStatus(
        name=name,
        task=entry.task,
        schedule=str(entry.schedule),
        last_run_at=state.last_run_at,
        last_success_at=state.last_success_at,
        last_error_at=state.last_error_at,
        last_error=state.last_error,
        last_duration_s=state.last_duration_s,
        last_result=state.last_result,
        running=state.running,
        next_run_at=api_scheduler.next_run_at(name),
    )


@status_router.get("/status", response_model=SystemStatusResponse)
async def get_system_status(admin: CurrentAdmin) -> SystemStatusResponse:
    """Configuration e-mail et état de chaque tâche planifiée (administrateur seulement)."""
    return SystemStatusResponse(
        email_enabled=settings.email_enabled,
        smtp_host=settings.SMTP_HOST or "(not configured)",
        smtp_port=settings.SMTP_PORT,
        smtp_from=settings.SMTP_FROM_EMAIL,
        scheduler="celery" if settings.CELERY_WORKER_AVAILABLE else "api",
        tasks=[_task_status(name) for name in api_scheduler.entries],
    )
