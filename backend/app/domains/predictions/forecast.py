import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.redis_client import (
    _data_hash,
    cache_ensemble,
    cache_prediction,
    get_cached_ensemble,
    get_cached_prediction,
)
from app.domains.market_data.fear_greed import fetch_fear_greed_index
from app.domains.market_data.history.reader import local_series
from app.domains.market_data.prices.service import price_feed
from app.domains.portfolio.models import AssetType
from app.domains.predictions.adjustments import apply_liquidity, apply_regime, clamp_intervals, with_liquidity_warning
from app.domains.predictions.core import PredictionCore
from app.domains.predictions.fallbacks import (
    daily_volatility,
    ema20_forecast,
    empty_prediction,
    random_walk_forecast,
    smart_round,
)
from app.domains.predictions.levels import support_resistance
from app.domains.predictions.prediction_log import log_prediction
from app.domains.predictions.recommendation import generate_recommendation
from app.domains.predictions.types import HISTORY_DAYS, ForecastPoint, PricePrediction
from app.ml import adaptive_thresholds as at
from app.ml.forecaster import ForecastResult
from app.ml.market_context import MarketContext, compute_market_context

logger = logging.getLogger(__name__)

MAX_MOVE_PCT = 50


@dataclass
class _MarketInputs:
    dates: list[datetime]
    prices: list[float]
    volumes: list[float] | None
    btc_prices: list[float] | None
    fear_greed: int | None
    btc_dominance: float | None
    ctx: MarketContext | None


@dataclass
class _Forecast:
    predictions: list[ForecastPoint]
    trend: str
    trend_strength: float
    model_used: str
    models_detail: list[dict[str, Any]]
    explanations: list[dict[str, Any]]


async def _cached_prediction(symbol: str, days_ahead: int) -> PricePrediction | None:
    cached = await get_cached_prediction(symbol, days_ahead)
    if not cached:
        return None
    cached_preds = cached.get("predictions", [])
    cached_price = cached.get("current_price", 0)
    if cached_preds and cached_price > 0:
        cached_change_pct = (cached_preds[-1]["price"] - cached_price) / cached_price * 100
        if abs(cached_change_pct) > MAX_MOVE_PCT:
            logger.warning(
                "SANITY CHECK (cache): %s cached prediction unrealistic (%.1f%% in %dd). Invalidating cache entry.",
                symbol,
                cached_change_pct,
                days_ahead,
            )
            return None
    return PricePrediction(**{k: v for k, v in cached.items() if not k.startswith("_")})


async def _market_inputs(symbol: str, asset_type: AssetType) -> _MarketInputs:
    history = await local_series(symbol, HISTORY_DAYS)
    btc_prices = None
    if asset_type == AssetType.CRYPTO and symbol.upper() != "BTC":
        btc_prices = (await local_series("BTC", HISTORY_DAYS)).prices or None
    fear_greed = await fetch_fear_greed_index()
    btc_dominance = None
    try:
        btc_dominance = await price_feed.btc_dominance()
    except Exception as exc:  # noqa: BLE001
        logger.debug("BTC dominance fetch failed (optional enrichment): %s", exc)
    prices = history.prices
    ctx = compute_market_context(prices, symbol, asset_type.value, fear_greed) if prices and len(prices) >= 30 else None
    return _MarketInputs(history.dates, prices, history.volumes, btc_prices, fear_greed, btc_dominance, ctx)


def _points(result: ForecastResult) -> list[ForecastPoint]:
    return [
        {
            "date": result.dates[i],
            "price": smart_round(result.prices[i]),
            "confidence_low": smart_round(result.confidence_low[i]),
            "confidence_high": smart_round(result.confidence_high[i]),
        }
        for i in range(len(result.dates))
    ]


def _clamped(predictions: list[ForecastPoint], current_price: float) -> list[ForecastPoint]:
    low = current_price * (1 - MAX_MOVE_PCT / 100)
    high = current_price * (1 + MAX_MOVE_PCT / 100)
    return [
        {
            **p,
            **{key: smart_round(min(max(p[key], low), high)) for key in ("price", "confidence_low", "confidence_high")},
        }
        for p in predictions
    ]


def _sanity_checked(
    result: ForecastResult, prices: list[float], current_price: float, days_ahead: int, symbol: str
) -> _Forecast:
    predictions = _points(result)
    if predictions and current_price > 0:
        ensemble_change_pct = (predictions[-1]["price"] - current_price) / current_price * 100
        if abs(ensemble_change_pct) > MAX_MOVE_PCT:
            logger.warning(
                "SANITY CHECK: %s ensemble prediction unrealistic (%.1f%% in %dd). Falling back to EMA-20.",
                symbol,
                ensemble_change_pct,
                days_ahead,
            )
            ema_predictions, ema_trend, ema_strength = ema20_forecast(prices, current_price, days_ahead)
            if ema_predictions:
                detail = [{"name": "EMA-20 (sanity fallback)", "weight_pct": 100, "mape": None, "trend": ema_trend}]
                return _Forecast(ema_predictions, ema_trend, ema_strength, "ema20_sanity_fallback", detail, [])
            predictions = _clamped(predictions, current_price)
    return _Forecast(
        predictions, result.trend, result.trend_strength, result.model_used, result.models_detail, result.explanations
    )


