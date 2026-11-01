"""Ordres de rééquilibrage vers l'optimum de Markowitz, freinés en marché baissier."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.analytics.service import analytics_service
from app.domains.insights.results import RebalancingOrder
from app.ml.regime_detector import MarketRegime

logger = logging.getLogger(__name__)

_MIN_WEIGHT_GAP = 0.05
_BEAR_WEIGHT_GAP = 0.10
_BEAR_REGIMES = ("bearish", "top")
_BEAR_CONFIDENCE = 0.5
_DEFERRED_SALE_CONFIDENCE = 0.6
_MAX_CASH_RESERVE = 0.30
_CASH_RESERVE_RATIO = 0.4


def _bear_confidence(market_regime: MarketRegime | None) -> float | None:
    if market_regime is None or market_regime.market.dominant_regime not in _BEAR_REGIMES:
        return None
    confidence = market_regime.market.confidence
    return confidence if confidence > _BEAR_CONFIDENCE else None


def _cash_reserve_order(total_value: float, confidence: float) -> RebalancingOrder:
    reserve = min(_MAX_CASH_RESERVE, confidence * _CASH_RESERVE_RATIO)
    amount = total_value * reserve
    return RebalancingOrder(
        symbol="CASH",
        name="Réserve de liquidités",
        action="hold",
        current_weight=0.0,
        target_weight=reserve,
        current_value_eur=0.0,
        target_value_eur=amount,
        amount_eur=amount,
        reason=(
            f"Marché baissier (confiance {confidence * 100:.0f}%) — "
            f"Constituez une réserve cash de {reserve * 100:.0f}% "
            f"({amount:,.0f}€) pour accumuler au creux."
        ),
    )


def _action_and_reason(amount: float, current: float, target: float, confidence: float | None) -> tuple[str, str]:
    if amount > 0:
        return "buy", f"Augmenter de {current * 100:.1f}% → {target * 100:.1f}% pour optimiser le Sharpe"
    if confidence is not None and confidence > _DEFERRED_SALE_CONFIDENCE:
        return "hold", (
            "Marché baissier — vente différée. "
            f"Poids actuel {current * 100:.1f}% vs optimal {target * 100:.1f}%. "
            "Attendre une amélioration du régime avant de rééquilibrer."
        )
    return "sell", f"Réduire de {current * 100:.1f}% → {target * 100:.1f}% (surpondéré)"


def _orders(
    optimal_weights: dict[str, float],
    allocation: dict[str, float],
    total_value: float,
    confidence: float | None,
) -> list[RebalancingOrder]:
    min_gap = _MIN_WEIGHT_GAP if confidence is None else _BEAR_WEIGHT_GAP
    orders = []
    for symbol, target_weight in optimal_weights.items():
        percent = allocation.get(symbol)
        current_weight = percent / 100 if percent is not None else 0
        current_value = total_value * percent / 100 if percent is not None else 0
        if abs(target_weight - current_weight) < min_gap:
            continue
        target_value = total_value * target_weight
        amount = target_value - current_value
        action, reason = _action_and_reason(amount, current_weight, target_weight, confidence)
        orders.append(
            RebalancingOrder(
                symbol=symbol,
                name=symbol,
                action=action,
                current_weight=current_weight,
                target_weight=target_weight,
                current_value_eur=current_value,
                target_value_eur=target_value,
                amount_eur=abs(amount),
                reason=reason,
            )
        )
    return orders


async def rebalancing_orders(
    db: AsyncSession,
    user_id: str,
    total_value: float,
    market_regime: MarketRegime | None,
    allocation: dict[str, float],
) -> list[RebalancingOrder]:
    """Ordres triés par montant ; en marché baissier, écart exigé doublé, ventes différées et réserve de liquidités."""
    if total_value <= 0:
        return []
    try:
        optimization = await analytics_service.optimize_portfolio(db, user_id, objective="max_sharpe")
        if not optimization or not optimization.weights:
            return []
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to get optimization: %s", exc)
        return []
    confidence = _bear_confidence(market_regime)
    optimal_weights = {symbol: weight / 100 for symbol, weight in optimization.weights.items()}
    orders = _orders(optimal_weights, allocation, total_value, confidence)
    if confidence is not None:
        orders.insert(0, _cash_reserve_order(total_value, confidence))
    orders.sort(key=lambda order: order.amount_eur, reverse=True)
    return orders
