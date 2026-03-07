"""Strategy service — deployment capacity and munitions intelligence.

Compares available liquidity (Cash + Stablecoins) with the next Alpha
signal to determine whether the user can execute the recommended trade.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# Strategy profile presets: what % of incoming DCA goes to risk vs reserve
PROFILE_ALLOCATION = {
    "aggressive": {"risk_pct": 90, "reserve_pct": 10},
    "moderate": {"risk_pct": 70, "reserve_pct": 30},
    "conservative": {"risk_pct": 40, "reserve_pct": 60},
}


@dataclass
class DeploymentCapacity:
    """Result of deployment capacity check."""

    available_liquidity: float
    total_value: float
    liquidity_pct: float  # % of portfolio that is liquid
    invested_pct: float  # % of portfolio that is invested (risky)

    # Next alpha signal
    next_signal_symbol: Optional[str] = None
    next_signal_action: Optional[str] = None
    next_signal_amount: float = 0.0
    can_execute: bool = True
    shortfall: float = 0.0
    message: Optional[str] = None

    # Deployment suggestion based on profile
    profile: str = "moderate"
    deploy_to_risk: float = 0.0
    keep_in_reserve: float = 0.0


class StrategyService:
    """Munitions intelligence and deployment capacity."""

    async def get_deployment_capacity(
        self,
        db: AsyncSession,
        user_id: str,
        monthly_dca: float = 300.0,
        profile: str = "moderate",
    ) -> DeploymentCapacity:
        """Compare available liquidity with next Alpha signal.

        Returns deployment capacity including whether the user can execute
        the top recommended trade and how to split the monthly DCA.
        """
        from app.services.metrics_service import metrics_service

        # 1. Get dashboard metrics for liquidity + total value
        try:
            dashboard = await metrics_service.get_user_dashboard_metrics(db, user_id)
            available_liquidity = float(dashboard.get("available_liquidity", 0))
            total_value = float(dashboard.get("total_value", 0))
        except Exception as e:
            logger.warning("Failed to get dashboard metrics: %s", e)
            available_liquidity = 0.0
            total_value = 0.0

        # 2. Compute allocation split
        liquidity_pct = round(available_liquidity / total_value * 100, 1) if total_value > 0 else 0.0
        invested_pct = round(100 - liquidity_pct, 1)

        # 3. Get top Alpha signal from strategy table
        next_symbol = None
        next_action = None
        next_amount = 0.0
        try:
            from app.services.prediction_service import prediction_service

            strategy_data = await prediction_service.get_strategy_table(db, user_id)
            assets = strategy_data.get("assets", [])
            # Find the first buy/DCA signal
            for asset in assets:
                action = asset.get("action", "")
                if "ACHAT" in action or action == "DCA":
                    next_symbol = asset.get("symbol")
                    next_action = action
                    next_amount = float(asset.get("impact_eur", 0))
                    break
        except Exception as e:
            logger.warning("Failed to get strategy table: %s", e)

        # 4. Can we execute?
        can_execute = available_liquidity >= next_amount if next_amount > 0 else True
        shortfall = max(0, next_amount - available_liquidity) if not can_execute else 0.0
        message = None
        if not can_execute and next_symbol:
            message = (
                f"Liquidité insuffisante pour le signal Alpha sur {next_symbol} "
                f"({next_amount:.2f} € requis, {available_liquidity:.2f} € disponible)."
            )

        # 5. DCA deployment suggestion based on profile
        alloc = PROFILE_ALLOCATION.get(profile, PROFILE_ALLOCATION["moderate"])
        deploy_risk = round(monthly_dca * alloc["risk_pct"] / 100, 2)
        keep_reserve = round(monthly_dca * alloc["reserve_pct"] / 100, 2)

        return DeploymentCapacity(
            available_liquidity=available_liquidity,
            total_value=total_value,
            liquidity_pct=liquidity_pct,
            invested_pct=invested_pct,
            next_signal_symbol=next_symbol,
            next_signal_action=next_action,
            next_signal_amount=next_amount,
            can_execute=can_execute,
            shortfall=shortfall,
            message=message,
            profile=profile,
            deploy_to_risk=deploy_risk,
            keep_in_reserve=keep_reserve,
        )


# Singleton
strategy_service = StrategyService()
