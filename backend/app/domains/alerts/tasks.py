import logging
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import session_factory
from app.domains.alerts.checker import check_all_user_alerts
from app.domains.alerts.risk_weights import risk_weights
from app.domains.identity.models import User
from app.domains.portfolio.models import Portfolio
from app.tasks.async_runner import run_async
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _check() -> dict[str, Any]:
    async with session_factory() as db:
        return await check_all_user_alerts(db)


@celery_app.task(name="app.domains.alerts.tasks.check_all_alerts")  # type: ignore[untyped-decorator]
def check_all_alerts() -> dict[str, Any]:
    """Évalue les alertes de tous les utilisateurs et notifie les déclenchements."""
    logger.info("Starting alert check for all users...")
    result: dict[str, Any] = run_async(_check())
    logger.info(
        "Alert check completed: %s users checked, %s alerts triggered",
        result["users_checked"],
        result["alerts_triggered"],
    )
    return result


async def _seed_user(db: AsyncSession, user_id: str, today: str) -> int:
    seeded = 0
    portfolio_ids = (await db.execute(select(Portfolio.id).where(Portfolio.user_id == user_id))).scalars().all()
    for portfolio_id in portfolio_ids:
        try:
            seeded += len(await risk_weights.store_portfolio(db, str(portfolio_id), today))
        except Exception as exc:  # noqa: BLE001
            logger.debug("Skip portfolio %s: %s", portfolio_id, exc)
    return seeded


async def _seed() -> int:
    seeded = 0
    today = date.today().isoformat()
    async with session_factory() as db:
        user_ids = [str(uid) for uid in (await db.execute(select(User.id).where(User.is_active.is_(True)))).scalars()]
        for user_id in user_ids:
            try:
                seeded += await _seed_user(db, user_id, today)
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to seed risk weights for user %s: %s", user_id, exc)
    return seeded


@celery_app.task(name="app.domains.alerts.tasks.seed_risk_weight_snapshots")  # type: ignore[untyped-decorator]
def seed_risk_weight_snapshots() -> dict[str, int]:
    """Enregistre chaque nuit la contribution au risque de chaque actif, base de comparaison des pics de volatilité."""
    logger.info("Seeding daily risk weight snapshots...")
    count: int = run_async(_seed())
    logger.info("Risk weight seeding complete: %d snapshots cached", count)
    return {"seeded": count}
