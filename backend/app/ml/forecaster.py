"""Price forecasting using an ensemble of models:
   Prophet, ARIMA, XGBoost, EMA, Linear Regression, and Mean-Reversion (OU).
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import redis

from app.core.config import settings
from app.ml import adaptive_thresholds as at
from app.ml.market_context import MarketContext

logger = logging.getLogger(__name__)

# Sync Redis client for caching individual model results within sync forecaster
_sync_redis: Optional[redis.Redis] = None


def _get_sync_redis() -> redis.Redis:
    global _sync_redis
    if _sync_redis is None:
        _sync_redis = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )
    return _sync_redis


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
        self._arima_available = self._check_import("statsmodels.tsa.arima.model", "ARIMA")
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
        symbol: Optional[str] = None,
        data_hash: Optional[str] = None,
        volumes: Optional[List[float]] = None,
        btc_prices: Optional[List[float]] = None,
        fear_greed: Optional[int] = None,
        btc_dominance: Optional[float] = None,
        market_context: Optional[MarketContext] = None,
    ) -> ForecastResult:
        """Run all available models, weight by backtest, combine.

        Args:
            prices: Historical price list.
            dates: Corresponding date list.
            days_ahead: Forecast horizon in days.
            symbol: Asset symbol for per-model Redis caching.
            data_hash: Hash of price data for cache key staleness detection.
            volumes: Historical volume list (same length as prices), optional.
            btc_prices: BTC price history for correlation features, optional.
            fear_greed: Fear & Greed index (0-100), optional.
            btc_dominance: BTC dominance percentage, optional.
            market_context: Pre-computed MarketContext for adaptive thresholds.
        """

        if len(prices) < 5:
            return self._fallback_forecast(prices, days_ahead)

        # FIX6: Load cached Optuna hyperparams if available (thread-safe copy)
        if symbol:
            cached_hparams = self._load_cached_hyperparams(symbol)
            if cached_hparams:
                self._hyperparams = {**self._hyperparams, **cached_hparams}

        # ── 1. Collect individual forecasts ──────────────────────────
        candidates: List[Tuple[str, ForecastResult]] = []

        # Prophet
        if self._prophet_available and len(prices) >= 14:
            try:
                r = self._get_or_run_model("Prophet", symbol, data_hash, days_ahead, prices, dates)
                candidates.append(("Prophet", r))
            except Exception as e:
                logger.warning("Prophet ensemble: %s", e)

        # ARIMA
        if self._arima_available and len(prices) >= 20:
            try:
                r = self._get_or_run_model("ARIMA", symbol, data_hash, days_ahead, prices, dates)
                candidates.append(("ARIMA", r))
            except Exception as e:
                logger.warning("ARIMA ensemble: %s", e)

        # XGBoost (with volume + BTC features)
        if self._xgboost_available and len(prices) >= 30:
            try:
                r = self._get_or_run_model(
                    "XGBoost",
                    symbol,
                    data_hash,
                    days_ahead,
                    prices,
                    dates,
                    volumes=volumes,
                    btc_prices=btc_prices,
                )
                candidates.append(("XGBoost", r))
            except Exception as e:
                logger.warning("XGBoost ensemble: %s", e)

        # EMA (always available if >=7 points)
        if len(prices) >= 7:
            try:
                r = self._get_or_run_model("EMA", symbol, data_hash, days_ahead, prices, dates)
                candidates.append(("EMA", r))
            except Exception as e:
                logger.warning("EMA ensemble: %s", e)

        # Linear (always available if >=5 points)
        try:
            r = self._get_or_run_model("Linear", symbol, data_hash, days_ahead, prices, dates)
            candidates.append(("Linear", r))
        except Exception as e:
            logger.warning("Linear ensemble: %s", e)

        # Mean-Reversion (Ornstein-Uhlenbeck) — provides counter-trend diversity
        if len(prices) >= 30:
            try:
                r = self._get_or_run_model("MeanReversion", symbol, data_hash, days_ahead, prices, dates)
                candidates.append(("MeanReversion", r))
            except Exception as e:
                logger.warning("MeanReversion ensemble: %s", e)

        if not candidates:
            return self._fallback_forecast(prices, days_ahead)
        if len(candidates) == 1:
            name, result = candidates[0]
            result.model_used = name.lower()
            result.models_detail = [{"name": name, "weight_pct": 100, "mape": 0, "trend": result.trend}]
            return result

        # ── 2. Compute weights via mini-backtest ─────────────────────
        weights, ci_calibration = self._compute_weights(prices, dates, candidates)

        # ── 3. Weighted combination ──────────────────────────────────
        n_days = days_ahead
        combined_prices = [0.0] * n_days
        result_dates = candidates[0][1].dates[:n_days]

        for (name, res), w in zip(candidates, weights):
            for i in range(min(n_days, len(res.prices))):
                combined_prices[i] += res.prices[i] * w

        # ── 3b. Calibrated CIs: empirical quantiles + EWMA scaling ──
        ewma_vols = self._ewma_volatility_forecast(prices, n_days)
        combined_low, combined_high = self._empirical_quantile_ci(
            prices,
            prices[-1],
            n_days,
            combined_prices,
            ewma_vols,
        )

        # Apply CI floor by asset type
        if market_context:
            for i in range(n_days):
                floor = at.ci_floor(market_context, i + 1)
                mid = combined_prices[i]
                half_width = (combined_high[i] - combined_low[i]) / 2
                min_half = mid * floor
                if half_width < min_half:
                    combined_low[i] = max(0.0, mid - min_half)
                    combined_high[i] = mid + min_half

        # FIX7: apply CI calibration from backtest coverage
        if ci_calibration != 1.0:
            for i in range(n_days):
                mid = combined_prices[i]
                half_width = (combined_high[i] - combined_low[i]) / 2
                combined_low[i] = max(0.0, mid - half_width * ci_calibration)
                combined_high[i] = mid + half_width * ci_calibration

        # ── 4. Trend = weighted vote ─────────────────────────────────
        trend_scores = {"bullish": 0.0, "bearish": 0.0, "neutral": 0.0}
        for (name, res), w in zip(candidates, weights):
            trend_scores[res.trend] += w
        final_trend = max(trend_scores, key=trend_scores.get)  # type: ignore
        final_strength = self._compute_trend(
            prices[-1], combined_prices[-1], prices, days_ahead=days_ahead, ctx=market_context
        )[1]

        # ── 5. Build model_used string and details ───────────────────
        details = []
        parts = []
        for (name, res), w in zip(candidates, weights):
            pct = round(w * 100)
            mape = self._quick_mape(prices, dates, name, res)
            details.append(
                {
                    "name": name,
                    "weight_pct": pct,
                    "mape": round(mape, 1),
                    "trend": res.trend,
                }
            )
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
        self,
        prices: List[float],
        dates: List[datetime],
        days_ahead: int,
        volumes: Optional[List[float]] = None,
    ) -> ForecastResult:
        """Facebook Prophet forecast with optional volume regressor (P10)."""
        from prophet import Prophet

        df = pd.DataFrame({"ds": dates, "y": prices})
        has_volume = volumes is not None and len(volumes) == len(prices)
        if has_volume:
            df["volume"] = volumes

        prophet_params = self._hyperparams.get("prophet", {})
        model = Prophet(
            daily_seasonality=False,
            weekly_seasonality=len(prices) >= 14,
            yearly_seasonality=len(prices) >= 365,
            changepoint_prior_scale=prophet_params.get("changepoint_prior_scale", 0.1),
            seasonality_mode=prophet_params.get("seasonality_mode", "additive"),
            interval_width=0.95,
            mcmc_samples=0,  # MAP estimation — fully deterministic
        )
        if has_volume:
            model.add_regressor("volume")
        model.fit(df)
        future = model.make_future_dataframe(periods=days_ahead)
        if has_volume:
            recent_vol_mean = float(np.mean(volumes[-7:])) if len(volumes) >= 7 else float(np.mean(volumes))
            all_volumes = list(volumes) + [recent_vol_mean] * days_ahead
            future["volume"] = all_volumes[: len(future)]
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

    def _arima_forecast(self, prices: List[float], dates: List[datetime], days_ahead: int) -> ForecastResult:
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
                best_order = model.order
            except Exception as e:
                logger.warning("auto_arima failed, falling back to grid: %s", e)
                model, fc, ci, best_order = self._arima_grid_search(y, days_ahead)
        else:
            model, fc, ci, best_order = self._arima_grid_search(y, days_ahead)

        last_date = dates[-1]
        result_dates = [(last_date + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(1, days_ahead + 1)]
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
        ci_arr = ci.values if hasattr(ci, "values") else np.asarray(ci)
        return fit, np.array(mean), ci_arr, best_order

    def _xgboost_forecast(
        self,
        prices: List[float],
        dates: List[datetime],
        days_ahead: int,
        volumes: Optional[List[float]] = None,
        btc_prices: Optional[List[float]] = None,
    ) -> ForecastResult:
        """XGBoost forecast with engineered features (price + volume + BTC)."""
        from xgboost import XGBRegressor

        arr = np.array(prices, dtype=float)
        # Align volumes to prices (P2: handle length mismatch with NaN padding)
        if volumes and len(volumes) >= len(prices):
            vol_arr = np.array(volumes[-len(prices) :], dtype=float)
        elif volumes and len(volumes) > 0:
            pad_size = len(prices) - len(volumes)
            vol_arr = np.concatenate([np.full(pad_size, np.nan), np.array(volumes, dtype=float)])
        else:
            vol_arr = None
        btc_arr = np.array(btc_prices, dtype=float) if btc_prices and len(btc_prices) >= len(prices) else None
        # Align BTC to same length as prices (take last N)
        if btc_arr is not None and len(btc_arr) > len(arr):
            btc_arr = btc_arr[-len(arr) :]

        # Pre-compute RSI array once (O(N) instead of O(N²) per call)
        rsi_array = self._precompute_rsi(arr, period=14)

        # Build feature matrix
        features = []
        targets = []
        lookback = 7

        for i in range(lookback + 14, len(arr)):
            row = self._build_features(arr, i, vol_arr, btc_arr, rsi_array=rsi_array)
            features.append(row)
            targets.append(arr[i])

        X = np.array(features)
        y = np.array(targets)

        xgb_params = self._hyperparams.get("xgboost", {})
        xgb_base_params = dict(
            n_estimators=xgb_params.get("n_estimators", 100),
            max_depth=xgb_params.get("max_depth", 4),
            learning_rate=xgb_params.get("learning_rate", 0.1),
            subsample=xgb_params.get("subsample", 1.0),
            colsample_bytree=xgb_params.get("colsample_bytree", 1.0),
            random_state=42,
            verbosity=0,
        )

        # --- Honest CI: train/val split for residual estimation ---
        split_idx = max(int(len(X) * 0.8), 1)
        if split_idx < len(X):
            model_val = XGBRegressor(**xgb_base_params)
            model_val.fit(X[:split_idx], y[:split_idx])
            val_preds = model_val.predict(X[split_idx:])
            residuals = y[split_idx:] - val_preds
        else:
            # Not enough data for split — fall back to in-sample (rare)
            residuals = np.array([0.0])

        # --- Final model: refit on ALL data for predictions ---
        model = XGBRegressor(**xgb_base_params)
        model.fit(X, y)

        # Iterative prediction with decay dampening (P5: reduce error propagation)
        extended = list(arr)
        result_prices = []
        last_date = dates[-1]
        result_dates = []
        last_real_price = float(arr[-1])
        decay = 0.95  # default; overridden by adaptive threshold in ensemble_forecast

        for d in range(1, days_ahead + 1):
            feat = self._build_features(np.array(extended), len(extended), vol_arr, btc_arr)
            raw_pred = float(model.predict(np.array([feat]))[0])
            raw_pred = max(0.0, raw_pred)
            # Dampen: pull prediction toward last real price exponentially
            pred = last_real_price + (raw_pred - last_real_price) * (decay**d)
            pred = max(0.0, pred)
            result_prices.append(pred)
            extended.append(pred)
            result_dates.append((last_date + timedelta(days=d)).strftime("%Y-%m-%d"))

        # Fat-tailed confidence from honest held-out residuals (P5)
        residual_std = float(np.std(residuals)) if len(residuals) > 1 else float(np.abs(residuals).mean())
        residual_std *= 1.2  # Widen slightly to compensate for decay variance
        z = self._fat_tail_z(residuals)
        result_low = [max(0.0, result_prices[i] - z * residual_std * np.sqrt(i + 1)) for i in range(len(result_prices))]
        result_high = [result_prices[i] + z * residual_std * np.sqrt(i + 1) for i in range(len(result_prices))]

        trend, strength = self._compute_trend(prices[-1], result_prices[-1], prices)

        # SHAP explainability
        explanations = []
        try:
            import shap

            explainer = shap.TreeExplainer(model)
            last_feat = np.array([self._build_features(np.array(extended[:-1]), len(extended) - 1, vol_arr, btc_arr)])
            shap_values = explainer.shap_values(last_feat)

            feature_names = getattr(self, "FEATURE_NAMES", [f"f{i}" for i in range(len(shap_values[0]))])

            # Top 3 most impactful features
            abs_shap = np.abs(shap_values[0])
            top_indices = np.argsort(abs_shap)[-3:][::-1]

            for idx in top_indices:
                fname = feature_names[idx] if idx < len(feature_names) else f"feature_{idx}"
                val = float(shap_values[0][idx])
                explanations.append(
                    {
                        "feature_name": fname,
                        "importance": round(abs(val), 6),
                        "direction": "hausse" if val > 0 else "baisse",
                    }
                )
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

    # Feature names for SHAP explainability (27 features)
    FEATURE_NAMES = [
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
        # Volume features (3)
        "volume_change_1d",
        "volume_sma7_ratio",
        "volume_price_divergence",
        # BTC correlation features (2)
        "btc_return_1d",
        "btc_return_7d",
        # New features for diversity (5)
        "bb_position",
        "vol_ratio_7_30",
        "distance_sma200",
        "day_of_week_sin",
        "day_of_week_cos",
    ]

    @staticmethod
    def _precompute_rsi(prices: np.ndarray, period: int = 14) -> np.ndarray:
        """Pre-compute RSI for all indices in O(N) using Wilder's smoothing."""
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

    @staticmethod
    def _build_features(
        prices: np.ndarray,
        idx: int,
        volumes: Optional[np.ndarray] = None,
        btc_prices: Optional[np.ndarray] = None,
        rsi_array: Optional[np.ndarray] = None,
    ) -> List[float]:
        """Build feature vector for XGBoost at given index.

        Returns 27 features: 7 lagged returns + 10 technical + 3 volume + 2 BTC + 5 new.
        """
        feats: List[float] = []

        # --- Lagged returns J-1 to J-7 (7 features) ---
        for lag in range(1, 8):
            if idx - lag >= 1:
                feats.append((prices[idx - lag] - prices[idx - lag - 1]) / max(prices[idx - lag - 1], 1e-10))
            else:
                feats.append(0.0)

        # --- Volatility 7d (1 feature) ---
        if idx >= 8:
            rets = [(prices[idx - i] - prices[idx - i - 1]) / max(prices[idx - i - 1], 1e-10) for i in range(1, 8)]
            feats.append(float(np.std(rets)))
        else:
            feats.append(0.0)

        # --- RSI 14 (1 feature) --- use pre-computed array if available (P8)
        if rsi_array is not None and idx < len(rsi_array):
            feats.append(float(rsi_array[idx]))
        elif idx >= 15:
            period = 14
            all_deltas = [prices[j] - prices[j - 1] for j in range(1, idx)]
            all_gains = [max(d, 0) for d in all_deltas]
            all_losses = [-min(d, 0) for d in all_deltas]
            if len(all_deltas) >= period:
                avg_gain = sum(all_gains[:period]) / period
                avg_loss = sum(all_losses[:period]) / period
                for k in range(period, len(all_deltas)):
                    avg_gain = (avg_gain * (period - 1) + all_gains[k]) / period
                    avg_loss = (avg_loss * (period - 1) + all_losses[k]) / period
                rs = avg_gain / max(avg_loss, 1e-10)
                feats.append(100 - 100 / (1 + rs))
            else:
                feats.append(50.0)
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
                feats.append((prices[idx - 1] - prices[idx - period - 1]) / max(prices[idx - period - 1], 1e-10))
            else:
                feats.append(0.0)

        # --- Volatility 14d (1 feature) ---
        if idx >= 15:
            rets_14 = [
                (prices[idx - i] - prices[idx - i - 1]) / max(prices[idx - i - 1], 1e-10)
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
            rets_7 = [(prices[idx - i] - prices[idx - i - 1]) / max(prices[idx - i - 1], 1e-10) for i in range(1, 8)]
            feats.append(float(np.mean(rets_7)))
        else:
            feats.append(0.0)

        # --- Volume features (3 features) ---
        if volumes is not None and idx >= 2 and idx - 1 < len(volumes):
            # volume_change_1d
            prev_vol = max(volumes[idx - 2], 1e-10) if idx >= 2 else 1e-10
            feats.append((volumes[idx - 1] - prev_vol) / prev_vol)

            # volume_sma7_ratio
            if idx >= 8:
                vol_window = volumes[max(0, idx - 7) : idx]
                vol_sma = float(np.mean(vol_window)) if vol_window else 1e-10
                feats.append(volumes[idx - 1] / max(vol_sma, 1e-10))
            else:
                feats.append(1.0)

            # volume_price_divergence (P17: continuous score instead of binary)
            if idx >= 2 and prices[idx - 2] > 1e-10 and volumes[idx - 2] > 1e-10:
                price_return = (prices[idx - 1] - prices[idx - 2]) / prices[idx - 2]
                volume_return = (volumes[idx - 1] - volumes[idx - 2]) / volumes[idx - 2]
                feats.append(float(price_return - volume_return))
            else:
                feats.append(0.0)
        else:
            # P2: Use NaN for missing volume features (XGBoost handles NaN natively)
            feats.extend([float("nan"), float("nan"), float("nan")])

        # --- BTC correlation features (2 features) ---
        if btc_prices is not None and idx >= 2 and idx - 1 < len(btc_prices):
            # btc_return_1d
            if idx >= 2:
                feats.append((btc_prices[idx - 1] - btc_prices[idx - 2]) / max(btc_prices[idx - 2], 1e-10))
            else:
                feats.append(0.0)

            # btc_return_7d
            if idx >= 8 and idx - 7 < len(btc_prices):
                feats.append((btc_prices[idx - 1] - btc_prices[idx - 8]) / max(btc_prices[idx - 8], 1e-10))
            else:
                feats.append(0.0)
        else:
            feats.extend([0.0, 0.0])

        # --- Bollinger Band position (1 feature) ---
        # (price - lower) / (upper - lower), where bands = SMA20 ± 2*std
        if idx >= 21:
            window_20 = prices[idx - 20 : idx]
            sma_20 = float(np.mean(window_20))
            std_20 = float(np.std(window_20))
            upper = sma_20 + 2 * std_20
            lower = sma_20 - 2 * std_20
            band_width = upper - lower
            if band_width > 1e-10:
                feats.append((prices[idx - 1] - lower) / band_width)
            else:
                feats.append(0.5)
        else:
            feats.append(0.5)

        # --- Vol ratio 7d/30d (1 feature) ---
        if idx >= 31:
            rets_7 = [(prices[idx - i] - prices[idx - i - 1]) / max(prices[idx - i - 1], 1e-10) for i in range(1, 8)]
            rets_30 = [(prices[idx - i] - prices[idx - i - 1]) / max(prices[idx - i - 1], 1e-10) for i in range(1, 31)]
            vol_7 = float(np.std(rets_7))
            vol_30 = float(np.std(rets_30))
            feats.append(vol_7 / max(vol_30, 1e-10))
        else:
            feats.append(1.0)

        # --- Distance from SMA200 (1 feature) ---
        if idx >= 201:
            sma_200 = float(np.mean(prices[idx - 200 : idx]))
            feats.append((prices[idx - 1] - sma_200) / max(sma_200, 1e-10))
        else:
            feats.append(0.0)

        # --- Day of week (2 features: sin/cos cyclical encoding) ---
        # Assumes daily data; uses index modulo 7 as proxy
        day_idx = idx % 7
        feats.append(float(np.sin(2 * np.pi * day_idx / 7)))
        feats.append(float(np.cos(2 * np.pi * day_idx / 7)))

        return feats

    def _ema_forecast(self, prices: List[float], dates: List[datetime], days_ahead: int) -> ForecastResult:
        """EMA-based forecast using 7-day and 21-day EMAs."""
        arr = np.array(prices, dtype=float)

        ema7 = self._ema(arr, 7)
        ema21 = self._ema(arr, min(21, len(arr)))

        # Slope from last 3 EMA7 values
        if len(ema7) >= 3:
            slope7 = (ema7[-1] - ema7[-3]) / 2
        else:
            slope7 = 0.0

        # P6: EMA7/EMA21 cross signal adjusts slope
        if len(ema21) >= 1 and abs(ema21[-1]) > 1e-10:
            cross_gap = (ema7[-1] - ema21[-1]) / abs(ema21[-1])
            cross_bias = cross_gap * ema7[-1] * 0.1
        else:
            cross_bias = 0.0

        slope = slope7 + cross_bias

        # Residuals for confidence (fat-tailed)
        residuals = arr[-min(30, len(arr)) :] - ema7[-min(30, len(ema7)) :]
        std_r = float(np.std(residuals)) if len(residuals) > 1 else abs(arr[-1]) * 0.02
        z = self._fat_tail_z(residuals)

        last_date = dates[-1]
        result_dates = []
        result_prices = []
        result_low = []
        result_high = []
        base = ema7[-1]

        for i in range(1, days_ahead + 1):
            pred = base + slope * i
            pred = max(0.0, float(pred))
            ci = z * std_r * np.sqrt(i)
            result_dates.append((last_date + timedelta(days=i)).strftime("%Y-%m-%d"))
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

    def _linear_forecast(self, prices: List[float], dates: List[datetime], days_ahead: int) -> ForecastResult:
        """Linear regression on log prices."""
        n = len(prices)
        x = np.arange(n, dtype=float)
        y = np.log(np.maximum(np.array(prices, dtype=float), 1e-10))

        coeffs = np.polyfit(x, y, 1)
        slope, intercept = coeffs
        y_pred = slope * x + intercept
        residuals = y - y_pred
        std_r = float(np.std(residuals))
        z = self._fat_tail_z(residuals)

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
            ci = z * std_r * np.sqrt(1 + 1 / n + (fx - np.mean(x)) ** 2 / np.sum((x - np.mean(x)) ** 2))
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

    def _mean_reversion_forecast(
        self,
        prices: List[float],
        dates: List[datetime],
        days_ahead: int,
    ) -> ForecastResult:
        """Mean-reversion forecast using Ornstein-Uhlenbeck process.

        This model predicts that prices revert to a long-term mean,
        providing genuine diversification against the trend-following models.
        E[X(t)] = mu + (X0 - mu) * exp(-theta * t)
        """
        arr = np.array(prices, dtype=float)
        n = len(arr)

        # Long-term mean: SMA200 if enough data, else median
        if n >= 200:
            mu = float(np.mean(arr[-200:]))
        else:
            mu = float(np.median(arr))

        # Log returns for parameter estimation
        log_prices = np.log(np.maximum(arr, 1e-10))
        log_returns = np.diff(log_prices)

        # Estimate theta (speed of mean reversion) from AR(1) on log prices
        # log(X_t) = c + phi * log(X_{t-1}) + epsilon
        # theta = -ln(phi) per day
        if n >= 10:
            y = log_prices[1:]
            x = log_prices[:-1]
            x_mean = float(np.mean(x))
            y_mean = float(np.mean(y))
            cov_xy = float(np.mean((x - x_mean) * (y - y_mean)))
            var_x = float(np.var(x))
            phi = cov_xy / max(var_x, 1e-15)
            phi = np.clip(phi, 0.01, 0.999)  # Ensure mean-reverting
            theta = -np.log(phi)
        else:
            theta = 0.05  # Default: slow reversion

        # Residual volatility
        sigma = float(np.std(log_returns)) if len(log_returns) > 1 else 0.02

        current_price = float(arr[-1])
        last_date = dates[-1]
        result_dates = []
        result_prices = []
        result_low = []
        result_high = []

        for d in range(1, days_ahead + 1):
            t = float(d)
            # OU expected value (in price space via log transform)
            log_mu = np.log(max(mu, 1e-10))
            log_current = np.log(max(current_price, 1e-10))
            log_expected = log_mu + (log_current - log_mu) * np.exp(-theta * t)
            expected_price = float(np.exp(log_expected))

            # OU variance
            if theta > 1e-10:
                log_var = (sigma**2 / (2 * theta)) * (1 - np.exp(-2 * theta * t))
            else:
                log_var = sigma**2 * t
            log_std = np.sqrt(max(log_var, 0))

            ci_low = float(np.exp(log_expected - 1.96 * log_std))
            ci_high = float(np.exp(log_expected + 1.96 * log_std))

            result_dates.append((last_date + timedelta(days=d)).strftime("%Y-%m-%d"))
            result_prices.append(max(0.0, expected_price))
            result_low.append(max(0.0, ci_low))
            result_high.append(ci_high)

        trend, strength = self._compute_trend(prices[-1], result_prices[-1], prices)

        return ForecastResult(
            dates=result_dates,
            prices=[round(p, 8) for p in result_prices],
            confidence_low=[round(p, 8) for p in result_low],
            confidence_high=[round(p, 8) for p in result_high],
            trend=trend,
            trend_strength=round(strength, 1),
            model_used="mean_reversion",
        )

    def _ewma_volatility_forecast(
        self,
        prices: List[float],
        days_ahead: int,
    ) -> Dict[str, float]:
        """EWMA volatility forecast (RiskMetrics lambda=0.94).

        Returns a dict with per-horizon volatility forecasts.
        Used to calibrate ensemble CIs, not as a price forecast.
        """
        arr = np.array(prices, dtype=float)
        log_returns = np.diff(np.log(np.maximum(arr, 1e-10)))

        if len(log_returns) < 5:
            base_vol = 0.02
            return {d: base_vol * np.sqrt(d) for d in range(1, days_ahead + 1)}

        # EWMA variance
        lam = 0.94
        ewma_var = float(np.var(log_returns))
        for r in log_returns:
            ewma_var = lam * ewma_var + (1 - lam) * r**2

        result = {}
        for d in range(1, days_ahead + 1):
            # EWMA vol scales with sqrt(horizon)
            result[d] = float(np.sqrt(ewma_var * d))

        return result

    def _empirical_quantile_ci(
        self,
        prices: List[float],
        current_price: float,
        days_ahead: int,
        predicted_prices: List[float],
        ewma_vols: Dict[str, float],
    ) -> Tuple[List[float], List[float]]:
        """Compute calibrated CIs using empirical return distribution + EWMA scaling.

        Uses the actual N-day return distribution rather than Gaussian assumptions.
        """
        arr = np.array(prices, dtype=float)
        n = len(arr)

        ci_lows = []
        ci_highs = []

        # Historical daily vol for scaling ratio
        log_returns = np.diff(np.log(np.maximum(arr, 1e-10)))
        hist_daily_vol = float(np.std(log_returns)) if len(log_returns) > 5 else 0.02

        for d in range(1, days_ahead + 1):
            pred_price = predicted_prices[d - 1] if d - 1 < len(predicted_prices) else current_price

            # Compute empirical N-day returns
            if n > d + 5:
                n_day_returns = []
                for i in range(n - d):
                    if arr[i] > 1e-10:
                        n_day_returns.append(arr[i + d] / arr[i] - 1)

                if len(n_day_returns) >= 10:
                    # Empirical quantiles
                    q_low = float(np.percentile(n_day_returns, 2.5))
                    q_high = float(np.percentile(n_day_returns, 97.5))

                    # Scale by EWMA vol ratio (current vs historical)
                    ewma_vol = ewma_vols.get(d, hist_daily_vol * np.sqrt(d))
                    hist_horizon_vol = hist_daily_vol * np.sqrt(d)
                    vol_ratio = ewma_vol / max(hist_horizon_vol, 1e-10)
                    vol_ratio = np.clip(vol_ratio, 0.5, 3.0)

                    # Apply to predicted price
                    ci_low = pred_price * (1 + q_low * vol_ratio)
                    ci_high = pred_price * (1 + q_high * vol_ratio)
                else:
                    # Not enough data: use parametric fallback
                    vol = ewma_vols.get(d, hist_daily_vol * np.sqrt(d))
                    ci_low = pred_price * (1 - 1.96 * vol)
                    ci_high = pred_price * (1 + 1.96 * vol)
            else:
                # Very short history
                vol = ewma_vols.get(d, 0.02 * np.sqrt(d))
                ci_low = pred_price * (1 - 1.96 * vol)
                ci_high = pred_price * (1 + 1.96 * vol)

            ci_lows.append(max(0.0, ci_low))
            ci_highs.append(ci_high)

        return ci_lows, ci_highs

    def _fallback_forecast(self, prices: List[float], days_ahead: int) -> ForecastResult:
        """Random walk fallback for very little data."""
        if not prices:
            return ForecastResult(
                dates=[],
                prices=[],
                confidence_low=[],
                confidence_high=[],
                trend="neutral",
                trend_strength=0,
                model_used="fallback",
            )
        current = prices[-1]
        vol = np.std(prices) / np.mean(prices) if len(prices) > 1 else 0.03
        daily_vol = vol / np.sqrt(max(len(prices), 1))
        drift = 0.0
        if len(prices) >= 2 and prices[0] > 1e-10:
            drift = (prices[-1] / prices[0]) ** (1 / len(prices)) - 1

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
            dates=result_dates,
            prices=result_prices,
            confidence_low=result_low,
            confidence_high=result_high,
            trend=trend,
            trend_strength=round(strength, 1),
            model_used="fallback",
        )

    # ─────────────────────────────────────────────────────────────────
    # Weighting & Helpers
    # ─────────────────────────────────────────────────────────────────

    def _get_or_run_model(
        self,
        model_name: str,
        symbol: Optional[str],
        data_hash: Optional[str],
        days_ahead: int,
        prices: List[float],
        dates: List[datetime],
        volumes: Optional[List[float]] = None,
        btc_prices: Optional[List[float]] = None,
    ) -> ForecastResult:
        """Try to load a cached individual model result; run and cache on miss."""
        # Attempt cache lookup when symbol and data_hash are provided
        if symbol and data_hash:
            cached = self._get_cached_model_result(symbol, model_name, data_hash, days_ahead)
            if cached is not None:
                logger.debug("Cache hit for %s:%s:%s:%d", symbol, model_name, data_hash, days_ahead)
                return cached

        # Run the model
        result = self._run_model_by_name(model_name, prices, dates, days_ahead, volumes, btc_prices)

        # Cache the result for next time
        if symbol and data_hash:
            self._cache_model_result(symbol, model_name, data_hash, days_ahead, result)

        return result

    @staticmethod
    def _get_cached_model_result(symbol: str, model_name: str, data_hash: str, days: int) -> Optional[ForecastResult]:
        """Get cached individual model ForecastResult from Redis (sync)."""
        try:
            r = _get_sync_redis()
            data = r.get(f"{symbol}:{model_name}:{data_hash}:{days}")
            if data:
                return ForecastResult(**json.loads(data))
        except Exception as e:
            logger.debug("Redis model result cache miss %s:%s: %s", symbol, model_name, e)
        return None

    @staticmethod
    def _cache_model_result(
        symbol: str, model_name: str, data_hash: str, days: int, result: ForecastResult, ttl: int = 14400
    ) -> None:
        """Cache individual model ForecastResult in Redis (sync, default 4h TTL)."""
        try:
            r = _get_sync_redis()
            payload = json.dumps(
                {
                    "dates": result.dates,
                    "prices": result.prices,
                    "confidence_low": result.confidence_low,
                    "confidence_high": result.confidence_high,
                    "trend": result.trend,
                    "trend_strength": result.trend_strength,
                    "model_used": result.model_used,
                    "models_detail": result.models_detail,
                    "explanations": result.explanations,
                },
                default=str,
            )
            r.setex(f"{symbol}:{model_name}:{data_hash}:{days}", ttl, payload)
        except Exception as e:
            logger.warning("Failed to cache model result %s:%s: %s", symbol, model_name, e)

    @staticmethod
    def _load_cached_hyperparams(symbol: str) -> Optional[Dict]:
        """Load cached Optuna hyperparameters from Redis (FIX6).

        Reads keys 'hparams:{symbol}:xgboost' and 'hparams:{symbol}:prophet'
        set by the Celery tuning task.
        """
        try:
            r = _get_sync_redis()
            result = {}
            for model in ("xgboost", "prophet"):
                data = r.get(f"hparams:{symbol}:{model}")
                if data:
                    result[model] = json.loads(data)
            return result if result else None
        except Exception as e:
            logger.debug("Failed to load cached hyperparams for %s: %s", symbol, e)
            return None

    def _compute_weights(
        self,
        prices: List[float],
        dates: List[datetime],
        candidates: List[Tuple[str, ForecastResult]],
    ) -> Tuple[List[float], float]:
        """Compute weights via rolling walk-forward backtest across multiple windows.

        Returns:
            (weights, ci_calibration): weights per model and CI calibration factor.
        """
        n_cand = len(candidates)
        n = len(prices)

        if n < 28:
            w = self._compute_weights_single(prices, dates, candidates, split=min(7, n // 2))
            return w, 1.0

        # FIX1: Sliding windows every 14 days up to min(n/2, 180) instead of fixed 3
        window_size = 14
        max_offset = min(n // 2, 180)
        windows = []
        offset = 14
        while offset <= max_offset:
            if n - offset >= 30:  # Need at least 30 days for training
                windows.append(offset)
            offset += 14

        if not windows:
            w = self._compute_weights_single(prices, dates, candidates, split=7)
            return w, 1.0

        # Per-window inverse-MAPE for recency-weighted aggregation
        per_window_inv = []

        # FIX7: track CI coverage during backtest
        ci_covered = 0
        ci_total = 0

        for offset in windows:
            train_prices = prices[:-offset]
            train_dates = dates[:-offset]
            actual = prices[-offset : -offset + window_size] if offset > window_size else prices[-offset:]
            horizon = min(window_size, len(actual))

            window_scores = [0.0] * n_cand
            for ci_idx, (name, _) in enumerate(candidates):
                try:
                    bt = self._run_model_by_name(name, train_prices, train_dates, horizon)
                    pred_prices = bt.prices[:horizon]
                    errs = [
                        abs(pred_prices[j] - actual[j]) / max(actual[j], 1e-10)
                        for j in range(min(len(pred_prices), len(actual)))
                    ]
                    mape = float(np.mean(errs)) * 100 if errs else 50.0

                    # FIX7: check CI coverage
                    for j in range(min(len(bt.confidence_low), len(bt.confidence_high), len(actual))):
                        ci_total += 1
                        if bt.confidence_low[j] <= actual[j] <= bt.confidence_high[j]:
                            ci_covered += 1
                except Exception:
                    mape = 50.0
                window_scores[ci_idx] = 1.0 / max(mape, 0.1)
            per_window_inv.append(window_scores)

        # Exponential recency decay: recent windows get highest weight
        # Windows are ordered oldest→newest (offset decreasing), so index 0 is oldest
        n_windows = len(per_window_inv)
        decay_rate = 0.85
        window_weights = [decay_rate ** (n_windows - 1 - i) for i in range(n_windows)]
        ww_total = sum(window_weights)
        window_weights = [w / ww_total for w in window_weights]

        accumulated_inv = [0.0] * n_cand
        for w_idx in range(n_windows):
            for ci_idx in range(n_cand):
                accumulated_inv[ci_idx] += per_window_inv[w_idx][ci_idx] * window_weights[w_idx]

        total = sum(accumulated_inv)
        if total == 0:
            weights = [1.0 / n_cand] * n_cand
        else:
            weights = [w / total for w in accumulated_inv]

        # FIX1: minimum weight floor of 5% per model to prevent total exclusion
        min_weight = 0.05
        for i in range(n_cand):
            if weights[i] < min_weight:
                weights[i] = min_weight
        # Re-normalize after floor
        total_w = sum(weights)
        weights = [w / total_w for w in weights]

        # FIX7: compute CI calibration factor from backtest coverage
        ci_calibration = 1.0
        if ci_total > 0:
            coverage_rate = ci_covered / ci_total
            target_coverage = 0.95
            if coverage_rate < 0.90:
                ci_calibration = target_coverage / max(coverage_rate, 0.01)
            elif coverage_rate > 0.98:
                ci_calibration = target_coverage / coverage_rate
            ci_calibration = max(0.5, min(2.0, ci_calibration))

        return weights, ci_calibration

    def _compute_weights_single(
        self,
        prices: List[float],
        dates: List[datetime],
        candidates: List[Tuple[str, ForecastResult]],
        split: int = 7,
    ) -> List[float]:
        """Fallback single-window backtest for short histories."""
        n_cand = len(candidates)
        if len(prices) < 14 or split < 1:
            return [1.0 / n_cand] * n_cand

        split = min(split, len(prices) // 2)
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
                mape = 50.0
            mapes.append(max(mape, 0.1))

        inv = [1.0 / m for m in mapes]
        total = sum(inv)
        return [w / total for w in inv]

    def _run_model_by_name(
        self,
        name: str,
        prices: List[float],
        dates: List[datetime],
        days: int,
        volumes: Optional[List[float]] = None,
        btc_prices: Optional[List[float]] = None,
    ) -> ForecastResult:
        """Run a specific model by name."""
        if name == "Prophet":
            return self._prophet_forecast(prices, dates, days, volumes=volumes)
        elif name == "ARIMA":
            return self._arima_forecast(prices, dates, days)
        elif name == "XGBoost":
            return self._xgboost_forecast(prices, dates, days, volumes=volumes, btc_prices=btc_prices)
        elif name == "EMA":
            return self._ema_forecast(prices, dates, days)
        elif name == "MeanReversion":
            return self._mean_reversion_forecast(prices, dates, days)
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
        recent_change = (prices[-1] - prices[-min(7, len(prices))]) / max(prices[-min(7, len(prices))], 1e-10) * 100
        predicted_change = (result.prices[-1] - prices[-1]) / max(prices[-1], 1e-10) * 100
        return abs(recent_change - predicted_change)

    @staticmethod
    def _fat_tail_z(residuals: np.ndarray, confidence: float = 0.95) -> float:
        """Compute critical value using Student-t to account for fat tails.

        Uses excess kurtosis to estimate degrees of freedom. Crypto returns
        typically have kurtosis >> 3, requiring wider confidence intervals.
        Falls back to 1.96 (normal) if scipy unavailable or data too short.
        """
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

            # Excess kurtosis (normal = 0)
            kurt = float(np.mean((arr - mean) ** 4) / std**4) - 3.0

            # Estimate df from excess kurtosis: kurt = 6/(df-4) for Student-t with df>4
            if kurt > 0.5:
                df = max(3.0, 6.0 / kurt + 4.0)
            else:
                df = 30.0  # close to normal

            z = float(student_t.ppf(1 - (1 - confidence) / 2, df))
            return min(z, 5.0)  # cap at 5 to avoid extreme widening
        except Exception:
            return 1.96

    @staticmethod
    def _compute_trend(
        current_price: float,
        final_predicted: float,
        historical: List[float],
        days_ahead: int = 7,
        ctx: Optional[MarketContext] = None,
    ) -> Tuple[str, float]:
        """Compute trend direction and strength using adaptive thresholds."""
        if current_price == 0:
            return "neutral", 0.0
        pct_change = (final_predicted - current_price) / current_price * 100
        if len(historical) >= 5:
            recent_momentum = (historical[-1] - historical[-5]) / historical[-5] * 100
            combined = pct_change * 0.6 + recent_momentum * 0.4
        else:
            combined = pct_change

        # Adaptive threshold: a move is significant if it exceeds noise level
        threshold = at.trend_significance_threshold(ctx, days_ahead) if ctx else 2.0
        strength_scale = at.trend_strength_scale(ctx, days_ahead) if ctx else 0.2

        if combined > threshold:
            trend = "bullish"
        elif combined < -threshold:
            trend = "bearish"
        else:
            trend = "neutral"
        strength = min(100.0, abs(combined) / max(strength_scale, 0.01) * 50)
        return trend, strength
