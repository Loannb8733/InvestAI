"""Pure risk/return math for analytics — no I/O, no class state.

Extracted from analytics_service so the numerical core (volatility, VaR/CVaR,
Sharpe/Sortino/Calmar, drawdown, XIRR) lives in one testable module. Every
function takes plain arrays/lists and returns numbers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Tuple

import numpy as np
from scipy import optimize as sp_optimize

from app.core.finance_constants import RISK_FREE_RATE
from app.core.finance_constants import annualization_days as _trading_days
from app.models.transaction import Transaction, TransactionType


def _compute_returns(prices: List[float]) -> np.ndarray:
    """Compute daily log returns from price series."""
    arr = np.array(prices, dtype=float)
    if len(arr) < 2:
        return np.array([])
    arr = arr[arr > 0]
    if len(arr) < 2:
        return np.array([])
    return np.diff(np.log(arr))


def _annualized_volatility(returns: np.ndarray, asset_type=None) -> float:
    """Annualized volatility (%) from daily log returns."""
    if len(returns) < 2:
        return 0.0
    td = _trading_days(asset_type) if asset_type else 365
    return float(np.std(returns, ddof=1) * np.sqrt(td) * 100)


def _downside_deviation(returns: np.ndarray, threshold: float = 0.0, asset_type=None) -> float:
    """Annualized downside deviation (%) — only negative returns count."""
    if len(returns) < 2:
        return 0.0
    neg = returns[returns < threshold] - threshold
    if len(neg) == 0:
        return 0.0
    td = _trading_days(asset_type) if asset_type else 365
    return float(np.sqrt(np.mean(neg**2)) * np.sqrt(td) * 100)


def _max_drawdown(prices: List[float]) -> float:
    """Max drawdown (%) from price series. Returns negative number."""
    if len(prices) < 2:
        return 0.0
    arr = np.array(prices, dtype=float)
    peak = np.maximum.accumulate(arr)
    dd = (arr - peak) / np.where(peak > 0, peak, 1)
    return float(np.min(dd) * 100)


def _daily_return_pct(prices: List[float]) -> float:
    """Latest daily return %."""
    if len(prices) < 2:
        return 0.0
    p0, p1 = prices[-2], prices[-1]
    if p0 <= 0:
        return 0.0
    return (p1 - p0) / p0 * 100


def _var_historical(returns: np.ndarray, confidence: float = 0.95) -> float:
    """Historical VaR as positive % (loss). E.g. 3.2 means 3.2% daily loss."""
    if len(returns) < 5:
        return 0.0
    q = np.percentile(returns, (1 - confidence) * 100)
    return float(-q * 100)


def _var_parametric(returns: np.ndarray, confidence: float = 0.95) -> float:
    """Parametric (Gaussian) VaR as positive % daily loss.

    Assumes returns ~ N(mu, sigma). VaR = -(mu + z * sigma).
    More stable than historical VaR with small samples.
    """
    if len(returns) < 5:
        return 0.0
    from scipy.stats import norm

    mu = float(np.mean(returns))
    sigma = float(np.std(returns, ddof=1))
    z = norm.ppf(1 - confidence)  # negative, e.g. -1.645 for 95%
    var = -(mu + z * sigma)
    return float(max(0.0, var * 100))


def _cvar_historical(returns: np.ndarray, confidence: float = 0.95) -> float:
    """Conditional VaR (Expected Shortfall) as positive %."""
    if len(returns) < 5:
        return 0.0
    q = np.percentile(returns, (1 - confidence) * 100)
    tail = returns[returns <= q]
    if len(tail) == 0:
        return float(-q * 100)
    return float(-np.mean(tail) * 100)


def _sharpe(return_pct: float, volatility: float, risk_free_rate: float = RISK_FREE_RATE) -> float:
    """Sharpe ratio. return_pct and volatility in % (annualized)."""
    if volatility == 0:
        return 0.0
    excess = return_pct - (risk_free_rate * 100)
    return round(excess / volatility, 2)


def _sortino(return_pct: float, downside_dev: float, risk_free_rate: float = RISK_FREE_RATE) -> float:
    """Sortino ratio."""
    if downside_dev == 0:
        return 0.0
    excess = return_pct - (risk_free_rate * 100)
    return round(excess / downside_dev, 2)


def _calmar(return_pct: float, max_dd: float) -> float:
    """Calmar ratio = annualized return / |max drawdown|."""
    if max_dd == 0:
        return 0.0
    return round(return_pct / abs(max_dd), 2)


def _annualized_return(returns: np.ndarray, asset_type=None) -> float:
    """Annualized return (%) from daily log returns.

    Converts continuous (log) return to discrete % for human-readable display:
    discrete_annual = (exp(mean_daily * td) - 1) * 100
    This avoids misleading values like -328% for assets that dropped ~96%.
    """
    if len(returns) < 2:
        return 0.0
    td = _trading_days(asset_type) if asset_type else 365
    mean_daily = float(np.mean(returns))
    return (np.exp(mean_daily * td) - 1) * 100


def _xirr(cashflows: List[Tuple[datetime, float]], guess: float = 0.1) -> Optional[float]:
    """
    Compute XIRR (Extended Internal Rate of Return) from a list of (date, amount).
    Convention used by all callers (compute_xirr, stress_test_service):
        negative amount = cash outflow (investment), positive = cash inflow
        (proceeds / income / current value).
    Returns annualized rate as decimal (0.12 = 12%).
    """
    if len(cashflows) < 2:
        return None

    dates = [cf[0] for cf in cashflows]
    amounts = [cf[1] for cf in cashflows]
    d0 = min(dates)

    def npv(rate: float) -> float:
        return sum(amt / (1.0 + rate) ** ((d - d0).days / 365.25) for d, amt in zip(dates, amounts))

    try:
        result = sp_optimize.brentq(npv, -0.99, 10.0, maxiter=200)
        return float(result)
    except (ValueError, RuntimeError, TypeError, OverflowError):
        try:
            result = sp_optimize.newton(npv, guess, maxiter=200)
            return float(result)
        except (ValueError, RuntimeError, TypeError, OverflowError):
            return None


# Transaction kinds that represent EXTERNAL cash entering/leaving the portfolio.
# Internal moves (TRANSFER_IN/OUT — auto-mirrored wallet hops) and crypto↔crypto
# swaps (CONVERSION_IN/OUT) are deliberately excluded: they are not external cash
# flows and would inject phantom -X/+X pairs that distort the rate (audit F-03).
_XIRR_INFLOW_TYPES = frozenset(
    {
        TransactionType.SELL,
        TransactionType.DIVIDEND,
        TransactionType.INTEREST,
        TransactionType.STAKING_REWARD,
        TransactionType.AIRDROP,
    }
)


def _build_xirr_cashflows(
    transactions: "List[Transaction]",
    eur_to_target: float = 1.0,
) -> Tuple[List[Tuple[datetime, float]], int]:
    """Build external cashflows for XIRR from a transaction list (pure, no I/O).

    Sign convention matches ``_xirr``: negative = cash out (investment), positive =
    cash in (proceeds / income). Each line is converted to the portfolio currency
    using its OWN ``conversion_rate`` (EUR per unit of the trade currency, captured
    at execution — audit F-02), then scaled by ``eur_to_target`` for non-EUR views.

    Scope (audit F-02/F-03/F-04):
      * BUY                        -> outflow (cash really spent)
      * SELL                       -> inflow  (cash really received)
      * DIVIDEND / INTEREST        -> inflow  (income from stocks / crowdfunding)
      * STAKING_REWARD / AIRDROP   -> inflow  (income, market value at receipt)
      * TRANSFER_IN / TRANSFER_OUT -> EXCLUDED (internal wallet moves)
      * CONVERSION_IN / CONVERSION_OUT / FEE / STAKING -> EXCLUDED (not external cash)

    Returns ``(cashflows, skipped)``; ``skipped`` counts rows with no execution date.
    """
    cashflows: List[Tuple[datetime, float]] = []
    skipped = 0
    for tx in transactions:
        dt = tx.executed_at
        if dt is None:
            skipped += 1
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        # Per-line historical conversion to EUR, then EUR -> target currency.
        fx = float(tx.conversion_rate) if tx.conversion_rate else 1.0
        to_target = fx * eur_to_target
        amount = float(tx.quantity) * float(tx.price) * to_target
        fee = float(tx.fee or 0) * to_target

        ttype = tx.transaction_type
        if ttype == TransactionType.BUY:
            cashflows.append((dt, -(amount + fee)))
        elif ttype in _XIRR_INFLOW_TYPES:
            # SELL nets the fee out of proceeds; pure income lines have fee 0.
            cashflows.append((dt, amount - fee if ttype == TransactionType.SELL else amount))
    return cashflows, skipped
