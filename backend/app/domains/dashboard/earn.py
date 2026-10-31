"""Synthèse du staking : valeur des positions, récompenses et rendement annualisé."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.dashboard import repository
from app.domains.dashboard.schemas import EarnAsset, EarnSummary
from app.domains.market_data.fx.cold_start import USD_EUR as COLD_START_USD_EUR
from app.domains.market_data.fx.spot import spot_rates
from app.domains.portfolio.classification import is_stablecoin

_DAYS_PER_YEAR = 365


def _unit_prices(metrics: dict[str, Any]) -> dict[str, float]:
    prices: dict[str, float] = {}
    for asset in metrics.get("aggregated_assets", []):
        quantity = asset.get("quantity", 0)
        if quantity and float(quantity) > 0:
            prices[asset["symbol"].upper()] = float(asset["current_value"]) / float(quantity)
    return prices


async def _annual_rate(db: AsyncSession, user_id: UUID, rewards: float, staked: float) -> float | None:
    if staked <= 0 or rewards <= 0:
        return None
    first = await repository.first_reward_date(db, user_id)
    if not first:
        return None
    days_earning = max((datetime.now(UTC) - first.replace(tzinfo=first.tzinfo or UTC)).days, 1)
    return round((rewards / staked) * (_DAYS_PER_YEAR / days_earning) * 100, 2)


async def build_earn_summary(
    db: AsyncSession, user_id: UUID, metrics: dict[str, Any]
) -> tuple[EarnSummary | None, dict[str, float]]:
    """Rend la synthèse, absente sans position, et les quantités en staking par symbole."""
    staked = await repository.net_staked_quantities(db, user_id)
    rewards = await repository.staking_rewards(db, user_id)
    prices = _unit_prices(metrics)
    usd_eur = float(await spot_rates.get("USD", "EUR") or COLD_START_USD_EUR)

    def price_of(symbol: str) -> float | None:
        if symbol in prices:
            return prices[symbol]
        return usd_eur if is_stablecoin(symbol) else None

    positions = [
        EarnAsset(symbol=symbol, staked_quantity=quantity, current_value=quantity * (price_of(symbol) or 0.0))
        for symbol, quantity in staked.items()
        if quantity > 0
    ]
    total_staked = sum((position.current_value for position in positions), 0.0)
    total_rewards = sum((quantity * (price_of(symbol) or 0.0) for symbol, quantity in rewards.items()), 0.0)
    positions.sort(key=lambda position: position.current_value, reverse=True)
    if not positions:
        return None, staked
    apr = await _annual_rate(db, user_id, total_rewards, total_staked)
    return (
        EarnSummary(total_staked_value=total_staked, total_rewards=total_rewards, apr=apr, assets=positions),
        staked,
    )
