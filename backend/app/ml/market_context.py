"""MarketContext — data-driven snapshot of current market conditions.

Computes all market metrics from raw price data so that downstream
modules (regime detector, forecaster, prediction service, etc.) can
derive thresholds adaptively instead of using hardcoded constants.
"""

import logging
import math
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Annualization factors by asset type
_ANNUALIZATION = {
    "crypto": 365,
    "stock": 252,
    "etf": 252,
    "real_estate": 252,
}


def _safe_float(v: float) -> float:
    """Return 0.0 for nan/inf."""
    if v is None or math.isnan(v) or math.isinf(v):
        return 0.0
    return float(v)


def _sma(arr: np.ndarray, period: int) -> float:
    """Simple moving average of last *period* values."""
    if len(arr) < period:
        return float(np.mean(arr)) if len(arr) > 0 else 0.0
    return float(np.mean(arr[-period:]))


def _rsi_single(prices: np.ndarray, period: int = 14) -> float:
    """Compute RSI from a price array. Returns 50 on insufficient data."""
    if len(prices) < period + 1:
        return 50.0
    deltas = np.diff(prices[-(period + 1) :])
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = float(np.mean(gains))
    avg_loss = float(np.mean(losses))
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return float(100.0 - 100.0 / (1.0 + rs))


@dataclass
class MarketContext:
    """Data-driven snapshot of current market conditions for one asset.

    All fields are computed from raw price data.  Downstream modules use
    this instead of hardcoded magic numbers so that thresholds adapt
    automatically to each asset and market condition.
    """

    # Identity
    symbol: str
    asset_type: str  # "crypto", "stock", "etf", "real_estate"

    # ── Volatility profile ──────────────────────────────────
    realized_vol_7d: float  # std of 7-day daily returns (decimal, e.g. 0.03 = 3%)
    realized_vol_30d: float
    realized_vol_90d: float
    vol_percentile: float  # where 30d vol sits in its 1yr distribution [0-100]

    # ── Price position ──────────────────────────────────────
    price_vs_sma20: float  # (price - sma20) / sma20  (decimal)
    price_vs_sma50: float
    price_vs_sma200: float
    position_in_52w_range: float  # (price - 52w_low) / (52w_high - 52w_low) [0-1]

    # ── Momentum ────────────────────────────────────────────
    momentum_7d: float  # 7-day return (decimal)
    momentum_30d: float
    rsi_14: float  # RSI 14 (0-100)

    # ── Distribution shape ──────────────────────────────────
    kurtosis: float  # excess kurtosis of 90d returns (0 = normal)
    skewness: float

    # ── External ────────────────────────────────────────────
    fear_greed: Optional[int]  # 0-100, None if unavailable

    # ── Derived convenience ─────────────────────────────────
    daily_vol: float  # = realized_vol_30d
    annualization_factor: int  # 252 or 365

    # ── Historical indicator percentiles (for adaptive thresholds) ──
    rsi_history_p10: float  # 10th percentile of RSI over history
    rsi_history_p90: float  # 90th percentile of RSI over history
    momentum_history_p10: float  # 10th percentile of 14d momentum
    momentum_history_p90: float
    vol_history_p10: float  # 10th percentile of 30d realized vol
    vol_history_p90: float

    # ── Risk ────────────────────────────────────────────────
    max_drawdown_30d: float  # max drawdown in last 30 days (negative decimal)


