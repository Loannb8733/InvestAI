"""Contexte de marché d'un actif calculé à partir de ses seuls cours, d'où dérivent tous les seuils adaptatifs."""

import math
from dataclasses import dataclass

import numpy as np

ANNUALIZATION = {"crypto": 365, "stock": 252, "etf": 252, "real_estate": 252}
CRYPTO_FALLBACKS = {"rsi": (22.0, 78.0), "momentum": (-15.0, 15.0), "volatility": (0.015, 0.06)}
OTHER_FALLBACKS = {"rsi": (28.0, 72.0), "momentum": (-8.0, 8.0), "volatility": (0.005, 0.025)}


def _safe_float(v: float) -> float:
    if v is None or math.isnan(v) or math.isinf(v):
        return 0.0
    return float(v)


def _sma(arr: np.ndarray, period: int) -> float:
    if len(arr) < period:
        return float(np.mean(arr)) if len(arr) > 0 else 0.0
    return float(np.mean(arr[-period:]))


def _rsi_single(prices: np.ndarray, period: int = 14) -> float:
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
    """Volatilités, position du prix, élan, forme de la distribution et percentiles historiques d'un actif.

    Volatilités et rendements en fraction décimale, RSI et Fear & Greed de 0 à 100, ``vol_percentile``
    de 0 à 100, ``position_in_52w_range`` de 0 à 1 ; ``daily_vol`` égale la volatilité sur 30 jours.
    """

    symbol: str
    asset_type: str
    realized_vol_7d: float
    realized_vol_30d: float
    realized_vol_90d: float
    vol_percentile: float
    price_vs_sma20: float
    price_vs_sma50: float
    price_vs_sma200: float
    position_in_52w_range: float
    momentum_7d: float
    momentum_30d: float
    rsi_14: float
    kurtosis: float
    skewness: float
    fear_greed: int | None
    daily_vol: float
    annualization_factor: int
    rsi_history_p10: float
    rsi_history_p90: float
    momentum_history_p10: float
    momentum_history_p90: float
    vol_history_p10: float
    vol_history_p90: float
    max_drawdown_30d: float


def _vol(returns: np.ndarray, period: int) -> float:
    if len(returns) < period:
        return _safe_float(float(np.std(returns, ddof=1))) if len(returns) > 1 else 0.0
    return _safe_float(float(np.std(returns[-period:], ddof=1)))


