import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select

from app.core.db.session import session_factory
from app.domains.portfolio.models import Asset, Portfolio
from app.domains.predictions.models import PredictionLog
from app.domains.system.invariants import ledger_quantity
from app.domains.transactions.models import Transaction
from app.domains.transactions.transfers import COLD_WALLET_DESTINATION
from app.models.notification import Notification

logger = logging.getLogger(__name__)

HEALING_TOLERANCE = 0.00001
REPORT_SAMPLE = 20
LOGGED_SAMPLE = 10


async def purge_read_notifications(days_to_keep: int = 30) -> dict[str, int]:
    """Supprime les notifications lues de plus de ``days_to_keep`` jours."""
    notifications = Notification.__table__.c
    cutoff = datetime.now(UTC) - timedelta(days=days_to_keep)
    async with session_factory() as db:
        result = await db.execute(
            delete(Notification)
            .where(notifications.is_read.is_(True), notifications.created_at < cutoff)
            .returning(notifications.id)
        )
        deleted = len(result.all())
        if deleted:
            await db.commit()
            logger.info("Deleted %d old read notifications (older than %d days)", deleted, days_to_keep)
    return {"deleted_notifications": deleted}


async def purge_old_predictions(days_to_keep: int = 90) -> dict[str, int]:
    """Supprime les prédictions journalisées de plus de ``days_to_keep`` jours."""
    cutoff = datetime.now(UTC) - timedelta(days=days_to_keep)
    async with session_factory() as db:
        result = await db.execute(
            delete(PredictionLog).where(PredictionLog.created_at < cutoff).returning(PredictionLog.id)
        )
        deleted = len(result.all())
        if deleted:
            await db.commit()
            logger.info("Deleted %d old predictions (older than %d days)", deleted, days_to_keep)
    return {"deleted_predictions": deleted}


async def remove_duplicate_transactions() -> dict[str, int]:
    """Ne garde, pour chaque identifiant externe en double, que la transaction créée la première."""
    duplicated = (
        select(Transaction.external_id)
        .where(Transaction.external_id.is_not(None))
        .group_by(Transaction.external_id)
        .having(func.count(Transaction.id) > 1)
    )
    deleted = 0
    async with session_factory() as db:
        for external_id in (await db.execute(duplicated)).scalars().all():
            same = select(Transaction).where(Transaction.external_id == external_id).order_by(Transaction.created_at)
            for transaction in (await db.execute(same)).scalars().all()[1:]:
                await db.delete(transaction)
                deleted += 1
        if deleted:
            await db.commit()
            logger.info("Deleted %d duplicate transactions", deleted)
    return {"deleted_duplicates": deleted}


def _heals(asset: Asset, computed: float) -> bool:
    return (asset.exchange or "") in ("", COLD_WALLET_DESTINATION) and computed >= 0


async def check_holdings() -> dict[str, Any]:
    """Compare la quantité de chaque actif à celle de ses transactions et recale les actifs sans exchange.

    Un actif d'exchange est seulement signalé : la synchronisation le recale sur le solde de la plateforme, qui fait
    foi. Une quantité calculée négative n'est jamais écrite.
    """
    query = (
        select(Asset, Portfolio.name, ledger_quantity())
        .join(Portfolio, Asset.portfolio_id == Portfolio.id)
        .outerjoin(Transaction, Transaction.asset_id == Asset.id)
        .group_by(Asset.id, Portfolio.name)
    )
    inconsistencies: list[dict[str, Any]] = []
    healed: list[dict[str, Any]] = []
    async with session_factory() as db:
        rows = (await db.execute(query)).all()
        for asset, portfolio_name, ledger in rows:
            computed, stored = float(ledger or 0), float(asset.quantity)
            if abs(computed - stored) <= HEALING_TOLERANCE:
                continue
            where = {"asset_id": str(asset.id), "symbol": asset.symbol, "portfolio": portfolio_name}
            inconsistencies.append(
                {**where, "stored_qty": stored, "calculated_qty": computed, "difference": stored - computed}
            )
            if _heals(asset, computed):
                asset.quantity = Decimal(ledger or 0)
                healed.append({**where, "from": stored, "to": computed})
        if healed:
            await db.commit()
    if inconsistencies:
        logger.warning(
            "Found %d portfolio inconsistencies; healed %d cold-wallet assets", len(inconsistencies), len(healed)
        )
        for gap in inconsistencies[:LOGGED_SAMPLE]:
            logger.warning(
                "  %s/%s: stored=%.8f calc=%.8f",
                gap["portfolio"],
                gap["symbol"],
                gap["stored_qty"],
                gap["calculated_qty"],
            )
    return {
        "total_assets_checked": len(rows),
        "inconsistencies_found": len(inconsistencies),
        "healed_count": len(healed),
        "details": inconsistencies[:REPORT_SAMPLE],
        "healed": healed[:REPORT_SAMPLE],
    }


async def weekly_cleanup() -> dict[str, dict[str, Any]]:
    """Purge des notifications lues et des vieilles prédictions, puis dédoublonnage des transactions ; une étape en
    échec rend son erreur sans arrêter les suivantes."""
    results: dict[str, dict[str, Any]] = {}
    for name, step in (
        ("notifications", purge_read_notifications),
        ("predictions", purge_old_predictions),
        ("duplicates", remove_duplicate_transactions),
    ):
        try:
            results[name] = await step()
        except Exception as exc:  # noqa: BLE001
            logger.error("%s cleanup failed: %s", name, exc)
            results[name] = {"error": str(exc)}
    return results
