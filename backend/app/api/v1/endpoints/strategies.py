"""Strategy endpoints — CRUD + AI suggestions."""

import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.models.strategy import ActionStatus, Strategy, StrategyAction, StrategySource, StrategyStatus
from app.models.user import User
from app.schemas.strategy import StrategyActionUpdate, StrategyCreate, StrategyResponse, StrategyUpdate

logger = logging.getLogger(__name__)

router = APIRouter()


async def _enrich(db: AsyncSession, strategy: Strategy) -> dict:
    """Build response dict with actions included."""
    result = await db.execute(
        select(StrategyAction).where(StrategyAction.strategy_id == strategy.id).order_by(StrategyAction.created_at)
    )
    actions = result.scalars().all()

    return {
        "id": strategy.id,
        "user_id": strategy.user_id,
        "name": strategy.name,
        "description": strategy.description,
        "source": strategy.source.value if strategy.source else "USER",
        "status": strategy.status.value if strategy.status else "ACTIVE",
        "params": strategy.params or {},
        "ai_reasoning": strategy.ai_reasoning,
        "market_regime": strategy.market_regime,
        "confidence": float(strategy.confidence) if strategy.confidence else None,
        "actions": [
            {
                "id": a.id,
                "strategy_id": a.strategy_id,
                "action": a.action,
                "symbol": a.symbol,
                "amount": float(a.amount) if a.amount else None,
                "currency": a.currency,
                "reason": a.reason,
                "status": a.status.value if a.status else "PENDING",
                "scheduled_at": a.scheduled_at,
                "executed_at": a.executed_at,
                "created_at": a.created_at,
            }
            for a in actions
        ],
        "created_at": strategy.created_at,
        "updated_at": strategy.updated_at,
    }


@router.get("", response_model=List[StrategyResponse])
@limiter.limit("30/minute")
async def list_strategies(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all strategies for the current user."""
    result = await db.execute(
        select(Strategy).where(Strategy.user_id == current_user.id).order_by(Strategy.created_at.desc())
    )
    strategies = result.scalars().all()
    return [await _enrich(db, s) for s in strategies]


@router.post("", response_model=StrategyResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_strategy(
    request: Request,
    data: StrategyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a user-defined strategy with optional actions."""
    strategy = Strategy(
        user_id=current_user.id,
        name=data.name,
        description=data.description,
        source=StrategySource.USER,
        status=StrategyStatus.ACTIVE,
        params=data.params,
    )
    db.add(strategy)
    await db.flush()

    for action_data in data.actions:
        action = StrategyAction(
            strategy_id=strategy.id,
            action=action_data.action,
            symbol=action_data.symbol,
            amount=action_data.amount,
            currency=action_data.currency,
            reason=action_data.reason,
            status=ActionStatus.PENDING,
        )
        db.add(action)

    await db.commit()
    await db.refresh(strategy)
    return await _enrich(db, strategy)


@router.patch("/{strategy_id}", response_model=StrategyResponse)
@limiter.limit("20/minute")
async def update_strategy(
    request: Request,
    strategy_id: UUID,
    data: StrategyUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a strategy (name, description, status, params)."""
    result = await db.execute(
        select(Strategy).where(
            Strategy.id == strategy_id,
            Strategy.user_id == current_user.id,
        )
    )
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(status_code=404, detail="Stratégie non trouvée")

    if data.name is not None:
        strategy.name = data.name
    if data.description is not None:
        strategy.description = data.description
    if data.status is not None:
        strategy.status = StrategyStatus(data.status)
    if data.params is not None:
        strategy.params = data.params

    await db.commit()
    await db.refresh(strategy)
    return await _enrich(db, strategy)


@router.delete("/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")
async def delete_strategy(
    request: Request,
    strategy_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a strategy and its actions."""
    result = await db.execute(
        select(Strategy).where(
            Strategy.id == strategy_id,
            Strategy.user_id == current_user.id,
        )
    )
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(status_code=404, detail="Stratégie non trouvée")

    await db.delete(strategy)
    await db.commit()


@router.post("/ai-suggest", response_model=List[StrategyResponse])
@limiter.limit("5/minute")
async def ai_suggest_strategies(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ask AI to analyze portfolio and suggest strategies.

    Generates new strategy proposals based on current market regime,
    portfolio composition, alpha scores, and liquidity.
    """
    from app.services.ai_strategy_service import ai_strategy_service

    suggestions = await ai_strategy_service.suggest_strategies(db, str(current_user.id))
    saved = await ai_strategy_service.save_suggestions(db, str(current_user.id), suggestions)

    return [await _enrich(db, s) for s in saved]


@router.patch("/{strategy_id}/accept", response_model=StrategyResponse)
@limiter.limit("10/minute")
async def accept_strategy(
    request: Request,
    strategy_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Accept an AI-proposed strategy (changes status to ACTIVE)."""
    result = await db.execute(
        select(Strategy).where(
            Strategy.id == strategy_id,
            Strategy.user_id == current_user.id,
        )
    )
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(status_code=404, detail="Stratégie non trouvée")

    strategy.status = StrategyStatus.ACTIVE
    await db.commit()
    await db.refresh(strategy)
    return await _enrich(db, strategy)


@router.patch("/{strategy_id}/reject", response_model=StrategyResponse)
@limiter.limit("10/minute")
async def reject_strategy(
    request: Request,
    strategy_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reject an AI-proposed strategy."""
    result = await db.execute(
        select(Strategy).where(
            Strategy.id == strategy_id,
            Strategy.user_id == current_user.id,
        )
    )
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(status_code=404, detail="Stratégie non trouvée")

    strategy.status = StrategyStatus.REJECTED
    await db.commit()
    await db.refresh(strategy)
    return await _enrich(db, strategy)


@router.patch("/actions/{action_id}", response_model=dict)
@limiter.limit("20/minute")
async def update_action_status(
    request: Request,
    action_id: UUID,
    data: StrategyActionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark an action as EXECUTED or SKIPPED."""
    result = await db.execute(
        select(StrategyAction)
        .join(Strategy, Strategy.id == StrategyAction.strategy_id)
        .where(
            StrategyAction.id == action_id,
            Strategy.user_id == current_user.id,
        )
    )
    action = result.scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail="Action non trouvée")

    action.status = ActionStatus(data.status)
    if data.status == "EXECUTED":
        from datetime import datetime, timezone

        action.executed_at = datetime.now(timezone.utc)

    await db.commit()
    return {"id": str(action.id), "status": action.status.value}