def _rolling_vols(returns: np.ndarray, n: int, samples: int) -> list[float]:
    if n < 60:
        return []
    step = max(1, (n - 30) // samples)
    windows = (returns[i - 30 : i] for i in range(30, n, step))
    return [float(np.std(w, ddof=1)) for w in windows if len(w) >= 10]


def _vol_percentile(returns: np.ndarray, n: int, vol_30d: float) -> float:
    rolling = _rolling_vols(returns, n, 50)
    if not rolling:
        return 50.0
    return float(np.searchsorted(np.sort(rolling), vol_30d) / len(rolling) * 100)


def _relative(current: float, reference: float) -> float:
    return (current - reference) / reference if reference != 0 else 0.0


def _range_position(arr: np.ndarray, current: float) -> float:
    lookback = min(len(arr), 365)
    high = float(np.max(arr[-lookback:]))
    low = float(np.min(arr[-lookback:]))
    return (current - low) / (high - low) if high > low else 0.5


def _momentum(arr: np.ndarray, days: int) -> float:
    if len(arr) > days and arr[-days - 1] != 0:
        return float((arr[-1] - arr[-days - 1]) / arr[-days - 1])
    return 0.0


def _shape(returns: np.ndarray) -> tuple[float, float]:
    ret_90 = returns[-90:] if len(returns) >= 90 else returns
    if len(ret_90) < 10:
        return 0.0, 0.0
    mean_r = float(np.mean(ret_90))
    std_r = float(np.std(ret_90, ddof=1))
    if std_r <= 0:
        return 0.0, 0.0
    centered = ret_90 - mean_r
    return float(np.mean(centered**4) / (std_r**4)) - 3.0, float(np.mean(centered**3) / (std_r**3))


def _percentiles(values: list[float], fallback: tuple[float, float]) -> tuple[float, float]:
    if len(values) < 5:
        return fallback
    return float(np.percentile(values, 10)), float(np.percentile(values, 90))


def _rsi_history(arr: np.ndarray) -> list[float]:
    n = len(arr)
    if n < 30:
        return []
    return [_rsi_single(arr[: i + 1], 14) for i in range(20, n, max(1, (n - 20) // 40))]


def _momentum_history(arr: np.ndarray) -> list[float]:
    n = len(arr)
    if n < 20:
        return []
    steps = range(14, n, max(1, (n - 14) // 40))
    return [float((arr[i] - arr[i - 14]) / arr[i - 14] * 100) for i in steps if arr[i - 14] != 0]


def _max_drawdown(arr: np.ndarray) -> float:
    if len(arr) < 2:
        return 0.0
    window = arr[-min(len(arr), 30) :]
    peak = np.maximum.accumulate(window)
    return float(np.min((window - peak) / np.where(peak > 0, peak, 1)))


def compute_market_context(
    prices: list[float],
    symbol: str,
    asset_type: str,
    fear_greed: int | None = None,
) -> MarketContext:
    """Contexte d'un actif d'après ses cours quotidiens, du plus ancien au plus récent (30 au moins conseillés)."""
    arr = np.asarray(prices, dtype=float)
    n = len(arr)
    fallbacks = CRYPTO_FALLBACKS if asset_type == "crypto" else OTHER_FALLBACKS
    returns = np.diff(arr) / np.where(arr[:-1] != 0, arr[:-1], 1e-10) if n >= 2 else np.array([0.0])
    vol_30d = _vol(returns, 30)
    current = float(arr[-1])
    kurt, skew = _shape(returns)
    rsi_p10, rsi_p90 = _percentiles(_rsi_history(arr), fallbacks["rsi"])
    mom_p10, mom_p90 = _percentiles(_momentum_history(arr), fallbacks["momentum"])
    vol_p10, vol_p90 = _percentiles(_rolling_vols(returns, n, 40), fallbacks["volatility"])
    return MarketContext(
        symbol=symbol,
        asset_type=asset_type,
        realized_vol_7d=_safe_float(_vol(returns, 7)),
        realized_vol_30d=_safe_float(vol_30d),
        realized_vol_90d=_safe_float(_vol(returns, 90)),
        vol_percentile=_safe_float(_vol_percentile(returns, n, vol_30d)),
        price_vs_sma20=_safe_float(_relative(current, _sma(arr, 20))),
        price_vs_sma50=_safe_float(_relative(current, _sma(arr, 50))),
        price_vs_sma200=_safe_float(_relative(current, _sma(arr, 200))),
        position_in_52w_range=_safe_float(np.clip(_range_position(arr, current), 0, 1)),
        momentum_7d=_safe_float(_momentum(arr, 7)),
        momentum_30d=_safe_float(_momentum(arr, 30)),
        rsi_14=_safe_float(_rsi_single(arr, 14)),
        kurtosis=_safe_float(kurt),
        skewness=_safe_float(skew),
        fear_greed=fear_greed,
        daily_vol=_safe_float(vol_30d),
        annualization_factor=ANNUALIZATION.get(asset_type, 365),
        rsi_history_p10=_safe_float(rsi_p10),
        rsi_history_p90=_safe_float(rsi_p90),
        momentum_history_p10=_safe_float(mom_p10),
        momentum_history_p90=_safe_float(mom_p90),
        vol_history_p10=_safe_float(vol_p10),
        vol_history_p90=_safe_float(vol_p90),
        max_drawdown_30d=_safe_float(_max_drawdown(arr)),
    )
