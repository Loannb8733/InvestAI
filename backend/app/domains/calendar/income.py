import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from dateutil.relativedelta import relativedelta
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.calendar.models import INCOME_TYPES, CalendarEvent
from app.domains.calendar.recurrence import occurrences
from app.domains.calendar.schemas import (
    CalendarSummaryResponse,
    MonthlyPassiveIncome,
    PassiveIncomeResponse,
    PassiveIncomeSources,
)
from app.domains.crowdfunding.calendar import upcoming_coupon_income
from app.domains.market_data.fx.spot import spot_rates

logger = logging.getLogger(__name__)

PASSIVE_MONTHS = 12


class EuroConverter:
    """Convertit en euros au cours du jour, un appel par devise ; sans cours, le montant reste tel quel."""

    def __init__(self) -> None:
        self._rates: dict[str, Decimal | None] = {}

    async def to_eur(self, amount: float, currency: str | None) -> float:
        """Montant en euros ; inchangé quand le cours de la devise est indisponible."""
        code = (currency or "EUR").upper()
        if not amount:
            return 0.0
        if code == "EUR":
            return float(amount)
        if code not in self._rates:
            try:
                self._rates[code] = await spot_rates.get(code, "EUR")
            except Exception as exc:  # noqa: BLE001
                logger.debug("Conversion %s->EUR indisponible pour le calendrier: %s", code, exc)
                self._rates[code] = None
        rate = self._rates[code]
        return float(amount) * float(rate) if rate else float(amount)


async def _count(db: AsyncSession, *conditions: Any) -> int:
    count = await db.execute(select(func.count()).select_from(CalendarEvent).where(*conditions))
    return count.scalar() or 0


async def _income(db: AsyncSession, converter: EuroConverter, *conditions: Any) -> float:
    rows = await db.execute(
        select(CalendarEvent.currency, func.coalesce(func.sum(CalendarEvent.amount), 0))
        .where(CalendarEvent.event_type.in_(INCOME_TYPES), CalendarEvent.is_completed.is_(False), *conditions)
        .group_by(CalendarEvent.currency)
    )
    total = 0.0
    for currency, amount in rows.all():
        total += await converter.to_eur(float(amount or 0), currency)
    return total


async def calendar_summary(db: AsyncSession, user_id: uuid.UUID) -> CalendarSummaryResponse:
    """Nombre d'événements (à venir, faits, du mois) et revenus attendus en euros, à venir et du mois."""
    now = datetime.now(UTC)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_end = (month_start + timedelta(days=32)).replace(day=1)
    mine = CalendarEvent.user_id == user_id
    this_month = (CalendarEvent.event_date >= month_start, CalendarEvent.event_date < month_end)
    converter = EuroConverter()
    return CalendarSummaryResponse(
        total_events=await _count(db, mine),
        upcoming_events=await _count(db, mine, CalendarEvent.is_completed.is_(False), CalendarEvent.event_date >= now),
        completed_events=await _count(db, mine, CalendarEvent.is_completed.is_(True)),
        total_expected_income=await _income(db, converter, mine, CalendarEvent.event_date >= now),
        events_this_month=await _count(db, mine, *this_month),
        projected_income_this_month=round(await _income(db, converter, mine, *this_month), 2),
    )


def _month_keys(now: datetime) -> list[str]:
    keys = []
    for offset in range(PASSIVE_MONTHS):
        moment = now + relativedelta(months=offset)
        keys.append(f"{moment.year:04d}-{moment.month:02d}")
    return keys


async def _event_income(
    db: AsyncSession, user_id: uuid.UUID, buckets: dict[str, float], now: datetime, cutoff: datetime
) -> float:
    rows = await db.execute(
        select(CalendarEvent).where(
            CalendarEvent.user_id == user_id,
            CalendarEvent.event_type.in_(INCOME_TYPES),
            CalendarEvent.is_completed.is_(False),
            CalendarEvent.source_project_id.is_(None),
            CalendarEvent.amount.is_not(None),
            CalendarEvent.event_date <= cutoff,
        )
    )
    converter = EuroConverter()
    total = 0.0
    for event in rows.scalars().all():
        amount = await converter.to_eur(float(event.amount or 0), event.currency)
        if amount <= 0:
            continue
        rule = event.recurrence_rule if event.is_recurring else None
        for moment in occurrences(event.event_date, rule, now, cutoff):
            key = f"{moment.year:04d}-{moment.month:02d}"
            if key in buckets:
                buckets[key] += amount
                total += amount
    return total


async def passive_income(db: AsyncSession, user_id: uuid.UUID) -> PassiveIncomeResponse:
    """Revenus passifs des douze prochains mois : événements de revenus, récurrences dépliées, et coupons crowdfunding.

    Les événements issus du crowdfunding sont comptés par la seconde source seulement.
    """
    now = datetime.now(UTC)
    keys = _month_keys(now)
    buckets = dict.fromkeys(keys, 0.0)
    events_total = await _event_income(db, user_id, buckets, now, now + relativedelta(months=PASSIVE_MONTHS))
    crowdfunding_total = 0.0
    for entry in await upcoming_coupon_income(db, user_id, months_ahead=PASSIVE_MONTHS):
        offset = int(entry["month_offset"])
        if 0 <= offset < len(keys):
            buckets[keys[offset]] += float(entry["amount"])
            crowdfunding_total += float(entry["amount"])
    return PassiveIncomeResponse(
        total_12m=round(sum(buckets.values()), 2),
        monthly=[MonthlyPassiveIncome(month=key, amount=round(buckets[key], 2)) for key in keys],
        sources=PassiveIncomeSources(events=round(events_total, 2), crowdfunding=round(crowdfunding_total, 2)),
    )
