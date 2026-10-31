import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.dashboard.metrics.service import metrics_service
from app.domains.predictions.service import prediction_service

logger = logging.getLogger(__name__)

PROFILE_ALLOCATION: dict[str, dict[str, int]] = {
    "aggressive": {"risk_pct": 90, "reserve_pct": 10},
    "moderate": {"risk_pct": 70, "reserve_pct": 30},
    "conservative": {"risk_pct": 40, "reserve_pct": 60},
}


@dataclass
class DeploymentCapacity:
    """``liquidity_pct`` et ``invested_pct`` : parts liquide et investie (risquée) du patrimoine, en %."""

    available_liquidity: float
    total_value: float
    liquidity_pct: float
    invested_pct: float
    next_signal_symbol: str | None = None
    next_signal_action: str | None = None
    next_signal_amount: float = 0.0
    can_execute: bool = True
    shortfall: float = 0.0
    message: str | None = None
    profile: str = "moderate"
    deploy_to_risk: float = 0.0
    keep_in_reserve: float = 0.0


async def _liquidity_and_value(db: AsyncSession, user_id: str) -> tuple[float, float]:
    try:
        dashboard = await metrics_service.get_user_dashboard_metrics(db, user_id)
        available_liquidity = round(float(dashboard.get("available_liquidity", 0)), 2)
        total_value = round(float(dashboard.get("total_value", 0)), 2)
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to get dashboard metrics: %s", e)
        return 0.0, 0.0
    return available_liquidity, total_value


async def _next_buy_signal(db: AsyncSession, user_id: str) -> tuple[str | None, str | None, float]:
    next_symbol = None
    next_action = None
    next_amount = 0.0
    try:
        strategy_data = await prediction_service.get_strategy_map(db, user_id)
        assets = strategy_data.get("assets", [])
        for asset in assets:
            action = asset.get("action", "")
            if "ACHAT" in action or action == "DCA":
                next_symbol = asset.get("symbol")
                next_action = action
                next_amount = round(float(asset.get("impact_eur", 0)), 2)
                break
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to get strategy table: %s", e)
    return next_symbol, next_action, next_amount


async def compute_deployment_capacity(
    db: AsyncSession, user_id: str, monthly_dca: float, profile: str
) -> DeploymentCapacity:
    """Liquidité (cash + stablecoins) face au premier signal ACHAT/DCA de la table de stratégie, et répartition du DCA
    mensuel entre risque et réserve selon le profil ; montants arrondis au centime."""
    available_liquidity, total_value = await _liquidity_and_value(db, user_id)
    liquidity_pct = round(available_liquidity / total_value * 100, 1) if total_value > 0 else 0.0
    invested_pct = round(100 - liquidity_pct, 1) if total_value > 0 else 0.0

    next_symbol, next_action, next_amount = await _next_buy_signal(db, user_id)

    can_execute = available_liquidity >= next_amount if next_amount > 0 else True
    shortfall = round(max(0, next_amount - available_liquidity), 2) if not can_execute else 0.0
    message = None
    if not can_execute and next_symbol:
        message = (
            f"Liquidité insuffisante pour le signal Alpha sur {next_symbol} "
            f"({next_amount:.2f} € requis, {available_liquidity:.2f} € disponible)."
        )

    alloc = PROFILE_ALLOCATION[profile]
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
