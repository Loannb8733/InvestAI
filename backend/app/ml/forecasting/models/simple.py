from datetime import UTC, datetime, timedelta

import numpy as np

from app.ml.forecasting.confidence import fat_tail_z
from app.ml.forecasting.trend import compute_trend
from app.ml.forecasting.types import ForecastResult, rounded

LINEAR_WINDOW = 90
TREND_DAMPING = 0.9


def ou_reversion_speed(phi: float) -> float:
    """Vitesse de retour à la moyenne (Ornstein-Uhlenbeck) d'un coefficient AR(1) ; 0 près d'une racine unitaire."""
    if phi >= 0.98:
        return 0.0
    return float(-np.log(max(phi, 0.01)))


def ema(data: np.ndarray, span: int) -> np.ndarray:
    """Moyenne mobile exponentielle de période ``span``."""
    alpha = 2 / (span + 1)
    result = np.zeros(len(data))
    result[0] = data[0]
    for i in range(1, len(data)):
        result[i] = alpha * data[i] + (1 - alpha) * result[i - 1]
    return result


def _day(last: datetime, offset: int) -> str:
    return (last + timedelta(days=offset)).strftime("%Y-%m-%d")


def damped_steps(i: int, phi: float = TREND_DAMPING) -> float:
    """Nombre de pas de pente cumulés au pas ``i`` d'une tendance amortie : φ + φ² + … + φⁱ."""
    return phi * (1 - phi**i) / (1 - phi)


def ema_forecast(prices: list[float], dates: list[datetime], days_ahead: int) -> ForecastResult:
    """Pente des trois derniers points de l'EMA 7, corrigée de l'écart entre EMA 7 et EMA 21, prolongée depuis le
    dernier prix et amortie (φ = 0,9)."""
    arr = np.array(prices, dtype=float)
    ema7 = ema(arr, 7)
    ema21 = ema(arr, min(21, len(arr)))
    slope7 = (ema7[-1] - ema7[-3]) / 2 if len(ema7) >= 3 else 0.0
    if len(ema21) >= 1 and abs(ema21[-1]) > 1e-10:
        cross_gap = (ema7[-1] - ema21[-1]) / abs(ema21[-1])
        cross_bias = cross_gap * ema7[-1] * 0.1
    else:
        cross_bias = 0.0
    slope = slope7 + cross_bias
    residuals = arr[-min(30, len(arr)) :] - ema7[-min(30, len(ema7)) :]
    std_r = float(np.std(residuals)) if len(residuals) > 1 else abs(arr[-1]) * 0.02
    z = fat_tail_z(residuals)
    base = float(arr[-1])
    result_prices, result_low, result_high = [], [], []
    for i in range(1, days_ahead + 1):
        pred = max(0.0, float(base + slope * damped_steps(i)))
        ci = z * std_r * np.sqrt(i)
        result_prices.append(pred)
        result_low.append(max(0.0, pred - ci))
        result_high.append(pred + ci)
    dates_out = [_day(dates[-1], i) for i in range(1, days_ahead + 1)]
    trend = compute_trend(prices[-1], result_prices[-1], prices)
    return rounded(dates_out, result_prices, result_low, result_high, trend, "ema")


def _log_window(prices: list[float]) -> np.ndarray:
    window: np.ndarray = np.log(np.maximum(np.array(prices[-LINEAR_WINDOW:], dtype=float), 1e-10))
    return window


def _random_walk_band(y: np.ndarray) -> tuple[float, float]:
    returns = np.diff(y)
    step_std = float(np.std(returns)) if len(returns) > 1 else 0.02
    return step_std, fat_tail_z(returns)


def linear_forecast(prices: list[float], dates: list[datetime], days_ahead: int) -> ForecastResult:
    """Pente de la régression linéaire du logarithme des ``LINEAR_WINDOW`` derniers prix, prolongée depuis le
    dernier prix et amortie (φ = 0,9) ; intervalle aux queues épaisses qui s'élargit comme une marche aléatoire
    des rendements."""
    y = _log_window(prices)
    slope = float(np.polyfit(np.arange(len(y), dtype=float), y, 1)[0]) if len(y) >= 2 else 0.0
    step_std, z = _random_walk_band(y)
    result_prices, result_low, result_high = [], [], []
    for i in range(1, days_ahead + 1):
        pred_log = float(y[-1]) + slope * damped_steps(i)
        ci = z * step_std * np.sqrt(i)
        result_prices.append(max(0.0, float(np.exp(pred_log))))
        result_low.append(max(0.0, float(np.exp(pred_log - ci))))
        result_high.append(float(np.exp(pred_log + ci)))
    dates_out = [_day(dates[-1], i) for i in range(1, days_ahead + 1)]
    trend = compute_trend(prices[-1], result_prices[-1], prices)
    return rounded(dates_out, result_prices, result_low, result_high, trend, "linear")


