from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_session
from app.core.rate_limit import limiter
from app.domains.identity.dependencies import get_current_user
from app.domains.identity.models import User
from app.domains.journal.repository import NoteFilters, NoteRepository
from app.domains.journal.schemas import (
    NoteCreate,
    NoteResponse,
    NoteSummaryResponse,
    NoteUpdate,
    ScorecardResponse,
)
from app.domains.journal.service import JournalService

router = APIRouter()


def get_journal_service(session: Annotated[AsyncSession, Depends(get_session)]) -> JournalService:
    return JournalService(NoteRepository(session))


Service = Annotated[JournalService, Depends(get_journal_service)]


def current_user_id(user: Annotated[User, Depends(get_current_user)]) -> UUID:
    return cast(UUID, user.id)


UserId = Annotated[UUID, Depends(current_user_id)]


@router.get("/summary")
async def get_notes_summary(user_id: UserId, service: Service) -> NoteSummaryResponse:
    return await service.summary(user_id)


@router.get("/scorecard")
@limiter.limit("30/minute")
async def get_notes_scorecard(request: Request, user_id: UserId, service: Service) -> ScorecardResponse:
    return await service.scorecard(user_id)


@router.get("")
async def list_notes(
    user_id: UserId,
    service: Service,
    tag: str | None = None,
    asset_id: UUID | None = None,
    search: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[NoteResponse]:
    filters = NoteFilters(tag=tag, asset_id=asset_id, search=search, skip=skip, limit=limit)
    return await service.list_notes(user_id, filters)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_note(note_in: NoteCreate, user_id: UserId, service: Service) -> NoteResponse:
    return await service.create(user_id, note_in)


@router.get("/{note_id}")
async def get_note(note_id: UUID, user_id: UserId, service: Service) -> NoteResponse:
    return await service.get(note_id, user_id)


@router.patch("/{note_id}")
async def update_note(note_id: UUID, note_in: NoteUpdate, user_id: UserId, service: Service) -> NoteResponse:
    return await service.update(note_id, user_id, note_in)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(note_id: UUID, user_id: UserId, service: Service) -> None:
    await service.delete(note_id, user_id)
