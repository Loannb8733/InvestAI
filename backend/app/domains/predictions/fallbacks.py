import logging
import math
from datetime import UTC, datetime, timedelta

import numpy as np

from app.domains.market_data.history.reader import local_series
from app.domains.portfolio.models import AssetType
from app.domains.predictions.types import ForecastPoint, PricePrediction

logger = logging.getLogger(__name__)

FALLBACK_VOLATILITY = {
    AssetType.CRYPTO: 0.05,
    AssetType.STOCK: 0.015,
    AssetType.ETF: 0.01,
    AssetType.REAL_ESTATE: 0.002,
}


def smart_round(v: float) -> float:
    """Arrondi à 2 décimales, 10 sous 0,01 pour les micro-cours (PEPE, SHIB…)."""
    if v == 0:
        return 0.0
    if abs(v) < 0.01:
        return round(v, 10)
    return round(v, 2)


def _random_walk_round(v: float) -> float:
    if abs(v) < 0.01:
        return round(v, 10)
    return round(v, 2)


def empty_prediction(symbol: str) -> PricePrediction:
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


async def daily_volatility(symbol: str, asset_type: AssetType) -> float:
    """Écart-type des rendements quotidiens sur 30 jours ; à défaut une volatilité type de la classe d'actif."""
    try:
        prices = (await local_series(symbol, 30)).prices
        if prices and len(prices) >= 5:
            returns = [(prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices)) if prices[i - 1] > 0]
            if returns:
                return float(np.std(returns))
    except Exception as exc:  # noqa: BLE001
        logger.debug("Daily volatility computation failed for %s, using fallback: %s", symbol, exc)
    return FALLBACK_VOLATILITY.get(asset_type, 0.02)


def ema20_forecast(
    prices: list[float], current_price: float, days_ahead: int
) -> tuple[list[ForecastPoint], str, float]:
    """Prolongement de la pente de l'EMA-20 (bornée à ±2 %/jour, intervalle ±3 % * √jour), repli du garde-fou ;
    liste vide sous 20 cours."""
    if not prices or len(prices) < 20 or current_price <= 0:
        return [], "neutral", 0.0

    arr = np.array(prices[-20:], dtype=float)
    ema = arr.copy()
    k = 2 / 21
    for idx in range(1, len(ema)):
        ema[idx] = arr[idx] * k + ema[idx - 1] * (1 - k)

    daily_slope = (ema[-1] - ema[-5]) / max(ema[-5], 1e-10) / 5
    daily_slope = max(-0.02, min(0.02, daily_slope))

    trend = "bullish" if daily_slope > 0.001 else "bearish" if daily_slope < -0.001 else "neutral"
    trend_strength = min(80.0, abs(daily_slope) * 5000)

    predictions: list[ForecastPoint] = []
    for day in range(1, days_ahead + 1):
        date = (datetime.now(UTC) + timedelta(days=day)).strftime("%Y-%m-%d")
        predicted = current_price * (1 + daily_slope * day)
        predicted = max(0.0, predicted)
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


async def _momentum(symbol: str) -> float:
    cached_prices = (await local_series(symbol, 30)).prices
    if len(cached_prices) >= 2:
        window = cached_prices[-min(7, len(cached_prices)) :]
        if len(window) >= 2 and window[0] > 0:
            return (window[-1] - window[0]) / (window[0] * len(window))
    return 0.0


async def random_walk_forecast(
    symbol: str, current_price: float, asset_type: AssetType, days_ahead: int
) -> tuple[list[ForecastPoint], str, float]:
    """Projection linéaire déterministe sans historique : momentum des 7 derniers cours connus (sinon plat),
    intervalle à 1,96 * volatilité * √jour."""
    volatility = await daily_volatility(symbol, asset_type)
    trend_factor = await _momentum(symbol)

    trend = "bullish" if trend_factor > 0.005 else "bearish" if trend_factor < -0.005 else "neutral"
    trend_strength = min(100.0, abs(trend_factor) * 1000)

    predictions: list[ForecastPoint] = []
    for day in range(1, days_ahead + 1):
        date = datetime.now(UTC) + timedelta(days=day)
        predicted_price = current_price * (1 + trend_factor * day)
        predicted_price = max(0.0, predicted_price)
        ci_width = volatility * math.sqrt(day) * 1.96
        confidence_low = predicted_price * (1 - ci_width)
        confidence_high = predicted_price * (1 + ci_width)
        predictions.append(
            {
                "date": date.strftime("%Y-%m-%d"),
                "price": _random_walk_round(predicted_price),
                "confidence_low": _random_walk_round(max(0, confidence_low)),
                "confidence_high": _random_walk_round(confidence_high),
            }
        )
    return predictions, trend, trend_strength
