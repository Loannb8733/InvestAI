"""Régime de marché, sur le BTC pris pour le marché et sur les premières lignes."""

import logging
from typing import Any

from app.domains.market_data.fear_greed import fetch_fear_greed_index
from app.domains.market_data.history.reader import local_series
from app.domains.market_data.prices.service import price_feed
from app.ml.regime_detector import MarketRegime, MarketRegimeDetector, RegimeConfig, RegimeResult

logger = logging.getLogger(__name__)

_MIN_REGIME_DAYS = 90
_MIN_PRICES = 7
_TOP_HOLDINGS = 5

_detector = MarketRegimeDetector()


async def _per_asset(
    top_holdings: list[dict[str, Any]], days: int, fear_greed: int | None, vix: float | None
) -> list[RegimeResult]:
    results: list[RegimeResult] = []
    done: set[str] = set()
    for holding in top_holdings[:_TOP_HOLDINGS]:
        symbol = holding.get("symbol", "")
        if not symbol or symbol in done:
            continue
        done.add(symbol)
        try:
            prices = (await local_series(symbol, days)).prices
            if len(prices) >= _MIN_PRICES:
                results.append(_detector.detect(prices, symbol, fear_greed, vix=vix))
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not fetch history for %s: %s", symbol, exc)
    return results


async def detect_market_regime(top_holdings: list[dict[str, Any]], days: int = 30) -> MarketRegime | None:
    """Régime du marché et des cinq premières lignes ; None sans historique du BTC ou en cas d'échec."""
    regime_days = max(days, _MIN_REGIME_DAYS)
    try:
        fear_greed = await fetch_fear_greed_index(timeout=10.0)
        vix = await price_feed.index_level("^VIX")
        btc_prices = (await local_series("BTC", regime_days)).prices
        if len(btc_prices) < _MIN_PRICES:
            logger.warning("Historique BTC indisponible — régime de marché non calculé")
            return None
        market = _detector.detect(btc_prices, "BTC (Marche)", fear_greed, vix=vix)
        return MarketRegime(market=market, per_asset=await _per_asset(top_holdings, regime_days, fear_greed, vix))
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to detect market regime: %s", exc)
        return None


async def current_vol_regime() -> str:
    """Régime de volatilité du BTC : `stress`, `normal` ou `low` ; `normal` si la détection échoue."""
    try:
        prices = (await local_series("BTC", _MIN_REGIME_DAYS)).prices
        if len(prices) < _MIN_PRICES:
            return "normal"
        result = _detector.detect(prices, "BTC")
        return RegimeConfig.from_regime(result.dominant_regime, result.confidence).vol_regime
    except Exception:
        logger.warning("Détection de régime indisponible — régime supposé normal", exc_info=True)
        return "normal"
