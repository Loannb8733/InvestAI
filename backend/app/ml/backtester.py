"""Walk-forward backtesting framework for ML models."""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class BacktestMetrics:
    """Comprehensive backtest metrics."""
    mape: float = 0.0
    rmse: float = 0.0
    mae: float = 0.0
    r2_score: float = 0.0
    hit_rate: float = 0.0  # % of correct direction predictions
    max_error: float = 0.0
    n_samples: int = 0


def compute_metrics(actual: List[float], predicted: List[float]) -> BacktestMetrics:
    """Compute comprehensive metrics from actual vs predicted values."""
    if not actual or not predicted or len(actual) != len(predicted):
        return BacktestMetrics()

    actual_arr = np.array(actual, dtype=float)
    pred_arr = np.array(predicted, dtype=float)
    n = len(actual_arr)

    # MAPE
    nonzero = actual_arr != 0
    if nonzero.any():
        mape = float(np.mean(np.abs((actual_arr[nonzero] - pred_arr[nonzero]) / actual_arr[nonzero])) * 100)
    else:
        mape = 0.0

    # RMSE
    rmse = float(np.sqrt(np.mean((actual_arr - pred_arr) ** 2)))

    # MAE
    mae = float(np.mean(np.abs(actual_arr - pred_arr)))

    # R²
    ss_res = np.sum((actual_arr - pred_arr) ** 2)
    ss_tot = np.sum((actual_arr - np.mean(actual_arr)) ** 2)
    r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

    # Hit rate (direction accuracy)
    if n >= 2:
        actual_dir = np.diff(actual_arr) > 0
        pred_dir = np.diff(pred_arr) > 0
        hit_rate = float(np.mean(actual_dir == pred_dir) * 100)
    else:
        hit_rate = 50.0

    # Max error
    max_error = float(np.max(np.abs(actual_arr - pred_arr)))

    return BacktestMetrics(
        mape=round(mape, 2),
        rmse=round(rmse, 6),
        mae=round(mae, 6),
        r2_score=round(r2, 4),
        hit_rate=round(hit_rate, 1),
        max_error=round(max_error, 6),
        n_samples=n,
    )


def walk_forward_backtest(
    forecaster,
    prices: List[float],
    dates: list,
    horizons: List[int] = None,
    model_name: str = "ensemble",
) -> BacktestMetrics:
    """Run walk-forward validation on a forecaster.

    Tests on multiple train/test splits to get robust metrics.
    """
    if horizons is None:
        horizons = [7, 14, 21]

    all_actual = []
    all_predicted = []

    n = len(prices)

    for horizon in horizons:
        split = n - horizon
        if split < max(30, n // 3):
            continue

        train_prices = prices[:split]
        train_dates = dates[:split] if dates else None

        try:
            if model_name == "ensemble":
                result = forecaster.ensemble_forecast(train_prices, train_dates, horizon)
            else:
                result = forecaster._run_model_by_name(
                    model_name, train_prices, train_dates, horizon
                )

            for i in range(min(len(result.prices), horizon)):
                if split + i < n:
                    all_actual.append(prices[split + i])
                    all_predicted.append(result.prices[i])

        except Exception as e:
            logger.debug("Backtest failed for horizon %d: %s", horizon, e)

    if not all_actual:
        return BacktestMetrics()

    return compute_metrics(all_actual, all_predicted)


def backtest_all_models(
    forecaster,
    prices: List[float],
    dates: list,
) -> Dict[str, BacktestMetrics]:
    """Backtest each model individually + the ensemble."""
    results = {}

    models = ["ensemble"]
    if forecaster._prophet_available and len(prices) >= 14:
        models.append("Prophet")
    if forecaster._arima_available and len(prices) >= 20:
        models.append("ARIMA")
    if forecaster._xgboost_available and len(prices) >= 30:
        models.append("XGBoost")
    if len(prices) >= 7:
        models.append("EMA")
    models.append("Linear")

    for model_name in models:
        try:
            metrics = walk_forward_backtest(
                forecaster, prices, dates, model_name=model_name
            )
            results[model_name] = metrics
        except Exception as e:
            logger.debug("Backtest failed for %s: %s", model_name, e)
            results[model_name] = BacktestMetrics()

    return results
