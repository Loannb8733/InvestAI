"""Notes endpoints for investment journal."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.asset import Asset
from app.models.note import Note
from app.models.portfolio import Portfolio
from app.models.user import User

router = APIRouter()


class NoteCreate(BaseModel):
    """Schema for creating a note."""

    title: str = Field(..., min_length=1, max_length=200)
    content: Optional[str] = None
    tags: Optional[str] = Field(None, max_length=500)
    asset_id: Optional[UUID] = None
    transaction_ids: Optional[str] = None  # Comma-separated UUIDs
    attachments: Optional[str] = None  # JSON array
    sentiment: Optional[str] = Field(None, pattern="^(bullish|bearish|neutral)$")


class NoteUpdate(BaseModel):
    """Schema for updating a note."""

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    content: Optional[str] = None
    tags: Optional[str] = Field(None, max_length=500)
    asset_id: Optional[UUID] = None
    transaction_ids: Optional[str] = None
    attachments: Optional[str] = None
    sentiment: Optional[str] = Field(None, pattern="^(bullish|bearish|neutral)$")


class NoteResponse(BaseModel):
    """Note response schema."""

    id: UUID
    title: str
    content: Optional[str]
    tags: Optional[str]
    asset_id: Optional[UUID]
    asset_symbol: Optional[str] = None
    asset_name: Optional[str] = None
    transaction_ids: Optional[str] = None
    attachments: Optional[str] = None
    sentiment: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class NoteSummaryResponse(BaseModel):
    """Note summary response."""

    total_notes: int
    notes_this_month: int
    unique_tags: List[str]


@router.get("/summary", response_model=NoteSummaryResponse)
async def get_notes_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NoteSummaryResponse:
    """Get summary of user's notes."""
    result = await db.execute(
        select(Note).where(
            Note.user_id == current_user.id,
        )
    )
    notes = result.scalars().all()

    # Count notes this month
    now = datetime.utcnow()
    notes_this_month = sum(
        1 for n in notes
        if n.created_at.year == now.year and n.created_at.month == now.month
    )

    # Collect unique tags
    all_tags = set()
    for note in notes:
        if note.tags:
            for tag in note.tags.split(","):
                tag = tag.strip()
                if tag:
                    all_tags.add(tag)

    return NoteSummaryResponse(
        total_notes=len(notes),
        notes_this_month=notes_this_month,
        unique_tags=sorted(list(all_tags)),
    )


