from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.predictions.models import PlannedOrder, PlannedOrderStatus
from app.domains.predictions.schemas import PlannedOrderCreate

SETTABLE_STATUSES = ("executed", "cancelled")


def _pending_payload(o: PlannedOrder) -> dict[str, Any]:
    return {
        "id": str(o.id),
        "symbol": o.symbol,
        "action": o.action,
        "order_eur": o.order_eur,
        "alpha_score": o.alpha_score,
        "regime": o.regime,
        "prob_ruin_before": o.prob_ruin_before,
        "prob_ruin_after": o.prob_ruin_after,
        "source": o.source,
        "status": o.status.value if o.status else "pending",
        "notes": o.notes,
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }


async def list_pending(db: AsyncSession, user_id: UUID) -> list[dict[str, Any]]:
    """Ordres planifiés en attente de l'utilisateur, du plus récent au plus ancien."""
    result = await db.execute(
        select(PlannedOrder)
        .where(
            PlannedOrder.user_id == user_id,
            PlannedOrder.status == PlannedOrderStatus.PENDING,
        )
        .order_by(PlannedOrder.created_at.desc())
    )
    return [_pending_payload(o) for o in result.scalars().all()]


async def create_pending(db: AsyncSession, user_id: UUID, data: PlannedOrderCreate) -> dict[str, Any]:
    """Enregistre un ordre en attente : ``buy`` devient ACHAT, ``sell`` VENDRE, montant arrondi au centime."""
    order = PlannedOrder(
        user_id=user_id,
        symbol=data.symbol.upper(),
        action="ACHAT" if data.side == "buy" else "VENDRE",
        order_eur=round(data.amount_eur, 2),
        source=data.source,
        status=PlannedOrderStatus.PENDING,
        notes=data.notes,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)

    return {
        "id": str(order.id),
        "symbol": order.symbol,
        "action": order.action,
        "order_eur": float(order.order_eur),
        "source": order.source,
        "status": order.status.value,
        "notes": order.notes,
        "created_at": order.created_at.isoformat() if order.created_at else None,
    }


async def find_owned(db: AsyncSession, order_id: UUID, user_id: UUID) -> PlannedOrder | None:
    result = await db.execute(
        select(PlannedOrder).where(
            PlannedOrder.id == order_id,
            PlannedOrder.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def apply_status(db: AsyncSession, order: PlannedOrder, new_status: Any) -> dict[str, Any]:
    """Seuls ``executed`` et ``cancelled`` modifient l'ordre ; tout autre statut est ignoré sans erreur."""
    if new_status in SETTABLE_STATUSES:
        order.status = PlannedOrderStatus(new_status)
        await db.commit()
    return {"id": str(order.id), "status": order.status.value}


async def add_telegram_order(db: AsyncSession, user_id: str, symbol: str, order_eur: float, chat_id: str) -> None:
    """Ajoute l'achat planifié depuis le bouton d'une alerte Telegram, sans le valider."""
    db.add(
        PlannedOrder(
            user_id=UUID(user_id),
            symbol=symbol,
            action="ACHAT",
            order_eur=Decimal(str(order_eur)),
            source="telegram",
            status=PlannedOrderStatus.PENDING,
            notes=f"Planifié via Telegram (chat {chat_id})",
        )
    )
