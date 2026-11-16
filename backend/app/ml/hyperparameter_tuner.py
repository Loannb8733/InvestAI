"""Réglage des hyperparamètres d'XGBoost et de Prophet par Optuna."""

import logging
from datetime import datetime
from typing import Any

import numpy as np

from app.ml.forecasting.models.xgboost import FIRST_ROW, forecast_prices

logger = logging.getLogger(__name__)

XGBOOST_DEFAULTS = {"n_estimators": 100, "max_depth": 4, "learning_rate": 0.1}
PROPHET_DEFAULTS = {"changepoint_prior_scale": 0.1}
HORIZON = 7
MIN_ROWS = 10
TUNING_SEED = 0


def _split_errors(params: dict[str, Any], arr: np.ndarray, split: int) -> list[float]:
    """Erreurs relatives à 1..7 jours du modèle de production entraîné sur ``arr[:split]``."""
    if split - FIRST_ROW < MIN_ROWS:
        return []
    predicted = forecast_prices(arr[:split], HORIZON, params)
    return [
        abs(pred - arr[split + d]) / arr[split + d]
        for d, pred in enumerate(predicted)
        if split + d < len(arr) and arr[split + d] > 0
    ]


def _walk_forward_mape(params: dict[str, Any], arr: np.ndarray) -> float:
    errors: list[float] = []
    for split_pct in (0.6, 0.7, 0.8):
        split = int(len(arr) * split_pct)
        if split < 30 or split + HORIZON > len(arr):
            continue
        errors.extend(_split_errors(params, arr, split))
    return float(np.mean(errors)) * 100 if errors else 100.0


def tune_xgboost(prices: list[float], n_trials: int = 30) -> dict[str, Any]:
    """Hyperparamètres d'XGBoost minimisant l'erreur à 7 jours sur trois coupes successives ; défauts sous 40 cours."""
    try:
        import optuna
        import xgboost  # noqa: F401

        optuna.logging.set_verbosity(optuna.logging.WARNING)
    except ImportError:
        logger.warning("Optuna not available, using defaults")
        return dict(XGBOOST_DEFAULTS)
    arr = np.array(prices, dtype=float)
    if len(arr) < 40:
        return dict(XGBOOST_DEFAULTS)

    def objective(trial: Any) -> float:
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 50, 300),
            "max_depth": trial.suggest_int("max_depth", 2, 8),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
        }
        return _walk_forward_mape(params, arr)

    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=TUNING_SEED))
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    best: dict[str, Any] = study.best_params
    logger.info("XGBoost tuning complete: MAPE=%.2f%%, params=%s", study.best_value, best)
    return best


def tune_prophet(prices: list[float], dates: list[datetime], n_trials: int = 15) -> dict[str, Any]:
    """Hyperparamètres de Prophet minimisant l'erreur sur les 7 derniers cours ; défauts sous 30 cours."""
    try:
        import optuna
        import pandas as pd
        from prophet import Prophet

        optuna.logging.set_verbosity(optuna.logging.WARNING)
    except ImportError:
        return dict(PROPHET_DEFAULTS)
    if len(prices) < 30:
        return dict(PROPHET_DEFAULTS)

    def objective(trial: Any) -> float:
        cps = trial.suggest_float("changepoint_prior_scale", 0.001, 0.5, log=True)
        seasonality_mode = trial.suggest_categorical("seasonality_mode", ["additive", "multiplicative"])
        split = len(prices) - HORIZON
        model = Prophet(
            daily_seasonality=False,
            weekly_seasonality=len(prices) >= 14,
            yearly_seasonality=False,
            changepoint_prior_scale=cps,
            seasonality_mode=seasonality_mode,
            mcmc_samples=0,
            uncertainty_samples=0,
        )
        model.fit(pd.DataFrame({"ds": dates[:split], "y": prices[:split]}))
        fc = model.predict(model.make_future_dataframe(periods=HORIZON)).tail(HORIZON)
        errors = [
            abs(pred - prices[split + i]) / prices[split + i]
            for i, pred in enumerate(fc["yhat"].values)
            if split + i < len(prices) and prices[split + i] > 0
        ]
        return float(np.mean(errors)) * 100 if errors else 100.0

    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=TUNING_SEED))
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    logger.info("Prophet tuning complete: MAPE=%.2f%%, params=%s", study.best_value, study.best_params)
    best: dict[str, Any] = study.best_params
    return best
