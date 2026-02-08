"""Price forecasting using an ensemble of models:
   Prophet, ARIMA, XGBoost, EMA, and Linear Regression.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class ForecastResult:
    """Result of a price forecast."""

    dates: List[str]
    prices: List[float]
    confidence_low: List[float]
    confidence_high: List[float]
    trend: str  # bullish, bearish, neutral
    trend_strength: float  # 0-100
    model_used: str  # e.g. "ensemble (prophet: 42%, xgboost: 35%)"
    models_detail: List[Dict] = field(default_factory=list)
    # [{name, weight_pct, mape, trend}]
    explanations: List[Dict] = field(default_factory=list)
    # [{feature_name: str, importance: float, direction: str}]


class PriceForecaster:
    """Ensemble price forecaster combining multiple models."""

    def __init__(self, hyperparams: Optional[Dict] = None):
        self._prophet_available = self._check_import("prophet", "Prophet")
        self._xgboost_available = self._check_import("xgboost", "XGBRegressor")
        self._arima_available = self._check_import(
            "statsmodels.tsa.arima.model", "ARIMA"
        )
        self._auto_arima_available = self._check_import("pmdarima", "auto_arima")
        self._hyperparams = hyperparams or {}

    @staticmethod
    def _check_import(module: str, cls: str) -> bool:
        try:
            mod = __import__(module, fromlist=[cls])
            getattr(mod, cls)
            return True
        except (ImportError, AttributeError):
            logger.warning("%s.%s not available", module, cls)
            return False

    # ─────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────

    def forecast(
        self,
        prices: List[float],
        dates: List[datetime],
        days_ahead: int = 7,
    ) -> ForecastResult:
        """Legacy single-model forecast (still used as inner call)."""
        if len(prices) < 5:
            return self._fallback_forecast(prices, days_ahead)
        if self._prophet_available and len(prices) >= 14:
            try:
                return self._prophet_forecast(prices, dates, days_ahead)
            except Exception as e:
                logger.warning("Prophet failed: %s", e)
        return self._linear_forecast(prices, dates, days_ahead)

    def ensemble_forecast(
        self,
        prices: List[float],
        dates: List[datetime],
        days_ahead: int = 7,
    ) -> ForecastResult:
        """Run all available models, weight by backtest, combine."""

        if len(prices) < 5:
            return self._fallback_forecast(prices, days_ahead)

        # ── 1. Collect individual forecasts ──────────────────────────
        candidates: List[Tuple[str, ForecastResult]] = []

        # Prophet
        if self._prophet_available and len(prices) >= 14:
            try:
                r = self._prophet_forecast(prices, dates, days_ahead)
                candidates.append(("Prophet", r))
            except Exception as e:
                logger.warning("Prophet ensemble: %s", e)

        # ARIMA
        if self._arima_available and len(prices) >= 20:
            try:
                r = self._arima_forecast(prices, dates, days_ahead)
                candidates.append(("ARIMA", r))
            except Exception as e:
                logger.warning("ARIMA ensemble: %s", e)

        # XGBoost
        if self._xgboost_available and len(prices) >= 30:
            try:
                r = self._xgboost_forecast(prices, dates, days_ahead)
                candidates.append(("XGBoost", r))
            except Exception as e:
                logger.warning("XGBoost ensemble: %s", e)

        # EMA (always available if >=7 points)
        if len(prices) >= 7:
            try:
                r = self._ema_forecast(prices, dates, days_ahead)
                candidates.append(("EMA", r))
            except Exception as e:
                logger.warning("EMA ensemble: %s", e)

        # Linear (always available if >=5 points)
        try:
            r = self._linear_forecast(prices, dates, days_ahead)
            candidates.append(("Linear", r))
        except Exception as e:
            logger.warning("Linear ensemble: %s", e)

        if not candidates:
            return self._fallback_forecast(prices, days_ahead)
        if len(candidates) == 1:
            name, result = candidates[0]
            result.model_used = name.lower()
            result.models_detail = [
                {"name": name, "weight_pct": 100, "mape": 0, "trend": result.trend}
            ]
            return result

        # ── 2. Compute weights via mini-backtest ─────────────────────
        weights = self._compute_weights(prices, dates, candidates)

        # ── 3. Weighted combination ──────────────────────────────────
        n_days = days_ahead
        combined_prices = [0.0] * n_days
        combined_low = [float("inf")] * n_days
        combined_high = [float("-inf")] * n_days
        result_dates = candidates[0][1].dates[:n_days]

        for (name, res), w in zip(candidates, weights):
            for i in range(min(n_days, len(res.prices))):
                combined_prices[i] += res.prices[i] * w
                combined_low[i] = min(combined_low[i], res.confidence_low[i])
                combined_high[i] = max(combined_high[i], res.confidence_high[i])

        # ── 4. Trend = weighted vote ─────────────────────────────────
        trend_scores = {"bullish": 0.0, "bearish": 0.0, "neutral": 0.0}
        for (name, res), w in zip(candidates, weights):
            trend_scores[res.trend] += w
        final_trend = max(trend_scores, key=trend_scores.get)  # type: ignore
        final_strength = self._compute_trend(
            prices[-1], combined_prices[-1], prices
        )[1]

        # ── 5. Build model_used string and details ───────────────────
        details = []
        parts = []
        for (name, res), w in zip(candidates, weights):
            pct = round(w * 100)
            mape = self._quick_mape(prices, dates, name, res)
            details.append({
                "name": name,
                "weight_pct": pct,
                "mape": round(mape, 1),
                "trend": res.trend,
            })
            parts.append(f"{name}: {pct}%")

        model_str = f"ensemble ({', '.join(parts)})"

        return ForecastResult(
            dates=result_dates,
            prices=[round(p, 8) for p in combined_prices],
            confidence_low=[round(max(0, p), 8) for p in combined_low],
            confidence_high=[round(p, 8) for p in combined_high],
            trend=final_trend,
            trend_strength=round(final_strength, 1),
            model_used=model_str,
            models_detail=details,
        )

    # ─────────────────────────────────────────────────────────────────
    # Individual Models
    # ─────────────────────────────────────────────────────────────────

    def _prophet_forecast(
        self, prices: List[float], dates: List[datetime], days_ahead: int
    ) -> ForecastResult:
        """Facebook Prophet forecast."""
        from prophet import Prophet

        df = pd.DataFrame({"ds": dates, "y": prices})
        prophet_params = self._hyperparams.get("prophet", {})
        model = Prophet(
            daily_seasonality=False,
            weekly_seasonality=len(prices) >= 14,
            yearly_seasonality=len(prices) >= 365,
            changepoint_prior_scale=prophet_params.get("changepoint_prior_scale", 0.1),
            seasonality_mode=prophet_params.get("seasonality_mode", "additive"),
            interval_width=0.95,
        )
        model.fit(df)
        future = model.make_future_dataframe(periods=days_ahead)
        fc = model.predict(future).tail(days_ahead)

        result_dates = [d.strftime("%Y-%m-%d") for d in fc["ds"]]
        result_prices = [max(0.0, p) for p in fc["yhat"].tolist()]
        result_low = [max(0.0, p) for p in fc["yhat_lower"].tolist()]
        result_high = fc["yhat_upper"].tolist()
        trend, strength = self._compute_trend(prices[-1], result_prices[-1], prices)

        return ForecastResult(
            dates=result_dates,
            prices=[round(p, 8) for p in result_prices],
            confidence_low=[round(p, 8) for p in result_low],
            confidence_high=[round(p, 8) for p in result_high],
            trend=trend,
            trend_strength=round(strength, 1),
            model_used="prophet",
        )

    def _arima_forecast(
        self, prices: List[float], dates: List[datetime], days_ahead: int
    ) -> ForecastResult:
        """ARIMA forecast with auto parameter selection via pmdarima or grid search."""
        import warnings

        y = np.array(prices, dtype=float)

        # Scale up tiny prices for numerical stability
        scale = 1.0
        if np.mean(y) < 0.01:
            scale = 1.0 / np.mean(y)
            y = y * scale

        # Use pmdarima.auto_arima if available (much better than manual grid)
        if self._auto_arima_available:
            try:
                from pmdarima import auto_arima as pm_auto_arima

                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    model = pm_auto_arima(
                        y,
                        start_p=0, max_p=5,
                        start_q=0, max_q=3,
                        d=1, max_d=2,
                        seasonal=False,
                        stepwise=True,
                        suppress_warnings=True,
                        error_action="ignore",
                    )
                fc, ci = model.predict(n_periods=days_ahead, return_conf_int=True, alpha=0.05)
                best_order = model.order
            except Exception as e:
                logger.warning("auto_arima failed, falling back to grid: %s", e)
                model, fc, ci, best_order = self._arima_grid_search(y, days_ahead)
        else:
            model, fc, ci, best_order = self._arima_grid_search(y, days_ahead)

        last_date = dates[-1]
        result_dates = [
            (last_date + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(1, days_ahead + 1)
        ]
        result_prices = [max(0.0, float(v) / scale) for v in fc]
        result_low = [max(0.0, float(ci[i, 0]) / scale) for i in range(days_ahead)]
        result_high = [float(ci[i, 1]) / scale for i in range(days_ahead)]
        trend, strength = self._compute_trend(prices[-1], result_prices[-1], prices)

        return ForecastResult(
            dates=result_dates,
            prices=[round(p, 8) for p in result_prices],
            confidence_low=[round(p, 8) for p in result_low],
            confidence_high=[round(p, 8) for p in result_high],
            trend=trend,
            trend_strength=round(strength, 1),
            model_used=f"arima{best_order}",
        )

    def _arima_grid_search(self, y, days_ahead):
        """Fallback manual ARIMA grid search."""
        import warnings
        from statsmodels.tsa.arima.model import ARIMA

        best_aic = float("inf")
        best_order = (1, 1, 0)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for p in range(0, 4):
                for q in range(0, 3):
                    try:
                        m = ARIMA(y, order=(p, 1, q))
                        res = m.fit()
                        if res.aic < best_aic:
                            best_aic = res.aic
                            best_order = (p, 1, q)
                    except Exception:
                        continue

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = ARIMA(y, order=best_order)
            fit = model.fit()
        fc_result = fit.get_forecast(steps=days_ahead)
        mean = fc_result.predicted_mean
        ci = fc_result.conf_int(alpha=0.05)
        ci_arr = ci.values if hasattr(ci, 'values') else np.asarray(ci)
        return fit, np.array(mean), ci_arr, best_order

    def _xgboost_forecast(
        self, prices: List[float], dates: List[datetime], days_ahead: int
    ) -> ForecastResult:
        """XGBoost forecast with engineered features."""
        from xgboost import XGBRegressor

        arr = np.array(prices, dtype=float)

        # Build feature matrix
        features = []
        targets = []
        lookback = 7

        for i in range(lookback + 14, len(arr)):
            row = self._build_features(arr, i)
            features.append(row)
            targets.append(arr[i])

        X = np.array(features)
        y = np.array(targets)

        xgb_params = self._hyperparams.get("xgboost", {})
        model = XGBRegressor(
            n_estimators=xgb_params.get("n_estimators", 100),
            max_depth=xgb_params.get("max_depth", 4),
            learning_rate=xgb_params.get("learning_rate", 0.1),
            subsample=xgb_params.get("subsample", 1.0),
            colsample_bytree=xgb_params.get("colsample_bytree", 1.0),
            verbosity=0,
        )
        model.fit(X, y)

        # Iterative prediction
        extended = list(arr)
        result_prices = []
        last_date = dates[-1]
        result_dates = []

        for d in range(1, days_ahead + 1):
            feat = self._build_features(np.array(extended), len(extended))
            pred = float(model.predict(np.array([feat]))[0])
            pred = max(0.0, pred)
            result_prices.append(pred)
            extended.append(pred)
            result_dates.append(
                (last_date + timedelta(days=d)).strftime("%Y-%m-%d")
            )

        # Confidence from residuals
        train_preds = model.predict(X)
        residual_std = float(np.std(y - train_preds))
        result_low = [max(0.0, p - 1.96 * residual_std) for p in result_prices]
        result_high = [p + 1.96 * residual_std for p in result_prices]

        trend, strength = self._compute_trend(prices[-1], result_prices[-1], prices)

        # SHAP explainability
        explanations = []
        try:
            import shap
            explainer = shap.TreeExplainer(model)
            # Explain the last prediction
            last_feat = np.array([self._build_features(np.array(extended[:-1]), len(extended) - 1)])
            shap_values = explainer.shap_values(last_feat)

            feature_names = getattr(self, 'FEATURE_NAMES', [f"f{i}" for i in range(len(shap_values[0]))])

            # Top 3 most impactful features
            abs_shap = np.abs(shap_values[0])
            top_indices = np.argsort(abs_shap)[-3:][::-1]

            for idx in top_indices:
                fname = feature_names[idx] if idx < len(feature_names) else f"feature_{idx}"
                val = float(shap_values[0][idx])
                explanations.append({
                    "feature": fname,
                    "importance": round(abs(val), 6),
                    "direction": "hausse" if val > 0 else "baisse",
                })
        except Exception as e:
            logger.debug("SHAP computation failed: %s", e)

        return ForecastResult(
            dates=result_dates,
            prices=[round(p, 8) for p in result_prices],
            confidence_low=[round(p, 8) for p in result_low],
            confidence_high=[round(p, 8) for p in result_high],
            trend=trend,
            trend_strength=round(strength, 1),
            model_used="xgboost",
            explanations=explanations,
        )

    # Feature names for SHAP explainability
    FEATURE_NAMES = [
        "ret_1d", "ret_2d", "ret_3d", "ret_4d", "ret_5d", "ret_6d", "ret_7d",
        "volatility_7d", "rsi_14", "price_sma20_ratio",
        "momentum_3d", "momentum_7d", "momentum_14d",
        "volatility_14d", "price_sma7_ratio",
        "high_low_range_7d", "mean_return_7d",
    ]

    @staticmethod
    def _build_features(prices: np.ndarray, idx: int) -> List[float]:
        """Build feature vector for XGBoost at given index.

        Returns 17 features: 7 lagged returns + 10 technical indicators.
        """
        feats = []

        # --- Lagged returns J-1 to J-7 (7 features) ---
        for lag in range(1, 8):
            if idx - lag >= 1:
                feats.append(
                    (prices[idx - lag] - prices[idx - lag - 1])
                    / max(prices[idx - lag - 1], 1e-10)
                )
            else:
                feats.append(0.0)

        # --- Volatility 7d (1 feature) ---
        if idx >= 8:
            rets = [
                (prices[idx - i] - prices[idx - i - 1])
                / max(prices[idx - i - 1], 1e-10)
                for i in range(1, 8)
            ]
            feats.append(float(np.std(rets)))
        else:
            feats.append(0.0)

        # --- RSI 14 (1 feature) ---
        if idx >= 15:
            deltas = [prices[idx - i] - prices[idx - i - 1] for i in range(1, 15)]
            gains = [d for d in deltas if d > 0]
            losses = [-d for d in deltas if d < 0]
            avg_gain = np.mean(gains) if gains else 0.0
            avg_loss = np.mean(losses) if losses else 1e-10
            rs = avg_gain / max(avg_loss, 1e-10)
            feats.append(100 - 100 / (1 + rs))
        else:
            feats.append(50.0)

        # --- Price / SMA20 (1 feature) ---
        if idx >= 20:
            sma20 = float(np.mean(prices[idx - 20 : idx]))
            feats.append(prices[idx - 1] / max(sma20, 1e-10))
        else:
            feats.append(1.0)

        # --- Momentum 3d, 7d, 14d (3 features) ---
        for period in [3, 7, 14]:
            if idx >= period + 1:
                feats.append(
                    (prices[idx - 1] - prices[idx - period - 1])
                    / max(prices[idx - period - 1], 1e-10)
                )
            else:
                feats.append(0.0)

        # --- Volatility 14d (1 feature) ---
        if idx >= 15:
            rets_14 = [
                (prices[idx - i] - prices[idx - i - 1])
                / max(prices[idx - i - 1], 1e-10)
                for i in range(1, min(15, idx))
            ]
            feats.append(float(np.std(rets_14)))
        else:
            feats.append(0.0)

        # --- Price / SMA7 (1 feature) ---
        if idx >= 8:
            sma7 = float(np.mean(prices[idx - 7 : idx]))
            feats.append(prices[idx - 1] / max(sma7, 1e-10))
        else:
            feats.append(1.0)

        # --- High-low range 7d (1 feature) ---
        if idx >= 8:
            window = prices[idx - 7 : idx]
            high = float(np.max(window))
            low = float(np.min(window))
            feats.append((high - low) / max(low, 1e-10))
        else:
            feats.append(0.0)

        # --- Mean return 7d (1 feature) ---
        if idx >= 8:
            rets_7 = [
                (prices[idx - i] - prices[idx - i - 1])
                / max(prices[idx - i - 1], 1e-10)
                for i in range(1, 8)
            ]
            feats.append(float(np.mean(rets_7)))
        else:
            feats.append(0.0)

        return feats

    def _ema_forecast(
        self, prices: List[float], dates: List[datetime], days_ahead: int
    ) -> ForecastResult:
        """EMA-based forecast using 7-day and 21-day EMAs."""
        arr = np.array(prices, dtype=float)

        ema7 = self._ema(arr, 7)
        ema21 = self._ema(arr, min(21, len(arr)))

        # Slope from last 3 EMA7 values
        if len(ema7) >= 3:
            slope = (ema7[-1] - ema7[-3]) / 2
        else:
            slope = 0.0

        # Residuals for confidence
        residuals = arr[-min(30, len(arr)) :] - ema7[-min(30, len(ema7)) :]
        std_r = float(np.std(residuals)) if len(residuals) > 1 else abs(arr[-1]) * 0.02

        last_date = dates[-1]
        result_dates = []
        result_prices = []
        result_low = []
        result_high = []
        base = ema7[-1]

        for i in range(1, days_ahead + 1):
            pred = base + slope * i
            pred = max(0.0, float(pred))
            ci = 1.96 * std_r * np.sqrt(i)
            result_dates.append(
                (last_date + timedelta(days=i)).strftime("%Y-%m-%d")
            )
            result_prices.append(pred)
            result_low.append(max(0.0, pred - ci))
            result_high.append(pred + ci)

        trend, strength = self._compute_trend(prices[-1], result_prices[-1], prices)

        return ForecastResult(
            dates=result_dates,
            prices=[round(p, 8) for p in result_prices],
            confidence_low=[round(p, 8) for p in result_low],
            confidence_high=[round(p, 8) for p in result_high],
            trend=trend,
            trend_strength=round(strength, 1),
            model_used="ema",
        )

    @staticmethod
    def _ema(data: np.ndarray, span: int) -> np.ndarray:
        """Compute exponential moving average."""
        alpha = 2 / (span + 1)
        result = np.zeros(len(data))
        result[0] = data[0]
        for i in range(1, len(data)):
            result[i] = alpha * data[i] + (1 - alpha) * result[i - 1]
        return result

    def _linear_forecast(
        self, prices: List[float], dates: List[datetime], days_ahead: int
    ) -> ForecastResult:
        """Linear regression on log prices."""
        n = len(prices)
        x = np.arange(n, dtype=float)
        y = np.log(np.maximum(np.array(prices, dtype=float), 1e-10))

        coeffs = np.polyfit(x, y, 1)
        slope, intercept = coeffs
        y_pred = slope * x + intercept
        std_r = float(np.std(y - y_pred))

        last_date = dates[-1]
        result_dates = []
        result_prices = []
        result_low = []
        result_high = []

        for i in range(1, days_ahead + 1):
            fx = n + i - 1
            d = last_date + timedelta(days=i)
            result_dates.append(d.strftime("%Y-%m-%d"))
            pred_log = slope * fx + intercept
            pred = float(np.exp(pred_log))
            ci = 1.96 * std_r * np.sqrt(
                1 + 1 / n + (fx - np.mean(x)) ** 2 / np.sum((x - np.mean(x)) ** 2)
            )
            result_prices.append(max(0.0, pred))
            result_low.append(max(0.0, float(np.exp(pred_log - ci))))
            result_high.append(float(np.exp(pred_log + ci)))

        trend, strength = self._compute_trend(prices[-1], result_prices[-1], prices)
        return ForecastResult(
            dates=result_dates,
            prices=[round(p, 8) for p in result_prices],
            confidence_low=[round(p, 8) for p in result_low],
            confidence_high=[round(p, 8) for p in result_high],
            trend=trend,
            trend_strength=round(strength, 1),
            model_used="linear",
        )

    def _fallback_forecast(
        self, prices: List[float], days_ahead: int
    ) -> ForecastResult:
        """Random walk fallback for very little data."""
        if not prices:
            return ForecastResult(
                dates=[], prices=[], confidence_low=[], confidence_high=[],
                trend="neutral", trend_strength=0, model_used="fallback",
            )
        current = prices[-1]
        vol = np.std(prices) / np.mean(prices) if len(prices) > 1 else 0.03
        daily_vol = vol / np.sqrt(max(len(prices), 1))
        drift = (prices[-1] / prices[0]) ** (1 / len(prices)) - 1 if len(prices) >= 2 else 0.0

        now = datetime.utcnow()
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

        trend, strength = self._compute_trend(current, result_prices[-1], prices)
        return ForecastResult(
            dates=result_dates, prices=result_prices,
            confidence_low=result_low, confidence_high=result_high,
            trend=trend, trend_strength=round(strength, 1), model_used="fallback",
        )

    # ─────────────────────────────────────────────────────────────────
    # Weighting & Helpers
    # ─────────────────────────────────────────────────────────────────

    def _compute_weights(
        self,
        prices: List[float],
        dates: List[datetime],
        candidates: List[Tuple[str, ForecastResult]],
    ) -> List[float]:
        """Compute weights via mini-backtest: predict last 7 days from prior data."""
        if len(prices) < 14:
            # Not enough data for backtest → equal weights
            n = len(candidates)
            return [1.0 / n] * n

        # Split: train = all but last 7, test = last 7
        split = min(7, len(prices) // 2)
        train_prices = prices[:-split]
        train_dates = dates[:-split]
        actual = prices[-split:]

        mapes = []
        for name, _ in candidates:
            try:
                bt = self._run_model_by_name(name, train_prices, train_dates, split)
                pred_prices = bt.prices[:split]
                errs = [
                    abs(pred_prices[i] - actual[i]) / max(actual[i], 1e-10)
                    for i in range(min(len(pred_prices), len(actual)))
                ]
                mape = float(np.mean(errs)) * 100 if errs else 50.0
            except Exception:
                mape = 50.0  # fallback MAPE
            mapes.append(max(mape, 0.1))  # avoid division by zero

        # Inverse MAPE weighting
        inv = [1.0 / m for m in mapes]
        total = sum(inv)
        return [w / total for w in inv]

    def _run_model_by_name(
        self, name: str, prices: List[float], dates: List[datetime], days: int
    ) -> ForecastResult:
        """Run a specific model by name."""
        if name == "Prophet":
            return self._prophet_forecast(prices, dates, days)
        elif name == "ARIMA":
            return self._arima_forecast(prices, dates, days)
        elif name == "XGBoost":
            return self._xgboost_forecast(prices, dates, days)
        elif name == "EMA":
            return self._ema_forecast(prices, dates, days)
        else:
            return self._linear_forecast(prices, dates, days)

    @staticmethod
    def _quick_mape(
        prices: List[float],
        dates: List[datetime],
        name: str,
        result: ForecastResult,
    ) -> float:
        """Quick MAPE estimation from the last known prices vs model direction."""
        if not prices or not result.prices:
            return 0.0
        # Approximate: use the recent price trend vs predicted trend as proxy
        recent_change = (prices[-1] - prices[-min(7, len(prices))]) / max(
            prices[-min(7, len(prices))], 1e-10
        ) * 100
        predicted_change = (result.prices[-1] - prices[-1]) / max(
            prices[-1], 1e-10
        ) * 100
        return abs(recent_change - predicted_change)

    @staticmethod
    def _compute_trend(
        current_price: float,
        final_predicted: float,
        historical: List[float],
    ) -> Tuple[str, float]:
        """Compute trend direction and strength."""
        if current_price == 0:
            return "neutral", 0.0
        pct_change = (final_predicted - current_price) / current_price * 100
        if len(historical) >= 5:
            recent_momentum = (historical[-1] - historical[-5]) / historical[-5] * 100
            combined = pct_change * 0.6 + recent_momentum * 0.4
        else:
            combined = pct_change
        if combined > 2:
            trend = "bullish"
        elif combined < -2:
            trend = "bearish"
        else:
            trend = "neutral"
        strength = min(100.0, abs(combined) * 5)
        return trend, strength
