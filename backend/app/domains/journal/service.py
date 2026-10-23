from datetime import UTC, datetime
from uuid import UUID

from app.core.errors import NotFoundError
from app.domains.journal.models import Note
from app.domains.journal.repository import AssetRef, NoteFilters, NoteRepository
from app.domains.journal.schemas import (
    NoteCreate,
    NoteResponse,
    NoteSummaryResponse,
    NoteUpdate,
    ScorecardResponse,
)
from app.domains.journal.scorecard import build_scorecard, earliest_price_date

NOTE_NOT_FOUND = "Note non trouvée"
ASSET_NOT_FOUND = "Actif non trouvé"
_UPDATABLE_TEXT_FIELDS = ("title", "content", "tags", "transaction_ids", "attachments", "sentiment")


def _to_response(note: Note, asset: AssetRef | None) -> NoteResponse:
    return NoteResponse(
        id=note.id,
        title=note.title,
        content=note.content,
        tags=note.tags,
        asset_id=note.asset_id,
        asset_symbol=asset.symbol if asset else None,
        asset_name=asset.name if asset else None,
        transaction_ids=note.transaction_ids,
        attachments=note.attachments,
        sentiment=note.sentiment,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


class JournalService:
    """Cas d'usage du journal d'investissement d'un utilisateur."""

    def __init__(self, repository: NoteRepository) -> None:
        self._repository = repository

    async def summary(self, user_id: UUID) -> NoteSummaryResponse:
        """Nombre de notes, notes du mois courant et tags distincts."""
        notes = await self._repository.list_all(user_id)
        now = datetime.now(UTC)
        tags = {tag.strip() for note in notes if note.tags for tag in note.tags.split(",")} - {""}
        return NoteSummaryResponse(
            total_notes=len(notes),
            notes_this_month=sum(1 for n in notes if (n.created_at.year, n.created_at.month) == (now.year, now.month)),
            unique_tags=sorted(tags),
        )

    async def scorecard(self, user_id: UUID) -> ScorecardResponse:
        """Sentiment enregistré confronté à la performance réalisée à 30 et 90 jours."""
        notes = await self._repository.list_scorable(user_id)
        if not notes:
            return build_scorecard([], {}, {}, datetime.now(UTC).date())
        assets = await self._repository.assets_by_id({n.asset_id for n in notes if n.asset_id})
        symbols = {a.symbol for a in assets.values() if a.symbol}
        history = await self._repository.price_history(symbols, earliest_price_date(notes))
        return build_scorecard(notes, assets, history, datetime.now(UTC).date())

    async def list_notes(self, user_id: UUID, filters: NoteFilters) -> list[NoteResponse]:
        """Notes de l'utilisateur, les plus récentes d'abord."""
        notes = await self._repository.find(user_id, filters)
        assets = await self._repository.assets_by_id({n.asset_id for n in notes if n.asset_id})
        return [_to_response(n, assets.get(n.asset_id) if n.asset_id else None) for n in notes]

    async def get(self, note_id: UUID, user_id: UUID) -> NoteResponse:
        """Une note de l'utilisateur ; NotFoundError si elle n'existe pas ou appartient à un autre."""
        note = await self._owned_note(note_id, user_id)
        return _to_response(note, await self._linked_asset(note))

    async def create(self, user_id: UUID, data: NoteCreate) -> NoteResponse:
        """Crée une note ; l'actif lié doit appartenir à l'utilisateur."""
        asset = await self._owned_asset(data.asset_id, user_id) if data.asset_id else None
        note = await self._repository.add(Note(user_id=user_id, **data.model_dump()))
        return _to_response(note, asset)

    async def update(self, note_id: UUID, user_id: UUID, data: NoteUpdate) -> NoteResponse:
        """Met à jour les champs fournis ; asset_id explicitement nul délie l'actif."""
        note = await self._owned_note(note_id, user_id)
        for name in _UPDATABLE_TEXT_FIELDS:
            value = getattr(data, name)
            if value is not None:
                setattr(note, name, value)
        if "asset_id" in data.model_fields_set and data.asset_id is None:
            note.asset_id = None
        if data.asset_id is not None:
            note.asset_id = (await self._owned_asset(data.asset_id, user_id)).id
        note = await self._repository.save(note)
        return _to_response(note, await self._linked_asset(note))

    async def delete(self, note_id: UUID, user_id: UUID) -> None:
        """Supprime une note de l'utilisateur."""
        await self._repository.delete(await self._owned_note(note_id, user_id))

    async def _owned_note(self, note_id: UUID, user_id: UUID) -> Note:
        note = await self._repository.get_owned(note_id, user_id)
        if note is None:
            raise NotFoundError(NOTE_NOT_FOUND)
        return note

    async def _owned_asset(self, asset_id: UUID, user_id: UUID) -> AssetRef:
        asset = await self._repository.find_owned_asset(asset_id, user_id)
        if asset is None:
            raise NotFoundError(ASSET_NOT_FOUND)
        return asset

    async def _linked_asset(self, note: Note) -> AssetRef | None:
        if note.asset_id is None:
            return None
        return (await self._repository.assets_by_id({note.asset_id})).get(note.asset_id)
