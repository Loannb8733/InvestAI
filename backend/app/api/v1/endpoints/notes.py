"""Notes endpoints for investment journal."""

import bisect
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.models.asset import Asset
from app.models.asset_price_history import AssetPriceHistory
from app.models.note import Note
from app.models.portfolio import Portfolio
from app.models.user import User

router = APIRouter()

# --- Scorecard : seuils documentés -----------------------------------------
# Verdict directionnel : un sentiment bullish est "correct" si la performance
# dépasse +2 % (au-delà du bruit de marché) ; bearish si elle est sous −2 %.
SCORECARD_DIRECTIONAL_THRESHOLD_PCT = 2.0
# Un sentiment neutre est "correct" si la performance reste dans ±5 %
# (bande plus large : un avis neutre tolère des variations modérées).
SCORECARD_NEUTRAL_BAND_PCT = 5.0
# Tolérance de recherche d'un prix historique autour d'une date cible
# (week-ends / trous de données pour les actions et ETF).
SCORECARD_PRICE_TOLERANCE_DAYS = 3
# Horizons d'évaluation en jours.
SCORECARD_HORIZONS = (30, 90)


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


class ScorecardEntry(BaseModel):
    """A journal note scored against realized performance."""

    note_id: UUID
    title: str
    symbol: str
    sentiment: str
    note_date: date
    perf_30d: Optional[float] = None
    perf_90d: Optional[float] = None
    verdict_30d: str  # correct | incorrect | pending
    verdict_90d: str  # correct | incorrect | pending


class ScorecardSentimentStats(BaseModel):
    """Per-sentiment aggregate."""

    n: int
    hit_rate: Optional[float] = None


class ScorecardSummary(BaseModel):
    """Scorecard aggregates."""

    total_scored: int
    unscorable: int
    hit_rate_30d: Optional[float] = None
    hit_rate_90d: Optional[float] = None
    by_sentiment: Dict[str, ScorecardSentimentStats]


class ScorecardResponse(BaseModel):
    """Scorecard response: sentiment recorded vs realized performance."""

    entries: List[ScorecardEntry]
    summary: ScorecardSummary


def _nearest_price(
    dates: List[date],
    prices: List[Decimal],
    target: date,
) -> Optional[Decimal]:
    """Return the price closest to ``target`` within ±SCORECARD_PRICE_TOLERANCE_DAYS.

    ``dates`` must be sorted ascending and aligned with ``prices``.
    """
    if not dates:
        return None
    i = bisect.bisect_left(dates, target)
    best: Optional[Decimal] = None
    best_delta: Optional[int] = None
    for j in (i - 1, i):
        if 0 <= j < len(dates):
            delta = abs((dates[j] - target).days)
            if delta <= SCORECARD_PRICE_TOLERANCE_DAYS and (best_delta is None or delta < best_delta):
                best = prices[j]
                best_delta = delta
    return best


def _sentiment_verdict(sentiment: str, perf_pct: Optional[float], matured: bool) -> str:
    """Verdict for one note/horizon.

    Thresholds (documented on module constants):
    - bullish  -> correct if perf > +2 %
    - bearish  -> correct if perf < −2 %
    - neutral  -> correct if |perf| <= 5 %
    "pending" when the horizon is not reached yet, or when no price is available.
    """
    if perf_pct is None or not matured:
        return "pending"
    if sentiment == "bullish":
        return "correct" if perf_pct > SCORECARD_DIRECTIONAL_THRESHOLD_PCT else "incorrect"
    if sentiment == "bearish":
        return "correct" if perf_pct < -SCORECARD_DIRECTIONAL_THRESHOLD_PCT else "incorrect"
    return "correct" if abs(perf_pct) <= SCORECARD_NEUTRAL_BAND_PCT else "incorrect"


def _hit_rate(verdicts: List[str]) -> Optional[float]:
    """Hit rate (%) over decided verdicts only; None if nothing is decided yet."""
    decided = [v for v in verdicts if v in ("correct", "incorrect")]
    if not decided:
        return None
    return round(100.0 * sum(1 for v in decided if v == "correct") / len(decided), 1)


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
    now = datetime.now(timezone.utc)
    notes_this_month = sum(1 for n in notes if n.created_at.year == now.year and n.created_at.month == now.month)

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


