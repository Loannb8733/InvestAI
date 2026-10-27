import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
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
from app.domains.crowdfunding.calendar import coupon_income
from app.domains.market_data.fx.spot import spot_rates

PASSIVE_MONTHS = 12

Dated = list[tuple[datetime, float]]


class EuroConverter:
    """Convertit en euros au cours du jour, un appel par devise ; retient les devises restées sans cours."""

    def __init__(self) -> None:
        self._rates: dict[str, Decimal | None] = {}
        self.unconverted: set[str] = set()

    async def to_eur(self, amount: Decimal, currency: str) -> float | None:
        """Montant en euros ; None quand le cours de la devise est indisponible."""
        code = currency.upper()
        if code not in self._rates:
            self._rates[code] = await spot_rates.get(code, "EUR")
        rate = self._rates[code]
        if rate is None:
            self.unconverted.add(code)
            return None
        return float(amount * rate)


@dataclass(frozen=True)
class ExpectedIncome:
    """Revenus attendus d'une période en euros, datés, par source ; les devises sans cours n'y sont pas comptées."""

    events: Dated
    crowdfunding: Dated
    unconverted: list[str]

    @property
    def total(self) -> float:
        """Total en euros, toutes sources."""
        return sum(amount for _, amount in self.events + self.crowdfunding)


async def _event_income(
    db: AsyncSession, user_id: uuid.UUID, start: datetime, end: datetime, converter: EuroConverter
) -> Dated:
    rows = await db.execute(
        select(CalendarEvent).where(
            CalendarEvent.user_id == user_id,
            CalendarEvent.event_type.in_(INCOME_TYPES),
            CalendarEvent.is_completed.is_(False),
            CalendarEvent.source_project_id.is_(None),
            CalendarEvent.amount > 0,
            CalendarEvent.event_date < end,
        )
    )
    found: Dated = []
    for event in rows.scalars().all():
        rule = event.recurrence_rule if event.is_recurring else None
        moments = occurrences(event.event_date, rule, start, end)
        amount = await converter.to_eur(event.amount or Decimal(0), event.currency) if moments else None
        if amount is not None:
            found.extend((moment, amount) for moment in moments)
    return found


async def expected_income(db: AsyncSession, user_id: uuid.UUID, start: datetime, end: datetime) -> ExpectedIncome:
    """Revenus attendus entre ``start`` inclus et ``end`` exclu : événements de revenus non faits, récurrences
    dépliées, et intérêts nets des échéances crowdfunding non soldées, sans le capital remboursé.
    """
    converter = EuroConverter()
    events = await _event_income(db, user_id, start, end, converter)
    return ExpectedIncome(events, await coupon_income(db, user_id, start, end), sorted(converter.unconverted))


def _month_start(moment: datetime) -> datetime:
    return moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _month_key(moment: datetime) -> str:
    return f"{moment.year:04d}-{moment.month:02d}"


async def _count(db: AsyncSession, *conditions: Any) -> int:
    count = await db.execute(select(func.count()).select_from(CalendarEvent).where(*conditions))
    return count.scalar() or 0


async def calendar_summary(db: AsyncSession, user_id: uuid.UUID) -> CalendarSummaryResponse:
    """Nombre d'événements (à venir, faits, du mois), revenus attendus sur douze mois et revenus du mois, en euros."""
    now = datetime.now(UTC)
    month_start = _month_start(now)
    month_end = month_start + relativedelta(months=1)
    mine = CalendarEvent.user_id == user_id
    ahead = await expected_income(db, user_id, now, month_start + relativedelta(months=PASSIVE_MONTHS))
    this_month = await expected_income(db, user_id, month_start, month_end)
    return CalendarSummaryResponse(
        total_events=await _count(db, mine),
        upcoming_events=await _count(db, mine, CalendarEvent.is_completed.is_(False), CalendarEvent.event_date >= now),
        completed_events=await _count(db, mine, CalendarEvent.is_completed.is_(True)),
        total_expected_income=round(ahead.total, 2),
        events_this_month=await _count(
            db, mine, CalendarEvent.event_date >= month_start, CalendarEvent.event_date < month_end
        ),
        projected_income_this_month=round(this_month.total, 2),
        unconverted_currencies=sorted({*ahead.unconverted, *this_month.unconverted}),
    )


async def passive_income(db: AsyncSession, user_id: uuid.UUID) -> PassiveIncomeResponse:
    """Revenus passifs du mois en cours et des onze suivants, par mois et par source, en euros."""
    now = datetime.now(UTC)
    first = _month_start(now)
    keys = [_month_key(first + relativedelta(months=offset)) for offset in range(PASSIVE_MONTHS)]
    income = await expected_income(db, user_id, now, first + relativedelta(months=PASSIVE_MONTHS))
    buckets = dict.fromkeys(keys, 0.0)
    for moment, amount in income.events + income.crowdfunding:
        buckets[_month_key(moment)] += amount
    return PassiveIncomeResponse(
        total_12m=round(sum(buckets.values()), 2),
        monthly=[MonthlyPassiveIncome(month=key, amount=round(buckets[key], 2)) for key in keys],
        sources=PassiveIncomeSources(
            events=round(sum(amount for _, amount in income.events), 2),
            crowdfunding=round(sum(amount for _, amount in income.crowdfunding), 2),
        ),
        unconverted_currencies=income.unconverted,
    )
