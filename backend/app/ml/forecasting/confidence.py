from collections.abc import Sequence

import numpy as np

from app.ml import adaptive_thresholds as at
from app.ml.forecasting.types import Candidate
from app.ml.market_context import MarketContext

Z95 = 1.959963984540054
Interval = tuple[list[float], list[float]]


def fat_tail_z(residuals: Sequence[float] | np.ndarray, confidence: float = 0.95) -> float:
    """Valeur critique de Student dont les degrés de liberté suivent l'aplatissement des résidus, plafonnée à 5."""
    try:
        from scipy.stats import t as student_t

        arr = np.asarray(residuals, dtype=float)
        n = len(arr)
        if n < 10:
            return 1.96
        mean = float(np.mean(arr))
        std = float(np.std(arr, ddof=1))
        if std < 1e-15:
            return 1.96
        kurt = float(np.mean((arr - mean) ** 4) / std**4) - 3.0
        df = max(3.0, 6.0 / kurt + 4.0) if kurt > 0.5 else 30.0
        z = float(student_t.ppf(1 - (1 - confidence) / 2, df))
        return min(z, 5.0)
    except Exception:  # noqa: BLE001
        return 1.96


def ensemble_total_variance_ci(
    points: list[float],
    half_widths: list[float],
    weights: list[float],
    ensemble_mid: float,
) -> tuple[float, float]:
    """Intervalle à 95 % par la variance totale : variance propre de chaque modèle plus dispersion des prévisions."""
    within = 0.0
    between = 0.0
    for p, half, w in zip(points, half_widths, weights, strict=False):
        std = half / Z95 if half > 0 else 0.0
        within += w * std * std
        between += w * (p - ensemble_mid) * (p - ensemble_mid)
    total_std = float(np.sqrt(max(within + between, 0.0)))
    return ensemble_mid - Z95 * total_std, ensemble_mid + Z95 * total_std


def combine_native_ci(
    candidates: list[Candidate], weights: list[float], combined_prices: list[float], n_days: int
) -> Interval | None:
    """Intervalles propres des modèles combinés horizon par horizon ; None si un horizon n'en a aucun."""
    low = [0.0] * n_days
    high = [0.0] * n_days
    for i in range(n_days):
        pts: list[float] = []
        halves: list[float] = []
        ws: list[float] = []
        for (_name, res), w in zip(candidates, weights, strict=False):
            if i < len(res.prices) and i < len(res.confidence_low) and i < len(res.confidence_high):
                half = (res.confidence_high[i] - res.confidence_low[i]) / 2
                if half >= 0:
                    pts.append(res.prices[i])
                    halves.append(half)
                    ws.append(w)
        w_tot = sum(ws)
        if not ws or w_tot <= 0:
            return None
        ws = [x / w_tot for x in ws]
        lo, hi = ensemble_total_variance_ci(pts, halves, ws, combined_prices[i])
        low[i] = max(0.0, lo)
        high[i] = hi
    return low, high


def ewma_volatility_forecast(prices: list[float], days_ahead: int) -> dict[int, float]:
    """Volatilité EWMA (lambda 0,94) projetée à chaque horizon."""
    arr = np.array(prices, dtype=float)
    log_returns = np.diff(np.log(np.maximum(arr, 1e-10)))
    if len(log_returns) < 5:
        base_vol = 0.02
        return {d: base_vol * np.sqrt(d) for d in range(1, days_ahead + 1)}
    lam = 0.94
    ewma_var = float(np.var(log_returns))
    for r in log_returns:
        ewma_var = lam * ewma_var + (1 - lam) * r**2
    return {d: float(np.sqrt(ewma_var * d)) for d in range(1, days_ahead + 1)}


def _horizon_interval(
    arr: np.ndarray, d: int, pred_price: float, ewma_vols: dict[int, float], hist_daily_vol: float
) -> tuple[float, float]:
    n = len(arr)
    if n <= d + 5:
        vol = ewma_vols.get(d, 0.02 * np.sqrt(d))
        return pred_price * (1 - 1.96 * vol), pred_price * (1 + 1.96 * vol)
    n_day_returns = [arr[i + d] / arr[i] - 1 for i in range(n - d) if arr[i] > 1e-10]
    if len(n_day_returns) < 10:
        vol = ewma_vols.get(d, hist_daily_vol * np.sqrt(d))
        return pred_price * (1 - 1.96 * vol), pred_price * (1 + 1.96 * vol)
    q_low = float(np.percentile(n_day_returns, 2.5))
    q_high = float(np.percentile(n_day_returns, 97.5))
    ewma_vol = ewma_vols.get(d, hist_daily_vol * np.sqrt(d))
    hist_horizon_vol = hist_daily_vol * np.sqrt(d)
    vol_ratio = np.clip(ewma_vol / max(hist_horizon_vol, 1e-10), 0.5, 3.0)
    return pred_price * (1 + q_low * vol_ratio), pred_price * (1 + q_high * vol_ratio)


def empirical_quantile_ci(
    prices: list[float],
    current_price: float,
    days_ahead: int,
    predicted_prices: list[float],
    ewma_vols: dict[int, float],
) -> Interval:
    """Intervalle tiré de la distribution historique des rendements à N jours, mis à l'échelle de la volatilité EWMA."""
    arr = np.array(prices, dtype=float)
    log_returns = np.diff(np.log(np.maximum(arr, 1e-10)))
    hist_daily_vol = float(np.std(log_returns)) if len(log_returns) > 5 else 0.02
    ci_lows = []
    ci_highs = []
    for d in range(1, days_ahead + 1):
        pred_price = predicted_prices[d - 1] if d - 1 < len(predicted_prices) else current_price
        ci_low, ci_high = _horizon_interval(arr, d, pred_price, ewma_vols, hist_daily_vol)
        ci_lows.append(max(0.0, ci_low))
        ci_highs.append(ci_high)
    return ci_lows, ci_highs


def apply_floor(ctx: MarketContext, mids: list[float], interval: Interval) -> None:
    """Élargit sur place chaque demi-largeur trop étroite au plancher du type d'actif."""
    low, high = interval
    for i, mid in enumerate(mids):
        floor = at.ci_floor(ctx, i + 1)
        half_width = (high[i] - low[i]) / 2
        min_half = mid * floor
        if half_width < min_half:
            low[i] = max(0.0, mid - min_half)
            high[i] = mid + min_half


def calibrate(mids: list[float], interval: Interval, factor: float) -> None:
    """Multiplie sur place chaque demi-largeur par le facteur de couverture du backtest."""
    low, high = interval
    for i, mid in enumerate(mids):
        half_width = (high[i] - low[i]) / 2
        low[i] = max(0.0, mid - half_width * factor)
        high[i] = mid + half_width * factor
