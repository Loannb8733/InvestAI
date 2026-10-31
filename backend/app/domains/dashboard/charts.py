"""Courbes de la page portefeuille et comparaison aux indices."""

import math
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.domains.dashboard import repository
from app.domains.dashboard.overview import resolve_period_days
from app.domains.dashboard.schemas import BenchmarkDataPoint, BenchmarkSeries, HistoricalDataPoint, SparklineData
from app.domains.dashboard.snapshots.service import snapshot_service
from app.domains.market_data.history.benchmarks import DASHBOARD_BENCHMARKS
from app.domains.market_data.history.reader import local_history
from app.domains.market_data.history.tasks import schedule_refresh
from app.domains.portfolio.classification import is_cash_like
from app.domains.transactions.cost_basis.context import aware

_ALL_HISTORY_DAYS = 3650


def ensure_json_safe(value: Any) -> Any:
    """Convertit Decimal en nombre et remplace NaN et infinis par 0, récursivement."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, float):
        return 0.0 if math.isnan(value) or math.isinf(value) else value
    if isinstance(value, dict):
        return {key: ensure_json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [ensure_json_safe(item) for item in value]
    return value


async def require_owned_portfolio(db: AsyncSession, portfolio_id: UUID, user_id: UUID) -> None:
    """Lève une erreur 404 si le portefeuille n'appartient pas à l'utilisateur."""
    if not await repository.owns_portfolio(db, portfolio_id, user_id):
        raise NotFoundError("Portefeuille non trouvé")


def _sparkline(symbol: str, prices: list[float]) -> SparklineData:
    low, high = min(prices), max(prices)
    spread = high - low
    change = ((prices[-1] - prices[0]) / prices[0] * 100) if prices[0] > 0 else 0.0
    return SparklineData(
        symbol=symbol,
        prices=[(price - low) / spread if spread > 0 else 0.5 for price in prices],
        change_pct=round(change, 2),
    )


async def portfolio_sparklines(db: AsyncSession, portfolio_id: str, days: int) -> list[SparklineData]:
    """Mini-courbes des actifs détenus ; sans deux cours, le symbole est rafraîchi en tâche de fond."""
    held = await repository.held_symbols(db, portfolio_id)
    kinds = {symbol.upper(): kind.value for symbol, kind in held if not is_cash_like(symbol)}
    if not kinds:
        return []
    histories = await local_history(kinds, days, db)
    sparklines = []
    for symbol, kind in kinds.items():
        prices = histories[symbol].prices
        if len(prices) < 2:
            schedule_refresh(symbol, kind)
            continue
        sparklines.append(_sparkline(symbol, prices))
    return sparklines


async def _account_series(db: AsyncSession, user_id: UUID, days: int) -> list[dict[str, Any]]:
    period = days
    if days == 0:
        period = resolve_period_days(0, aware(await repository.first_transaction_date(db, user_id)))
    return await snapshot_service.build_portfolio_value_series(db, str(user_id), period)


async def historical_points(db: AsyncSession, user_id: UUID, days: int) -> list[HistoricalDataPoint]:
    """Courbe de valeur du compte ; `days=0` couvre tout l'historique."""
    series = await _account_series(db, user_id, days)
    for point in series:
        point["is_estimated"] = False
    return [HistoricalDataPoint(**point) for point in series]


async def benchmark_series(db: AsyncSession, user_id: UUID, days: int) -> list[BenchmarkSeries]:
    """Indices de référence et portefeuille, normalisés en base 100."""
    symbols = [symbol for _, symbol, _ in DASHBOARD_BENCHMARKS]
    histories = await local_history(symbols, days or _ALL_HISTORY_DAYS, db)
    result = []
    for name, symbol, _ in DASHBOARD_BENCHMARKS:
        history = histories[symbol]
        if len(history.prices) < 2:
            continue
        base = history.prices[0] or 1
        points = [
            BenchmarkDataPoint(date=day.strftime("%Y-%m-%d"), value=round(price / base * 100, 2))
            for day, price in zip(history.dates, history.prices, strict=True)
        ]
        result.append(BenchmarkSeries(name=name, symbol=symbol, data=points))
    series = await _account_series(db, user_id, days)
    if len(series) > 1:
        base = series[0].get("value", 1) or 1
        points = [BenchmarkDataPoint(date=p["full_date"][:10], value=round(p["value"] / base * 100, 2)) for p in series]
        result.append(BenchmarkSeries(name="Mon portefeuille", symbol="PORTFOLIO", data=points))
    return result
