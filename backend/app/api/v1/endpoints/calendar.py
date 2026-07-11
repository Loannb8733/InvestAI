"""Calendar endpoints for financial events and reminders."""

import calendar
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.calendar_event import CalendarEvent, EventType
from app.models.user import User
from app.services.crowdfunding_calendar_service import crowdfunding_calendar_service

logger = logging.getLogger(__name__)

router = APIRouter()


class EventCreate(BaseModel):
    """Schema for creating a calendar event."""

    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    event_type: EventType
    event_date: datetime
    is_recurring: bool = False
    recurrence_rule: Optional[str] = Field(None, max_length=100)
    amount: Optional[float] = None
    currency: str = Field(default="EUR", max_length=10)


class EventUpdate(BaseModel):
    """Schema for updating a calendar event."""

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    event_type: Optional[EventType] = None
    event_date: Optional[datetime] = None
    is_recurring: Optional[bool] = None
    recurrence_rule: Optional[str] = Field(None, max_length=100)
    amount: Optional[float] = None
    currency: Optional[str] = Field(None, max_length=10)
    is_completed: Optional[bool] = None


class EventResponse(BaseModel):
    """Calendar event response schema."""

    id: UUID
    title: str
    description: Optional[str]
    event_type: str
    event_date: datetime
    is_recurring: bool
    recurrence_rule: Optional[str]
    amount: Optional[float]
    currency: str
    is_completed: bool
    completed_at: Optional[datetime]
    created_at: datetime
    source_project_id: Optional[UUID] = None


class EventTypeInfo(BaseModel):
    """Event type information."""

    value: str
    label: str
    color: str


class CalendarSummaryResponse(BaseModel):
    """Calendar summary response."""

    total_events: int
    upcoming_events: int
    completed_events: int
    total_expected_income: float
    events_this_month: int
    projected_income_this_month: float = 0.0


class MonthlyPassiveIncome(BaseModel):
    """Revenus passifs projetés pour un mois donné."""

    month: str  # format "YYYY-MM"
    amount: float


class PassiveIncomeSources(BaseModel):
    """Répartition des revenus passifs par source."""

    events: float
    crowdfunding: float


class PassiveIncomeResponse(BaseModel):
    """Revenus passifs projetés sur les 12 prochains mois."""

    total_12m: float
    monthly: List[MonthlyPassiveIncome]
    sources: PassiveIncomeSources


class SeedTaxEventsResponse(BaseModel):
    """Résultat de la création des échéances fiscales françaises."""

    created: int
    skipped: int
    message: str


def _event_response(e: CalendarEvent) -> EventResponse:
    """Build an EventResponse from a CalendarEvent model."""
    return EventResponse(
        id=e.id,
        title=e.title,
        description=e.description,
        event_type=e.event_type.value,
        event_date=e.event_date,
        is_recurring=e.is_recurring,
        recurrence_rule=e.recurrence_rule,
        amount=float(e.amount) if e.amount else None,
        currency=e.currency,
        is_completed=e.is_completed,
        completed_at=e.completed_at,
        created_at=e.created_at,
        source_project_id=e.source_project_id,
    )


@router.get("/event-types", response_model=List[EventTypeInfo])
async def list_event_types() -> List[EventTypeInfo]:
    """List all available event types."""
    types = [
        {"value": "dividend", "label": "Dividende", "color": "#22c55e"},
        {"value": "rent", "label": "Loyer", "color": "#3b82f6"},
        {"value": "interest", "label": "Interet", "color": "#8b5cf6"},
        {"value": "payment_due", "label": "Echeance", "color": "#ef4444"},
        {"value": "rebalance", "label": "Reequilibrage", "color": "#f59e0b"},
        {"value": "tax_deadline", "label": "Echeance fiscale", "color": "#ec4899"},
        {"value": "reminder", "label": "Rappel", "color": "#6b7280"},
        {"value": "other", "label": "Autre", "color": "#71717a"},
    ]
    return [EventTypeInfo(**t) for t in types]


