from collections.abc import Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.strategies.capacity import DeploymentCapacity, compute_deployment_capacity
from app.domains.strategies.models import StrategyAction
from app.domains.strategies.performance import compute_strategy_performance


class StrategyService:
    async def get_deployment_capacity(
        self,
        db: AsyncSession,
        user_id: str,
        monthly_dca: float = 300.0,
        profile: str = "moderate",
    ) -> DeploymentCapacity:
        return await compute_deployment_capacity(db, user_id, monthly_dca, profile)

    async def get_strategy_performance(self, db: AsyncSession, actions: Sequence[StrategyAction]) -> dict[str, Any]:
        return await compute_strategy_performance(db, actions)


strategy_service = StrategyService()
