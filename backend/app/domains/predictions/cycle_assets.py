import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import numpy as np

from app.domains.portfolio.classification import is_safe_haven
from app.domains.portfolio.models import Asset
from app.ml import adaptive_thresholds as at
from app.ml.market_context import MarketContext, compute_market_context
from app.ml.regime_detector import MarketRegimeDetector, RegimeResult

logger = logging.getLogger(__name__)


def _empty_regime_weights() -> dict[str, float]:
    return {"bearish": 0.0, "bottom": 0.0, "bullish": 0.0, "top": 0.0}


@dataclass(slots=True)
class MarketReference:
    btc_prices: list[float] | None
    fear_greed: int | None
    btc_dominance: float | None
    btc_regime: dict[str, Any] | None = None
    btc_signals: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class PortfolioCycle:
    per_asset: list[dict[str, Any]] = field(default_factory=list)
    total_value: Decimal = Decimal("0")
    regime_weighted: dict[str, float] = field(default_factory=_empty_regime_weights)


def _btc_correlation(symbol: str, prices: list[float], btc_prices: list[float] | None) -> float | None:
    btc_corr = None
    if btc_prices and symbol != "BTC" and len(prices) >= 20:
        try:
            bp = btc_prices[-len(prices) :] if len(btc_prices) >= len(prices) else btc_prices
            n = min(len(bp), len(prices))
            if n >= 20:
                br = np.diff(np.log(np.array(bp[-n:], dtype=float)))
                ar = np.diff(np.log(np.array(prices[-n:], dtype=float)))
                btc_corr = round(float(np.corrcoef(br, ar)[0, 1]), 2)
        except Exception as exc:  # noqa: BLE001
            logger.debug("BTC correlation computation failed for %s: %s", symbol, exc)
    return btc_corr


def asset_cycle_row(
    detector: MarketRegimeDetector,
    asset: Asset,
    value: float,
    prices: list[float],
    ref: MarketReference,
) -> dict[str, Any]:
    """Régime d'un actif détenu ; le BTC reprend le régime de référence, comme la carte « Régime BTC »."""
    ath = max(prices)
    drawdown_from_ath = round((prices[-1] / ath - 1) * 100, 1) if ath > 0 else 0.0
    btc_corr = _btc_correlation(asset.symbol, prices, ref.btc_prices)

    if asset.symbol == "BTC" and ref.btc_regime:
        regime = RegimeResult(
            symbol=asset.symbol,
            probabilities=ref.btc_regime["probabilities"],
            dominant_regime=ref.btc_regime["dominant_regime"],
            confidence=ref.btc_regime["confidence"],
            signals=[],
            description="",
        )
    else:
        regime = detector.detect(
            prices,
            asset.symbol,
            ref.fear_greed,
            ref.btc_dominance,
            asset_type=asset.asset_type.value,
        )
    return {
        "symbol": asset.symbol,
        "name": asset.name,
        "asset_type": asset.asset_type.value,
        "value": round(value, 2),
        "dominant_regime": regime.dominant_regime,
        "regime_6phase": MarketRegimeDetector.refine_to_6phase(regime, prices),
        "confidence": regime.confidence,
        "probabilities": regime.probabilities,
        "drawdown_from_ath": drawdown_from_ath,
        "btc_correlation": btc_corr,
        "is_resilient": is_safe_haven(asset.symbol),
    }


def portfolio_probabilities(regime_weighted: dict[str, float], total_value: float) -> dict[str, float]:
    if total_value > 0:
        return {p: round(v / total_value, 4) for p, v in regime_weighted.items()}
    return {p: 0.25 for p in regime_weighted}


def market_cycle_position(ref: MarketReference) -> tuple[MarketContext | None, int]:
    """Position 0-100 dans le cycle, tirée du contexte BTC (30 jours minimum) ; sinon table fixe par régime dominant."""
    btc_ctx: MarketContext | None = None
    btc_probs = ref.btc_regime.get("probabilities") if ref.btc_regime else None
    if ref.btc_prices and len(ref.btc_prices) >= 30:
        btc_ctx = compute_market_context(ref.btc_prices, "BTC", "crypto", ref.fear_greed)
        return btc_ctx, round(at.cycle_position(btc_ctx, regime_probs=btc_probs))
    cycle_map = {"bottom": 10, "bullish": 40, "top": 75, "bearish": 85}
    return btc_ctx, cycle_map.get(ref.btc_regime["dominant_regime"] if ref.btc_regime else "bearish", 50)


def max_value_weight(per_asset: list[dict[str, Any]], total_value: float) -> float:
    """Plus forte part en valeur d'un actif, en %, approximation rapide de son poids de risque."""
    max_rw = 0.0
    if per_asset:
        values = [a["value"] for a in per_asset if a.get("value", 0) > 0]
        if values and total_value > 0:
            max_rw = max(v / total_value * 100 for v in values)
    return max_rw