@router.get("/summary", response_model=CalendarSummaryResponse)
async def get_calendar_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CalendarSummaryResponse:
    """Get summary of user's calendar events."""
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_end = (month_start + timedelta(days=32)).replace(day=1)
    income_types = [EventType.DIVIDEND, EventType.RENT, EventType.INTEREST]

    base = CalendarEvent.user_id == current_user.id

    total_result = await db.execute(select(func.count()).select_from(CalendarEvent).where(base))
    total_events = total_result.scalar() or 0

    upcoming_result = await db.execute(
        select(func.count())
        .select_from(CalendarEvent)
        .where(base, CalendarEvent.is_completed.is_(False), CalendarEvent.event_date >= now)
    )
    upcoming = upcoming_result.scalar() or 0

    completed_result = await db.execute(
        select(func.count()).select_from(CalendarEvent).where(base, CalendarEvent.is_completed.is_(True))
    )
    completed = completed_result.scalar() or 0

    month_result = await db.execute(
        select(func.count())
        .select_from(CalendarEvent)
        .where(base, CalendarEvent.event_date >= month_start, CalendarEvent.event_date < month_end)
    )
    events_this_month = month_result.scalar() or 0

    # Sommes PAR DEVISE puis conversion en EUR — l'ancien SUM brut additionnait
    # des montants EUR/USD/GBP entre eux et affichait le tout « en EUR ».
    async def _income_eur(*extra_conds) -> float:
        result = await db.execute(
            select(CalendarEvent.currency, func.coalesce(func.sum(CalendarEvent.amount), 0))
            .where(
                base,
                CalendarEvent.event_type.in_(income_types),
                CalendarEvent.is_completed.is_(False),
                *extra_conds,
            )
            .group_by(CalendarEvent.currency)
        )
        total = 0.0
        for ccy, amount in result.all():
            amount = float(amount or 0)
            ccy = (ccy or "EUR").upper()
            if ccy != "EUR" and amount:
                try:
                    from app.services.price_service import price_service

                    rate = await price_service.get_forex_rate(ccy, "EUR")
                    amount = amount * float(rate) if rate else amount
                except Exception as exc:  # noqa: BLE001 — best-effort, montant brut sinon
                    logger.debug("Conversion %s->EUR indisponible pour le résumé calendrier: %s", ccy, exc)
            total += amount
        return total

    total_income = await _income_eur(CalendarEvent.event_date >= now)
    income_this_month = await _income_eur(
        CalendarEvent.event_date >= month_start,
        CalendarEvent.event_date < month_end,
    )

    return CalendarSummaryResponse(
        total_events=total_events,
        upcoming_events=upcoming,
        completed_events=completed,
        total_expected_income=total_income,
        events_this_month=events_this_month,
        projected_income_this_month=round(income_this_month, 2),
    )


