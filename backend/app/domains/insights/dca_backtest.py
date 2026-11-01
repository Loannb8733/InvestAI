"""Backtest d'un investissement mensuel fixe depuis une date donnée."""

from datetime import UTC, datetime
from typing import Any

from app.domains.market_data.history.reader import local_series
from app.domains.market_data.history.tasks import schedule_refresh

_MIN_PRICES = 30
_MAX_DAYS = 365 * 5


def _next_month(current: datetime) -> datetime:
    if current.month == 12:
        return datetime(current.year + 1, 1, 1)
    return datetime(current.year, current.month + 1, 1)


def _monthly_buys(
    start: datetime, now: datetime, month_prices: dict[str, float], monthly_amount: float
) -> tuple[list[dict[str, Any]], float, float]:
    buys: list[dict[str, Any]] = []
    invested = 0.0
    units = 0.0
    current = start
    while current <= now:
        key = current.strftime("%Y-%m")
        price = month_prices.get(key)
        if price and price > 0:
            bought = monthly_amount / price
            invested += monthly_amount
            units += bought
            buys.append(
                {
                    "month": key,
                    "price": round(price, 4),
                    "units": round(bought, 8),
                    "invested": round(invested, 2),
                    "value": round(units * price, 2),
                }
            )
        current = _next_month(current)
    return buys, invested, units


async def backtest_dca(
    symbol: str, asset_type: str, monthly_amount: float, start_year: int, start_month: int = 1
) -> dict[str, Any]:
    """Valeur d'un achat mensuel fixe, dès le premier mois coté ; un cas impossible rend une clé `error`."""
    now = datetime.now(UTC).replace(tzinfo=None)
    start = datetime(start_year, start_month, 1)
    total_months = (now.year - start.year) * 12 + (now.month - start.month)
    if total_months <= 0:
        return {"error": "La date de début doit être dans le passé"}
    history = await local_series(symbol, min(total_months * 31 + 30, _MAX_DAYS))
    if len(history.prices) < _MIN_PRICES:
        schedule_refresh(symbol, asset_type)
        return {"error": f"Pas assez d'historique pour {symbol} : chargement en cours, réessayez plus tard"}
    month_prices = {day.strftime("%Y-%m"): price for day, price in zip(history.dates, history.prices, strict=False)}
    buys, invested, units = _monthly_buys(start, now, month_prices, monthly_amount)
    if not buys:
        return {"error": "Aucune donnée de prix disponible pour cette période"}
    price = history.prices[-1]
    value = units * price
    gain = value - invested
    return {
        "symbol": symbol,
        "monthly_amount": monthly_amount,
        "start_date": buys[0]["month"],
        "nb_months": len(buys),
        "total_invested": round(invested, 2),
        "total_units": round(units, 8),
        "avg_buy_price": round(invested / units if units > 0 else 0, 4),
        "current_price": round(price, 4),
        "current_value": round(value, 2),
        "gain_loss": round(gain, 2),
        "gain_loss_pct": round(gain / invested * 100 if invested > 0 else 0, 2),
        "monthly_history": buys,
    }
