from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.strategies.models import Strategy, StrategyAction


async def list_user_strategies(db: AsyncSession, user_id: UUID) -> Sequence[Strategy]:
    result = await db.execute(select(Strategy).where(Strategy.user_id == user_id).order_by(Strategy.created_at.desc()))
    return result.scalars().all()


async def list_actions(db: AsyncSession, strategy_id: UUID) -> Sequence[StrategyAction]:
    result = await db.execute(
        select(StrategyAction).where(StrategyAction.strategy_id == strategy_id).order_by(StrategyAction.created_at)
    )
    return result.scalars().all()


async def find_owned_strategy(db: AsyncSession, strategy_id: UUID, user_id: UUID) -> Strategy | None:
    result = await db.execute(
        select(Strategy).where(
            Strategy.id == strategy_id,
            Strategy.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def find_owned_action(db: AsyncSession, action_id: UUID, user_id: UUID) -> StrategyAction | None:
    result = await db.execute(
        select(StrategyAction)
        .join(Strategy, Strategy.id == StrategyAction.strategy_id)
        .where(
            StrategyAction.id == action_id,
            Strategy.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()
