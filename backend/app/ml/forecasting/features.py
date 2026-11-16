import numpy as np

FEATURE_NAMES = (
    "ret_1d",
    "ret_2d",
    "ret_3d",
    "ret_4d",
    "ret_5d",
    "ret_6d",
    "ret_7d",
    "volatility_7d",
    "rsi_14",
    "price_sma20_ratio",
    "momentum_3d",
    "momentum_7d",
    "momentum_14d",
    "volatility_14d",
    "price_sma7_ratio",
    "high_low_range_7d",
    "mean_return_7d",
    "volume_change_1d",
    "volume_sma7_ratio",
    "volume_price_divergence",
    "btc_return_1d",
    "btc_return_7d",
    "bb_position",
    "vol_ratio_7_30",
    "distance_sma200",
    "day_of_week_sin",
    "day_of_week_cos",
)
NAN = float("nan")


def precompute_rsi(prices: np.ndarray, period: int = 14) -> np.ndarray:
    """RSI de Wilder à chaque indice en un passage ; 50 tant que l'historique est trop court."""
    n = len(prices)
    rsi = np.full(n, 50.0)
    if n < period + 2:
        return rsi
    deltas = np.diff(prices)
    gains = np.maximum(deltas, 0.0)
    losses = np.maximum(-deltas, 0.0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    for k in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[k]) / period
        avg_loss = (avg_loss * (period - 1) + losses[k]) / period
        rs = avg_gain / max(avg_loss, 1e-10)
        rsi[k + 1] = 100 - 100 / (1 + rs)
    return rsi


def _returns(prices: np.ndarray, idx: int, count: int) -> list[float]:
    return [(prices[idx - i] - prices[idx - i - 1]) / max(prices[idx - i - 1], 1e-10) for i in range(1, count)]


def _lagged_returns(prices: np.ndarray, idx: int) -> list[float]:
    return [
        (prices[idx - lag] - prices[idx - lag - 1]) / max(prices[idx - lag - 1], 1e-10) if idx - lag >= 1 else 0.0
        for lag in range(1, 8)
    ]


def _inline_rsi(prices: np.ndarray, idx: int) -> float:
    period = 14
    all_deltas = [prices[j] - prices[j - 1] for j in range(1, idx)]
    if len(all_deltas) < period:
        return 50.0
    all_gains = [max(d, 0) for d in all_deltas]
    all_losses = [-min(d, 0) for d in all_deltas]
    avg_gain = sum(all_gains[:period]) / period
    avg_loss = sum(all_losses[:period]) / period
    for k in range(period, len(all_deltas)):
        avg_gain = (avg_gain * (period - 1) + all_gains[k]) / period
        avg_loss = (avg_loss * (period - 1) + all_losses[k]) / period
    rs = avg_gain / max(avg_loss, 1e-10)
    return float(100 - 100 / (1 + rs))


def _rsi_feature(prices: np.ndarray, idx: int, rsi_array: np.ndarray | None) -> float:
    if rsi_array is not None and idx >= 1 and idx - 1 < len(rsi_array):
        return float(rsi_array[idx - 1])
    if idx >= 15:
        return _inline_rsi(prices, idx)
    return 50.0


def _trend_features(prices: np.ndarray, idx: int) -> list[float]:
    feats = [prices[idx - 1] / max(float(np.mean(prices[idx - 20 : idx])), 1e-10) if idx >= 20 else 1.0]
    for period in (3, 7, 14):
        if idx >= period + 1:
            feats.append((prices[idx - 1] - prices[idx - period - 1]) / max(prices[idx - period - 1], 1e-10))
        else:
            feats.append(0.0)
    feats.append(float(np.std(_returns(prices, idx, min(15, idx)))) if idx >= 15 else 0.0)
    return feats