@router.get("/upcoming", response_model=List[EventResponse])
async def list_upcoming_events(
    days: int = 30,
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[EventResponse]:
    """List upcoming events in the next N days."""
    now = datetime.now(timezone.utc)
    end_date = now + timedelta(days=days)

    result = await db.execute(
        select(CalendarEvent)
        .where(
            CalendarEvent.user_id == current_user.id,
            CalendarEvent.is_completed.is_(False),
            CalendarEvent.event_date >= now,
            CalendarEvent.event_date <= end_date,
        )
        .order_by(CalendarEvent.event_date.asc())
        .offset(skip)
        .limit(limit)
    )
    events = result.scalars().all()

    return [_event_response(e) for e in events]


@router.get("/passive-income", response_model=PassiveIncomeResponse)
async def get_passive_income(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PassiveIncomeResponse:
    """Revenus passifs projetés sur les 12 prochains mois.

    Agrège (a) les événements de revenus (dividendes, loyers, intérêts) non
    complétés — récurrences dépliées sur la fenêtre — et (b) les coupons
    crowdfunding via le service dédié. Montants convertis en EUR comme le summary.
    """
    now = datetime.now(timezone.utc)
    cutoff = now + relativedelta(months=12)
    income_types = [EventType.DIVIDEND, EventType.RENT, EventType.INTEREST]

    # 12 seaux mensuels ("YYYY-MM"), à partir du mois courant
    month_keys: List[str] = []
    buckets: dict = {}
    for offset in range(12):
        d = now + relativedelta(months=offset)
        key = f"{d.year:04d}-{d.month:02d}"
        month_keys.append(key)
        buckets[key] = 0.0

    # Devise -> EUR (même logique que le summary), avec cache de taux par requête
    rate_cache: dict = {}

    async def _to_eur(amount: float, ccy: Optional[str]) -> float:
        ccy = (ccy or "EUR").upper()
        if not amount:
            return 0.0
        if ccy == "EUR":
            return float(amount)
        if ccy not in rate_cache:
            try:
                from app.services.price_service import price_service

                rate_cache[ccy] = await price_service.get_forex_rate(ccy, "EUR")
            except Exception as exc:  # noqa: BLE001 — best-effort, montant brut sinon
                logger.debug("Conversion %s->EUR indisponible pour les revenus passifs: %s", ccy, exc)
                rate_cache[ccy] = None
        rate = rate_cache[ccy]
        return float(amount) * float(rate) if rate else float(amount)

    # (a) Événements de revenus — hors crowdfunding (source_project_id) pour
    # éviter le double comptage avec get_upcoming_coupon_income.
    result = await db.execute(
        select(CalendarEvent).where(
            CalendarEvent.user_id == current_user.id,
            CalendarEvent.event_type.in_(income_types),
            CalendarEvent.is_completed.is_(False),
            CalendarEvent.source_project_id.is_(None),
            CalendarEvent.amount.is_not(None),
            CalendarEvent.event_date <= cutoff,
        )
    )
    income_events = result.scalars().all()

    events_total = 0.0
    for event in income_events:
        amount_eur = await _to_eur(float(event.amount or 0), event.currency)
        if amount_eur <= 0:
            continue

        occurrence = event.event_date
        if occurrence.tzinfo is None:
            occurrence = occurrence.replace(tzinfo=timezone.utc)

        occurrences: List[datetime] = []
        if event.is_recurring and event.recurrence_rule:
            rule_upper = event.recurrence_rule.upper()
            # Avance rapide pour les règles courtes dont la date de base est passée
            if occurrence < now:
                behind_days = (now - occurrence).days
                if "DAILY" in rule_upper:
                    occurrence = occurrence + timedelta(days=behind_days)
                elif "WEEKLY" in rule_upper:
                    occurrence = occurrence + timedelta(weeks=behind_days // 7)
            # Déplie la récurrence sur la fenêtre (garde-fou : 400 itérations)
            guard = 0
            while occurrence <= cutoff and guard < 400:
                if occurrence >= now:
                    occurrences.append(occurrence)
                next_date = _get_next_occurrence(occurrence, event.recurrence_rule)
                if not next_date or next_date <= occurrence:
                    break
                if next_date.tzinfo is None:
                    next_date = next_date.replace(tzinfo=timezone.utc)
                occurrence = next_date
                guard += 1
        elif occurrence >= now:
            occurrences.append(occurrence)

        for occ in occurrences:
            key = f"{occ.year:04d}-{occ.month:02d}"
            if key in buckets:
                buckets[key] += amount_eur
                events_total += amount_eur

    # (b) Coupons crowdfunding (déjà en EUR)
    crowdfunding_total = 0.0
    coupon_income = await crowdfunding_calendar_service.get_upcoming_coupon_income(db, current_user.id, months_ahead=12)
    for entry in coupon_income:
        offset = int(entry["month_offset"])
        if 0 <= offset < len(month_keys):
            buckets[month_keys[offset]] += float(entry["amount"])
            crowdfunding_total += float(entry["amount"])

    monthly = [MonthlyPassiveIncome(month=k, amount=round(buckets[k], 2)) for k in month_keys]

    return PassiveIncomeResponse(
        total_12m=round(sum(buckets.values()), 2),
        monthly=monthly,
        sources=PassiveIncomeSources(
            events=round(events_total, 2),
            crowdfunding=round(crowdfunding_total, 2),
        ),
    )


def _french_tax_events_for_year(year: int) -> List[dict]:
    """Échéances fiscales françaises indicatives pour une année donnée.

    Dates approximatives — le calendrier exact est publié chaque année par la
    DGFiP (l'ouverture de la déclaration a lieu généralement début avril).
    """
    note = (
        "Date indicative — vérifiez le calendrier officiel sur impots.gouv.fr. "
        "Concerne notamment les formulaires 2042 (déclaration des revenus) "
        "et 2086 (plus-values sur actifs numériques)."
    )
    return [
        {
            "title": f"Ouverture de la déclaration des revenus {year}",
            "date": datetime(year, 4, 1, 9, 0, tzinfo=timezone.utc),
            "description": f"Ouverture du service de déclaration en ligne (généralement début avril). {note}",
        },
        {
            "title": f"Date limite de déclaration en ligne {year} (départements 50 et +)",
            "date": datetime(year, 6, 8, 9, 0, tzinfo=timezone.utc),
            "description": f"Date limite de la déclaration en ligne pour les départements 50 à 976. {note}",
        },
        {
            "title": f"Solde de l'impôt sur le revenu {year}",
            "date": datetime(year, 9, 15, 9, 0, tzinfo=timezone.utc),
            "description": f"Prélèvement du solde de l'impôt sur le revenu (généralement mi-septembre). {note}",
        },
    ]


@router.post("/seed-tax-events", response_model=SeedTaxEventsResponse)
async def seed_tax_events(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SeedTaxEventsResponse:
    """Crée les échéances fiscales françaises manquantes (année en cours + suivante).

    Idempotent : l'existence est vérifiée par titre (qui inclut l'année) avant
    insertion. Les échéances déjà passées ne sont pas créées.
    """
    now = datetime.now(timezone.utc)

    existing_result = await db.execute(
        select(CalendarEvent.title).where(
            CalendarEvent.user_id == current_user.id,
            CalendarEvent.event_type == EventType.TAX_DEADLINE,
        )
    )
    existing_titles = set(existing_result.scalars().all())

    created = 0
    skipped = 0
    for year in (now.year, now.year + 1):
        for candidate in _french_tax_events_for_year(year):
            if candidate["title"] in existing_titles or candidate["date"] < now:
                skipped += 1
                continue
            db.add(
                CalendarEvent(
                    user_id=current_user.id,
                    title=candidate["title"],
                    description=candidate["description"],
                    event_type=EventType.TAX_DEADLINE,
                    event_date=candidate["date"],
                    is_recurring=False,
                    currency="EUR",
                    is_completed=False,
                )
            )
            existing_titles.add(candidate["title"])
            created += 1

    if created:
        await db.commit()

    if created:
        message = f"{created} échéance(s) fiscale(s) ajoutée(s). Dates indicatives — vérifiez sur impots.gouv.fr."
    else:
        message = "Aucune échéance à ajouter : elles existent déjà ou sont passées."

    return SeedTaxEventsResponse(created=created, skipped=skipped, message=message)


@router.get("", response_model=List[EventResponse])
async def list_events(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    event_type: Optional[EventType] = None,
    show_completed: bool = True,
    income_only: bool = False,
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[EventResponse]:
    """List all calendar events for the current user."""
    query = select(CalendarEvent).where(CalendarEvent.user_id == current_user.id)

    if start_date:
        query = query.where(CalendarEvent.event_date >= start_date)
    if end_date:
        query = query.where(CalendarEvent.event_date <= end_date)
    if event_type:
        query = query.where(CalendarEvent.event_type == event_type)
    if income_only:
        query = query.where(CalendarEvent.event_type.in_([EventType.DIVIDEND, EventType.RENT, EventType.INTEREST]))
    if not show_completed:
        query = query.where(CalendarEvent.is_completed.is_(False))

    result = await db.execute(query.order_by(CalendarEvent.event_date.asc()).offset(skip).limit(limit))
    events = result.scalars().all()

    return [_event_response(e) for e in events]


@router.post("", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    event_in: EventCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EventResponse:
    """Create a new calendar event."""
    event = CalendarEvent(
        user_id=current_user.id,
        title=event_in.title,
        description=event_in.description,
        event_type=event_in.event_type,
        event_date=event_in.event_date,
        is_recurring=event_in.is_recurring,
        recurrence_rule=event_in.recurrence_rule,
        amount=event_in.amount,
        currency=event_in.currency,
        is_completed=False,
    )

    db.add(event)
    await db.commit()
    await db.refresh(event)

    return _event_response(event)


@router.get("/{event_id}", response_model=EventResponse)
async def get_event(
    event_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EventResponse:
    """Get a specific calendar event."""
    result = await db.execute(
        select(CalendarEvent).where(
            CalendarEvent.id == event_id,
            CalendarEvent.user_id == current_user.id,
        )
    )
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Événement non trouvé",
        )

    return _event_response(event)


@router.patch("/{event_id}", response_model=EventResponse)
async def update_event(
    event_id: UUID,
    event_in: EventUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EventResponse:
    """Update a calendar event."""
    result = await db.execute(
        select(CalendarEvent).where(
            CalendarEvent.id == event_id,
            CalendarEvent.user_id == current_user.id,
        )
    )
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Événement non trouvé",
        )

    if event_in.title is not None:
        event.title = event_in.title
    if event_in.description is not None:
        event.description = event_in.description
    if event_in.event_type is not None:
        event.event_type = event_in.event_type
    if event_in.event_date is not None:
        event.event_date = event_in.event_date
    if event_in.is_recurring is not None:
        event.is_recurring = event_in.is_recurring
    if event_in.recurrence_rule is not None:
        event.recurrence_rule = event_in.recurrence_rule
    if event_in.amount is not None:
        event.amount = event_in.amount
    if event_in.currency is not None:
        event.currency = event_in.currency
    if event_in.is_completed is not None:
        event.is_completed = event_in.is_completed
        if event_in.is_completed:
            event.completed_at = datetime.now(timezone.utc)
        else:
            event.completed_at = None

    await db.commit()
    await db.refresh(event)

    return _event_response(event)


@router.post("/{event_id}/complete", response_model=EventResponse)
async def complete_event(
    event_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EventResponse:
    """Mark a calendar event as completed."""
    result = await db.execute(
        select(CalendarEvent).where(
            CalendarEvent.id == event_id,
            CalendarEvent.user_id == current_user.id,
        )
    )
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Événement non trouvé",
        )

    event.is_completed = True
    event.completed_at = datetime.now(timezone.utc)

    # If recurring, create next occurrence
    if event.is_recurring and event.recurrence_rule:
        next_date = _get_next_occurrence(event.event_date, event.recurrence_rule)
        if next_date:
            next_event = CalendarEvent(
                user_id=current_user.id,
                title=event.title,
                description=event.description,
                event_type=event.event_type,
                event_date=next_date,
                is_recurring=True,
                recurrence_rule=event.recurrence_rule,
                amount=event.amount,
                currency=event.currency,
                is_completed=False,
            )
            db.add(next_event)

    await db.commit()
    await db.refresh(event)

    return _event_response(event)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    event_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a calendar event."""
    result = await db.execute(
        select(CalendarEvent).where(
            CalendarEvent.id == event_id,
            CalendarEvent.user_id == current_user.id,
        )
    )
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Événement non trouvé",
        )

    await db.delete(event)
    await db.commit()


def _get_next_occurrence(current_date: datetime, rule: str) -> Optional[datetime]:
    """Calculate the next occurrence based on recurrence rule."""
    rule = rule.upper()

    if "DAILY" in rule:
        return current_date + timedelta(days=1)
    elif "WEEKLY" in rule:
        return current_date + timedelta(weeks=1)
    elif "MONTHLY" in rule:
        # Add one month
        month = current_date.month + 1
        year = current_date.year
        if month > 12:
            month = 1
            year += 1
        last_day = calendar.monthrange(year, month)[1]
        day = min(current_date.day, last_day)
        return current_date.replace(year=year, month=month, day=day)
    elif "YEARLY" in rule:
        return current_date.replace(year=current_date.year + 1)

    return None
