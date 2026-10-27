from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_session
from app.domains.calendar.income import calendar_summary, passive_income
from app.domains.calendar.models import INCOME_TYPES, CalendarEvent, EventType
from app.domains.calendar.recurrence import next_occurrence
from app.domains.calendar.schemas import (
    CalendarSummaryResponse,
    EventCreate,
    EventResponse,
    EventTypeInfo,
    EventUpdate,
    PassiveIncomeResponse,
    SeedTaxEventsResponse,
)
from app.domains.calendar.tax import seed_tax_events as seed_french_tax_events
from app.domains.identity.dependencies import CurrentUser

router = APIRouter()

Session = Annotated[AsyncSession, Depends(get_session)]

EVENT_TYPES = (
    EventTypeInfo(value="dividend", label="Dividende", color="#22c55e"),
    EventTypeInfo(value="rent", label="Loyer", color="#3b82f6"),
    EventTypeInfo(value="interest", label="Interet", color="#8b5cf6"),
    EventTypeInfo(value="payment_due", label="Echeance", color="#ef4444"),
    EventTypeInfo(value="rebalance", label="Reequilibrage", color="#f59e0b"),
    EventTypeInfo(value="tax_deadline", label="Echeance fiscale", color="#ec4899"),
    EventTypeInfo(value="reminder", label="Rappel", color="#6b7280"),
    EventTypeInfo(value="other", label="Autre", color="#71717a"),
)


async def _owned(session: AsyncSession, event_id: UUID, user_id: UUID) -> CalendarEvent:
    query = select(CalendarEvent).where(CalendarEvent.id == event_id, CalendarEvent.user_id == user_id)
    event = (await session.execute(query)).scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Événement non trouvé")
    return event


@router.get("/event-types", response_model=list[EventTypeInfo])
async def list_event_types() -> list[EventTypeInfo]:
    """Types d'événements proposés à l'écran, avec leur couleur."""
    return list(EVENT_TYPES)


@router.get("/summary", response_model=CalendarSummaryResponse)
async def get_calendar_summary(user: CurrentUser, session: Session) -> CalendarSummaryResponse:
    """Compteurs et revenus attendus du calendrier de l'utilisateur."""
    return await calendar_summary(session, user.id)


@router.get("/upcoming", response_model=list[EventResponse])
async def list_upcoming_events(
    user: CurrentUser, session: Session, days: int = 30, skip: int = 0, limit: int = 50
) -> list[EventResponse]:
    """Événements non faits des ``days`` prochains jours, du plus proche au plus lointain."""
    now = datetime.now(UTC)
    query = (
        select(CalendarEvent)
        .where(
            CalendarEvent.user_id == user.id,
            CalendarEvent.is_completed.is_(False),
            CalendarEvent.event_date >= now,
            CalendarEvent.event_date <= now + timedelta(days=days),
        )
        .order_by(CalendarEvent.event_date.asc())
        .offset(skip)
        .limit(limit)
    )
    return [EventResponse.of(event) for event in (await session.execute(query)).scalars().all()]


@router.get("/passive-income", response_model=PassiveIncomeResponse)
async def get_passive_income(user: CurrentUser, session: Session) -> PassiveIncomeResponse:
    """Revenus passifs projetés sur les douze prochains mois, en euros."""
    return await passive_income(session, user.id)


@router.post("/seed-tax-events", response_model=SeedTaxEventsResponse)
async def seed_tax_events(user: CurrentUser, session: Session) -> SeedTaxEventsResponse:
    """Ajoute les échéances fiscales françaises manquantes de l'année et de la suivante."""
    return await seed_french_tax_events(session, user.id)


@router.get("", response_model=list[EventResponse])
async def list_events(
    user: CurrentUser,
    session: Session,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    event_type: EventType | None = None,
    show_completed: bool = True,
    income_only: bool = False,
    skip: int = 0,
    limit: int = 50,
) -> list[EventResponse]:
    """Événements de l'utilisateur, filtrés, par date croissante."""
    query = select(CalendarEvent).where(CalendarEvent.user_id == user.id)
    if start_date:
        query = query.where(CalendarEvent.event_date >= start_date)
    if end_date:
        query = query.where(CalendarEvent.event_date <= end_date)
    if event_type:
        query = query.where(CalendarEvent.event_type == event_type)
    if income_only:
        query = query.where(CalendarEvent.event_type.in_(INCOME_TYPES))
    if not show_completed:
        query = query.where(CalendarEvent.is_completed.is_(False))
    rows = await session.execute(query.order_by(CalendarEvent.event_date.asc()).offset(skip).limit(limit))
    return [EventResponse.of(event) for event in rows.scalars().all()]


@router.post("", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(event_in: EventCreate, user: CurrentUser, session: Session) -> EventResponse:
    """Crée un événement."""
    event = CalendarEvent(user_id=user.id, is_completed=False, **event_in.model_dump())
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return EventResponse.of(event)


@router.get("/{event_id}", response_model=EventResponse)
async def get_event(event_id: UUID, user: CurrentUser, session: Session) -> EventResponse:
    """Événement de l'utilisateur."""
    return EventResponse.of(await _owned(session, event_id, user.id))


@router.patch("/{event_id}", response_model=EventResponse)
async def update_event(event_id: UUID, event_in: EventUpdate, user: CurrentUser, session: Session) -> EventResponse:
    """Modifie les champs fournis, null efface un champ facultatif ; fait ou rouvert date la réalisation."""
    event = await _owned(session, event_id, user.id)
    changes = event_in.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(event, field, value)
    if "is_completed" in changes:
        event.completed_at = datetime.now(UTC) if changes["is_completed"] else None
    await session.commit()
    await session.refresh(event)
    return EventResponse.of(event)


@router.post("/{event_id}/complete", response_model=EventResponse)
async def complete_event(event_id: UUID, user: CurrentUser, session: Session) -> EventResponse:
    """Marque l'événement fait ; un événement récurrent crée son occurrence suivante, une seule fois."""
    event = await _owned(session, event_id, user.id)
    if event.is_completed:
        return EventResponse.of(event)
    event.is_completed = True
    event.completed_at = datetime.now(UTC)
    following = (
        next_occurrence(event.event_date, event.recurrence_rule)
        if event.is_recurring and event.recurrence_rule
        else None
    )
    if following:
        session.add(
            CalendarEvent(
                user_id=user.id,
                title=event.title,
                description=event.description,
                event_type=event.event_type,
                event_date=following,
                is_recurring=True,
                recurrence_rule=event.recurrence_rule,
                amount=event.amount,
                currency=event.currency,
                is_completed=False,
            )
        )
    await session.commit()
    await session.refresh(event)
    return EventResponse.of(event)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(event_id: UUID, user: CurrentUser, session: Session) -> None:
    """Supprime un événement de l'utilisateur."""
    await session.delete(await _owned(session, event_id, user.id))
    await session.commit()
