import asyncio
import hmac
import logging
from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.core.config import settings
from app.core.db.session import session_factory
from app.domains.exchanges.sync.runner import sync_all
from app.domains.identity.dependencies import CurrentUser
from app.domains.identity.models import User, UserRole
from app.domains.planning.goals.sync import sync_active_goals
from app.domains.system.invariants import check_invariants
from app.domains.system.schemas import SystemStatusResponse
from app.services.regime_alert_service import regime_alert_service
from app.tasks.contrarian_stats import refresh_contrarian_stats
from app.tasks.snapshots import _create_all_snapshots_async

logger = logging.getLogger(__name__)

CELERY_TASKS = (
    "update-crypto-prices (5 min)",
    "update-stock-prices (5 min)",
    "sync-exchanges (1 hour)",
    "check-alerts (5 min)",
    "create-daily-snapshots (00:00 UTC)",
    "send-weekly-reports (Sunday 18:00 UTC)",
    "send-monthly-reports (1st of month 08:00 UTC)",
    "send-daily-digest (07:00 UTC)",
    "run-weekly-cleanup (Monday 03:00 UTC)",
)


async def verify_cron_token(x_cron_token: Annotated[str, Header()] = "") -> None:
    """Refuse la requête sans le secret cron ; sans secret configuré, les routes cron sont désactivées (503)."""
    if not settings.CRON_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cron endpoints are disabled (CRON_SECRET not configured).",
        )
    if not hmac.compare_digest(x_cron_token, settings.CRON_SECRET):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid cron token.")


def _admin(user: CurrentUser) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès administrateur requis")
    return user


cron_router = APIRouter(dependencies=[Depends(verify_cron_token)])
status_router = APIRouter()


def _ran(task: str, result: Any) -> dict[str, Any]:
    return {"task": task, "result": result}


@cron_router.post("/sync-exchanges")
async def cron_sync_exchanges() -> dict[str, Any]:
    """Synchronise toutes les clés d'exchange actives."""
    logger.info("Cron: sync-exchanges started")
    return _ran("sync-exchanges", asdict(await sync_all()))


@cron_router.post("/sync-goals")
async def cron_sync_goals() -> dict[str, Any]:
    """Recale les jauges des objectifs actifs de tous les utilisateurs sur leur portefeuille."""
    logger.info("Cron: sync-goals started")
    async with session_factory() as db:
        users, goals = await sync_active_goals(db)
    return _ran("sync-goals", {"users": users, "goals_synced": goals})


@cron_router.post("/daily-snapshot")
async def cron_daily_snapshot() -> dict[str, Any]:
    """Enregistre le snapshot quotidien du portefeuille de chaque utilisateur."""
    logger.info("Cron: daily-snapshot started")
    return _ran("daily-snapshot", await _create_all_snapshots_async())


@cron_router.post("/contrarian-refresh")
async def cron_contrarian_refresh() -> dict[str, Any]:
    """Recalcule les statistiques contrarian (Fear & Greed) dans Redis, dans un thread : le calcul est synchrone."""
    logger.info("Cron: contrarian-refresh started")
    return _ran("contrarian-refresh", await asyncio.to_thread(refresh_contrarian_stats))


@cron_router.post("/regime-check")
async def cron_regime_check() -> dict[str, Any]:
    """Détecte un changement de régime de marché et prévient les utilisateurs."""
    logger.info("Cron: regime-check started")
    return _ran("regime-check", await regime_alert_service.check_and_alert())


@cron_router.post("/invariants-check")
async def cron_invariants_check() -> dict[str, Any]:
    """Contrôle les invariants financiers de toute la base, pour le watchdog hebdomadaire."""
    return _ran("invariants-check", await check_invariants())


@status_router.get("/status", response_model=SystemStatusResponse)
async def get_system_status(admin: Annotated[User, Depends(_admin)]) -> SystemStatusResponse:
    """Configuration e-mail et tâches planifiées (administrateur seulement)."""
    return SystemStatusResponse(
        email_enabled=settings.email_enabled,
        smtp_host=settings.SMTP_HOST or "(not configured)",
        smtp_port=settings.SMTP_PORT,
        smtp_from=settings.SMTP_FROM_EMAIL,
        celery_tasks=list(CELERY_TASKS),
    )
