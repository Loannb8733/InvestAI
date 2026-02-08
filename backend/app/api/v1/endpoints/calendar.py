"""Calendar endpoints for financial events and reminders."""

from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.calendar_event import CalendarEvent, EventType
from app.models.user import User

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
    result = await db.execute(
        select(CalendarEvent).where(CalendarEvent.user_id == current_user.id)
    )
    events = result.scalars().all()

    now = datetime.utcnow()

    # Count upcoming events (not completed, date >= now)
    upcoming = sum(
        1 for e in events
        if not e.is_completed and e.event_date >= now
    )

    # Count completed events
    completed = sum(1 for e in events if e.is_completed)

    # Events this month
    events_this_month = sum(
        1 for e in events
        if e.event_date.year == now.year and e.event_date.month == now.month
    )

    # Total expected income (from dividends, rent, interest)
    income_types = [EventType.DIVIDEND, EventType.RENT, EventType.INTEREST]
    total_income = sum(
        float(e.amount or 0) for e in events
        if e.event_type in income_types and not e.is_completed and e.event_date >= now
    )

    return CalendarSummaryResponse(
        total_events=len(events),
        upcoming_events=upcoming,
        completed_events=completed,
        total_expected_income=total_income,
        events_this_month=events_this_month,
    )


@router.get("/upcoming", response_model=List[EventResponse])
async def list_upcoming_events(
    days: int = 30,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[EventResponse]:
    """List upcoming events in the next N days."""
    now = datetime.utcnow()
    end_date = now + timedelta(days=days)

    result = await db.execute(
        select(CalendarEvent).where(
            CalendarEvent.user_id == current_user.id,
            CalendarEvent.is_completed == False,
            CalendarEvent.event_date >= now,
            CalendarEvent.event_date <= end_date,
        ).order_by(CalendarEvent.event_date.asc())
    )
    events = result.scalars().all()

    return [
        EventResponse(
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
        )
        for e in events
    ]


@router.get("/", response_model=List[EventResponse])
async def list_events(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    event_type: Optional[EventType] = None,
    show_completed: bool = True,
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
    if not show_completed:
        query = query.where(CalendarEvent.is_completed == False)

    result = await db.execute(query.order_by(CalendarEvent.event_date.asc()))
    events = result.scalars().all()

    return [
        EventResponse(
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
        )
        for e in events
    ]


@router.post("/", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
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

    return EventResponse(
        id=event.id,
        title=event.title,
        description=event.description,
        event_type=event.event_type.value,
        event_date=event.event_date,
        is_recurring=event.is_recurring,
        recurrence_rule=event.recurrence_rule,
        amount=float(event.amount) if event.amount else None,
        currency=event.currency,
        is_completed=event.is_completed,
        completed_at=event.completed_at,
        created_at=event.created_at,
    )


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
            detail="Evenement non trouve",
        )

    return EventResponse(
        id=event.id,
        title=event.title,
        description=event.description,
        event_type=event.event_type.value,
        event_date=event.event_date,
        is_recurring=event.is_recurring,
        recurrence_rule=event.recurrence_rule,
        amount=float(event.amount) if event.amount else None,
        currency=event.currency,
        is_completed=event.is_completed,
        completed_at=event.completed_at,
        created_at=event.created_at,
    )


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
            detail="Evenement non trouve",
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
            event.completed_at = datetime.utcnow()
        else:
            event.completed_at = None

    await db.commit()
    await db.refresh(event)

    return EventResponse(
        id=event.id,
        title=event.title,
        description=event.description,
        event_type=event.event_type.value,
        event_date=event.event_date,
        is_recurring=event.is_recurring,
        recurrence_rule=event.recurrence_rule,
        amount=float(event.amount) if event.amount else None,
        currency=event.currency,
        is_completed=event.is_completed,
        completed_at=event.completed_at,
        created_at=event.created_at,
    )


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
            detail="Evenement non trouve",
        )

    event.is_completed = True
    event.completed_at = datetime.utcnow()

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

    return EventResponse(
        id=event.id,
        title=event.title,
        description=event.description,
        event_type=event.event_type.value,
        event_date=event.event_date,
        is_recurring=event.is_recurring,
        recurrence_rule=event.recurrence_rule,
        amount=float(event.amount) if event.amount else None,
        currency=event.currency,
        is_completed=event.is_completed,
        completed_at=event.completed_at,
        created_at=event.created_at,
    )


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
            detail="Evenement non trouve",
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
        day = min(current_date.day, 28)  # Safe day for all months
        return current_date.replace(year=year, month=month, day=day)
    elif "YEARLY" in rule:
        return current_date.replace(year=current_date.year + 1)

    return None
