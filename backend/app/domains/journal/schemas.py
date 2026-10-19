from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

SENTIMENT_PATTERN = "^(bullish|bearish|neutral)$"
Verdict = Literal["correct", "incorrect", "pending"]


class NoteCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str | None = None
    tags: str | None = Field(None, max_length=500)
    asset_id: UUID | None = None
    transaction_ids: str | None = None
    attachments: str | None = None
    sentiment: str | None = Field(None, pattern=SENTIMENT_PATTERN)


class NoteUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    content: str | None = None
    tags: str | None = Field(None, max_length=500)
    asset_id: UUID | None = None
    transaction_ids: str | None = None
    attachments: str | None = None
    sentiment: str | None = Field(None, pattern=SENTIMENT_PATTERN)


class NoteResponse(BaseModel):
    id: UUID
    title: str
    content: str | None
    tags: str | None
    asset_id: UUID | None
    asset_symbol: str | None = None
    asset_name: str | None = None
    transaction_ids: str | None = None
    attachments: str | None = None
    sentiment: str | None = None
    created_at: datetime
    updated_at: datetime


class NoteSummaryResponse(BaseModel):
    total_notes: int
    notes_this_month: int
    unique_tags: list[str]


class ScorecardEntry(BaseModel):
    note_id: UUID
    title: str
    symbol: str
    sentiment: str
    note_date: date
    perf_30d: float | None = None
    perf_90d: float | None = None
    verdict_30d: Verdict
    verdict_90d: Verdict


class ScorecardSentimentStats(BaseModel):
    n: int
    hit_rate: float | None = None


class ScorecardSummary(BaseModel):
    total_scored: int
    unscorable: int
    hit_rate_30d: float | None = None
    hit_rate_90d: float | None = None
    by_sentiment: dict[str, ScorecardSentimentStats]


class ScorecardResponse(BaseModel):
    entries: list[ScorecardEntry]
    summary: ScorecardSummary
