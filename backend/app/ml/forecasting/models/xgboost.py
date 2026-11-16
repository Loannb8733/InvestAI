import logging
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from app.ml.forecasting.confidence import fat_tail_z
from app.ml.forecasting.features import FEATURE_NAMES, build_features, precompute_rsi
from app.ml.forecasting.trend import compute_trend
from app.ml.forecasting.types import ForecastResult, rounded

logger = logging.getLogger(__name__)

LOOKBACK = 7
DECAY = 0.95


def _aligned_volumes(volumes: list[float] | None, length: int) -> np.ndarray | None:
    if volumes and len(volumes) >= length:
        return np.array(volumes[-length:], dtype=float)
    if volumes and len(volumes) > 0:
        return np.concatenate([np.full(length - len(volumes), np.nan), np.array(volumes, dtype=float)])
    return None


def _aligned_btc(btc_prices: list[float] | None, length: int) -> np.ndarray | None:
    btc_arr = np.array(btc_prices, dtype=float) if btc_prices and len(btc_prices) >= length else None
    if btc_arr is not None and len(btc_arr) > length:
        btc_arr = btc_arr[-length:]
    return btc_arr


def _held_out_residuals(regressor: Any, params: dict[str, Any], x: np.ndarray, y: np.ndarray) -> np.ndarray:
    split_idx = max(int(len(x) * 0.8), 1)
    if split_idx >= len(x):
        return np.array([0.0])
    model_val = regressor(**params)
    model_val.fit(x[:split_idx], y[:split_idx])
    residuals: np.ndarray = y[split_idx:] - model_val.predict(x[split_idx:])
    return residuals


def _explanations(model: Any, last_features: np.ndarray) -> list[dict[str, Any]]:
    explanations: list[dict[str, Any]] = []
    try:
        import shap

        shap_values = shap.TreeExplainer(model).shap_values(last_features)
        abs_shap = np.abs(shap_values[0])
        for idx in np.argsort(abs_shap)[-3:][::-1]:
            name = FEATURE_NAMES[idx] if idx < len(FEATURE_NAMES) else f"feature_{idx}"
            val = float(shap_values[0][idx])
            explanations.append(
                {"feature_name": name, "importance": round(abs(val), 6), "direction": "hausse" if val > 0 else "baisse"}
            )
    except Exception as e:  # noqa: BLE001
        logger.debug("SHAP computation failed: %s", e)
    return explanations


def xgboost_forecast(
    prices: list[float],
    dates: list[datetime],
    days_ahead: int,
    params: dict[str, Any],
    volumes: list[float] | None = None,
    btc_prices: list[float] | None = None,
) -> ForecastResult:
    """XGBoost sur 27 variables, prédit pas à pas avec un amortissement vers le dernier prix réel."""
    from xgboost import XGBRegressor

    arr = np.array(prices, dtype=float)
    vol_arr = _aligned_volumes(volumes, len(prices))
    btc_arr = _aligned_btc(btc_prices, len(arr))
    rsi_array = precompute_rsi(arr, period=14)
    rows = [build_features(arr, i, vol_arr, btc_arr, rsi_array=rsi_array) for i in range(LOOKBACK + 14, len(arr))]
    x = np.array(rows)
    y = np.array([arr[i] for i in range(LOOKBACK + 14, len(arr))])
    base_params = {
        "n_estimators": params.get("n_estimators", 100),
        "max_depth": params.get("max_depth", 4),
        "learning_rate": params.get("learning_rate", 0.1),
        "subsample": params.get("subsample", 1.0),
        "colsample_bytree": params.get("colsample_bytree", 1.0),
        "random_state": 42,
        "verbosity": 0,
    }
    residuals = _held_out_residuals(XGBRegressor, base_params, x, y)
    model = XGBRegressor(**base_params)
    model.fit(x, y)
    extended = list(arr)
    last_real_price = float(arr[-1])
    result_prices = []
    for d in range(1, days_ahead + 1):
        feat = build_features(np.array(extended), len(extended), vol_arr, btc_arr)
        raw_pred = max(0.0, float(model.predict(np.array([feat]))[0]))
        pred = max(0.0, last_real_price + (raw_pred - last_real_price) * (DECAY**d))
        result_prices.append(pred)
        extended.append(pred)
    residual_std = float(np.std(residuals)) if len(residuals) > 1 else float(np.abs(residuals).mean())
    residual_std *= 1.2
    z = fat_tail_z(residuals)
    width = [z * residual_std * np.sqrt(i + 1) for i in range(len(result_prices))]
    last_features = np.array([build_features(np.array(extended[:-1]), len(extended) - 1, vol_arr, btc_arr)])
    return rounded(
        [(dates[-1] + timedelta(days=d)).strftime("%Y-%m-%d") for d in range(1, days_ahead + 1)],
        result_prices,
        [max(0.0, p - w) for p, w in zip(result_prices, width, strict=True)],
        [p + w for p, w in zip(result_prices, width, strict=True)],
        compute_trend(prices[-1], result_prices[-1], prices),
        "xgboost",
        _explanations(model, last_features),
    )
