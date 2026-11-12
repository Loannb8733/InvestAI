import logging
from datetime import datetime
from functools import partial
from typing import Any

from app.ml.forecasting import confidence
from app.ml.forecasting.cache import cached_hyperparams, run_cached
from app.ml.forecasting.models.arima import arima_forecast
from app.ml.forecasting.models.prophet import prophet_forecast
from app.ml.forecasting.models.simple import ema_forecast, fallback_forecast, linear_forecast, mean_reversion_forecast
from app.ml.forecasting.models.xgboost import xgboost_forecast
from app.ml.forecasting.trend import compute_trend
from app.ml.forecasting.types import Candidate, ForecastResult
from app.ml.forecasting.weighting import compute_weights, quick_mape
from app.ml.market_context import MarketContext

logger = logging.getLogger(__name__)


def _available(module: str, attribute: str) -> bool:
    try:
        getattr(__import__(module, fromlist=[attribute]), attribute)
        return True
    except (ImportError, AttributeError):
        logger.warning("%s.%s not available", module, attribute)
        return False


def _combined_prices(candidates: list[Candidate], weights: list[float], n_days: int) -> list[float]:
    combined = [0.0] * n_days
    for (_name, res), w in zip(candidates, weights, strict=False):
        for i in range(min(n_days, len(res.prices))):
            combined[i] += res.prices[i] * w
    return combined


def _interval(
    prices: list[float],
    candidates: list[Candidate],
    weights: list[float],
    combined: list[float],
    ctx: MarketContext | None,
    calibration: float,
) -> confidence.Interval:
    n_days = len(combined)
    interval = confidence.combine_native_ci(candidates, weights, combined, n_days)
    if interval is None:
        vols = confidence.ewma_volatility_forecast(prices, n_days)
        interval = confidence.empirical_quantile_ci(prices, prices[-1], n_days, combined, vols)
    if ctx:
        confidence.apply_floor(ctx, combined, interval)
    if calibration != 1.0:
        confidence.calibrate(combined, interval, calibration)
    return interval


def _vote(candidates: list[Candidate], weights: list[float]) -> str:
    scores = {"bullish": 0.0, "bearish": 0.0, "neutral": 0.0}
    for (_name, res), w in zip(candidates, weights, strict=False):
        scores[res.trend] += w
    return max(scores, key=lambda trend: scores[trend])


def _details(
    candidates: list[Candidate], weights: list[float], mapes: list[float], prices: list[float]
) -> list[dict[str, Any]]:
    details = []
    for idx, ((name, res), w) in enumerate(zip(candidates, weights, strict=False)):
        mape = mapes[idx] if idx < len(mapes) else quick_mape(prices, res)
        details.append({"name": name, "weight_pct": round(w * 100), "mape": round(mape, 1), "trend": res.trend})
    return details


