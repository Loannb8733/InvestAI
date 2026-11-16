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
FIRST_ROW = LOOKBACK + 14
DECAY = 0.8
CLIP_SIGMAS = 2.0
HELD_OUT = 0.2


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


def _extended(series: np.ndarray | None, days: int, value: float | None = None) -> np.ndarray | None:
    """Série prolongée sur l'horizon par une valeur constante : moyenne des 7 derniers points par défaut."""
    if series is None:
        return None
    tail = series[~np.isnan(series)][-7:]
    fill = value if value is not None else (float(np.mean(tail)) if len(tail) else np.nan)
    return np.concatenate([series, np.full(days, fill)])


def _log_returns(arr: np.ndarray) -> np.ndarray:
    safe = np.maximum(arr, 1e-10)
    returns: np.ndarray = np.diff(np.log(safe))
    return returns


def _base_params(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "n_estimators": params.get("n_estimators", 100),
        "max_depth": params.get("max_depth", 4),
        "learning_rate": params.get("learning_rate", 0.1),
        "subsample": params.get("subsample", 1.0),
        "colsample_bytree": params.get("colsample_bytree", 1.0),
        "random_state": 42,
        "verbosity": 0,
    }


def _training_set(
    arr: np.ndarray, vol_arr: np.ndarray | None, btc_arr: np.ndarray | None
) -> tuple[np.ndarray, np.ndarray]:
    rsi_array = precompute_rsi(arr, period=14)
    rows = [build_features(arr, i, vol_arr, btc_arr, rsi_array=rsi_array) for i in range(FIRST_ROW, len(arr))]
    returns = _log_returns(arr)
    return np.array(rows), np.array([returns[i - 1] for i in range(FIRST_ROW, len(arr))])


def _held_out_residuals(regressor: Any, params: dict[str, Any], x: np.ndarray, y: np.ndarray) -> np.ndarray:
    split_idx = max(int(len(x) * (1 - HELD_OUT)), 1)
    if split_idx >= len(x):
        return np.array([float(np.std(y))]) if len(y) else np.array([0.0])
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


def predicted_path(
    model: Any,
    arr: np.ndarray,
    days_ahead: int,
    vol_arr: np.ndarray | None,
    btc_arr: np.ndarray | None,
    limit: float,
) -> tuple[list[float], np.ndarray]:
    """Prix prévus pas à pas : rendement logarithmique prédit, borné à ``limit``, amorti de ``DECAY`` par jour, puis
    composé depuis le dernier prix réel. Rend aussi les variables du dernier pas."""
    n = len(arr)
    future_vol = _extended(vol_arr, days_ahead)
    future_btc = _extended(btc_arr, days_ahead, float(btc_arr[-1]) if btc_arr is not None else None)
    extended = list(arr)
    feat = np.array(build_features(np.array(extended), n, future_vol, future_btc))
    for d in range(1, days_ahead + 1):
        feat = np.array(build_features(np.array(extended), len(extended), future_vol, future_btc))
        step = float(np.clip(model.predict(np.array([feat]))[0], -limit, limit)) * DECAY**d
        extended.append(extended[-1] * float(np.exp(step)))
    return [max(0.0, p) for p in extended[n:]], feat


def forecast_prices(arr: np.ndarray, days_ahead: int, params: dict[str, Any]) -> list[float]:
    """Trajectoire prévue sans volumes ni cours du BTC, pour le réglage des hyperparamètres."""
    from xgboost import XGBRegressor

    x, y = _training_set(arr, None, None)
    model = XGBRegressor(**_base_params(params))
    model.fit(x, y)
    return predicted_path(model, arr, days_ahead, None, None, CLIP_SIGMAS * float(np.std(y)))[0]


def xgboost_forecast(
    prices: list[float],
    dates: list[datetime],
    days_ahead: int,
    params: dict[str, Any],
    volumes: list[float] | None = None,
    btc_prices: list[float] | None = None,
) -> ForecastResult:
    """XGBoost sur 27 variables, entraîné à prédire le rendement logarithmique du lendemain ; la trajectoire compose
    les rendements prédits (bornés à deux écarts-types, amortis vers zéro) depuis le dernier prix réel, et
    l'intervalle suit l'erreur hors échantillon des rendements comme une marche aléatoire."""
    from xgboost import XGBRegressor

    arr = np.array(prices, dtype=float)
    vol_arr = _aligned_volumes(volumes, len(prices))
    btc_arr = _aligned_btc(btc_prices, len(arr))
    x, y = _training_set(arr, vol_arr, btc_arr)
    base_params = _base_params(params)
    residuals = _held_out_residuals(XGBRegressor, base_params, x, y)
    model = XGBRegressor(**base_params)
    model.fit(x, y)
    result_prices, last_features = predicted_path(
        model, arr, days_ahead, vol_arr, btc_arr, CLIP_SIGMAS * float(np.std(y))
    )
    step_std = float(np.std(residuals)) if len(residuals) > 1 else float(np.abs(residuals).mean())
    z = fat_tail_z(residuals)
    width = [z * step_std * np.sqrt(i + 1) for i in range(len(result_prices))]
    return rounded(
        [(dates[-1] + timedelta(days=d)).strftime("%Y-%m-%d") for d in range(1, days_ahead + 1)],
        result_prices,
        [p * float(np.exp(-w)) for p, w in zip(result_prices, width, strict=True)],
        [p * float(np.exp(w)) for p, w in zip(result_prices, width, strict=True)],
        compute_trend(prices[-1], result_prices[-1], prices),
        "xgboost",
        _explanations(model, np.array([last_features])),
    )