async def _levels(symbol: str, asset_type: AssetType, prices: list[float], current_price: float) -> tuple[float, float]:
    if prices and len(prices) >= 10:
        return support_resistance(prices, current_price)
    vol = await daily_volatility(symbol, asset_type)
    return max(0, current_price * (1 - vol * 5)), current_price * (1 + vol * 5)


class ForecastMixin(PredictionCore):
    async def _ensemble_result(self, symbol: str, days_ahead: int, market: _MarketInputs) -> ForecastResult:
        dhash = _data_hash(market.prices)
        cached_ens = await get_cached_ensemble(symbol, dhash, days_ahead)
        if cached_ens:
            return ForecastResult(**cached_ens)
        result = await asyncio.to_thread(
            self.forecaster.ensemble_forecast,
            market.prices,
            market.dates,
            days_ahead,
            symbol=symbol,
            data_hash=dhash,
            volumes=market.volumes,
            btc_prices=market.btc_prices,
            fear_greed=market.fear_greed,
            btc_dominance=market.btc_dominance,
            market_context=market.ctx,
        )
        await cache_ensemble(
            symbol,
            dhash,
            days_ahead,
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
        )
        return result

    async def _forecast(
        self, symbol: str, asset_type: AssetType, days_ahead: int, current_price: float, market: _MarketInputs
    ) -> _Forecast:
        if market.prices and len(market.prices) >= 5:
            result = await self._ensemble_result(symbol, days_ahead, market)
            return _sanity_checked(result, market.prices, current_price, days_ahead, symbol)
        logger.warning("No historical data for %s, using random walk", symbol)
        predictions, trend, trend_strength = await random_walk_forecast(symbol, current_price, asset_type, days_ahead)
        return _Forecast(predictions, trend, trend_strength, "random_walk", [], [])

    async def get_price_prediction(
        self,
        symbol: str,
        asset_type: AssetType,
        days_ahead: int = 7,
    ) -> PricePrediction:
        """Prévision servie depuis le cache sauf si elle annonce plus de ±50 % ; sinon ensemble de modèles
        (cache d'ensemble par empreinte des cours, repli EMA-20 au-delà de ±50 %, marche déterministe sans
        historique), corrigée du régime et de la liquidité, journalisée puis mise en cache."""
        cached = await _cached_prediction(symbol, days_ahead)
        if cached is not None:
            return cached

        current_price = await self._get_current_price(symbol, asset_type)
        if current_price is None:
            return empty_prediction(symbol)

        market = await _market_inputs(symbol, asset_type)
        forecast = await self._forecast(symbol, asset_type, days_ahead, current_price, market)
        support, resistance = await _levels(symbol, asset_type, market.prices, current_price)

        trend = forecast.trend
        regime_info: dict[str, Any] | None = None
        if market.prices and len(market.prices) >= 7:
            mtf = await asyncio.to_thread(
                self.regime_detector.detect_multi_timeframe,
                market.prices,
                symbol,
                market.fear_greed,
                market.btc_dominance,
                asset_type=asset_type.value,
                market_context=market.ctx,
            )
            regime_info, trend = apply_regime(mtf, forecast.predictions, trend, current_price, market.ctx, days_ahead)

        liquidity_warning = apply_liquidity(market.volumes, forecast.predictions)
        clamp_intervals(forecast.predictions)
        regime_info = with_liquidity_warning(regime_info, liquidity_warning)

        recommendation = generate_recommendation(
            trend, forecast.trend_strength, current_price, support, resistance, regime_info=regime_info
        )
        await log_prediction(
            symbol=symbol,
            asset_type=asset_type,
            model_used=forecast.model_used,
            predictions=forecast.predictions,
            current_price=current_price,
            days_ahead=days_ahead,
            models_detail=forecast.models_detail,
            fear_greed=market.fear_greed,
            btc_dominance=market.btc_dominance,
            regime_info=regime_info,
            prices=market.prices,
        )
        return await _cached_result(
            symbol, days_ahead, current_price, forecast, trend, support, resistance, recommendation, regime_info, market
        )


async def _cached_result(
    symbol: str,
    days_ahead: int,
    current_price: float,
    forecast: _Forecast,
    trend: str,
    support: float,
    resistance: float,
    recommendation: str,
    regime_info: dict[str, Any] | None,
    market: _MarketInputs,
) -> PricePrediction:
    result_dict = {
        "symbol": symbol,
        "current_price": current_price,
        "predictions": forecast.predictions,
        "trend": trend,
        "trend_strength": round(forecast.trend_strength, 1),
        "support_level": smart_round(support),
        "resistance_level": smart_round(resistance),
        "recommendation": recommendation,
        "model_used": forecast.model_used,
        "models_detail": forecast.models_detail or [],
        "regime_info": regime_info,
        "display_thresholds": at.build_display_thresholds(market.ctx),
    }
    await cache_prediction(symbol, days_ahead, result_dict)
    return PricePrediction(
        symbol=symbol,
        current_price=current_price,
        predictions=forecast.predictions,
        trend=trend,
        trend_strength=round(forecast.trend_strength, 1),
        support_level=smart_round(support),
        resistance_level=smart_round(resistance),
        recommendation=recommendation,
        model_used=forecast.model_used,
        models_detail=forecast.models_detail or [],
        explanations=forecast.explanations or [],
        regime_info=regime_info,
        display_thresholds=at.build_display_thresholds(market.ctx),
        _history_dates=market.dates,
        _history_prices=market.prices,
    )
