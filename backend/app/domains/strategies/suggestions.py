import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import get_cached_contrarian_stats
from app.domains.predictions.service import prediction_service
from app.domains.strategies.builders_buy import build_conviction_buy_strategy, build_dca_strategy, build_vca_strategy
from app.domains.strategies.builders_portfolio import (
    build_rebalance_strategy,
    build_stablecoin_yield_strategy,
    build_swing_strategy,
)
from app.domains.strategies.builders_sell import (
    build_profit_taking_strategy,
    build_progressive_profit_plan,
    build_rotation_strategy,
)
from app.domains.strategies.disclaimer import AI_DISCLAIMER
from app.domains.strategies.models import ActionStatus, Strategy, StrategyAction, StrategySource, StrategyStatus
from app.domains.strategies.service import strategy_service
from app.domains.strategies.suggestion_types import BEAR_REGIMES, AssetRow, Suggestion

logger = logging.getLogger(__name__)

_ACCUMULATION_REGIMES = (*BEAR_REGIMES, "bottoming")
_SELL_KEYWORDS = ("VENDRE", "PROFITS", "ALLÉGER")
_BUY_ACTIONS = ("VCA", "DCA", "ACHAT", "ACHAT FORT", "RENFORCER")
_RISK_MAP: dict[str, tuple[int, int]] = {
    "observation": (1, 1),
    "stablecoin_yield": (1, 1),
    "defensive": (1, 2),
    "rebalance": (2, 2),
    "dca_sélectif": (2, 2),
    "dca_modéré": (2, 2),
    "profit_taking": (2, 3),
    "progressive_profit": (2, 3),
    "rotation": (3, 3),
    "dca_agressif": (3, 3),
    "vca": (3, 4),
    "swing": (4, 4),
    "conviction_buy": (4, 4),
}


@dataclass(frozen=True)
class _Signals:
    assets: list[AssetRow]
    regime: str
    confidence: float
    fear_greed: Any
    liquidity: float
    total_value: float
    buy: list[AssetRow]
    sell: list[AssetRow]
    hold: list[AssetRow]
    has_high_volatility: bool
    is_accumulation: bool