def compute_market_context(
    prices: List[float],
    symbol: str,
    asset_type: str,
    fear_greed: Optional[int] = None,
) -> MarketContext:
    """Compute a MarketContext from raw price history.

    Parameters
    ----------
    prices : list of float
        Daily closing prices, oldest first.  At least 30 required.
    symbol : str
        Ticker symbol (e.g. "BTC", "AAPL").
    asset_type : str
        One of "crypto", "stock", "etf", "real_estate".
    fear_greed : int or None
        Current Fear & Greed Index (0-100), if available.

    Returns
    -------
    MarketContext
    """
    arr = np.asarray(prices, dtype=float)
    n = len(arr)
    ann = _ANNUALIZATION.get(asset_type, 365)

    # ── Daily returns ───────────────────────────────────────
    if n >= 2:
        returns = np.diff(arr) / np.where(arr[:-1] != 0, arr[:-1], 1e-10)
    else:
        returns = np.array([0.0])

    # ── Volatility ──────────────────────────────────────────
    def _vol(period: int) -> float:
        if len(returns) < period:
            return _safe_float(float(np.std(returns, ddof=1))) if len(returns) > 1 else 0.0
        return _safe_float(float(np.std(returns[-period:], ddof=1)))

    vol_7d = _vol(7)
    vol_30d = _vol(30)
    vol_90d = _vol(90)

    # Vol percentile: where current 30d vol sits in rolling 30d windows over 1yr
    if n >= 60:
        rolling_vols = []
        step = max(1, (n - 30) // 50)  # ~50 samples for efficiency
        for i in range(30, n, step):
            window_ret = returns[i - 30 : i]
            if len(window_ret) >= 10:
                rolling_vols.append(float(np.std(window_ret, ddof=1)))
        if rolling_vols:
            vol_pct = float(np.searchsorted(np.sort(rolling_vols), vol_30d) / len(rolling_vols) * 100)
        else:
            vol_pct = 50.0
    else:
        vol_pct = 50.0

    # ── Price position vs MAs ───────────────────────────────
    current_price = float(arr[-1])

    sma20 = _sma(arr, 20)
    sma50 = _sma(arr, 50)
    sma200 = _sma(arr, 200)

    vs_sma20 = (current_price - sma20) / sma20 if sma20 != 0 else 0.0
    vs_sma50 = (current_price - sma50) / sma50 if sma50 != 0 else 0.0
    vs_sma200 = (current_price - sma200) / sma200 if sma200 != 0 else 0.0

    # Position in 52-week (or available) range
    lookback = min(n, 365)
    high_52w = float(np.max(arr[-lookback:]))
    low_52w = float(np.min(arr[-lookback:]))
    if high_52w > low_52w:
        pos_52w = (current_price - low_52w) / (high_52w - low_52w)
    else:
        pos_52w = 0.5

    # ── Momentum ────────────────────────────────────────────
    def _momentum(days: int) -> float:
        if n > days and arr[-days - 1] != 0:
            return float((arr[-1] - arr[-days - 1]) / arr[-days - 1])
        return 0.0

    mom_7d = _momentum(7)
    mom_30d = _momentum(30)

    rsi_14 = _rsi_single(arr, 14)

    # ── Distribution shape ──────────────────────────────────
    ret_90 = returns[-90:] if len(returns) >= 90 else returns
    if len(ret_90) >= 10:
        mean_r = float(np.mean(ret_90))
        std_r = float(np.std(ret_90, ddof=1))
        if std_r > 0:
            centered = ret_90 - mean_r
            kurt = float(np.mean(centered**4) / (std_r**4)) - 3.0
            skew = float(np.mean(centered**3) / (std_r**3))
        else:
            kurt, skew = 0.0, 0.0
    else:
        kurt, skew = 0.0, 0.0

    # ── Historical RSI percentiles ──────────────────────────
    # Compute RSI at multiple points in history, then take p10/p90
    rsi_values = []
    if n >= 30:
        rsi_step = max(1, (n - 20) // 40)  # ~40 samples
        for i in range(20, n, rsi_step):
            rsi_values.append(_rsi_single(arr[: i + 1], 14))

    if len(rsi_values) >= 5:
        rsi_p10 = float(np.percentile(rsi_values, 10))
        rsi_p90 = float(np.percentile(rsi_values, 90))
    else:
        # Fallback: wider thresholds for crypto, tighter for stocks
        if asset_type == "crypto":
            rsi_p10, rsi_p90 = 22.0, 78.0
        else:
            rsi_p10, rsi_p90 = 28.0, 72.0

    # ── Historical momentum percentiles ─────────────────────
    mom_values = []
    if n >= 20:
        mom_step = max(1, (n - 14) // 40)
        for i in range(14, n, mom_step):
            if arr[i - 14] != 0:
                mom_values.append(float((arr[i] - arr[i - 14]) / arr[i - 14] * 100))

    if len(mom_values) >= 5:
        mom_p10 = float(np.percentile(mom_values, 10))
        mom_p90 = float(np.percentile(mom_values, 90))
    else:
        if asset_type == "crypto":
            mom_p10, mom_p90 = -15.0, 15.0
        else:
            mom_p10, mom_p90 = -8.0, 8.0

    # ── Historical volatility percentiles ───────────────────
    vol_values = []
    if n >= 60:
        vol_step = max(1, (n - 30) // 40)
        for i in range(30, n, vol_step):
            w = returns[i - 30 : i]
            if len(w) >= 10:
                vol_values.append(float(np.std(w, ddof=1)))

    if len(vol_values) >= 5:
        vol_p10 = float(np.percentile(vol_values, 10))
        vol_p90 = float(np.percentile(vol_values, 90))
    else:
        if asset_type == "crypto":
            vol_p10, vol_p90 = 0.015, 0.06
        else:
            vol_p10, vol_p90 = 0.005, 0.025

    # ── Max drawdown (30d) ──────────────────────────────────
    if n >= 2:
        lookback_dd = min(n, 30)
        window = arr[-lookback_dd:]
        peak = np.maximum.accumulate(window)
        dd = (window - peak) / np.where(peak > 0, peak, 1)
        max_dd_30d = float(np.min(dd))
    else:
        max_dd_30d = 0.0

    return MarketContext(
        symbol=symbol,
        asset_type=asset_type,
        realized_vol_7d=_safe_float(vol_7d),
        realized_vol_30d=_safe_float(vol_30d),
        realized_vol_90d=_safe_float(vol_90d),
        vol_percentile=_safe_float(vol_pct),
        price_vs_sma20=_safe_float(vs_sma20),
        price_vs_sma50=_safe_float(vs_sma50),
        price_vs_sma200=_safe_float(vs_sma200),
        position_in_52w_range=_safe_float(np.clip(pos_52w, 0, 1)),
        momentum_7d=_safe_float(mom_7d),
        momentum_30d=_safe_float(mom_30d),
        rsi_14=_safe_float(rsi_14),
        kurtosis=_safe_float(kurt),
        skewness=_safe_float(skew),
        fear_greed=fear_greed,
        daily_vol=_safe_float(vol_30d),
        annualization_factor=ann,
        rsi_history_p10=_safe_float(rsi_p10),
        rsi_history_p90=_safe_float(rsi_p90),
        momentum_history_p10=_safe_float(mom_p10),
        momentum_history_p90=_safe_float(mom_p90),
        vol_history_p10=_safe_float(vol_p10),
        vol_history_p90=_safe_float(vol_p90),
        max_drawdown_30d=_safe_float(max_dd_30d),
    )