class PriceForecaster:
    """Prévision de prix par un ensemble de modèles pondérés selon leur erreur de backtest."""

    def __init__(self, hyperparams: dict[str, Any] | None = None) -> None:
        self.prophet_available = _available("prophet", "Prophet")
        self.xgboost_available = _available("xgboost", "XGBRegressor")
        self.arima_available = _available("statsmodels.tsa.arima.model", "ARIMA")
        self.auto_arima_available = _available("pmdarima", "auto_arima")
        self.hyperparams: dict[str, Any] = hyperparams or {}

    def run_model(
        self,
        name: str,
        prices: list[float],
        dates: list[datetime],
        days: int,
        volumes: list[float] | None = None,
        btc_prices: list[float] | None = None,
    ) -> ForecastResult:
        """Prévision d'un seul modèle ; un nom inconnu donne la régression linéaire."""
        if name == "Prophet":
            return prophet_forecast(prices, dates, days, self.hyperparams.get("prophet", {}), volumes=volumes)
        if name == "ARIMA":
            return arima_forecast(prices, dates, days, self.auto_arima_available)
        if name == "XGBoost":
            params = self.hyperparams.get("xgboost", {})
            return xgboost_forecast(prices, dates, days, params, volumes=volumes, btc_prices=btc_prices)
        if name == "EMA":
            return ema_forecast(prices, dates, days)
        if name == "MeanReversion":
            return mean_reversion_forecast(prices, dates, days)
        return linear_forecast(prices, dates, days)

    def forecast(self, prices: list[float], dates: list[datetime], days_ahead: int = 7) -> ForecastResult:
        """Prophet seul dès 14 points, sinon régression linéaire ; marche aléatoire sous 5 points."""
        if len(prices) < 5:
            return fallback_forecast(prices, days_ahead)
        if self.prophet_available and len(prices) >= 14:
            try:
                return prophet_forecast(prices, dates, days_ahead, self.hyperparams.get("prophet", {}))
            except Exception as e:  # noqa: BLE001
                logger.warning("Prophet failed: %s", e)
        return linear_forecast(prices, dates, days_ahead)

    def _candidates(
        self,
        prices: list[float],
        dates: list[datetime],
        days_ahead: int,
        cache_key: tuple[str | None, str | None],
        volumes: list[float] | None,
        btc_prices: list[float] | None,
    ) -> list[Candidate]:
        n = len(prices)
        enabled = (
            ("Prophet", self.prophet_available and n >= 14),
            ("ARIMA", self.arima_available and n >= 20),
            ("XGBoost", self.xgboost_available and n >= 30),
            ("EMA", n >= 7),
            ("Linear", True),
            ("MeanReversion", n >= 30),
        )
        candidates: list[Candidate] = []
        for name, active in enabled:
            if not active:
                continue
            extra = (volumes, btc_prices) if name == "XGBoost" else (None, None)
            run = partial(self.run_model, name, prices, dates, days_ahead, *extra)
            try:
                result = run_cached(name, *cache_key, days_ahead, run)
            except Exception as e:  # noqa: BLE001
                logger.warning("%s ensemble: %s", name, e)
                continue
            candidates.append((name, result))
        return candidates

    def ensemble_forecast(
        self,
        prices: list[float],
        dates: list[datetime],
        days_ahead: int = 7,
        symbol: str | None = None,
        data_hash: str | None = None,
        volumes: list[float] | None = None,
        btc_prices: list[float] | None = None,
        fear_greed: int | None = None,
        btc_dominance: float | None = None,
        market_context: MarketContext | None = None,
    ) -> ForecastResult:
        """Moyenne des modèles disponibles pondérée par backtest, intervalle par variance totale, tendance votée.

        ``fear_greed`` et ``btc_dominance`` sont acceptés pour les appelants mais n'entrent dans aucun modèle.
        """
        if len(prices) < 5:
            return fallback_forecast(prices, days_ahead)
        if symbol:
            tuned = cached_hyperparams(symbol)
            if tuned:
                self.hyperparams = {**self.hyperparams, **tuned}
        candidates = self._candidates(prices, dates, days_ahead, (symbol, data_hash), volumes, btc_prices)
        if not candidates:
            return fallback_forecast(prices, days_ahead)
        if len(candidates) == 1:
            name, result = candidates[0]
            result.model_used = name.lower()
            result.models_detail = [{"name": name, "weight_pct": 100, "mape": 0, "trend": result.trend}]
            return result
        weights, calibration, mapes = compute_weights(prices, dates, candidates, self.run_model)
        combined = _combined_prices(candidates, weights, days_ahead)
        low, high = _interval(prices, candidates, weights, combined, market_context, calibration)
        strength = compute_trend(prices[-1], combined[-1], prices, days_ahead=days_ahead, ctx=market_context)[1]
        details = _details(candidates, weights, mapes, prices)
        parts = ", ".join(f"{d['name']}: {d['weight_pct']}%" for d in details)
        return ForecastResult(
            dates=candidates[0][1].dates[:days_ahead],
            prices=[round(p, 8) for p in combined],
            confidence_low=[round(max(0, p), 8) for p in low],
            confidence_high=[round(p, 8) for p in high],
            trend=_vote(candidates, weights),
            trend_strength=round(strength, 1),
            model_used=f"ensemble ({parts})",
            models_detail=details,
        )
