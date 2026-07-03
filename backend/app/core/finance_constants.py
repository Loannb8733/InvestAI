"""Finance constants shared across services.

Kept in the low-level ``core`` layer so services (price, snapshot, metrics) can
import it without creating cycles.
"""

from decimal import Decimal

# Last-resort USD->EUR rate, used ONLY when the live forex API, its Redis cache,
# and the last-known value are all unavailable (cold start). Every real code path
# prefers a live or last-known rate; this constant merely prevents a hard failure
# and is always surfaced to the UI as a stale/guessed rate — never as a quote.
COLD_START_USD_EUR: Decimal = Decimal("0.92")

# Annualized risk-free rate (EUR, decimal). Single source of truth for Sharpe /
# Sortino / Jensen's-alpha excess-return calculations.
RISK_FREE_RATE: float = 0.035  # ~3.5% — approximate EUR risk-free

# Annualization factors for scaling daily volatility/returns to a yearly figure.
TRADING_DAYS_PER_YEAR: int = 252  # stocks / ETFs — market days, weekends excluded
CALENDAR_DAYS_PER_YEAR: int = 365  # crypto / calendar-daily portfolio series


def annualization_days(asset_type) -> int:
    """Annualization factor by asset type: 252 for stocks/ETF (trading days),
    365 for crypto and everything else (calendar days). Accepts a str or an
    enum-like with a ``.value``."""
    if isinstance(asset_type, str):
        at = asset_type.lower()
    else:
        at = asset_type.value.lower() if hasattr(asset_type, "value") else str(asset_type).lower()
    return TRADING_DAYS_PER_YEAR if at in ("stock", "etf") else CALENDAR_DAYS_PER_YEAR


def annualized_return_pct(
    initial: float,
    final: float,
    years: float,
    *,
    floor: float = -99.0,
    ceil: float = 999.0,
) -> float:
    """Compound annual growth rate as a percentage, clamped to ``[floor, ceil]``.

    Single source of truth for the ``(final / initial) ** (1 / years) - 1``
    annualisation used by the dashboard ROI and per-asset annualised return.
    Returns ``0.0`` for non-positive inputs. Callers pass their own clamp bounds
    so existing display behaviour is preserved exactly (the dashboard historically
    clamps to ``[-95, 1000]``, per-asset returns to ``[-99, 999]``).
    """
    if initial <= 0 or final <= 0 or years <= 0:
        return 0.0
    raw = (pow(final / initial, 1.0 / years) - 1.0) * 100.0
    return max(floor, min(raw, ceil))