def naive_forecast(prices: list[float], dates: list[datetime], days_ahead: int) -> ForecastResult:
    """Prévision naïve (marche aléatoire) : le dernier prix, avec l'intervalle d'une marche aléatoire des rendements
    logarithmiques ; la référence que les autres modèles doivent battre."""
    y = _log_window(prices)
    step_std, z = _random_walk_band(y)
    last = float(prices[-1])
    result_low = [max(0.0, last * float(np.exp(-z * step_std * np.sqrt(i)))) for i in range(1, days_ahead + 1)]
    result_high = [last * float(np.exp(z * step_std * np.sqrt(i))) for i in range(1, days_ahead + 1)]
    dates_out = [_day(dates[-1], i) for i in range(1, days_ahead + 1)]
    trend = compute_trend(prices[-1], last, prices)
    return rounded(dates_out, [last] * days_ahead, result_low, result_high, trend, "naive")


def _reversion_speed(log_prices: np.ndarray) -> float:
    if len(log_prices) < 10:
        return 0.05
    y = log_prices[1:]
    x = log_prices[:-1]
    x_mean = float(np.mean(x))
    y_mean = float(np.mean(y))
    cov_xy = float(np.mean((x - x_mean) * (y - y_mean)))
    var_x = float(np.var(x))
    return ou_reversion_speed(cov_xy / max(var_x, 1e-15))


def mean_reversion_forecast(prices: list[float], dates: list[datetime], days_ahead: int) -> ForecastResult:
    """Retour vers la moyenne (SMA 200 ou médiane) selon un processus d'Ornstein-Uhlenbeck sur le log des prix."""
    arr = np.array(prices, dtype=float)
    mu = float(np.mean(arr[-200:])) if len(arr) >= 200 else float(np.median(arr))
    log_prices = np.log(np.maximum(arr, 1e-10))
    log_returns = np.diff(log_prices)
    theta = _reversion_speed(log_prices)
    sigma = float(np.std(log_returns)) if len(log_returns) > 1 else 0.02
    current_price = float(arr[-1])
    result_prices, result_low, result_high = [], [], []
    for d in range(1, days_ahead + 1):
        t = float(d)
        log_mu = np.log(max(mu, 1e-10))
        log_current = np.log(max(current_price, 1e-10))
        log_expected = log_mu + (log_current - log_mu) * np.exp(-theta * t)
        log_var = (sigma**2 / (2 * theta)) * (1 - np.exp(-2 * theta * t)) if theta > 1e-10 else sigma**2 * t
        log_std = np.sqrt(max(log_var, 0))
        result_prices.append(max(0.0, float(np.exp(log_expected))))
        result_low.append(max(0.0, float(np.exp(log_expected - 1.96 * log_std))))
        result_high.append(float(np.exp(log_expected + 1.96 * log_std)))
    dates_out = [_day(dates[-1], d) for d in range(1, days_ahead + 1)]
    trend = compute_trend(prices[-1], result_prices[-1], prices)
    return rounded(dates_out, result_prices, result_low, result_high, trend, "mean_reversion")


def fallback_forecast(prices: list[float], days_ahead: int) -> ForecastResult:
    """Marche aléatoire à dérive moyenne, pour un historique de moins de cinq points ; vide sans historique."""
    if not prices:
        return ForecastResult([], [], [], [], "neutral", 0, "fallback")
    current = prices[-1]
    vol = np.std(prices) / np.mean(prices) if len(prices) > 1 else 0.03
    daily_vol = vol / np.sqrt(max(len(prices), 1))
    drift = 0.0
    if len(prices) >= 2 and prices[0] > 1e-10:
        drift = (prices[-1] / prices[0]) ** (1 / len(prices)) - 1
    now = datetime.now(UTC)
    result_dates, result_prices, result_low, result_high = [], [], [], []
    base = current
    for i in range(1, days_ahead + 1):
        result_dates.append((now + timedelta(days=i)).strftime("%Y-%m-%d"))
        pred = base * (1 + drift)
        ci = 1.96 * daily_vol * np.sqrt(i) * base
        result_prices.append(max(0.0, round(pred, 8)))
        result_low.append(max(0.0, round(pred - ci, 8)))
        result_high.append(round(pred + ci, 8))
        base = pred
    trend, strength = compute_trend(current, result_prices[-1], prices)
    return ForecastResult(result_dates, result_prices, result_low, result_high, trend, round(strength, 1), "fallback")
