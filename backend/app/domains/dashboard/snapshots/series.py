"""Série de valeur d'un compte, reconstruite depuis ses transactions et les cours historiques."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.dashboard.models import PortfolioSnapshot
from app.domains.dashboard.snapshots import repository
from app.domains.dashboard.snapshots.holdings import DailyHoldings, replay_daily_holdings
from app.domains.dashboard.snapshots.periods import data_point_interval, format_date_for_period
from app.domains.dashboard.snapshots.prices import PriceSeries, fetch_price_series
from app.domains.market_data.fx.cold_start import USD_EUR as COLD_START_USD_EUR
from app.domains.market_data.fx.spot import spot_rates
from app.domains.portfolio.classification import STABLECOIN_PEGS, STABLECOIN_SYMBOLS

logger = logging.getLogger(__name__)

_MAX_FETCH_DAYS = 1825
_MIN_FETCH_DAYS = 90
_FETCH_MARGIN_DAYS = 5


def value_point(moment: datetime, days: int, value: float, invested: float, net_capital: float) -> dict[str, Any]:
    """Un point de la série, montants arrondis au centime."""
    return {
        "date": format_date_for_period(moment, days),
        "full_date": moment.isoformat(),
        "value": round(value, 2),
        "invested": round(invested, 2),
        "net_capital": round(net_capital, 2),
        "gain_loss": round(value - net_capital, 2),
    }


def _snapshot_point(snapshot: PortfolioSnapshot, days: int) -> dict[str, Any]:
    point = value_point(
        snapshot.snapshot_date.replace(tzinfo=None),
        days,
        float(snapshot.total_value),
        float(snapshot.total_invested),
        float(snapshot.total_invested),
    )
    return {**point, "gain_loss": None}


async def _stablecoin_rate() -> float:
    try:
        return float(await spot_rates.get("USD", "EUR") or COLD_START_USD_EUR)
    except Exception:  # noqa: BLE001
        logger.warning("Taux USD→EUR indisponible — repli sur la constante de démarrage à froid")
        return float(COLD_START_USD_EUR)


def _held_symbols(daily: DailyHoldings) -> dict[str, str]:
    held: dict[str, str] = {}
    for holdings in daily.holdings.values():
        for symbol in holdings:
            if symbol in daily.asset_types:
                held.setdefault(symbol, daily.asset_types[symbol])
    return held


async def _stored_series_if_prices_missing(
    db: AsyncSession, user_id: str, days: int, today: datetime, symbols: dict[str, str], prices: PriceSeries
) -> list[dict[str, Any]] | None:
    quoted = {symbol for symbol in symbols if symbol not in STABLECOIN_SYMBOLS}
    priced = {symbol for symbol in quoted if prices.get(symbol)}
    if not quoted or len(priced) >= len(quoted) / 2:
        return None
    logger.warning(
        "Missing price data for %d/%d symbols, falling back to DB snapshots", len(quoted) - len(priced), len(quoted)
    )
    stored = await repository.global_snapshots_since(db, user_id, today - timedelta(days=days + _FETCH_MARGIN_DAYS))
    return [_snapshot_point(snapshot, days) for snapshot in stored] or None


@dataclass
class _Valuer:
    prices: PriceSeries
    stablecoin_rate: float
    last_known: dict[str, float] = field(default_factory=dict)

    def remember(self, day: str) -> None:
        for symbol, series in self.prices.items():
            if day in series:
                self.last_known[symbol] = series[day]

    def _closest(self, symbol: str, day: str) -> float | None:
        series = self.prices[symbol]
        available = sorted(series)
        for candidate in reversed(available):
            if candidate <= day:
                return series[candidate]
        return series[available[0]] if available else None

    def _unit_price(self, symbol: str, day: str) -> float | None:
        series = self.prices.get(symbol)
        if series is not None and day in series:
            return series[day]
        if symbol in self.last_known:
            return self.last_known[symbol]
        if symbol in STABLECOIN_SYMBOLS:
            return 1.0 if STABLECOIN_PEGS.get(symbol) == "EUR" else self.stablecoin_rate
        return self._closest(symbol, day) if series is not None else None

    def value(self, holdings: dict[str, float], day: str) -> float:
        total = 0.0
        for symbol, quantity in holdings.items():
            price = self._unit_price(symbol, day)
            if price is not None:
                self.last_known[symbol] = price
                total += quantity * price
        return total


def _points(daily: DailyHoldings, valuer: _Valuer, start: datetime, days: int) -> list[dict[str, Any]]:
    start_day = start.strftime("%Y-%m-%d")
    period = sorted(day for day in daily.holdings if day >= start_day)
    interval = data_point_interval(days)
    points = []
    for index, day in enumerate(period):
        if index % interval != 0 and index not in (0, len(period) - 1):
            valuer.remember(day)
            continue
        value = valuer.value(daily.holdings[day], day)
        moment = datetime.strptime(day, "%Y-%m-%d")
        points.append(value_point(moment, days, value, daily.invested.get(day, 0.0), daily.net_capital.get(day, 0.0)))
    return points


def _replay_start(transactions: Sequence[Any], today: datetime, period_start: datetime) -> datetime:
    first = transactions[0].executed_at or transactions[0].created_at or today
    earliest = min(first.replace(tzinfo=None), period_start)
    return earliest.replace(hour=0, minute=0, second=0, microsecond=0)


async def compute_value_series(db: AsyncSession, user_id: str, days: int) -> list[dict[str, Any]]:
    """Valeur du compte sur `days` jours ; sans cours pour la moitié des symboles, relit les instantanés stockés."""
    transactions = await repository.user_transactions(db, user_id)
    if not transactions:
        return []
    today = datetime.now(UTC)
    naive_today = today.replace(tzinfo=None)
    period_start = naive_today - timedelta(days=days)
    start = _replay_start(transactions, naive_today, period_start)
    daily = replay_daily_holdings(transactions, start, naive_today)
    symbols = _held_symbols(daily)
    if not symbols:
        return []
    fetch_days = min(max(days, (naive_today - start).days + _FETCH_MARGIN_DAYS, _MIN_FETCH_DAYS), _MAX_FETCH_DAYS)
    prices = await fetch_price_series(symbols, fetch_days, db)
    stablecoin_rate = await _stablecoin_rate()
    stored = await _stored_series_if_prices_missing(db, user_id, days, today, symbols, prices)
    if stored is not None:
        return stored
    return _points(daily, _Valuer(prices, stablecoin_rate), max(period_start, start), days)
