"""ML Prediction service for price forecasting and anomaly detection."""

import asyncio
import logging
import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

import httpx
import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import (
    _data_hash,
    cache_ensemble,
    cache_history,
    cache_prediction,
    get_cached_ensemble,
    get_cached_history,
    get_cached_prediction,
)
from app.ml import adaptive_thresholds as at
from app.ml.anomaly_detector import AnomalyDetector
from app.ml.forecaster import PriceForecaster
from app.ml.historical_data import HistoricalDataFetcher
from app.ml.market_context import MarketContext, compute_market_context
from app.ml.regime_detector import MarketRegimeDetector, RegimeConfig, _rsi
from app.models.asset import Asset, AssetType
from app.models.portfolio import Portfolio
from app.services.metrics_service import is_cash_like, is_safe_haven
from app.services.prediction_cycles import PredictionCyclesMixin
from app.services.prediction_types import _HISTORY_DAYS  # noqa: F401 — re-exported
from app.services.prediction_types import (  # noqa: F401 — re-exported for compatibility
    AnomalyDetection,
    MarketSentiment,
    PricePrediction,
)
from app.services.price_service import PriceService

logger = logging.getLogger(__name__)


class PredictionService(PredictionCyclesMixin):
    """Service for ML-based predictions and analysis."""

    def __init__(self):
        self.price_service = PriceService()
        self.forecaster = PriceForecaster()
        self.anomaly_detector = AnomalyDetector()
        self.regime_detector = MarketRegimeDetector()
        self.data_fetcher = HistoricalDataFetcher(
            coingecko_api_key=getattr(self.price_service, "coingecko_api_key", None)
        )

    async def get_price_prediction(
        self,
        symbol: str,
        asset_type: AssetType,
        days_ahead: int = 7,
    ) -> PricePrediction:
        """Generate price predictions using ML models."""
        # Check cache first
        cached = await get_cached_prediction(symbol, days_ahead)
        if cached:
            # ── C-21 Sanity check on cached result ────────────────────────
            # Apply the ±50% guard even for cache hits so that stale entries
            # produced before the sanity check was introduced are never served.
            cached_preds = cached.get("predictions", [])
            cached_price = cached.get("current_price", 0)
            if cached_preds and cached_price > 0:
                final_cached = cached_preds[-1]["price"]
                cached_change_pct = (final_cached - cached_price) / cached_price * 100
                if abs(cached_change_pct) > 50:
                    logger.warning(
                        "SANITY CHECK (cache): %s cached prediction unrealistic "
                        "(%.1f%% in %dd). Invalidating cache entry.",
                        symbol,
                        cached_change_pct,
                        days_ahead,
                    )
                    # Discard the stale cache entry and fall through to recompute
                    cached = None
            if cached is not None:
                return PricePrediction(**{k: v for k, v in cached.items() if not k.startswith("_")})

        current_price = await self._get_current_price(symbol, asset_type)

        if current_price == 0:
            return self._empty_prediction(symbol)

        # Fetch historical data (365 days for better ML training)
        cached_hist = await get_cached_history(symbol, asset_type.value, _HISTORY_DAYS)
        if cached_hist:
            dates = [datetime.fromisoformat(d) for d in cached_hist["dates"]]
            prices = cached_hist["prices"]
            volumes = cached_hist.get("volumes")
        else:
            hist_result = await self.data_fetcher.get_history_extended(symbol, asset_type.value, days=_HISTORY_DAYS)
            dates, prices, volumes = (
                hist_result.dates,
                hist_result.prices,
                hist_result.volumes,
            )
            if dates and prices:
                cache_payload = {
                    "dates": [d.isoformat() for d in dates],
                    "prices": prices,
                }
                if volumes:
                    cache_payload["volumes"] = volumes
                await cache_history(symbol, asset_type.value, _HISTORY_DAYS, cache_payload)

        # Fetch BTC prices for altcoin correlation (crypto only, not BTC itself)
        btc_prices = None
        if asset_type == AssetType.CRYPTO and symbol.upper() != "BTC":
            btc_cached = await get_cached_history("BTC", "crypto", _HISTORY_DAYS)
            if btc_cached:
                btc_prices = btc_cached["prices"]
            else:
                btc_dates, btc_prices_raw = await self.data_fetcher.get_history("BTC", "crypto", days=_HISTORY_DAYS)
                if btc_dates and btc_prices_raw:
                    btc_prices = btc_prices_raw
                    await cache_history(
                        "BTC",
                        "crypto",
                        _HISTORY_DAYS,
                        {
                            "dates": [d.isoformat() for d in btc_dates],
                            "prices": btc_prices_raw,
                        },
                    )

        # Fetch Fear & Greed Index
        fear_greed = None
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get("https://api.alternative.me/fng/?limit=1")
                if resp.status_code == 200:
                    fng_data = resp.json()
                    if fng_data.get("data"):
                        fear_greed = int(fng_data["data"][0].get("value", 50))
        except Exception:
            pass

        # Fetch BTC dominance
        btc_dominance = None
        try:
            btc_dominance = await self.data_fetcher.get_btc_dominance()
        except Exception:
            pass

        # ── Compute MarketContext once for the entire pipeline ──────
        ctx: Optional[MarketContext] = None
        if prices and len(prices) >= 30:
            ctx = compute_market_context(prices, symbol, asset_type.value, fear_greed)

        # Use enough decimal places for micro-price assets (PEPE, SHIB, etc.)
        def smart_round(v: float) -> float:
            if v == 0:
                return 0.0
            if abs(v) < 0.01:
                return round(v, 10)
            return round(v, 2)

        if prices and len(prices) >= 5:
            # Check ensemble cache before running expensive ML models
            dhash = _data_hash(prices)
            cached_ens = await get_cached_ensemble(symbol, dhash, days_ahead)
            if cached_ens:
                from app.ml.forecaster import ForecastResult

                result = ForecastResult(**cached_ens)
            else:
                # ensemble_forecast fits Prophet/ARIMA/XGBoost synchronously (CPU-bound,
                # seconds). Offload to a thread so it never blocks the async event loop /
                # other concurrent requests on the worker.
                result = await asyncio.to_thread(
                    self.forecaster.ensemble_forecast,
                    prices,
                    dates,
                    days_ahead,
                    symbol=symbol,
                    data_hash=dhash,
                    volumes=volumes,
                    btc_prices=btc_prices,
                    fear_greed=fear_greed,
                    btc_dominance=btc_dominance,
                    market_context=ctx,
                )
                # Cache the ensemble result for future requests
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

            predictions = [
                {
                    "date": result.dates[i],
                    "price": smart_round(result.prices[i]),
                    "confidence_low": smart_round(result.confidence_low[i]),
                    "confidence_high": smart_round(result.confidence_high[i]),
                }
                for i in range(len(result.dates))
            ]

            # ── Sanity check: reject unrealistic ensemble predictions ─────
            # Applied to BOTH cache hits and freshly computed results.
            # If 7d predicted move > ±50%, fallback to EMA-20 extrapolation.
            if predictions and current_price > 0:
                final_price = predictions[-1]["price"]
                ensemble_change_pct = (final_price - current_price) / current_price * 100
                if abs(ensemble_change_pct) > 50:
                    logger.warning(
                        "SANITY CHECK: %s ensemble prediction unrealistic " "(%.1f%% in %dd). Falling back to EMA-20.",
                        symbol,
                        ensemble_change_pct,
                        days_ahead,
                    )
                    predictions, ema_trend, ema_strength = self._ema20_fallback(
                        prices,
                        current_price,
                        days_ahead,
                        smart_round,
                    )
                    if predictions:
                        result_trend = ema_trend
                        result_strength = ema_strength
                        result_model = "ema20_sanity_fallback"
                        result_detail = [
                            {
                                "name": "EMA-20 (sanity fallback)",
                                "weight_pct": 100,
                                "mape": None,
                                "trend": ema_trend,
                            }
                        ]
                        result_explanations = []
                    else:
                        # EMA fallback also failed — keep original but clamp
                        result_trend = result.trend
                        result_strength = result.trend_strength
                        result_model = result.model_used
                        result_detail = result.models_detail
                        result_explanations = getattr(result, "explanations", [])
                else:
                    result_trend = result.trend
                    result_strength = result.trend_strength
                    result_model = result.model_used
                    result_detail = result.models_detail
                    result_explanations = getattr(result, "explanations", [])
            else:
                result_trend = result.trend
                result_strength = result.trend_strength
                result_model = result.model_used
                result_detail = result.models_detail
                result_explanations = getattr(result, "explanations", [])

            trend = result_trend
            trend_strength = result_strength
            model_used = result_model
            models_detail = result_detail
            explanations = result_explanations
        else:
            # Fallback: simple random walk when no historical data
            logger.warning("No historical data for %s, using random walk", symbol)
            predictions, trend, trend_strength = await self._random_walk_fallback(
                symbol, current_price, asset_type, days_ahead
            )
            model_used = "random_walk"
            models_detail = []
            explanations = []

        # Support/resistance from pivot points + price level clustering
        if prices and len(prices) >= 10:
            support, resistance = self._compute_support_resistance(prices, current_price)
        else:
            vol = await self._get_daily_volatility(symbol, asset_type)
            support = max(0, current_price * (1 - vol * 5))
            resistance = current_price * (1 + vol * 5)

        # Regime detection — multi-timeframe (P15) + adjust CI and recommendation
        regime_info = None
        if prices and len(prices) >= 7:
            mtf = self.regime_detector.detect_multi_timeframe(
                prices,
                symbol,
                fear_greed,
                btc_dominance,
                asset_type=asset_type.value,
                market_context=ctx,
            )
            daily_regime = mtf["daily"]
            regime_info = {
                "dominant_regime": daily_regime.dominant_regime,
                "confidence": daily_regime.confidence,
                "probabilities": daily_regime.probabilities,
                "timeframe_alignment": mtf.get("timeframe_alignment", "unknown"),
                "weekly_regime": mtf["weekly"].dominant_regime if mtf.get("weekly") else None,
                "note": mtf.get("note", ""),
            }

            # ── Post-ensemble regime correction ──────────────────────────
            # When regime disagrees with ensemble direction at high confidence,
            # dampen the prediction toward flat. NOT double-counting because:
            # regime uses 7 indicators (RSI, MACD, Bollinger, MA cross, momentum,
            # vol, F&G) while most ensemble models use only raw price history.
            predicted_change_pct = (
                (predictions[-1]["price"] - current_price) / current_price * 100
                if current_price > 0 and predictions
                else 0.0
            )
            # Bearish/top regime but prediction is positive (any upward prediction)
            if (
                daily_regime.confidence > 0.6
                and daily_regime.dominant_regime in ("bearish", "top")
                and predicted_change_pct > 0
                and predictions
                and ctx
            ):
                adj_factor = at.regime_adjustment_factor(
                    ctx,
                    daily_regime.dominant_regime,
                    daily_regime.confidence,
                    predicted_change_pct,
                )
                # Scale adjustment: full for bullish trend, partial for neutral
                if trend != "bullish":
                    adj_factor *= 0.6  # lighter for neutral predictions

                for pred in predictions:
                    original_price = pred["price"]
                    dampened = current_price + (original_price - current_price) * (1.0 - adj_factor)
                    pred["price"] = smart_round(dampened)
                    if original_price != 0:
                        ratio = dampened / original_price
                        pred["confidence_low"] = smart_round(pred["confidence_low"] * ratio)
                        pred["confidence_high"] = smart_round(pred["confidence_high"] * ratio)

                # Re-evaluate trend after dampening
                new_final = predictions[-1]["price"]
                pct = (new_final - current_price) / current_price * 100 if current_price > 0 else 0
                threshold = at.trend_significance_threshold(ctx, days_ahead)
                if pct > threshold:
                    trend = "bullish"
                elif pct < -threshold:
                    trend = "bearish"
                else:
                    trend = "neutral"

                regime_info["regime_price_adjustment"] = True
                regime_info["adjustment_factor"] = round(adj_factor, 3)

            # Bullish/bottom regime but prediction is negative
            elif (
                daily_regime.confidence > 0.6
                and daily_regime.dominant_regime in ("bullish", "bottom")
                and predicted_change_pct < 0
                and predictions
                and ctx
            ):
                adj_factor = (
                    at.regime_adjustment_factor(
                        ctx,
                        daily_regime.dominant_regime,
                        daily_regime.confidence,
                        predicted_change_pct,
                    )
                    * 0.5
                )  # Lighter: recovery signals are less reliable
                for pred in predictions:
                    original_price = pred["price"]
                    dampened = current_price + (original_price - current_price) * (1.0 - adj_factor)
                    pred["price"] = smart_round(dampened)
                    if original_price != 0:
                        ratio = dampened / original_price
                        pred["confidence_low"] = smart_round(pred["confidence_low"] * ratio)
                        pred["confidence_high"] = smart_round(pred["confidence_high"] * ratio)

                regime_info["regime_price_adjustment"] = True
                regime_info["adjustment_factor"] = round(adj_factor, 3)

            # ── Bearish/bullish drift ──────────────────────────────────
            # When regime is strongly bearish and recent momentum is negative,
            # apply a daily downward drift to counter mean-reversion bias.
            # This makes predictions reflect the ongoing trend direction.
            if (
                daily_regime.confidence > 0.5
                and daily_regime.dominant_regime in ("bearish", "top")
                and ctx
                and ctx.momentum_30d < -0.05  # at least -5% in 30 days
                and predictions
            ):
                daily_drift = at.bearish_drift_factor(ctx)
                # Scale by regime confidence (stronger bear → stronger drift)
                drift_scale = min(1.0, daily_regime.confidence * 1.2)
                for i, pred in enumerate(predictions):
                    day_num = i + 1
                    drift_multiplier = 1.0 - daily_drift * drift_scale * day_num
                    pred["price"] = smart_round(pred["price"] * drift_multiplier)
                    pred["confidence_low"] = smart_round(pred["confidence_low"] * drift_multiplier)
                    pred["confidence_high"] = smart_round(pred["confidence_high"] * drift_multiplier)

                # Re-evaluate trend after drift
                if predictions:
                    new_final = predictions[-1]["price"]
                    pct = (new_final - current_price) / current_price * 100 if current_price > 0 else 0
                    threshold = at.trend_significance_threshold(ctx, days_ahead)
                    if pct > threshold:
                        trend = "bullish"
                    elif pct < -threshold:
                        trend = "bearish"
                    else:
                        trend = "neutral"

            # Adaptive CI widening for uncertain regimes
            ci_widen = (
                at.ci_widening_factor(ctx, daily_regime.dominant_regime, daily_regime.confidence) if ctx else 0.05
            )
            if ci_widen > 0.01:
                for pred in predictions:
                    width = pred["confidence_high"] - pred["confidence_low"]
                    pred["confidence_low"] = smart_round(pred["confidence_low"] - width * ci_widen)
                    pred["confidence_high"] = smart_round(pred["confidence_high"] + width * ci_widen)

            # Widen CI when daily and weekly diverge (conflicting signals)
            if mtf.get("timeframe_alignment") == "divergent":
                for pred in predictions:
                    width = pred["confidence_high"] - pred["confidence_low"]
                    pred["confidence_low"] = smart_round(pred["confidence_low"] - width * 0.05)
                    pred["confidence_high"] = smart_round(pred["confidence_high"] + width * 0.05)

        # P16: Liquidity analysis from 24h volume
        liquidity_warning = None
        if volumes and len(volumes) >= 1:
            avg_recent_volume = float(np.mean(volumes[-7:])) if len(volumes) >= 7 else float(volumes[-1])
            # Volume < 1M EUR → illiquid, slippage risk
            if avg_recent_volume < 1_000_000:
                liquidity_warning = (
                    f"Faible liquidité — volume moyen 7j: {avg_recent_volume:,.0f} EUR. "
                    "Slippage probable sur les ordres importants."
                )
                # Widen CI proportionally to lack of liquidity
                liquidity_factor = max(0.05, min(0.25, 1.0 - avg_recent_volume / 1_000_000))
                for pred in predictions:
                    width = pred["confidence_high"] - pred["confidence_low"]
                    pred["confidence_low"] = smart_round(pred["confidence_low"] - width * liquidity_factor)
                    pred["confidence_high"] = smart_round(pred["confidence_high"] + width * liquidity_factor)

        # Sanitize confidence intervals after all adjustments
        for pred in predictions:
            pred["confidence_low"] = min(pred["confidence_low"], pred["price"])
            pred["confidence_high"] = max(pred["confidence_high"], pred["price"])

        # Attach liquidity warning to regime_info for the frontend
        if liquidity_warning and regime_info:
            regime_info["liquidity_warning"] = liquidity_warning
        elif liquidity_warning:
            regime_info = {
                "dominant_regime": "neutral",
                "confidence": 0.0,
                "probabilities": {},
                "timeframe_alignment": "unknown",
                "weekly_regime": None,
                "note": "",
                "liquidity_warning": liquidity_warning,
            }

        recommendation = self._generate_recommendation(
            trend,
            trend_strength,
            current_price,
            support,
            resistance,
            regime_info=regime_info,
        )

        # Log prediction for monitoring (with CI for calibration tracking)
        try:
            from app.core.database import AsyncSessionLocal
            from app.models.prediction_log import PredictionLog

            if predictions:
                last_pred = predictions[-1]
                log_entry = PredictionLog(
                    symbol=symbol,
                    asset_type=asset_type.value,
                    model_name=model_used,
                    predicted_price=float(last_pred["price"]),
                    price_at_creation=float(current_price),
                    target_date=datetime.strptime(last_pred["date"], "%Y-%m-%d"),
                    horizon_days=days_ahead,
                    models_detail=models_detail,
                    confidence_low=float(last_pred.get("confidence_low", 0)),
                    confidence_high=float(last_pred.get("confidence_high", 0)),
                    prediction_data={
                        "current_price": float(current_price),
                        "fear_greed": fear_greed,
                        "btc_dominance": btc_dominance,
                        "regime": regime_info.get("dominant_regime") if regime_info else None,
                        "history_days": len(prices) if prices else 0,
                        "model_weights": models_detail.get("weights") if models_detail else None,
                    },
                )
                async with AsyncSessionLocal() as log_db:
                    log_db.add(log_entry)
                    await log_db.commit()
        except Exception as e:
            logger.warning("Failed to log prediction for %s: %s", symbol, e)

        # Cache the result
        result_dict = {
            "symbol": symbol,
            "current_price": current_price,
            "predictions": predictions,
            "trend": trend,
            "trend_strength": round(trend_strength, 1),
            "support_level": smart_round(support),
            "resistance_level": smart_round(resistance),
            "recommendation": recommendation,
            "model_used": model_used,
            "models_detail": models_detail or [],
            "regime_info": regime_info,
            "display_thresholds": at.build_display_thresholds(ctx),
        }
        await cache_prediction(symbol, days_ahead, result_dict)

        return PricePrediction(
            symbol=symbol,
            current_price=current_price,
            predictions=predictions,
            trend=trend,
            trend_strength=round(trend_strength, 1),
            support_level=smart_round(support),
            resistance_level=smart_round(resistance),
            recommendation=recommendation,
            model_used=model_used,
            models_detail=models_detail or [],
            explanations=explanations or [],
            regime_info=regime_info,
            display_thresholds=at.build_display_thresholds(ctx),
            _history_dates=dates,
            _history_prices=prices,
        )

    async def detect_anomalies(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> List[AnomalyDetection]:
        """Detect anomalies using Isolation Forest and Z-score."""
        anomalies = []

        result = await db.execute(
            select(Portfolio).where(
                Portfolio.user_id == user_id,
            )
        )
        portfolios = result.scalars().all()
        portfolio_ids = [p.id for p in portfolios]

        if not portfolio_ids:
            return anomalies

        result = await db.execute(
            select(Asset).where(
                Asset.portfolio_id.in_(portfolio_ids),
                Asset.quantity > 0,
            )
        )
        assets = result.scalars().all()

        for asset in assets:
            try:
                current_price = await self._get_current_price(asset.symbol, asset.asset_type)
                if current_price == 0:
                    continue

                # Fetch historical prices for ML-based detection (with cache)
                cached_hist = await get_cached_history(asset.symbol, asset.asset_type.value, 30)
                if cached_hist:
                    prices = cached_hist["prices"]
                else:
                    hist_dates, prices = await self.data_fetcher.get_history(
                        asset.symbol, asset.asset_type.value, days=30
                    )
                    if hist_dates and prices:
                        await cache_history(
                            asset.symbol,
                            asset.asset_type.value,
                            30,
                            {
                                "dates": [d.isoformat() for d in hist_dates],
                                "prices": prices,
                            },
                        )

                anomaly = self.anomaly_detector.detect(
                    symbol=asset.symbol,
                    prices=prices if prices else [current_price],
                    current_price=current_price,
                    avg_buy_price=float(asset.avg_buy_price),
                    asset_type=asset.asset_type.value,
                )

                if anomaly:
                    anomalies.append(
                        AnomalyDetection(
                            symbol=anomaly.symbol,
                            is_anomaly=anomaly.is_anomaly,
                            anomaly_type=anomaly.anomaly_type,
                            severity=anomaly.severity,
                            description=anomaly.description,
                            detected_at=anomaly.detected_at,
                            price_change_percent=anomaly.price_change_percent,
                        )
                    )

            except Exception as e:
                logger.warning("Error checking anomaly for %s: %s", asset.symbol, e)

        return anomalies

    async def get_market_sentiment(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> MarketSentiment:
        """Analyze market sentiment based on real price data."""
        result = await db.execute(
            select(Portfolio).where(
                Portfolio.user_id == user_id,
            )
        )
        portfolios = result.scalars().all()
        portfolio_ids = [p.id for p in portfolios]

        crypto_count = 0
        stock_count = 0
        bullish_count = 0
        bearish_count = 0
        total_change = 0.0
        asset_count = 0

        if portfolio_ids:
            result = await db.execute(
                select(Asset).where(
                    Asset.portfolio_id.in_(portfolio_ids),
                    Asset.quantity > 0,
                )
            )
            assets = result.scalars().all()

            # Separate crypto and stock/ETF symbols
            crypto_symbols = []
            stock_symbols = []
            for asset in assets[:15]:
                if asset.asset_type == AssetType.CRYPTO:
                    crypto_count += 1
                    crypto_symbols.append(asset.symbol)
                elif asset.asset_type in [AssetType.STOCK, AssetType.ETF]:
                    stock_count += 1
                    stock_symbols.append((asset.symbol, asset.asset_type.value))

            # Batch fetch crypto prices (single API call)
            # Use a default significance threshold; will be refined per-asset if ctx available
            sig_threshold = 1.0

            if crypto_symbols:
                try:
                    crypto_prices = await self.price_service.get_multiple_crypto_prices(crypto_symbols)
                    for sym, price_data in crypto_prices.items():
                        change_pct = float(price_data.get("change_percent_24h", 0))
                        total_change += change_pct
                        asset_count += 1
                        if change_pct > sig_threshold:
                            bullish_count += 1
                        elif change_pct < -sig_threshold:
                            bearish_count += 1
                except Exception as e:
                    logger.warning("Failed to fetch batch crypto prices for sentiment: %s", e)

            # Fetch stock/ETF prices individually (usually fewer)
            for sym, atype in stock_symbols:
                try:
                    price_data = await self.price_service.get_price(sym, atype)
                    if price_data:
                        change_pct = float(price_data.get("change_percent_24h", 0))
                        total_change += change_pct
                        asset_count += 1
                        if change_pct > sig_threshold:
                            bullish_count += 1
                        elif change_pct < -sig_threshold:
                            bearish_count += 1
                except Exception:
                    pass

        # Fetch real Fear & Greed Index from alternative.me
        fear_greed = 50
        try:
            import httpx

            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get("https://api.alternative.me/fng/?limit=1")
                resp.raise_for_status()
                fng_data = resp.json()
                if fng_data.get("data"):
                    fear_greed = int(fng_data["data"][0].get("value", 50))
        except Exception as e:
            logger.warning("Failed to fetch Fear & Greed Index: %s", e)
            # Fallback: compute from portfolio data
            if asset_count > 0:
                avg_change = total_change / asset_count
                fear_greed = int(max(0, min(100, 50 + avg_change * 10)))

        if fear_greed >= 60:
            sentiment = "bullish"
            phase = "markup"
        elif fear_greed <= 40:
            sentiment = "bearish"
            phase = "markdown"
        else:
            sentiment = "neutral"
            phase = "accumulation" if fear_greed > 50 else "distribution"

        sentiment_score = (fear_greed - 50) * 2

        signals = []

        if fear_greed > 75:
            signals.append(
                {
                    "type": "warning",
                    "message": "Marché en zone de cupidité extrême",
                    "action": "Envisagez de prendre des profits",
                }
            )
        elif fear_greed < 25:
            signals.append(
                {
                    "type": "opportunity",
                    "message": "Marché en zone de peur extrême",
                    "action": "Opportunité d'achat potentielle",
                }
            )

        if bullish_count > 0:
            signals.append(
                {
                    "type": "buy",
                    "message": f"{bullish_count} actif(s) en hausse significative (+1%)",
                    "action": "Momentum positif sur votre portefeuille",
                }
            )
        if bearish_count > 0:
            signals.append(
                {
                    "type": "sell",
                    "message": f"{bearish_count} actif(s) en baisse significative (-1%)",
                    "action": "Surveillez vos positions en baisse",
                }
            )

        total_assets = crypto_count + stock_count
        if crypto_count > 0 and total_assets > 0 and crypto_count / total_assets > 0.8 and crypto_count >= 3:
            signals.append(
                {
                    "type": "info",
                    "message": f"Forte concentration crypto: {crypto_count}/{total_assets} actifs",
                    "action": "Envisagez de diversifier avec d'autres classes d'actifs",
                }
            )

        return MarketSentiment(
            overall_sentiment=sentiment,
            sentiment_score=sentiment_score,
            fear_greed_index=fear_greed,
            market_phase=phase,
            signals=signals,
        )

    async def get_portfolio_predictions(
        self,
        db: AsyncSession,
        user_id: str,
        days_ahead: int = 7,
    ) -> Dict:
        """Get predictions for all assets in user's portfolio."""
        result = await db.execute(
            select(Portfolio).where(
                Portfolio.user_id == user_id,
            )
        )
        portfolios = result.scalars().all()
        portfolio_ids = [p.id for p in portfolios]

        if not portfolio_ids:
            return {
                "predictions": [],
                "summary": {
                    "total_current_value": 0.0,
                    "total_predicted_value": 0.0,
                    "expected_change_percent": 0.0,
                    "overall_sentiment": "neutral",
                    "bullish_assets": 0,
                    "bearish_assets": 0,
                    "neutral_assets": 0,
                    "days_ahead": days_ahead,
                },
                "display_thresholds": at.build_display_thresholds(None),
            }

        result = await db.execute(
            select(Asset).where(
                Asset.portfolio_id.in_(portfolio_ids),
                Asset.quantity > 0,
            )
        )
        raw_assets = result.scalars().all()

        if not raw_assets:
            return {
                "predictions": [],
                "summary": {
                    "total_current_value": 0.0,
                    "total_predicted_value": 0.0,
                    "expected_change_percent": 0.0,
                    "overall_sentiment": "neutral",
                    "bullish_assets": 0,
                    "bearish_assets": 0,
                    "neutral_assets": 0,
                    "days_ahead": days_ahead,
                },
                "display_thresholds": at.build_display_thresholds(None),
            }

        # Deduplicate by symbol: aggregate quantities (Decimal precision)
        asset_map: Dict[str, object] = {}
        quantity_map: Dict[str, Decimal] = {}
        for a in raw_assets:
            key = a.symbol
            if key not in asset_map:
                asset_map[key] = a
                quantity_map[key] = Decimal(str(a.quantity))
            else:
                quantity_map[key] += Decimal(str(a.quantity))
        assets = list(asset_map.values())

        predictions = []
        bullish_count = 0
        bearish_count = 0
        total_current = Decimal("0")
        total_predicted = Decimal("0")

        for asset in assets[:10]:
            # Skip stablecoins — their price is pegged, prediction is meaningless
            if PriceService.is_stablecoin(asset.symbol):
                continue

            prediction = await self.get_price_prediction(asset.symbol, asset.asset_type, days_ahead)

            qty = quantity_map[asset.symbol]
            price_dec = Decimal(str(prediction.current_price))
            current_value_dec = price_dec * qty
            pred_price = prediction.predictions[-1]["price"] if prediction.predictions else prediction.current_price
            predicted_value_dec = Decimal(str(pred_price)) * qty

            total_current += current_value_dec
            total_predicted += predicted_value_dec

            if prediction.trend == "bullish":
                bullish_count += 1
            elif prediction.trend == "bearish":
                bearish_count += 1

            predicted_price = (
                prediction.predictions[-1]["price"] if prediction.predictions else prediction.current_price
            )
            change_percent = (
                ((predicted_price - prediction.current_price) / prediction.current_price * 100)
                if prediction.current_price > 0
                else 0.0
            )

            # ── Reliability score from ensemble MAPE + model consensus ──
            models_detail = prediction.models_detail or []
            (
                skill_score,
                hit_rate,
                hit_rate_n,
                hit_rate_significant,
            ) = self._compute_reliability_from_ensemble(models_detail, prediction.trend)

            reliability_score = skill_score * 0.6 + hit_rate * 0.4
            reliability_score = round(min(reliability_score, 95.0), 1)

            if reliability_score >= 60:
                model_confidence = "useful"
            elif reliability_score >= 40:
                model_confidence = "uncertain"
            else:
                model_confidence = "unreliable"

            # Keep consensus for display but don't use in scoring
            models_detail = prediction.models_detail or []
            if len(models_detail) >= 2:
                trends = [m.get("trend", "neutral") for m in models_detail]
                models_agree = len(set(trends)) == 1
            else:
                models_agree = True

            predictions.append(
                {
                    "symbol": asset.symbol,
                    "name": asset.name,
                    "asset_type": asset.asset_type.value,
                    "current_price": prediction.current_price,
                    "predicted_price": predicted_price,
                    "change_percent": round(change_percent, 2),
                    "trend": prediction.trend,
                    "trend_strength": prediction.trend_strength,
                    "recommendation": prediction.recommendation,
                    "model_used": prediction.model_used,
                    "predictions": prediction.predictions,
                    "support_level": prediction.support_level,
                    "resistance_level": prediction.resistance_level,
                    "skill_score": skill_score,
                    "hit_rate": round(hit_rate, 1),
                    "hit_rate_significant": hit_rate_significant,
                    "hit_rate_n_samples": hit_rate_n,
                    "reliability_score": reliability_score,
                    "model_confidence": model_confidence,
                    "models_agree": models_agree,
                    "models_detail": models_detail,
                    "explanations": prediction.explanations or [],
                    "regime_info": prediction.regime_info,
                    "display_thresholds": prediction.display_thresholds,
                }
            )

        total_current_f = float(total_current)
        total_predicted_f = float(total_predicted)
        portfolio_change = ((total_predicted_f - total_current_f) / total_current_f * 100) if total_current_f > 0 else 0

        overall_sentiment = (
            "bullish" if bullish_count > bearish_count else "bearish" if bearish_count > bullish_count else "neutral"
        )

        # Use display_thresholds from the first prediction (representative)
        first_thresholds = (
            predictions[0].get("display_thresholds") if predictions else at.build_display_thresholds(None)
        )

        return {
            "predictions": predictions,
            "summary": {
                "total_current_value": round(total_current_f, 2),
                "total_predicted_value": round(total_predicted_f, 2),
                "expected_change_percent": round(portfolio_change, 2),
                "overall_sentiment": overall_sentiment,
                "bullish_assets": bullish_count,
                "bearish_assets": bearish_count,
                "neutral_assets": len(predictions) - bullish_count - bearish_count,
                "days_ahead": days_ahead,
            },
            "display_thresholds": first_thresholds,
        }

    # ------------------------------------------------------------------
    # Top Alpha detection
    # ------------------------------------------------------------------

    async def get_top_alpha_asset(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> Dict:
        """Detect the asset with the highest short-term alpha potential.

        Scores each held asset (quantity > 0) on 3 axes:
        1. RSI/Price divergence (bullish divergence = price down + RSI up).
        2. BTC de-correlation (lower Spearman correlation = more alpha).
        3. Regime momentum (bottom→bullish transition).

        Returns the top-scoring asset with reasons and 7d price prediction.
        """
        result = await db.execute(select(Portfolio).where(Portfolio.user_id == user_id))
        portfolios = result.scalars().all()
        portfolio_ids = [p.id for p in portfolios]

        if not portfolio_ids:
            return {"found": False}

        result = await db.execute(
            select(Asset).where(
                Asset.portfolio_id.in_(portfolio_ids),
                Asset.quantity > 0,
            )
        )
        raw_assets = result.scalars().all()

        # Deduplicate by symbol (Decimal precision)
        asset_map: Dict[str, object] = {}
        qty_map: Dict[str, Decimal] = {}
        cash_like_qty: Dict[str, Decimal] = {}
        for a in raw_assets:
            sym = a.symbol
            qty = Decimal(str(a.quantity))
            if is_cash_like(sym):
                cash_like_qty[sym] = cash_like_qty.get(sym, Decimal("0")) + qty
                continue
            if sym not in asset_map:
                asset_map[sym] = a
                qty_map[sym] = qty
            else:
                qty_map[sym] += qty

        if not asset_map:
            return {"found": False, "total_portfolio_value": 0.0}

        # ── Fetch BTC prices for correlation baseline ──
        btc_prices: List[float] = []
        try:
            cached = await get_cached_history("BTC", "crypto", 90)
            if cached and cached.get("prices"):
                btc_prices = cached["prices"]
            else:
                dates, prices = await self.data_fetcher.get_history("BTC", "crypto", days=90)
                if dates and prices:
                    btc_prices = prices
                    await cache_history(
                        "BTC",
                        "crypto",
                        90,
                        {"dates": [d.isoformat() for d in dates], "prices": prices},
                    )
        except Exception:
            logger.warning("Failed to fetch BTC history for alpha scoring")

        btc_returns = np.diff(np.log(np.array(btc_prices, dtype=float))) if len(btc_prices) > 10 else np.array([])

        # ── Fetch Fear & Greed for regime detection ──
        fear_greed: Optional[int] = None
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get("https://api.alternative.me/fng/?limit=1")
                if resp.status_code == 200:
                    fng_data = resp.json()
                    if fng_data.get("data"):
                        fear_greed = int(fng_data["data"][0].get("value", 50))
        except Exception:
            pass

        # ── Batch-fetch prices (same source as Dashboard for parity) ──
        crypto_symbols = [s for s, a in asset_map.items() if a.asset_type == AssetType.CRYPTO]
        stock_symbols = [s for s, a in asset_map.items() if a.asset_type in (AssetType.STOCK, AssetType.ETF)]
        price_map: Dict[str, float] = {}

        if crypto_symbols:
            try:
                batch = await self.price_service.get_multiple_crypto_prices(crypto_symbols, "eur")
                for sym, data in batch.items():
                    p = data.get("price", 0)
                    price_map[sym.upper()] = float(p) if p else 0.0
            except Exception as e:
                logger.warning("Batch crypto price fetch failed: %s", e)

        for sym in stock_symbols:
            try:
                data = await self.price_service.get_stock_price(sym)
                if data and data.get("price"):
                    price_map[sym.upper()] = float(data["price"])
            except Exception:
                pass

        # ── Pre-fetch all 90d histories in parallel ──
        import asyncio as _aio

        async def _fetch_history(sym: str, atype: str) -> tuple:
            """Fetch 90d history from cache or API."""
            cached_hist = await get_cached_history(sym, atype, 90)
            if cached_hist and cached_hist.get("prices"):
                return (sym, cached_hist["prices"])
            try:
                a_dates, a_prices_raw = await self.data_fetcher.get_history(sym, atype, days=90)
                if a_dates and a_prices_raw:
                    await cache_history(
                        sym,
                        atype,
                        90,
                        {
                            "dates": [d.isoformat() for d in a_dates],
                            "prices": a_prices_raw,
                        },
                    )
                    return (sym, a_prices_raw)
            except Exception:
                pass
            return (sym, [])

        # Limit assets to reduce memory usage on free-tier hosting (512 MB)
        _MAX_ASSETS = 7
        _PREDICTION_BATCH_SIZE = 3  # Process ensemble predictions in small batches

        _items = list(asset_map.items())[:_MAX_ASSETS]
        history_results = await _aio.gather(*[_fetch_history(s, a.asset_type.value) for s, a in _items])
        history_map: Dict[str, List[float]] = {sym: prices for sym, prices in history_results}

        # ── Pre-fetch 7d predictions in batches to limit memory ──
        import gc

        _prediction_cache: Dict[str, Optional[PricePrediction]] = {}

        async def _fetch_prediction(sym: str, atype: AssetType) -> tuple:
            try:
                pred = await self.get_price_prediction(sym, atype, days_ahead=7)
                return (sym, pred)
            except Exception as e:
                logger.debug("7d prediction failed for %s: %s", sym, e)
                return (sym, None)

        for batch_start in range(0, len(_items), _PREDICTION_BATCH_SIZE):
            batch = _items[batch_start : batch_start + _PREDICTION_BATCH_SIZE]
            batch_results = await _aio.gather(*[_fetch_prediction(s, a.asset_type) for s, a in batch])
            for sym, pred in batch_results:
                _prediction_cache[sym] = pred

            # Free memory between batches
            gc.collect()

        # ── Score each asset ──
        scored_assets = []
        total_value = Decimal("0")
        value_map: Dict[str, float] = {}

        for symbol, asset in _items:
            try:
                price = price_map.get(symbol.upper(), 0.0)
                if price <= 0:
                    # Fallback to individual fetch
                    price = await self._get_current_price(symbol, asset.asset_type)
                if price <= 0:
                    logger.warning("Price fetch failed for %s (batch + fallback), skipping", symbol)
                    continue
                qty_dec = qty_map[symbol]
                price_dec = Decimal(str(price))
                value_dec = qty_dec * price_dec
                total_value += value_dec
                value = float(value_dec)
                value_map[symbol] = value

                a_prices = history_map.get(symbol, [])

                if len(a_prices) < 20:
                    continue

                reasons = []
                score = 0.0

                # ── 1. RSI/Price divergence (0-35 points) ──
                rsi_now = _rsi(a_prices, period=14)
                rsi_prev = _rsi(a_prices[:-7], period=14) if len(a_prices) > 21 else None
                price_t = a_prices[-1]
                price_t7 = a_prices[-8] if len(a_prices) > 8 else price_t
                price_change_7d = (price_t / price_t7 - 1) * 100 if price_t7 > 0 else 0

                # Divergence log for audit / Telegram recap
                divergence_log = {
                    "price_t7": round(price_t7, 4),
                    "price_t": round(price_t, 4),
                    "rsi_t7": round(rsi_prev, 2) if rsi_prev is not None else None,
                    "rsi_t": round(rsi_now, 2) if rsi_now is not None else None,
                    "price_change_7d_pct": round(price_change_7d, 2),
                    "is_bullish_divergence": False,
                }

                if rsi_now is not None and rsi_prev is not None:
                    # Bullish divergence: price goes down but RSI goes up
                    rsi_delta = rsi_now - rsi_prev
                    if price_change_7d < -2 and rsi_delta > 3:
                        divergence_log["is_bullish_divergence"] = True
                        div_score = min(35, 15 + rsi_delta * 2)
                        score += div_score
                        reasons.append(
                            {
                                "label": "Divergence Haussière",
                                "detail": f"Prix {price_change_7d:+.1f}% mais RSI {rsi_delta:+.1f} pts",
                                "score": round(div_score),
                            }
                        )
                        logger.info(
                            "Divergence %s CONFIRMÉE: Prix(T-7)=%.4f > Prix(T)=%.4f " "ET RSI(T-7)=%.2f < RSI(T)=%.2f",
                            symbol,
                            price_t7,
                            price_t,
                            rsi_prev,
                            rsi_now,
                        )
                    elif price_change_7d < -2 and rsi_delta <= 3:
                        # Price dropped but RSI did NOT diverge — degrade score
                        penalty = min(10, abs(rsi_delta) * 1.5)
                        score -= penalty
                        divergence_log["degraded"] = True
                        divergence_log["penalty"] = round(penalty, 1)
                        reasons.append(
                            {
                                "label": "Divergence Non Confirmée",
                                "detail": f"Prix {price_change_7d:+.1f}% et RSI {rsi_delta:+.1f} pts (pas de divergence)",
                                "score": round(-penalty),
                            }
                        )
                        logger.info(
                            "Divergence %s NON CONFIRMÉE: Prix(T-7)=%.4f > Prix(T)=%.4f "
                            "mais RSI(T-7)=%.2f → RSI(T)=%.2f (delta %.1f ≤ 3)",
                            symbol,
                            price_t7,
                            price_t,
                            rsi_prev,
                            rsi_now,
                            rsi_delta,
                        )
                    elif rsi_now < 35:
                        # Oversold but no divergence yet — mild signal
                        ov_score = min(20, (35 - rsi_now) * 1.2)
                        score += ov_score
                        reasons.append(
                            {
                                "label": "Survente RSI",
                                "detail": f"RSI à {rsi_now:.0f} (seuil 35)",
                                "score": round(ov_score),
                            }
                        )

                # ── 2. BTC de-correlation (0-30 points) ──
                if len(btc_returns) > 10 and len(a_prices) > 10:
                    a_returns = np.diff(np.log(np.array(a_prices[-len(btc_returns) - 1 :], dtype=float)))
                    min_len = min(len(btc_returns), len(a_returns))
                    if min_len >= 10:
                        from scipy.stats import spearmanr

                        corr, _ = spearmanr(btc_returns[-min_len:], a_returns[-min_len:])
                        if not np.isnan(corr):
                            # Lower correlation = more alpha potential
                            # corr < 0.3 is considered "decoupled"
                            decorr_score = max(0, (0.6 - corr) / 0.6 * 30)
                            score += decorr_score
                            if decorr_score > 10:
                                reasons.append(
                                    {
                                        "label": "Décorrélé du BTC",
                                        "detail": f"Corrélation {corr:.2f} (faible = indépendant)",
                                        "score": round(decorr_score),
                                    }
                                )

                # ── 3. Regime momentum (0-35 points) ──
                regime_result = self.regime_detector.detect(
                    a_prices,
                    symbol,
                    fear_greed,
                    asset_type=asset.asset_type.value,
                )
                probs = regime_result.probabilities
                # Transition from bottom/bearish → bullish = strong alpha signal
                bottom_prob = probs.get("bottom", 0)
                bullish_prob = probs.get("bullish", 0)
                transition_signal = bottom_prob * 0.6 + bullish_prob * 0.4

                if transition_signal > 0.3:
                    reg_score = min(35, transition_signal * 70)
                    score += reg_score
                    dominant = regime_result.dominant_regime
                    reasons.append(
                        {
                            "label": "Momentum de Régime",
                            "detail": f"Régime: {dominant} (bottom {bottom_prob:.0%}, bull {bullish_prob:.0%})",
                            "score": round(reg_score),
                        }
                    )

                # ── 7d price prediction (Decimal precision) ──
                # Use pre-fetched batch prediction if available
                predicted_7d_pct = Decimal("0")
                prediction_source = "none"
                prediction = _prediction_cache.get(symbol)
                if prediction and prediction.predictions:
                    last_pred = prediction.predictions[-1]
                    pred_price = last_pred.get("price", 0)
                    if pred_price > 0 and price > 0:
                        raw_pct = (Decimal(str(pred_price)) / price_dec - 1) * 100
                        # Sanity check: reject > ±50% moves
                        if abs(raw_pct) > 50:
                            logger.warning(
                                "SANITY CHECK (alpha): %s ensemble 7d prediction "
                                "unrealistic (%.1f%%). Falling back to EMA-20.",
                                symbol,
                                float(raw_pct),
                            )
                            predicted_7d_pct = Decimal("0")
                            prediction_source = "none"
                        else:
                            predicted_7d_pct = raw_pct
                            prediction_source = "ensemble"

                # EMA-20 slope fallback: extrapolate 7 days if model unavailable
                if predicted_7d_pct == 0 and len(a_prices) >= 20:
                    try:
                        arr = np.array(a_prices[-20:], dtype=float)
                        ema = arr.copy()
                        k = 2 / 21  # EMA-20 smoothing factor
                        for idx in range(1, len(ema)):
                            ema[idx] = arr[idx] * k + ema[idx - 1] * (1 - k)
                        # Daily slope from last 5 EMA values
                        daily_slope = (ema[-1] - ema[-5]) / max(ema[-5], 1e-10) / 5
                        ema_7d_pct = daily_slope * 7 * 100
                        if abs(ema_7d_pct) > 0.01:  # only if meaningful
                            predicted_7d_pct = Decimal(str(round(ema_7d_pct, 4)))
                            prediction_source = "ema20_slope"
                    except Exception:
                        pass

                scored_assets.append(
                    {
                        "symbol": symbol,
                        "name": asset.name,
                        "asset_type": asset.asset_type.value,
                        "current_price": float(round(price_dec, 2)),
                        "score": round(score, 1),
                        "predicted_7d_pct": float(round(predicted_7d_pct, 2)),
                        "prediction_source": prediction_source,
                        "reasons": sorted(reasons, key=lambda r: -r["score"]),
                        "regime": regime_result.dominant_regime,
                        "regime_confidence": round(regime_result.confidence, 2),
                        "value": float(round(value_dec, 2)),
                        "divergence_log": divergence_log,
                    }
                )
            except Exception as e:
                logger.warning("Alpha scoring failed for %s: %s", symbol, e)

        if not scored_assets:
            return {"found": False, "total_portfolio_value": 0.0}

        # Include cash-like assets in total for accurate weight calculation
        for sym, qty in cash_like_qty.items():
            try:
                if PriceService.is_stablecoin(sym):
                    p = await self.price_service._stablecoin_price_eur(sym)
                else:
                    p = Decimal("1")  # fiat EUR=1, others approximated
                total_value += qty * p
            except Exception:
                total_value += qty  # fallback: assume 1:1

        total_value_f = float(total_value)

        # ── Concentration risk guard ──
        for sa in scored_assets:
            if total_value_f > 0:
                sa["weight_pct"] = round(sa["value"] / total_value_f * 100, 1)
            else:
                sa["weight_pct"] = 0.0

        # Sort by score desc
        scored_assets.sort(key=lambda x: -x["score"])
        top = scored_assets[0]

        # Flag if top alpha asset is already over-concentrated (> 50% weight)
        concentration_risk = top["weight_pct"] > 50

        return {
            "found": True,
            "top_alpha": top,
            "concentration_risk": concentration_risk,
            "all_scores": scored_assets[:5],  # Top 5 for frontend display
            "total_portfolio_value": float(round(total_value, 2)),
        }

    # ------------------------------------------------------------------
    # Strategy Map — decision matrix Alpha × Cycle
    # ------------------------------------------------------------------

    STRATEGY_MATRIX = {
        # (alpha_level, cycle_phase) → (action, description, impact_pct)
        # alpha_level: high (>= 60), medium (30-59), low (< 30)
        # cycle_phase: 6 professional phases
        # --- Bottoming (RSI < 30, divergence haussière, épuisement vendeur) ---
        ("high", "bottoming"): (
            "ACHAT FORT",
            "Alpha élevé + Bottoming : signal d'achat optimal (RSI survente + divergence)",
            5.0,
        ),
        ("medium", "bottoming"): (
            "DCA",
            "Signal moyen + Bottoming : DCA conservateur",
            3.0,
        ),
        ("low", "bottoming"): (
            "OBSERVER",
            "Faible alpha + Bottoming : surveiller les signaux",
            0.0,
        ),
        # --- Accumulation (prix stable, Smart Money Flow positif) ---
        ("high", "accumulation"): (
            "DCA",
            "Alpha élevé + Accumulation : accumuler progressivement",
            4.0,
        ),
        ("medium", "accumulation"): (
            "DCA",
            "Signal moyen + Accumulation : fenêtre d'entrée progressive",
            2.0,
        ),
        ("low", "accumulation"): (
            "OBSERVER",
            "Faible alpha + Accumulation : pas encore de signal clair",
            0.0,
        ),
        # --- Mark-up (cassure de résistance, volume croissant) ---
        ("high", "markup"): (
            "MAINTENIR",
            "Alpha élevé + Mark-up : laisser courir les gains",
            0.0,
        ),
        ("medium", "markup"): (
            "MAINTENIR",
            "Signal moyen + Mark-up : conserver les positions",
            0.0,
        ),
        ("low", "markup"): (
            "CONSERVER",
            "Faible alpha en Mark-up : ne pas vendre",
            0.0,
        ),
        # --- Topping (RSI > 70, divergence baissière, risque de retournement) ---
        ("high", "topping"): (
            "PRENDRE PROFITS",
            "Alpha élevé mais Topping : sécuriser 20-30%",
            -2.0,
        ),
        ("medium", "topping"): (
            "ALLÉGER",
            "Signal moyen + Topping : réduire l'exposition",
            -3.0,
        ),
        ("low", "topping"): (
            "VENDRE",
            "Faible alpha + Topping : signal de vente prioritaire",
            -5.0,
        ),
        # --- Distribution (prix stagne sur sommets, gros volumes sortants) ---
        ("high", "distribution"): (
            "ALLÉGER",
            "Alpha élevé + Distribution : sécuriser une partie",
            -2.0,
        ),
        ("medium", "distribution"): (
            "VENDRE",
            "Signal moyen + Distribution : réduire avant le markdown",
            -4.0,
        ),
        ("low", "distribution"): (
            "VENDRE",
            "Faible alpha + Distribution : sortir avant la chute",
            -5.0,
        ),
        # --- Markdown (structure descendante, Lower Highs) ---
        ("high", "markdown"): (
            "DCA",
            "Alpha élevé en Markdown : accumuler progressivement (contrarian)",
            3.0,
        ),
        ("medium", "markdown"): (
            "ATTENDRE",
            "Signal moyen en Markdown : patience, pas de renforcement",
            0.0,
        ),
        ("low", "markdown"): (
            "ÉVITER",
            "Faible alpha en Markdown : ne pas renforcer",
            0.0,
        ),
        # --- Backward-compat: old 4-phase names still work ---
        ("high", "bottom"): (
            "ACHAT FORT",
            "Alpha élevé + creux de marché : signal d'achat optimal",
            5.0,
        ),
        ("high", "bearish"): (
            "DCA",
            "Alpha élevé en bear market : accumuler progressivement",
            3.0,
        ),
        ("high", "bullish"): ("MAINTENIR", "Alpha élevé en bull : laisser courir", 0.0),
        ("high", "top"): (
            "PRENDRE PROFITS",
            "Alpha élevé mais sommet : sécuriser 20-30%",
            -2.0,
        ),
        ("medium", "bottom"): ("DCA", "Signal moyen + creux : DCA conservateur", 3.0),
        ("medium", "bearish"): ("ATTENDRE", "Signal moyen en bear : patience", 0.0),
        ("medium", "bullish"): (
            "MAINTENIR",
            "Signal moyen en bull : conserver les positions",
            0.0,
        ),
        ("medium", "top"): (
            "ALLÉGER",
            "Signal moyen au sommet : réduire l'exposition",
            -3.0,
        ),
        ("low", "bottom"): (
            "OBSERVER",
            "Faible alpha + creux : surveiller les signaux",
            0.0,
        ),
        ("low", "bearish"): ("ÉVITER", "Faible alpha en bear : ne pas renforcer", 0.0),
        ("low", "bullish"): (
            "CONSERVER",
            "Faible alpha en bull : ne pas vendre non plus",
            0.0,
        ),
        ("low", "top"): (
            "VENDRE",
            "Faible alpha + sommet : signal de vente prioritaire",
            -5.0,
        ),
    }

    async def get_strategy_map(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> Dict:
        """Build a strategy decision table crossing Alpha scores with Cycle phase.

        Calls get_top_alpha_asset() and get_market_cycle() then merges
        per-asset data using a decision matrix.
        """
        # Fetch both datasets in parallel (independent operations)
        import asyncio as _aio

        alpha_data, cycle_data = await _aio.gather(
            self.get_top_alpha_asset(db, user_id),
            self.get_market_cycle(db, user_id),
        )

        total_value = alpha_data.get("total_portfolio_value", 0.0)
        alpha_scores = alpha_data.get("all_scores", [])
        per_asset_cycle = cycle_data.get("per_asset", [])
        market_regime = cycle_data.get("market_regime", {})
        fear_greed = cycle_data.get("fear_greed")

        # Build regime lookup by symbol
        regime_map: Dict[str, Dict] = {}
        for a in per_asset_cycle:
            regime_map[a["symbol"]] = a

        # Merge: for each scored asset, cross with its cycle regime
        strategy_rows: List[Dict] = []
        summary_buys = 0
        summary_sells = 0
        summary_holds = 0

        for scored in alpha_scores:
            sym = scored["symbol"]
            score = scored["score"]
            value = scored.get("value", 0)
            weight_pct = scored.get("weight_pct", 0)

            # Alpha level — regime-aware thresholds via RegimeConfig.alpha_threshold
            _global_regime = market_regime.get("dominant_regime", "") if market_regime else ""
            _alpha_cfg = RegimeConfig.from_regime(_global_regime)
            _high_thresh = _alpha_cfg.alpha_threshold  # 85 in bear, 60 in bull
            _mid_thresh = max(30, _high_thresh - 30)  # 55 in bear, 30 in bull
            if score >= _high_thresh:
                alpha_level = "high"
            elif score >= _mid_thresh:
                alpha_level = "medium"
            else:
                alpha_level = "low"

            # Cycle phase — prefer 6-phase, fallback to 4-phase dominant_regime
            cycle_info = regime_map.get(sym, {})
            regime = cycle_info.get(
                "regime_6phase",
                cycle_info.get(
                    "dominant_regime",
                    market_regime.get("dominant_regime", "bullish") if market_regime else "bullish",
                ),
            )

            # Decision matrix lookup
            key = (alpha_level, regime)
            action, description, impact_pct = self.STRATEGY_MATRIX.get(key, ("OBSERVER", "Données insuffisantes", 0.0))

            # Bear market validation: ACHAT FORT requires RSI < 35 confirmation
            # when the global market is in markdown/bearish/distribution
            global_regime = market_regime.get("dominant_regime", "") if market_regime else ""
            if action == "ACHAT FORT" and global_regime in (
                "bearish",
                "top",
                "markdown",
                "distribution",
            ):
                # Check if scored asset has RSI divergence confirmation
                has_divergence = any(r.get("label", "") == "Divergence Haussière" for r in scored.get("reasons", []))
                if not has_divergence:
                    action = "DCA"
                    description = "Bear market : ACHAT FORT dégradé en DCA (divergence RSI non confirmée)"
                    impact_pct = 2.0

            # Compute portfolio impact
            impact_eur = round(value * impact_pct / 100, 2) if value > 0 else 0.0

            # Count summary
            if "ACHAT" in action or action == "DCA":
                summary_buys += 1
            elif "VENDRE" in action or "PROFITS" in action or "ALLÉGER" in action:
                summary_sells += 1
            else:
                summary_holds += 1

            # Bull market: virtual trailing stop hint based on EMA-20
            trailing_stop = None
            if regime in ("markup", "bullish") and action in ("MAINTENIR", "CONSERVER"):
                trailing_stop = "EMA-20 trailing stop recommandé — remonter le stop-loss sous l'EMA-20"

            strategy_rows.append(
                {
                    "symbol": sym,
                    "name": scored.get("name", sym),
                    "alpha_score": round(score, 1),
                    "alpha_level": alpha_level,
                    "regime": regime,
                    "regime_confidence": round(cycle_info.get("confidence", 0.5), 2),
                    "action": action,
                    "description": description,
                    "value": round(value, 2),
                    "weight_pct": round(weight_pct, 1),
                    "impact_pct": impact_pct,
                    "impact_eur": impact_eur,
                    "predicted_7d_pct": scored.get("predicted_7d_pct", 0),
                    "is_resilient": is_safe_haven(sym),
                    "trailing_stop": trailing_stop,
                }
            )

        return {
            "rows": strategy_rows,
            "total_portfolio_value": round(total_value, 2),
            "market_regime": market_regime.get("dominant_regime", "unknown") if market_regime else "unknown",
            "fear_greed": fear_greed,
            "summary": {
                "buys": summary_buys,
                "sells": summary_sells,
                "holds": summary_holds,
            },
        }

    async def get_what_if(
        self,
        db: AsyncSession,
        user_id: str,
        scenarios: List[Dict],
    ) -> Dict:
        """Simulate what-if scenarios on the portfolio."""
        result = await db.execute(
            select(Portfolio).where(
                Portfolio.user_id == user_id,
            )
        )
        portfolios = result.scalars().all()
        portfolio_ids = [p.id for p in portfolios]

        if not portfolio_ids:
            return {
                "current_value": 0,
                "simulated_value": 0,
                "impact_percent": 0,
                "per_asset": [],
            }

        result = await db.execute(
            select(Asset).where(
                Asset.portfolio_id.in_(portfolio_ids),
                Asset.quantity > 0,
            )
        )
        raw_assets = result.scalars().all()

        # Deduplicate by symbol (Decimal precision)
        wi_asset_map: Dict[str, object] = {}
        wi_qty_map: Dict[str, Decimal] = {}
        for a in raw_assets:
            if a.symbol not in wi_asset_map:
                wi_asset_map[a.symbol] = a
                wi_qty_map[a.symbol] = Decimal(str(a.quantity))
            else:
                wi_qty_map[a.symbol] += Decimal(str(a.quantity))
        assets = list(wi_asset_map.values())

        # Build scenario map
        scenario_map = {s["symbol"].upper(): s["change_percent"] for s in scenarios}

        per_asset = []
        total_current = Decimal("0")
        total_simulated = Decimal("0")

        for asset in assets[:15]:
            price = await self._get_current_price(asset.symbol, asset.asset_type)
            price_dec = Decimal(str(price))
            qty_dec = wi_qty_map[asset.symbol]
            current_val = price_dec * qty_dec
            change = scenario_map.get(asset.symbol.upper(), 0.0)
            simulated_val = current_val * Decimal(str(1 + change / 100))

            total_current += current_val
            total_simulated += simulated_val

            per_asset.append(
                {
                    "symbol": asset.symbol,
                    "name": asset.name,
                    "current_value": round(float(current_val), 2),
                    "simulated_value": round(float(simulated_val), 2),
                    "change_percent": change,
                    "impact": round(float(simulated_val - current_val), 2),
                }
            )

        total_current_f = float(total_current)
        total_simulated_f = float(total_simulated)
        impact_pct = ((total_simulated_f - total_current_f) / total_current_f * 100) if total_current_f > 0 else 0

        return {
            "current_value": round(total_current_f, 2),
            "simulated_value": round(total_simulated_f, 2),
            "impact_percent": round(impact_pct, 2),
            "per_asset": per_asset,
        }

    async def get_market_events(self) -> List[Dict]:
        """Return upcoming market events from web scraping + Forex Factory API."""
        import re

        now = datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC; all evt_date constructions are also naive
        current_year = now.year
        events = []

        # Month name mappings
        month_map = {
            "january": 1,
            "february": 2,
            "march": 3,
            "april": 4,
            "may": 5,
            "june": 6,
            "july": 7,
            "august": 8,
            "september": 9,
            "october": 10,
            "november": 11,
            "december": 12,
        }

        # 1. Fetch this week's economic events from Forex Factory (free, no key)
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json")
                resp.raise_for_status()
                data = resp.json()

            for item in data:
                impact = item.get("impact", "")
                if impact not in ("High", "Medium"):
                    continue
                date_str = item.get("date", "")
                if not date_str:
                    continue
                try:
                    evt_date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
                except (ValueError, TypeError):
                    continue
                if evt_date < now:
                    continue

                country = item.get("country", "")
                title = item.get("title", "Événement économique")
                forecast = item.get("forecast", "")
                previous = item.get("previous", "")
                desc_parts = []
                if country:
                    desc_parts.append(country)
                if previous:
                    desc_parts.append(f"Précédent: {previous}")
                if forecast:
                    desc_parts.append(f"Prévision: {forecast}")

                events.append(
                    {
                        "title": title,
                        "date": evt_date.strftime("%Y-%m-%d"),
                        "category": "macro",
                        "description": " — ".join(desc_parts) if desc_parts else title,
                        "impact": "high" if impact == "High" else "medium",
                        "days_until": (evt_date - now).days,
                    }
                )
        except Exception as e:
            logger.warning("Failed to fetch Forex Factory calendar: %s", e)

        # 2. Scrape FOMC meeting dates from Federal Reserve website
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get("https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm")
                resp.raise_for_status()
                html = resp.text

            # Pattern matches "Month DD-DD" or "Month DD-DD*" in FOMC calendar
            # The page groups by year, find the current/next year sections
            for year in [current_year, current_year + 1]:
                # Find meeting date patterns like "January 27-28" or "March 17-18*"
                pattern = rf'({"|".join(month_map.keys())})\s+(\d{{1,2}})-(\d{{1,2}})\*?'
                year_section_match = re.search(rf'class="[^"]*"[^>]*>\s*{year}\s*<', html, re.IGNORECASE)
                if not year_section_match:
                    continue

                # Search from year header to next year header or end
                start = year_section_match.start()
                next_year = re.search(
                    rf'class="[^"]*"[^>]*>\s*{year + 1}\s*<',
                    html[start + 100 :],
                    re.IGNORECASE,
                )
                end = start + 100 + next_year.start() if next_year else len(html)
                section = html[start:end]

                for match in re.finditer(pattern, section, re.IGNORECASE):
                    month_name = match.group(1).lower()
                    last_day = int(match.group(3))  # Decision day (2nd day)
                    month = month_map.get(month_name)
                    if not month:
                        continue
                    try:
                        evt_date = datetime(year, month, last_day)
                    except ValueError:
                        continue
                    if evt_date < now:
                        continue

                    events.append(
                        {
                            "title": "Réunion FOMC (Fed)",
                            "date": evt_date.strftime("%Y-%m-%d"),
                            "category": "macro",
                            "description": "Décision sur les taux d'intérêt américains",
                            "impact": "high",
                            "days_until": (evt_date - now).days,
                        }
                    )
        except Exception as e:
            logger.warning("Failed to scrape FOMC calendar: %s", e)

        # 3. Scrape ECB meeting dates
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get("https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html")
                resp.raise_for_status()
                html = resp.text

            # ECB calendar uses dates like "5 February", "19 March", etc.
            # Look for "Monetary policy" sections with dates
            # Pattern: day month year in various formats
            pattern = r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})"
            monetary_sections = re.split(r"(?i)monetary\s+polic", html)

            seen_ecb_dates = set()
            for section in monetary_sections[1:]:  # Skip text before first match
                # Find all dates in the next ~500 chars after "Monetary polic..."
                chunk = section[:800]
                for match in re.finditer(pattern, chunk, re.IGNORECASE):
                    day = int(match.group(1))
                    month_name = match.group(2).lower()
                    year = int(match.group(3))
                    month = month_map.get(month_name)
                    if not month or year < current_year:
                        continue
                    try:
                        evt_date = datetime(year, month, day)
                    except ValueError:
                        continue
                    if evt_date < now:
                        continue
                    date_key = evt_date.strftime("%Y-%m-%d")
                    if date_key in seen_ecb_dates:
                        continue
                    seen_ecb_dates.add(date_key)

                    events.append(
                        {
                            "title": "Réunion BCE",
                            "date": date_key,
                            "category": "macro",
                            "description": "Décision sur les taux d'intérêt européens",
                            "impact": "high",
                            "days_until": (evt_date - now).days,
                        }
                    )
        except Exception as e:
            logger.warning("Failed to scrape ECB calendar: %s", e)

        # 4. Fiscal events (quarterly — these are fixed by definition)
        for year in [current_year, current_year + 1]:
            for q, (m, d, label) in enumerate(
                [
                    (3, 31, "Q1"),
                    (6, 30, "Q2"),
                    (9, 30, "Q3"),
                    (12, 31, "Q4"),
                ],
                1,
            ):
                evt_date = datetime(year, m, d)
                if evt_date < now or (evt_date - now).days > 365:
                    continue
                events.append(
                    {
                        "title": f"Fin de trimestre {label}",
                        "date": evt_date.strftime("%Y-%m-%d"),
                        "category": "fiscal",
                        "description": f"Clôture {label} — rééquilibrages institutionnels",
                        "impact": "medium",
                        "days_until": (evt_date - now).days,
                    }
                )

        # 5. Crypto events — dynamically estimate next BTC halving from blockchain
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get("https://blockchain.info/q/getblockcount")
                if resp.status_code == 200:
                    current_block = int(resp.text.strip())
                    # Halving every 210,000 blocks
                    halving_interval = 210_000
                    next_halving_block = ((current_block // halving_interval) + 1) * halving_interval
                    blocks_remaining = next_halving_block - current_block
                    # ~10 minutes per block on average
                    minutes_remaining = blocks_remaining * 10
                    est_halving_date = now + timedelta(minutes=minutes_remaining)
                    halving_number = next_halving_block // halving_interval
                    if (est_halving_date - now).days > 0:
                        events.append(
                            {
                                "title": f"Halving Bitcoin #{halving_number}",
                                "date": est_halving_date.strftime("%Y-%m-%d"),
                                "category": "crypto",
                                "description": f"Réduction de la récompense de minage — bloc {next_halving_block:,}",
                                "impact": "high",
                                "days_until": (est_halving_date - now).days,
                            }
                        )
        except Exception as e:
            logger.warning("Failed to fetch BTC block height: %s", e)

        # Deduplicate by (title, date)
        seen = set()
        unique = []
        for e in events:
            key = (e["title"], e["date"])
            if key not in seen:
                seen.add(key)
                unique.append(e)

        unique.sort(key=lambda x: x["days_until"])
        return unique[:15]

    async def get_track_record(self, symbol: str, limit: int = 20, user_id: str | None = None) -> Dict:
        """Get historical prediction track record for a symbol.

        Returns past predictions with actual outcomes for transparency.
        """
        from app.core.database import AsyncSessionLocal
        from app.models.prediction_log import PredictionLog

        try:
            async with AsyncSessionLocal() as db:
                filters = [
                    PredictionLog.symbol == symbol.upper(),
                    PredictionLog.accuracy_checked.isnot(None),
                ]
                if user_id:
                    filters.append(PredictionLog.user_id == user_id)
                result = await db.execute(
                    select(PredictionLog).where(*filters).order_by(PredictionLog.created_at.desc()).limit(limit)
                )
                logs = result.scalars().all()

                if not logs:
                    return {
                        "symbol": symbol,
                        "records": [],
                        "summary": {
                            "total_checked": 0,
                            "avg_mape": None,
                            "direction_accuracy": None,
                            "ci_coverage": None,
                        },
                    }

                records = []
                mapes = []
                direction_hits = 0
                direction_total = 0
                ci_hits = 0
                ci_total = 0

                for log in logs:
                    record = {
                        "date": log.created_at.isoformat() if log.created_at else None,
                        "target_date": log.target_date.isoformat() if log.target_date else None,
                        "predicted_price": log.predicted_price,
                        "actual_price": log.actual_price,
                        "mape": round(log.mape, 1) if log.mape is not None else None,
                        "direction_correct": log.direction_correct,
                        "ci_covered": log.ci_covered,
                        "confidence_low": log.confidence_low,
                        "confidence_high": log.confidence_high,
                    }
                    records.append(record)

                    if log.mape is not None:
                        mapes.append(log.mape)
                    if log.direction_correct is not None:
                        direction_total += 1
                        if log.direction_correct:
                            direction_hits += 1
                    if log.ci_covered is not None:
                        ci_total += 1
                        if log.ci_covered:
                            ci_hits += 1

                return {
                    "symbol": symbol,
                    "records": records,
                    "summary": {
                        "total_checked": len(logs),
                        "avg_mape": round(float(np.mean(mapes)), 1) if mapes else None,
                        "direction_accuracy": round(direction_hits / direction_total * 100, 1)
                        if direction_total > 0
                        else None,
                        "ci_coverage": round(ci_hits / ci_total * 100, 1) if ci_total > 0 else None,
                    },
                }
        except Exception as e:
            logger.warning("Failed to get track record for %s: %s", symbol, e)
            return {
                "symbol": symbol,
                "records": [],
                "summary": {
                    "total_checked": 0,
                    "avg_mape": None,
                    "direction_accuracy": None,
                    "ci_coverage": None,
                },
            }

    async def get_portfolio_backtest(self, db: AsyncSession, user_id: str, days: int = 7) -> Dict:
        """Aggregate backtest across all portfolio assets.

        Compares predictions made *days* ago with actual prices recorded
        in PredictionLog.  Returns per-asset MAPE, direction accuracy,
        an overall MAPE, and a ``needs_retraining`` flag (MAPE > 10%).
        """
        from app.models.prediction_log import PredictionLog

        # Fetch user assets (same pattern as get_portfolio_predictions)
        port_result = await db.execute(select(Portfolio).where(Portfolio.user_id == user_id))
        portfolios = port_result.scalars().all()
        if not portfolios:
            return {
                "assets": [],
                "overall_mape": None,
                "overall_direction_accuracy": None,
                "needs_retraining": False,
                "days": days,
            }
        asset_result = await db.execute(
            select(Asset).where(
                Asset.portfolio_id.in_([p.id for p in portfolios]),
                Asset.quantity > 0,
            )
        )
        symbols = list({a.symbol.upper() for a in asset_result.scalars().all()})

        if not symbols:
            return {
                "assets": [],
                "overall_mape": None,
                "overall_direction_accuracy": None,
                "needs_retraining": False,
                "days": days,
            }

        result = await db.execute(
            select(PredictionLog)
            .where(
                PredictionLog.symbol.in_(symbols),
                PredictionLog.accuracy_checked.isnot(None),
                PredictionLog.horizon_days == days,
            )
            .order_by(PredictionLog.created_at.desc())
            .limit(len(symbols) * 20)
        )
        logs = result.scalars().all()

        # Group by symbol
        by_symbol: Dict[str, list] = {}
        for log in logs:
            by_symbol.setdefault(log.symbol, []).append(log)

        asset_results = []
        all_mapes: List[float] = []
        dir_hits = 0
        dir_total = 0

        for sym in symbols:
            sym_logs = by_symbol.get(sym, [])
            mapes = [entry.mape for entry in sym_logs if entry.mape is not None]
            dirs = [entry.direction_correct for entry in sym_logs if entry.direction_correct is not None]
            avg_mape = float(np.mean(mapes)) if mapes else None
            dir_acc = sum(1 for d in dirs if d) / len(dirs) * 100 if dirs else None

            if avg_mape is not None:
                all_mapes.append(avg_mape)
            dir_hits += sum(1 for d in dirs if d)
            dir_total += len(dirs)

            asset_results.append(
                {
                    "symbol": sym,
                    "samples": len(sym_logs),
                    "avg_mape": round(avg_mape, 1) if avg_mape is not None else None,
                    "direction_accuracy": round(dir_acc, 1) if dir_acc is not None else None,
                }
            )

        overall_mape = float(np.mean(all_mapes)) if all_mapes else None
        overall_dir = dir_hits / dir_total * 100 if dir_total > 0 else None

        return {
            "assets": asset_results,
            "overall_mape": round(overall_mape, 1) if overall_mape is not None else None,
            "overall_direction_accuracy": round(overall_dir, 1) if overall_dir is not None else None,
            "needs_retraining": overall_mape is not None and overall_mape > 10.0,
            "days": days,
        }

    @staticmethod
    def _compute_support_resistance(prices: List[float], current_price: float) -> Tuple[float, float]:
        """Compute support/resistance using pivot points + price clustering.

        1. Classic pivot points (H, L, C of recent window)
        2. K-means clustering of local extrema to find key price levels
        3. Pick nearest support below and resistance above current price
        """
        recent = prices[-min(60, len(prices)) :]
        arr = np.array(recent, dtype=float)

        # --- Pivot points ---
        high = float(np.max(arr))
        low = float(np.min(arr))
        close = float(arr[-1])
        pivot = (high + low + close) / 3
        s1 = 2 * pivot - high
        s2 = pivot - (high - low)
        r1 = 2 * pivot - low
        r2 = pivot + (high - low)

        # --- Local extrema detection ---
        levels = [s1, s2, r1, r2, pivot]
        # Find local minima and maxima (±2 neighbors)
        for i in range(2, len(arr) - 2):
            if arr[i] <= arr[i - 1] and arr[i] <= arr[i + 1] and arr[i] <= arr[i - 2] and arr[i] <= arr[i + 2]:
                levels.append(float(arr[i]))
            elif arr[i] >= arr[i - 1] and arr[i] >= arr[i + 1] and arr[i] >= arr[i - 2] and arr[i] >= arr[i + 2]:
                levels.append(float(arr[i]))

        # --- Cluster nearby levels (within 1.5% of each other) ---
        levels.sort()
        clusters: List[List[float]] = []
        for lv in levels:
            if clusters and abs(lv - np.mean(clusters[-1])) / max(np.mean(clusters[-1]), 1e-10) < 0.015:
                clusters[-1].append(lv)
            else:
                clusters.append([lv])

        # Use cluster centroids as key levels
        key_levels = [float(np.mean(c)) for c in clusters]

        # P18: Add psychological round number levels
        # Determine the scale of the price to pick relevant round numbers
        if current_price >= 10_000:
            round_steps = [10_000, 5_000, 1_000]
        elif current_price >= 1_000:
            round_steps = [1_000, 500, 100]
        elif current_price >= 100:
            round_steps = [100, 50, 10]
        elif current_price >= 10:
            round_steps = [10, 5, 1]
        elif current_price >= 1:
            round_steps = [1, 0.5, 0.1]
        else:
            # Micro-price assets (PEPE, SHIB, etc.)
            round_steps = [0.01, 0.001, 0.0001]

        # Add round numbers within ±15% of current price
        zone_low = current_price * 0.85
        zone_high = current_price * 1.15
        for step in round_steps:
            # Find the first round number above zone_low
            start = math.ceil(zone_low / step) * step
            level = start
            while level <= zone_high:
                # Snap existing pivots to round number if within 3%
                snapped = False
                for i, kl in enumerate(key_levels):
                    if abs(kl - level) / max(level, 1e-10) < 0.03:
                        key_levels[i] = level  # snap to round
                        snapped = True
                        break
                if not snapped:
                    key_levels.append(level)
                level += step

        # Deduplicate close levels after adding round numbers
        key_levels = sorted(set(key_levels))

        # Find nearest support (below current) and resistance (above current)
        supports = [lv for lv in key_levels if lv < current_price]
        resistances = [lv for lv in key_levels if lv > current_price]

        support = max(supports) if supports else current_price * 0.95
        resistance = min(resistances) if resistances else current_price * 1.05

        return support, resistance

    def _compute_accuracy_from_data(self, dates: List, prices: List[float], max_windows: int = 30) -> float:
        """Compute prediction skill score via walk-forward backtest.

        skill_score = max(0, 1 - ensemble_MAPE / naive_MAPE) * 100
        0 = no better than naive (last price = future price), 100 = perfect.
        50 = our model is ~2x better than naive.

        Uses sliding 14-day windows with 7-day stride for statistical robustness.
        """
        try:
            if not prices or len(prices) < 60:
                return 50.0  # Not enough data for meaningful backtest

            ensemble_errors = []
            naive_errors = []
            n = len(prices)
            window_size = 14
            stride = 7

            # Slide from the most recent data backward
            offset = window_size
            windows_tested = 0
            while offset <= min(n - 30, 365) and windows_tested < max_windows:
                split = n - offset
                if split < 30:
                    break

                train_prices = prices[:split]
                train_dates = dates[:split] if dates else None
                horizon = min(window_size, n - split)
                if horizon < 3:
                    offset += stride
                    continue

                try:
                    result = self.forecaster.ensemble_forecast(train_prices, train_dates, horizon)
                except Exception:
                    try:
                        result = self.forecaster._linear_forecast(train_prices, train_dates, horizon)
                    except Exception:
                        offset += stride
                        continue

                naive_price = prices[split - 1]  # last known price = naive forecast

                for i in range(min(len(result.prices), horizon)):
                    actual = prices[split + i]
                    predicted = result.prices[i]
                    if actual > 0:
                        ensemble_errors.append(abs(predicted - actual) / actual)
                        naive_errors.append(abs(naive_price - actual) / actual)

                windows_tested += 1
                offset += stride

            if len(ensemble_errors) < 3:
                return 50.0  # Not enough data points for reliable score

            ensemble_mape = float(np.mean(ensemble_errors))
            baseline_mape = float(np.mean(naive_errors))

            if baseline_mape < 1e-10:
                return 50.0  # Prices didn't move — naive is perfect

            skill_score = max(0.0, 1.0 - ensemble_mape / baseline_mape) * 100
            return round(min(skill_score, 100.0), 1)
        except Exception as e:
            logger.warning("Accuracy computation failed: %s", e)
            return 50.0

    def _compute_hit_rate(self, dates: List, prices: List[float], max_samples: int = 50) -> Tuple[float, int, bool]:
        """Compute directional hit rate with statistical significance.

        Uses walk-forward windows + binomial test (H0: random = 50%).

        Returns:
            (hit_rate_pct, n_samples, significant): hit rate 0-100, sample count,
            and whether the result is statistically significant (p < 0.05).
        """
        try:
            if not prices or len(prices) < 60:
                return 50.0, 0, False

            hits = 0
            total = 0
            n = len(prices)
            stride = 7
            offset = 7

            while offset <= min(n - 30, 365) and total < max_samples:
                split = n - offset
                if split < 30:
                    break

                train_prices = prices[:split]
                train_dates = dates[:split] if dates else None
                horizon = min(7, n - split)
                if horizon < 1:
                    offset += stride
                    continue

                try:
                    result = self.forecaster.ensemble_forecast(train_prices, train_dates, horizon)
                except Exception:
                    offset += stride
                    continue

                # Check direction at end of horizon
                last_known = prices[split - 1]
                predicted_final = result.prices[-1] if result.prices else last_known
                actual_final = prices[min(split + horizon - 1, n - 1)]

                predicted_up = predicted_final > last_known
                actual_up = actual_final > last_known

                if predicted_up == actual_up:
                    hits += 1
                total += 1
                offset += stride

            if total < 3:
                return 50.0, total, False

            hit_rate = (hits / total) * 100

            # Binomial test: is this significantly better than 50%?
            significant = False
            try:
                from scipy.stats import binomtest

                result = binomtest(hits, total, 0.5, alternative="greater")
                significant = result.pvalue < 0.05
            except ImportError:
                # Fallback: normal approximation for large samples
                if total >= 20:
                    z = (hits - total * 0.5) / (total * 0.25) ** 0.5
                    significant = z > 1.645  # one-sided 5%

            return round(hit_rate, 1), total, significant
        except Exception:
            return 50.0, 0, False

    # -- Reliability from ensemble results (instant, no backtest) --

    @staticmethod
    def _compute_reliability_from_ensemble(
        models_detail: List[Dict], ensemble_trend: str
    ) -> Tuple[float, float, int, bool]:
        """Compute reliability from the ensemble's own MAPE and model consensus.

        Uses the already-computed backtest MAPE from each model (available in
        models_detail) plus directional agreement between models.

        Returns (skill_score, hit_rate_proxy, n_models, significant).
        """
        if not models_detail:
            return 50.0, 50.0, 0, False

        n_models = len(models_detail)

        # 1. Skill score: weighted MAPE → skill
        # Lower MAPE = better model. MAPE < 2% is excellent, > 20% is poor.
        mapes = []
        weights = []
        for m in models_detail:
            mape = m.get("mape")
            w = m.get("weight_pct", 10)
            if mape is not None and mape > 0:
                mapes.append(mape)
                weights.append(w)

        if mapes:
            # Weighted average MAPE
            total_w = sum(weights)
            if total_w > 0:
                avg_mape = sum(m * w for m, w in zip(mapes, weights)) / total_w
            else:
                avg_mape = float(np.mean(mapes))

            # Convert MAPE to skill: MAPE=1% → 90, MAPE=5% → 70, MAPE=15% → 40
            # Formula: skill = 100 - mape * 4 (clamped 15-95)
            skill_score = float(np.clip(100.0 - avg_mape * 4, 15, 95))
        else:
            skill_score = 50.0

        # 2. Hit rate proxy: model consensus on direction
        # "neutral" is compatible with both bullish and bearish (not opposing)
        trends = [m.get("trend", "neutral") for m in models_detail]
        compatible = 0
        opposing = 0
        for t in trends:
            if t == ensemble_trend:
                compatible += 1  # exact match
            elif t == "neutral":
                compatible += 0.5  # neutral is partially compatible
            else:
                opposing += 1  # opposite direction
        consensus_ratio = compatible / max(n_models, 1)

        # Map consensus: high agreement → high hit rate
        # All agree → 85, half agree → 60, all disagree → 30
        hit_rate = float(np.clip(30 + consensus_ratio * 65, 30, 85))

        # Significance: significant if >= 4 models and no strong opposition
        significant = n_models >= 4 and opposing <= 1

        return round(skill_score, 1), round(hit_rate, 1), n_models, significant

    # -- Lightweight accuracy metrics (no expensive backtest) --

    @staticmethod
    def _compute_lightweight_skill(prices: List[float]) -> float:
        """Estimate model skill from price predictability metrics.

        Uses autocorrelation and trend consistency as a proxy for how well
        ML models can predict this asset. Fast (no model re-runs).
        Returns 0-100 where 50 = baseline.
        """
        if not prices or len(prices) < 60:
            return 50.0
        try:
            arr = np.array(prices[-365:], dtype=float)
            returns = np.diff(arr) / np.maximum(arr[:-1], 1e-10)

            # 1. Autocorrelation of returns (lag 1-7)
            # High autocorrelation = more predictable
            n = len(returns)
            mean_r = float(np.mean(returns))
            var_r = float(np.var(returns))
            if var_r < 1e-15:
                return 50.0
            autocorr_sum = 0.0
            for lag in range(1, min(8, n)):
                cov = float(np.mean((returns[lag:] - mean_r) * (returns[:-lag] - mean_r)))
                autocorr_sum += abs(cov / var_r)
            avg_autocorr = autocorr_sum / 7

            # 2. Trend consistency: % of 7-day windows with consistent direction
            consistent = 0
            total_windows = 0
            for i in range(0, n - 7, 7):
                window = returns[i : i + 7]
                pos = np.sum(window > 0)
                if pos >= 5 or pos <= 2:  # 5+ up or 5+ down = consistent
                    consistent += 1
                total_windows += 1
            trend_consistency = consistent / max(total_windows, 1)

            # 3. Combine: autocorrelation (40%) + trend consistency (60%)
            # Scale to 30-75 range (realistic for crypto)
            raw = avg_autocorr * 0.4 + trend_consistency * 0.6
            score = 30 + raw * 60  # maps [0,1] -> [30,90]
            return round(float(np.clip(score, 20, 80)), 1)
        except Exception:
            return 50.0

    @staticmethod
    def _compute_lightweight_hit_rate(
        prices: List[float],
    ) -> Tuple[float, int, bool]:
        """Estimate directional hit rate from trend persistence.

        Measures how often the 7-day direction matches the prior 7-day
        direction (proxy for whether trend-following models would succeed).
        Returns (hit_rate_pct, n_samples, significant).
        """
        if not prices or len(prices) < 60:
            return 50.0, 0, False
        try:
            arr = np.array(prices[-365:], dtype=float)
            hits = 0
            total = 0
            for i in range(14, len(arr), 7):
                prev_dir = arr[i - 7] < arr[i - 14]  # prior 7d went up?
                curr_dir = arr[i] > arr[i - 7]  # this 7d went up?
                # A simple predictor would predict "same direction continues"
                if prev_dir == curr_dir:
                    hits += 1
                total += 1

            if total < 3:
                return 50.0, total, False

            hit_rate = (hits / total) * 100

            # Significance: binomial test approximation
            significant = False
            if total >= 15:
                z = (hits - total * 0.5) / max((total * 0.25) ** 0.5, 1e-10)
                significant = z > 1.645  # one-sided 5%

            return round(hit_rate, 1), total, significant
        except Exception:
            return 50.0, 0, False

    # -- Private helpers --

    async def _get_current_price(self, symbol: str, asset_type: AssetType) -> float:
        """Get current price for an asset."""
        try:
            if asset_type == AssetType.CRYPTO:
                data = await self.price_service.get_crypto_price(symbol)
            elif asset_type in [AssetType.STOCK, AssetType.ETF]:
                data = await self.price_service.get_stock_price(symbol)
            else:
                return 0.0

            if data and "price" in data:
                return float(data["price"])
            return 0.0
        except Exception:
            return 0.0

    async def _get_daily_volatility(self, symbol: str, asset_type: AssetType) -> float:
        """Compute daily volatility from actual historical data."""
        try:
            cached_hist = await get_cached_history(symbol, asset_type.value, 30)
            if cached_hist:
                prices = cached_hist["prices"]
            else:
                hist_dates, prices = await self.data_fetcher.get_history(symbol, asset_type.value, days=30)
                if hist_dates and prices:
                    await cache_history(
                        symbol,
                        asset_type.value,
                        30,
                        {
                            "dates": [d.isoformat() for d in hist_dates],
                            "prices": prices,
                        },
                    )
            if prices and len(prices) >= 5:
                returns = [
                    (prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices)) if prices[i - 1] > 0
                ]
                if returns:
                    return float(np.std(returns))
        except Exception:
            pass
        # Fallback only if data unavailable
        fallback = {
            AssetType.CRYPTO: 0.05,
            AssetType.STOCK: 0.015,
            AssetType.ETF: 0.01,
            AssetType.REAL_ESTATE: 0.002,
        }
        return fallback.get(asset_type, 0.02)

    def _generate_recommendation(
        self,
        trend: str,
        trend_strength: float,
        current_price: float,
        support: float,
        resistance: float,
        regime_info: Optional[Dict] = None,
    ) -> str:
        """Observational regime/trend context, always suffixed with the non-advice disclaimer.

        Trust & Safety: framed as observations (what the detected regime is
        historically associated with), never as prescriptive orders — InvestAI is
        not a licensed adviser. The mandatory disclaimer is appended to every output.
        """
        # Lazy import avoids a circular import (ai_strategy_service imports this module).
        from app.services.ai_strategy_service import AI_DISCLAIMER

        body = self._recommendation_body(trend, trend_strength, current_price, support, resistance, regime_info)
        return f"{body}\n\n{AI_DISCLAIMER}"

    def _recommendation_body(
        self,
        trend: str,
        trend_strength: float,
        current_price: float,
        support: float,
        resistance: float,
        regime_info: Optional[Dict] = None,
    ) -> str:
        """Observational regime/trend context in French (no prescriptive orders)."""
        regime = regime_info.get("dominant_regime") if regime_info else None
        reg_conf = regime_info.get("confidence", 0) if regime_info else 0

        # Regime-first observations when confidence is high enough
        if reg_conf > 0.4 and regime:
            if regime == "bottom":
                if trend == "bearish":
                    return (
                        "Zone de creux potentiel avec une tendance encore baissière. "
                        "Historiquement, ces phases ont été associées à une accumulation "
                        "progressive plutôt qu'à un timing précis du point bas."
                    )
                return (
                    "Signaux de creux détectés ; un rebond pourrait se confirmer. "
                    "Ces configurations ont historiquement précédé des phases de reprise."
                )
            if regime == "bearish":
                if trend == "bearish" and trend_strength > 50:
                    return (
                        "Marché baissier confirmé : les prix sont décotés par rapport aux "
                        f"plus hauts récents. Support technique estimé vers {current_price * 0.9:.0f}."
                    )
                if trend == "bullish":
                    return (
                        "Signal haussier en marché baissier — possible retournement, sans garantie. "
                        "Ces zones ont historiquement présenté un rapport rendement/risque plus favorable."
                    )
                return (
                    "Marché baissier — contexte historiquement associé aux phases "
                    "d'accumulation ; les creux de cycle s'y sont souvent formés."
                )
            if regime == "top":
                return (
                    "Signes de sommet de marché : le risque de correction est "
                    f"historiquement élevé dans ces configurations. Support à surveiller : {support:.0f}."
                )
            if regime == "bullish":
                if trend == "bullish" and trend_strength > 50:
                    return (
                        "Tendance haussière forte. Le risque de retournement tend à "
                        f"augmenter à mesure que le mouvement s'étend ; résistance à surveiller : {resistance:.0f}."
                    )
                return "Marché haussier : la dynamique reste positive. " f"Résistance à surveiller : {resistance:.0f}."

        # Fallback: trend-based observation
        if trend == "bullish" and trend_strength > 50:
            return "Tendance haussière forte détectée."
        elif trend == "bullish":
            return "Tendance légèrement haussière détectée."
        elif trend == "bearish" and trend_strength > 50:
            return "Tendance baissière forte détectée ; prix décotés par rapport aux plus hauts récents."
        elif trend == "bearish":
            return "Tendance légèrement baissière détectée."
        return "Tendance neutre — pas de signal directionnel clair."

    @staticmethod
    def _ema20_fallback(
        prices: List[float],
        current_price: float,
        days_ahead: int,
        smart_round,
    ) -> Tuple[List[Dict], str, float]:
        """EMA-20 slope extrapolation — used as sanity fallback when ensemble is unrealistic.

        Returns (predictions_list, trend, trend_strength).
        Returns empty list if insufficient data.
        """
        if not prices or len(prices) < 20 or current_price <= 0:
            return [], "neutral", 0.0

        arr = np.array(prices[-20:], dtype=float)
        ema = arr.copy()
        k = 2 / 21  # EMA-20 smoothing factor
        for idx in range(1, len(ema)):
            ema[idx] = arr[idx] * k + ema[idx - 1] * (1 - k)

        # Daily slope from last 5 EMA values
        daily_slope = (ema[-1] - ema[-5]) / max(ema[-5], 1e-10) / 5
        # Clamp daily slope to ±2% per day (prevents extreme extrapolation)
        daily_slope = max(-0.02, min(0.02, daily_slope))

        trend = "bullish" if daily_slope > 0.001 else "bearish" if daily_slope < -0.001 else "neutral"
        trend_strength = min(80.0, abs(daily_slope) * 5000)

        predictions = []
        for day in range(1, days_ahead + 1):
            date = (datetime.now(timezone.utc) + timedelta(days=day)).strftime("%Y-%m-%d")
            predicted = current_price * (1 + daily_slope * day)
            predicted = max(0.0, predicted)
            # Conservative CI: ±3% * sqrt(day)
            ci_margin = 0.03 * math.sqrt(day)
            predictions.append(
                {
                    "date": date,
                    "price": smart_round(predicted),
                    "confidence_low": smart_round(predicted * (1 - ci_margin)),
                    "confidence_high": smart_round(predicted * (1 + ci_margin)),
                }
            )

        return predictions, trend, trend_strength

    async def _random_walk_fallback(
        self,
        symbol: str,
        current_price: float,
        asset_type: AssetType,
        days_ahead: int,
    ) -> Tuple[List[Dict], str, float]:
        """Deterministic fallback when no historical data available (FIX3).

        Uses observed momentum from cached prices if available,
        otherwise flat prediction. No randomness — identical calls
        produce identical results.
        """
        daily_volatility = await self._get_daily_volatility(symbol, asset_type)

        # Try to get cached prices for momentum estimation
        trend_factor = 0.0
        cached_hist = await get_cached_history(symbol, asset_type.value, 30)
        if cached_hist and len(cached_hist.get("prices", [])) >= 2:
            cached_prices = cached_hist["prices"]
            # Observed daily momentum from last 7 days (or available)
            window = cached_prices[-min(7, len(cached_prices)) :]
            if len(window) >= 2 and window[0] > 0:
                trend_factor = (window[-1] - window[0]) / (window[0] * len(window))

        trend = "bullish" if trend_factor > 0.005 else "bearish" if trend_factor < -0.005 else "neutral"
        trend_strength = min(100.0, abs(trend_factor) * 1000)

        predictions = []
        base_price = current_price

        def _rw_round(v):
            if abs(v) < 0.01:
                return round(v, 10)
            return round(v, 2)

        for day in range(1, days_ahead + 1):
            date = datetime.now(timezone.utc) + timedelta(days=day)
            # FIX3: linear projection instead of cumulative random chain
            predicted_price = base_price * (1 + trend_factor * day)
            predicted_price = max(0.0, predicted_price)
            # CI based on volatility * sqrt(day) * 1.96 (no randomness)
            ci_width = daily_volatility * math.sqrt(day) * 1.96
            confidence_low = predicted_price * (1 - ci_width)
            confidence_high = predicted_price * (1 + ci_width)

            predictions.append(
                {
                    "date": date.strftime("%Y-%m-%d"),
                    "price": _rw_round(predicted_price),
                    "confidence_low": _rw_round(max(0, confidence_low)),
                    "confidence_high": _rw_round(confidence_high),
                }
            )

        return predictions, trend, trend_strength

    def _empty_prediction(self, symbol: str) -> PricePrediction:
        """Return empty prediction."""
        return PricePrediction(
            symbol=symbol,
            current_price=0,
            predictions=[],
            trend="neutral",
            trend_strength=0,
            support_level=0,
            resistance_level=0,
            recommendation="Données insuffisantes pour générer une prédiction",
            model_used="none",
        )


# Singleton instance
prediction_service = PredictionService()
