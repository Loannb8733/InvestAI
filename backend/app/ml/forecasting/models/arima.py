import logging
import warnings
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from app.ml.forecasting.trend import compute_trend
from app.ml.forecasting.types import ForecastResult, rounded

logger = logging.getLogger(__name__)

Fitted = tuple[np.ndarray, np.ndarray, tuple[int, int, int]]


def _grid_search(y: np.ndarray, days_ahead: int) -> Fitted:
    from statsmodels.tsa.arima.model import ARIMA

    best_aic = float("inf")
    best_order = (1, 1, 0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for p in range(0, 4):
            for q in range(0, 3):
                try:
                    res = ARIMA(y, order=(p, 1, q)).fit()
                except Exception:  # noqa: BLE001
                    continue
                if res.aic < best_aic:
                    best_aic = res.aic
                    best_order = (p, 1, q)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit = ARIMA(y, order=best_order).fit()
    fc_result = fit.get_forecast(steps=days_ahead)
    ci = fc_result.conf_int(alpha=0.05)
    ci_arr = ci.values if hasattr(ci, "values") else np.asarray(ci)
    return np.array(fc_result.predicted_mean), ci_arr, best_order


def _auto(y: np.ndarray, days_ahead: int) -> Fitted:
    from pmdarima import auto_arima

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model: Any = auto_arima(
            y,
            start_p=0,
            max_p=5,
            start_q=0,
            max_q=3,
            d=1,
            max_d=2,
            seasonal=False,
            stepwise=True,
            suppress_warnings=True,
            error_action="ignore",
        )
    fc, ci = model.predict(n_periods=days_ahead, return_conf_int=True, alpha=0.05)
    return fc, ci, model.order


def arima_forecast(prices: list[float], dates: list[datetime], days_ahead: int, auto_available: bool) -> ForecastResult:
    """ARIMA d'ordre choisi par auto_arima, sinon par la meilleure AIC d'une grille ; petits prix remis à l'échelle."""
    y = np.array(prices, dtype=float)
    scale = 1.0
    if np.mean(y) < 0.01:
        scale = 1.0 / np.mean(y)
        y = y * scale
    if auto_available:
        try:
            fc, ci, best_order = _auto(y, days_ahead)
        except Exception as e:  # noqa: BLE001
            logger.warning("auto_arima failed, falling back to grid: %s", e)
            fc, ci, best_order = _grid_search(y, days_ahead)
    else:
        fc, ci, best_order = _grid_search(y, days_ahead)
    result_prices = [max(0.0, float(v) / scale) for v in fc]
    return rounded(
        [(dates[-1] + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(1, days_ahead + 1)],
        result_prices,
        [max(0.0, float(ci[i, 0]) / scale) for i in range(days_ahead)],
        [float(ci[i, 1]) / scale for i in range(days_ahead)],
        compute_trend(prices[-1], result_prices[-1], prices),
        f"arima{best_order}",
    )