async def _load_strategy_map(db: AsyncSession, user_id: str) -> dict[str, Any]:
    try:
        return await prediction_service.get_strategy_map(db, user_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to get strategy map: %s", e)
        return {"rows": [], "summary": {}, "market_regime": "unknown"}


async def _load_capacity(db: AsyncSession, user_id: str) -> tuple[float, float]:
    try:
        capacity = await strategy_service.get_deployment_capacity(db, user_id)
        return capacity.available_liquidity, capacity.total_value
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to get deployment capacity: %s", e)
        return 0.0, 0.0


def _accumulation_candidates(assets: list[AssetRow], fear_greed: Any) -> list[AssetRow]:
    min_alpha = 15 if (fear_greed and fear_greed < 25) else 30
    top_alpha = sorted(assets, key=lambda a: a.get("alpha_score", 0), reverse=True)
    candidates = [a for a in top_alpha if a.get("alpha_score", 0) >= min_alpha][:5]
    if not candidates and fear_greed and fear_greed < 15:
        return top_alpha[:3]
    return candidates


def _read_signals(strategy_map: dict[str, Any], liquidity: float, total_value: float) -> _Signals:
    assets: list[AssetRow] = strategy_map.get("rows", [])
    regime: str = strategy_map.get("market_regime", "unknown") or "unknown"
    fear_greed = strategy_map.get("fear_greed")
    confidence = (fear_greed / 100.0) if fear_greed and isinstance(fear_greed, int | float) else 0.5

    buy = [a for a in assets if "ACHAT" in a.get("action", "") or a.get("action") == "DCA"]
    sell = [a for a in assets if any(kw in a.get("action", "") for kw in _SELL_KEYWORDS)]
    hold = [a for a in assets if a not in buy and a not in sell]

    predictions = [abs(a.get("predicted_7d_pct", 0)) for a in assets if a.get("predicted_7d_pct")]
    avg_volatility = sum(predictions) / len(predictions) if predictions else 0

    is_accumulation = regime in _ACCUMULATION_REGIMES
    if is_accumulation and not buy:
        buy = _accumulation_candidates(assets, fear_greed)

    return _Signals(
        assets=assets,
        regime=regime,
        confidence=confidence,
        fear_greed=fear_greed,
        liquidity=liquidity,
        total_value=total_value,
        buy=buy,
        sell=sell,
        hold=hold,
        has_high_volatility=avg_volatility > 5,
        is_accumulation=is_accumulation,
    )


def _profit_taking_outside_accumulation(sig: _Signals) -> Suggestion | None:
    if sig.sell and not sig.is_accumulation:
        return build_profit_taking_strategy(sig.sell, sig.regime, sig.confidence)
    return None


def _rebalance_if_diversified(sig: _Signals) -> Suggestion | None:
    if len(sig.assets) >= 3:
        return build_rebalance_strategy(sig.assets, sig.regime, sig.confidence, sig.total_value)
    return None


def _selective_profit_taking(sig: _Signals) -> Suggestion | None:
    if not sig.sell or not sig.is_accumulation:
        return None
    very_weak = [a for a in sig.sell if a.get("alpha_score", 0) < 15]
    if not very_weak:
        return None
    return build_profit_taking_strategy(very_weak, sig.regime, sig.confidence)


def _signal_strategies(sig: _Signals) -> list[Suggestion | None]:
    return [
        build_vca_strategy(sig.buy, sig.regime, sig.confidence, sig.liquidity, sig.has_high_volatility),
        build_dca_strategy(sig.buy, sig.regime, sig.confidence, sig.liquidity, sig.has_high_volatility),
        _profit_taking_outside_accumulation(sig),
        build_rotation_strategy(sig.buy, sig.sell, sig.regime, sig.confidence, sig.total_value),
        _rebalance_if_diversified(sig),
        build_swing_strategy(sig.assets, sig.regime, sig.confidence, sig.has_high_volatility, sig.liquidity),
        _selective_profit_taking(sig),
        build_stablecoin_yield_strategy(sig.assets, sig.regime, sig.confidence, sig.liquidity, sig.total_value),
    ]


async def _cycle_strategies(sig: _Signals) -> list[Suggestion | None]:
    contrarian_stats = await get_cached_contrarian_stats()
    return [
        build_conviction_buy_strategy(
            sig.buy, sig.assets, sig.regime, sig.confidence, sig.fear_greed, sig.liquidity, contrarian_stats
        ),
        build_progressive_profit_plan(sig.sell, sig.hold, sig.regime, sig.confidence),
    ]


def _observation(regime: str, confidence: float) -> Suggestion:
    return {
        "name": "Observation — Attente de signaux",
        "description": (
            f"Le marché est en phase '{regime}' sans signaux forts. "
            "Continuez à surveiller. Aucune action immédiate recommandée."
        ),
        "params": {"type": "observation"},
        "ai_reasoning": "Aucun signal d'achat ou de vente suffisamment fort détecté.",
        "market_regime": regime,
        "confidence": confidence,
        "actions": [],
    }


def _enriched_params(strategy: Suggestion, liquidity: float, total_value: float) -> dict[str, Any]:
    params: dict[str, Any] = strategy.get("params", {})
    params["available_liquidity"] = round(liquidity, 2)
    params["total_portfolio_value"] = round(total_value, 2)

    stype = str(params.get("type", "")).lower()
    risk_level, perf_potential = _RISK_MAP.get(stype, (2, 2))
    params["risk_level"] = risk_level
    params["performance_potential"] = perf_potential

    total_proposed = sum(
        a.get("amount", 0) or 0 for a in strategy.get("actions", []) if a.get("action") in _BUY_ACTIONS
    )
    params["total_proposed_amount"] = round(total_proposed, 2)
    params["proposed_pct_of_liquidity"] = round(total_proposed / liquidity * 100, 1) if liquidity > 0 else 0
    return params


def _ranking_key(strategy: Suggestion) -> tuple[Any, Any]:
    return (
        -(strategy.get("params", {}).get("performance_potential", 2)),
        -(strategy.get("params", {}).get("risk_level", 2)),
    )


def _finalize(strategies: list[Suggestion], liquidity: float, total_value: float) -> list[Suggestion]:
    for s in strategies:
        s["params"] = _enriched_params(s, liquidity, total_value)
        existing_reasoning = (s.get("ai_reasoning") or "").rstrip()
        if AI_DISCLAIMER not in existing_reasoning:
            s["ai_reasoning"] = f"{existing_reasoning}\n\n{AI_DISCLAIMER}".strip()
    strategies.sort(key=_ranking_key)
    return strategies


class AIStrategyService:
    async def suggest_strategies(self, db: AsyncSession, user_id: str) -> list[dict[str, Any]]:
        """Propositions selon le régime de marché, les signaux alpha et la liquidité, triées par potentiel puis risque
        décroissants ; chacune porte la mention AI_DISCLAIMER, reprise telle quelle à l'enregistrement."""
        strategy_map = await _load_strategy_map(db, user_id)
        liquidity, total_value = await _load_capacity(db, user_id)
        sig = _read_signals(strategy_map, liquidity, total_value)

        candidates = _signal_strategies(sig) + await _cycle_strategies(sig)
        strategies = [s for s in candidates if s]
        if not strategies:
            strategies.append(_observation(sig.regime, sig.confidence))
        return _finalize(strategies, liquidity, total_value)

    async def save_suggestions(
        self,
        db: AsyncSession,
        user_id: str,
        suggestions: list[dict[str, Any]],
    ) -> list[Strategy]:
        """Enregistre chaque suggestion comme stratégie PROPOSED, ses actions PENDING planifiées à J+1."""
        saved: list[Strategy] = []
        now = datetime.now(UTC)

        for s in suggestions:
            strategy = Strategy(
                id=uuid.uuid4(),
                user_id=user_id,
                name=s["name"],
                description=s.get("description"),
                source=StrategySource.AI,
                status=StrategyStatus.PROPOSED,
                params=s.get("params", {}),
                ai_reasoning=s.get("ai_reasoning"),
                market_regime=s.get("market_regime"),
                confidence=s.get("confidence"),
            )
            db.add(strategy)
            await db.flush()

            for action_data in s.get("actions", []):
                action = StrategyAction(
                    id=uuid.uuid4(),
                    strategy_id=strategy.id,
                    action=action_data["action"],
                    symbol=action_data.get("symbol"),
                    amount=action_data.get("amount"),
                    currency=action_data.get("currency", "EUR"),
                    reason=action_data.get("reason"),
                    status=ActionStatus.PENDING,
                    scheduled_at=now + timedelta(days=1),
                )
                db.add(action)

            saved.append(strategy)

        await db.commit()
        for strategy in saved:
            await db.refresh(strategy)

        return saved


ai_strategy_service = AIStrategyService()
