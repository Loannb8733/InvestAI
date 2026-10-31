"""Part de chaque symbole dans le risque du portefeuille, d'après sa volatilité historique."""

import math
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.finance_constants import TRADING_DAYS_PER_YEAR
from app.domains.dashboard.metrics import repository

_WINDOW_DAYS = 90
_MIN_PRICES = 10


def _annualized_volatility(prices: list[float]) -> float:
    if len(prices) < _MIN_PRICES:
        return 0.0
    returns = [(prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices)) if prices[i - 1] > 0]
    if not returns:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / len(returns)
    return math.sqrt(variance) * math.sqrt(TRADING_DAYS_PER_YEAR)


async def compute_risk_weights(
    db: AsyncSession, symbol_values: dict[str, float], total_value: float
) -> dict[str, float]:
    """Contribution en pourcentage de chaque symbole : poids dans le portefeuille par volatilité, normalisé."""
    if not symbol_values or total_value <= 0:
        return {}
    cutoff = (datetime.now(UTC) - timedelta(days=_WINDOW_DAYS)).date()
    prices: dict[str, list[float]] = defaultdict(list)
    for symbol, price in await repository.priced_history(db, list(symbol_values), cutoff):
        prices[symbol].append(price)
    contributions = {
        symbol: value / total_value * _annualized_volatility(prices.get(symbol, []))
        for symbol, value in symbol_values.items()
    }
    total = sum(contributions.values())
    return {symbol: round(share / total * 100 if total > 0 else 0, 2) for symbol, share in contributions.items()}
