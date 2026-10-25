from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.planning.goals.models import Goal


async def list_user_goals(db: AsyncSession, user_id: UUID, skip: int, limit: int) -> Sequence[Goal]:
    result = await db.execute(
        select(Goal).where(Goal.user_id == user_id).order_by(Goal.created_at.desc()).offset(skip).limit(limit)
    )
    return result.scalars().all()


async def find_owned_goal(db: AsyncSession, goal_id: UUID, user_id: UUID) -> Goal | None:
    result = await db.execute(
        select(Goal).where(
            Goal.id == goal_id,
            Goal.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()