@router.get("/tags", response_model=List[str])
async def list_tags(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[str]:
    """List all unique tags used in notes."""
    result = await db.execute(
        select(Note.tags).where(
            Note.user_id == current_user.id,
            Note.tags.isnot(None),
        )
    )
    tags_list = result.scalars().all()

    all_tags = set()
    for tags in tags_list:
        if tags:
            for tag in tags.split(","):
                tag = tag.strip()
                if tag:
                    all_tags.add(tag)

    return sorted(list(all_tags))


@router.get("/", response_model=List[NoteResponse])
async def list_notes(
    tag: Optional[str] = None,
    asset_id: Optional[UUID] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[NoteResponse]:
    """List all notes for the current user."""
    query = select(Note).where(
        Note.user_id == current_user.id,
        Note.user_id == current_user.id,
    )

    if asset_id:
        query = query.where(Note.asset_id == asset_id)

    result = await db.execute(query.order_by(Note.created_at.desc()))
    notes = result.scalars().all()

    # Filter by tag if specified
    if tag:
        notes = [
            n for n in notes
            if n.tags and tag.lower() in n.tags.lower()
        ]

    # Filter by search term
    if search:
        search_lower = search.lower()
        notes = [
            n for n in notes
            if search_lower in n.title.lower()
            or (n.content and search_lower in n.content.lower())
        ]

    # Build response with asset info
    response = []
    for note in notes:
        asset_symbol = None
        asset_name = None

        if note.asset_id:
            asset_result = await db.execute(
                select(Asset).where(Asset.id == note.asset_id)
            )
            asset = asset_result.scalar_one_or_none()
            if asset:
                asset_symbol = asset.symbol
                asset_name = asset.name

        response.append(
            NoteResponse(
                id=note.id,
                title=note.title,
                content=note.content,
                tags=note.tags,
                asset_id=note.asset_id,
                asset_symbol=asset_symbol,
                asset_name=asset_name,
                transaction_ids=note.transaction_ids,
                attachments=note.attachments,
                sentiment=note.sentiment,
                created_at=note.created_at,
                updated_at=note.updated_at,
            )
        )

    return response


@router.post("/", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
async def create_note(
    note_in: NoteCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NoteResponse:
    """Create a new note."""
    # Verify asset belongs to user if specified
    asset_symbol = None
    asset_name = None

    if note_in.asset_id:
        result = await db.execute(
            select(Portfolio).where(
                Portfolio.user_id == current_user.id,
            )
        )
        portfolios = result.scalars().all()
        portfolio_ids = [p.id for p in portfolios]

        result = await db.execute(
            select(Asset).where(
                Asset.id == note_in.asset_id,
                Asset.portfolio_id.in_(portfolio_ids),
            )
        )
        asset = result.scalar_one_or_none()

        if not asset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Actif non trouve",
            )
        asset_symbol = asset.symbol
        asset_name = asset.name

    note = Note(
        user_id=current_user.id,
        title=note_in.title,
        content=note_in.content,
        tags=note_in.tags,
        asset_id=note_in.asset_id,
        transaction_ids=note_in.transaction_ids,
        attachments=note_in.attachments,
        sentiment=note_in.sentiment,
    )

    db.add(note)
    await db.commit()
    await db.refresh(note)

    return NoteResponse(
        id=note.id,
        title=note.title,
        content=note.content,
        tags=note.tags,
        asset_id=note.asset_id,
        asset_symbol=asset_symbol,
        asset_name=asset_name,
        transaction_ids=note.transaction_ids,
        attachments=note.attachments,
        sentiment=note.sentiment,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


@router.get("/{note_id}", response_model=NoteResponse)
async def get_note(
    note_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NoteResponse:
    """Get a specific note."""
    result = await db.execute(
        select(Note).where(
            Note.id == note_id,
            Note.user_id == current_user.id,
        )
    )
    note = result.scalar_one_or_none()

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note non trouvee",
        )

    asset_symbol = None
    asset_name = None

    if note.asset_id:
        asset_result = await db.execute(
            select(Asset).where(Asset.id == note.asset_id)
        )
        asset = asset_result.scalar_one_or_none()
        if asset:
            asset_symbol = asset.symbol
            asset_name = asset.name

    return NoteResponse(
        id=note.id,
        title=note.title,
        content=note.content,
        tags=note.tags,
        asset_id=note.asset_id,
        asset_symbol=asset_symbol,
        asset_name=asset_name,
        transaction_ids=note.transaction_ids,
        attachments=note.attachments,
        sentiment=note.sentiment,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


@router.patch("/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: UUID,
    note_in: NoteUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NoteResponse:
    """Update a note."""
    result = await db.execute(
        select(Note).where(
            Note.id == note_id,
            Note.user_id == current_user.id,
        )
    )
    note = result.scalar_one_or_none()

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note non trouvee",
        )

    if note_in.title is not None:
        note.title = note_in.title
    if note_in.content is not None:
        note.content = note_in.content
    if note_in.tags is not None:
        note.tags = note_in.tags
    if note_in.transaction_ids is not None:
        note.transaction_ids = note_in.transaction_ids
    if note_in.attachments is not None:
        note.attachments = note_in.attachments
    if note_in.sentiment is not None:
        note.sentiment = note_in.sentiment
    if note_in.asset_id is not None:
        # Verify asset belongs to user
        result = await db.execute(
            select(Portfolio).where(
                Portfolio.user_id == current_user.id,
            )
        )
        portfolios = result.scalars().all()
        portfolio_ids = [p.id for p in portfolios]

        result = await db.execute(
            select(Asset).where(
                Asset.id == note_in.asset_id,
                Asset.portfolio_id.in_(portfolio_ids),
            )
        )
        asset = result.scalar_one_or_none()

        if not asset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Actif non trouve",
            )
        note.asset_id = note_in.asset_id

    await db.commit()
    await db.refresh(note)

    asset_symbol = None
    asset_name = None

    if note.asset_id:
        asset_result = await db.execute(
            select(Asset).where(Asset.id == note.asset_id)
        )
        asset = asset_result.scalar_one_or_none()
        if asset:
            asset_symbol = asset.symbol
            asset_name = asset.name

    return NoteResponse(
        id=note.id,
        title=note.title,
        content=note.content,
        tags=note.tags,
        asset_id=note.asset_id,
        asset_symbol=asset_symbol,
        asset_name=asset_name,
        transaction_ids=note.transaction_ids,
        attachments=note.attachments,
        sentiment=note.sentiment,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a note."""
    result = await db.execute(
        select(Note).where(
            Note.id == note_id,
            Note.user_id == current_user.id,
        )
    )
    note = result.scalar_one_or_none()

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note non trouvee",
        )

    await db.delete(note)
    await db.commit()
