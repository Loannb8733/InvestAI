"""Hyperparameter tuning for ML models using Optuna."""

import logging
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


def tune_xgboost(prices: List[float], n_trials: int = 30) -> Dict:
    """Tune XGBoost hyperparameters using Optuna with walk-forward validation."""
    try:
        import optuna
        from xgboost import XGBRegressor

        optuna.logging.set_verbosity(optuna.logging.WARNING)
    except ImportError:
        logger.warning("Optuna not available, using defaults")
        return {"n_estimators": 100, "max_depth": 4, "learning_rate": 0.1}

    arr = np.array(prices, dtype=float)
    if len(arr) < 40:
        return {"n_estimators": 100, "max_depth": 4, "learning_rate": 0.1}

    from app.ml.forecaster import PriceForecaster

    def objective(trial):
        n_estimators = trial.suggest_int("n_estimators", 50, 300)
        max_depth = trial.suggest_int("max_depth", 2, 8)
        learning_rate = trial.suggest_float("learning_rate", 0.01, 0.3, log=True)
        subsample = trial.suggest_float("subsample", 0.6, 1.0)
        colsample_bytree = trial.suggest_float("colsample_bytree", 0.6, 1.0)

        # Walk-forward: train on [0:split], test on [split:split+7]
        errors = []
        for split_pct in [0.6, 0.7, 0.8]:
            split = int(len(arr) * split_pct)
            if split < 30 or split + 7 > len(arr):
                continue

            features, targets = [], []
            lookback = 7
            for i in range(lookback + 14, split):
                row = PriceForecaster._build_features(arr[:split], i)
                features.append(row)
                targets.append(arr[i])

            if len(features) < 10:
                continue

            X = np.array(features)
            y_train = np.array(targets)

            model = XGBRegressor(
                n_estimators=n_estimators,
                max_depth=max_depth,
                learning_rate=learning_rate,
                subsample=subsample,
                colsample_bytree=colsample_bytree,
                verbosity=0,
            )
            model.fit(X, y_train)

            # Predict next 7 days iteratively
            extended = list(arr[:split])
            for d in range(7):
                if split + d >= len(arr):
                    break
                feat = PriceForecaster._build_features(np.array(extended), len(extended))
                pred = float(model.predict(np.array([feat]))[0])
                actual = arr[split + d]
                if actual > 0:
                    errors.append(abs(pred - actual) / actual)
                extended.append(pred)

        if not errors:
            return 100.0
        return float(np.mean(errors)) * 100  # MAPE

    study = optuna.create_study(direction="minimize")
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    best = study.best_params
    logger.info("XGBoost tuning complete: MAPE=%.2f%%, params=%s", study.best_value, best)
    return best


def tune_prophet(prices: List[float], dates: list, n_trials: int = 15) -> Dict:
    """Tune Prophet hyperparameters."""
    try:
        import optuna
        from prophet import Prophet
        import pandas as pd

        optuna.logging.set_verbosity(optuna.logging.WARNING)
    except ImportError:
        return {"changepoint_prior_scale": 0.1}

    if len(prices) < 30:
        return {"changepoint_prior_scale": 0.1}

    def objective(trial):
        cps = trial.suggest_float("changepoint_prior_scale", 0.001, 0.5, log=True)
        seasonality_mode = trial.suggest_categorical("seasonality_mode", ["additive", "multiplicative"])

        split = len(prices) - 7
        train_df = pd.DataFrame({"ds": dates[:split], "y": prices[:split]})

        model = Prophet(
            daily_seasonality=False,
            weekly_seasonality=len(prices) >= 14,
            yearly_seasonality=False,
            changepoint_prior_scale=cps,
            seasonality_mode=seasonality_mode,
            interval_width=0.95,
        )
        model.fit(train_df)
        future = model.make_future_dataframe(periods=7)
        fc = model.predict(future).tail(7)

        errors = []
        for i, pred in enumerate(fc["yhat"].values):
            if split + i < len(prices) and prices[split + i] > 0:
                errors.append(abs(pred - prices[split + i]) / prices[split + i])

        return float(np.mean(errors)) * 100 if errors else 100.0

    study = optuna.create_study(direction="minimize")
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    logger.info("Prophet tuning complete: MAPE=%.2f%%, params=%s", study.best_value, study.best_params)
    return study.best_params