@router.get("/scorecard", response_model=ScorecardResponse)
@limiter.limit("30/minute")  # endpoint calculé (lecture lourde) — aligné sur les autres endpoints agrégés
async def get_notes_scorecard(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScorecardResponse:
    """Scorecard du journal : sentiment enregistré vs performance réalisée.

    Méthodologie :
    - Éligibilité : notes avec ``asset_id`` ET ``sentiment`` (bullish/bearish/neutral).
    - Prix de référence : ``AssetPriceHistory`` au jour de la note (tolérance ±3 jours).
      Sans prix de référence, la note est exclue et comptée dans ``summary.unscorable``.
    - Horizons : +30 j et +90 j. Échéance non atteinte → perf provisoire calculée
      sur le prix actuel de l'actif (flag partial via verdict ``pending``).
    - Verdicts : bullish correct si perf > +2 % ; bearish correct si perf < −2 % ;
      neutral correct si |perf| ≤ 5 %. ``pending`` si échéance non atteinte ou prix manquant.
    - ``hit_rate_30d``/``hit_rate_90d`` : % de verdicts corrects parmi les verdicts échus.
    - ``by_sentiment.hit_rate`` : agrège les verdicts échus des deux horizons.
    """
    result = await db.execute(
        select(Note)
        .where(
            Note.user_id == current_user.id,
            Note.asset_id.isnot(None),
            Note.sentiment.in_(["bullish", "bearish", "neutral"]),
        )
        .order_by(Note.created_at.desc())
    )
    notes = result.scalars().all()

    by_sentiment_verdicts: Dict[str, List[str]] = {"bullish": [], "bearish": [], "neutral": []}
    by_sentiment_n: Dict[str, int] = {"bullish": 0, "bearish": 0, "neutral": 0}

    def _build_summary(
        entries: List[ScorecardEntry],
        unscorable: int,
        verdicts_30: List[str],
        verdicts_90: List[str],
    ) -> ScorecardSummary:
        return ScorecardSummary(
            total_scored=len(entries),
            unscorable=unscorable,
            hit_rate_30d=_hit_rate(verdicts_30),
            hit_rate_90d=_hit_rate(verdicts_90),
            by_sentiment={
                s: ScorecardSentimentStats(n=by_sentiment_n[s], hit_rate=_hit_rate(by_sentiment_verdicts[s]))
                for s in ("bullish", "bearish", "neutral")
            },
        )

    if not notes:
        return ScorecardResponse(entries=[], summary=_build_summary([], 0, [], []))

    # Batch load des actifs liés (mêmes garanties que list_notes : l'appartenance
    # de l'actif a été vérifiée à la création/mise à jour de la note).
    asset_ids = {n.asset_id for n in notes if n.asset_id}
    assets_by_id: Dict[UUID, Asset] = {}
    asset_result = await db.execute(select(Asset).where(Asset.id.in_(asset_ids)))
    for asset in asset_result.scalars().all():
        assets_by_id[asset.id] = asset

    symbols = {a.symbol for a in assets_by_id.values() if a.symbol}
    earliest = min(n.created_at.date() for n in notes) - timedelta(days=SCORECARD_PRICE_TOLERANCE_DAYS)

    # Historique de prix chargé en une requête, indexé par symbole
    # (listes triées par date pour recherche dichotomique).
    history: Dict[str, Tuple[List[date], List[Decimal]]] = {}
    if symbols:
        ph_result = await db.execute(
            select(
                AssetPriceHistory.symbol,
                AssetPriceHistory.price_date,
                AssetPriceHistory.price_eur,
            )
            .where(
                AssetPriceHistory.symbol.in_(symbols),
                AssetPriceHistory.price_date >= earliest,
            )
            .order_by(AssetPriceHistory.symbol, AssetPriceHistory.price_date)
        )
        for sym, price_date, price_eur in ph_result.all():
            dates, prices = history.setdefault(sym, ([], []))
            dates.append(price_date)
            prices.append(price_eur)

    today = datetime.now(timezone.utc).date()
    entries: List[ScorecardEntry] = []
    verdicts_30: List[str] = []
    verdicts_90: List[str] = []
    unscorable = 0

    for note in notes:
        asset = assets_by_id.get(note.asset_id)
        if not asset or not asset.symbol:
            unscorable += 1
            continue

        dates, prices = history.get(asset.symbol, ([], []))
        note_date = note.created_at.date()
        base_price = _nearest_price(dates, prices, note_date)
        if base_price is None or base_price == 0:
            # Pas d'historique exploitable au jour de la note → non évaluable.
            unscorable += 1
            continue

        perfs: Dict[int, Optional[float]] = {}
        verdicts: Dict[int, str] = {}
        for horizon in SCORECARD_HORIZONS:
            target = note_date + timedelta(days=horizon)
            matured = target <= today
            if matured:
                horizon_price = _nearest_price(dates, prices, target)
            else:
                # Échéance non atteinte : perf provisoire sur le prix actuel.
                horizon_price = asset.current_price
            perf = float((horizon_price - base_price) / base_price * 100) if horizon_price is not None else None
            perfs[horizon] = round(perf, 2) if perf is not None else None
            verdicts[horizon] = _sentiment_verdict(note.sentiment, perf, matured)

        entries.append(
            ScorecardEntry(
                note_id=note.id,
                title=note.title,
                symbol=asset.symbol,
                sentiment=note.sentiment,
                note_date=note_date,
                perf_30d=perfs[30],
                perf_90d=perfs[90],
                verdict_30d=verdicts[30],
                verdict_90d=verdicts[90],
            )
        )
        verdicts_30.append(verdicts[30])
        verdicts_90.append(verdicts[90])
        by_sentiment_n[note.sentiment] += 1
        by_sentiment_verdicts[note.sentiment].extend([verdicts[30], verdicts[90]])

    return ScorecardResponse(
        entries=entries,
        summary=_build_summary(entries, unscorable, verdicts_30, verdicts_90),
    )


@router.get("", response_model=List[NoteResponse])
async def list_notes(
    tag: Optional[str] = None,
    asset_id: Optional[UUID] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[NoteResponse]:
    """List all notes for the current user."""
    query = select(Note).where(Note.user_id == current_user.id)

    if asset_id:
        query = query.where(Note.asset_id == asset_id)

    if tag:
        query = query.where(Note.tags.ilike(f"%{tag}%"))

    if search:
        query = query.where(
            or_(
                Note.title.ilike(f"%{search}%"),
                Note.content.ilike(f"%{search}%"),
            )
        )

    result = await db.execute(query.order_by(Note.created_at.desc()).offset(skip).limit(limit))
    notes = result.scalars().all()

    # Batch load assets to avoid N+1
    asset_ids = {n.asset_id for n in notes if n.asset_id}
    assets_by_id: dict = {}
    if asset_ids:
        asset_result = await db.execute(select(Asset).where(Asset.id.in_(asset_ids)))
        for asset in asset_result.scalars().all():
            assets_by_id[asset.id] = asset

    response = []
    for note in notes:
        asset = assets_by_id.get(note.asset_id) if note.asset_id else None
        response.append(
            NoteResponse(
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
        )

    return response


@router.post("", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
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
                detail="Actif non trouvé",
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
            detail="Note non trouvée",
        )

    asset_symbol = None
    asset_name = None

    if note.asset_id:
        asset_result = await db.execute(select(Asset).where(Asset.id == note.asset_id))
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
            detail="Note non trouvée",
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
    # PATCH sémantique : « asset_id présent avec null » = délier l'actif ;
    # « asset_id absent » = inchangé (model_fields_set fait la distinction).
    if "asset_id" in note_in.model_fields_set and note_in.asset_id is None:
        note.asset_id = None
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
                detail="Actif non trouvé",
            )
        note.asset_id = note_in.asset_id

    await db.commit()
    await db.refresh(note)

    asset_symbol = None
    asset_name = None

    if note.asset_id:
        asset_result = await db.execute(select(Asset).where(Asset.id == note.asset_id))
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
            detail="Note non trouvée",
        )

    await db.delete(note)
    await db.commit()