def _week_features(prices: np.ndarray, idx: int) -> list[float]:
    if idx < 8:
        return [1.0, 0.0, 0.0]
    window = prices[idx - 7 : idx]
    high = float(np.max(window))
    low = float(np.min(window))
    return [
        prices[idx - 1] / max(float(np.mean(prices[idx - 7 : idx])), 1e-10),
        (high - low) / max(low, 1e-10),
        float(np.mean(_returns(prices, idx, 8))),
    ]


def _volume_features(prices: np.ndarray, idx: int, volumes: np.ndarray | None) -> list[float]:
    if volumes is None or idx < 2 or idx - 1 >= len(volumes):
        return [NAN, NAN, NAN]
    prev_vol = max(volumes[idx - 2], 1e-10)
    feats = [(volumes[idx - 1] - prev_vol) / prev_vol]
    if idx >= 8:
        vol_window = volumes[max(0, idx - 7) : idx]
        vol_sma = float(np.mean(vol_window)) if vol_window else 1e-10
        feats.append(volumes[idx - 1] / max(vol_sma, 1e-10))
    else:
        feats.append(1.0)
    if prices[idx - 2] > 1e-10 and volumes[idx - 2] > 1e-10:
        price_return = (prices[idx - 1] - prices[idx - 2]) / prices[idx - 2]
        volume_return = (volumes[idx - 1] - volumes[idx - 2]) / volumes[idx - 2]
        feats.append(float(price_return - volume_return))
    else:
        feats.append(0.0)
    return feats


def _btc_features(idx: int, btc_prices: np.ndarray | None) -> list[float]:
    if btc_prices is None or idx < 2 or idx - 1 >= len(btc_prices):
        return [0.0, 0.0]
    day = (btc_prices[idx - 1] - btc_prices[idx - 2]) / max(btc_prices[idx - 2], 1e-10)
    if idx >= 8 and idx - 7 < len(btc_prices):
        return [day, (btc_prices[idx - 1] - btc_prices[idx - 8]) / max(btc_prices[idx - 8], 1e-10)]
    return [day, 0.0]


def _band_position(prices: np.ndarray, idx: int) -> float:
    if idx < 21:
        return 0.5
    window_20 = prices[idx - 20 : idx]
    sma_20 = float(np.mean(window_20))
    std_20 = float(np.std(window_20))
    upper = sma_20 + 2 * std_20
    lower = sma_20 - 2 * std_20
    band_width = upper - lower
    return float((prices[idx - 1] - lower) / band_width) if band_width > 1e-10 else 0.5


def _regime_features(prices: np.ndarray, idx: int) -> list[float]:
    if idx >= 31:
        vol_7 = float(np.std(_returns(prices, idx, 8)))
        vol_30 = float(np.std(_returns(prices, idx, 31)))
        ratio = vol_7 / max(vol_30, 1e-10)
    else:
        ratio = 1.0
    if idx >= 201:
        sma_200 = float(np.mean(prices[idx - 200 : idx]))
        distance = (prices[idx - 1] - sma_200) / max(sma_200, 1e-10)
    else:
        distance = 0.0
    day_idx = idx % 7
    return [ratio, distance, float(np.sin(2 * np.pi * day_idx / 7)), float(np.cos(2 * np.pi * day_idx / 7))]


def build_features(
    prices: np.ndarray,
    idx: int,
    volumes: np.ndarray | None = None,
    btc_prices: np.ndarray | None = None,
    rsi_array: np.ndarray | None = None,
) -> list[float]:
    """Les 27 variables d'XGBoost à l'indice ``idx``, calculées sur les prix strictement antérieurs."""
    return [
        *_lagged_returns(prices, idx),
        float(np.std(_returns(prices, idx, 8))) if idx >= 8 else 0.0,
        _rsi_feature(prices, idx, rsi_array),
        *_trend_features(prices, idx),
        *_week_features(prices, idx),
        *_volume_features(prices, idx, volumes),
        *_btc_features(idx, btc_prices),
        _band_position(prices, idx),
        *_regime_features(prices, idx),
    ]
