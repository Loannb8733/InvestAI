from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.domains.calendar.models import CalendarEvent, EventType


class EventCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    event_type: EventType
    event_date: datetime
    is_recurring: bool = False
    recurrence_rule: str | None = Field(None, max_length=100)
    amount: float | None = None
    currency: str = Field(default="EUR", max_length=10)


REQUIRED_ON_UPDATE = ("title", "event_type", "event_date", "is_recurring", "currency", "is_completed")


class EventUpdate(BaseModel):
    """Champs à modifier ; un champ facultatif envoyé à null est effacé."""

    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    event_type: EventType | None = None
    event_date: datetime | None = None
    is_recurring: bool | None = None
    recurrence_rule: str | None = Field(None, max_length=100)
    amount: float | None = None
    currency: str | None = Field(None, max_length=10)
    is_completed: bool | None = None

    @model_validator(mode="after")
    def _required_fields_stay_set(self) -> Self:
        cleared = [name for name in REQUIRED_ON_UPDATE if name in self.model_fields_set and getattr(self, name) is None]
        if cleared:
            raise ValueError(f"Ces champs ne peuvent pas être effacés : {', '.join(cleared)}")
        return self


class EventResponse(BaseModel):
    id: UUID
    title: str
    description: str | None
    event_type: str
    event_date: datetime
    is_recurring: bool
    recurrence_rule: str | None
    amount: float | None
    currency: str
    is_completed: bool
    completed_at: datetime | None
    created_at: datetime
    source_project_id: UUID | None = None

    @classmethod
    def of(cls, event: CalendarEvent) -> "EventResponse":
        """Réponse d'un événement."""
        return cls(
            id=event.id,
            title=event.title,
            description=event.description,
            event_type=event.event_type.value,
            event_date=event.event_date,
            is_recurring=event.is_recurring,
            recurrence_rule=event.recurrence_rule,
            amount=float(event.amount) if event.amount is not None else None,
            currency=event.currency,
            is_completed=event.is_completed,
            completed_at=event.completed_at,
            created_at=event.created_at,
            source_project_id=event.source_project_id,
        )


class EventTypeInfo(BaseModel):
    value: str
    label: str
    color: str


class CalendarSummaryResponse(BaseModel):
    total_events: int
    upcoming_events: int
    completed_events: int
    total_expected_income: float
    events_this_month: int
    projected_income_this_month: float = 0.0
    unconverted_currencies: list[str] = []


class MonthlyPassiveIncome(BaseModel):
    """Revenus passifs projetés d'un mois (« YYYY-MM »)."""

    month: str
    amount: float


class PassiveIncomeSources(BaseModel):
    events: float
    crowdfunding: float


class PassiveIncomeResponse(BaseModel):
    """Revenus passifs projetés sur les douze prochains mois, par mois et par source."""

    total_12m: float
    monthly: list[MonthlyPassiveIncome]
    sources: PassiveIncomeSources
    unconverted_currencies: list[str] = []


class SeedTaxEventsResponse(BaseModel):
    created: int
    skipped: int
    message: str
