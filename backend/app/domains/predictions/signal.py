import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.analytics.results import MonteCarloResult
from app.domains.analytics.service import analytics_service
from app.domains.insights.market_regime import current_vol_regime
from app.domains.predictions.service import prediction_service

MC_HORIZON_DAYS = 90
MC_SIMULATIONS = 2000


def _target(alpha_data: dict[str, Any], symbol: str | None) -> dict[str, Any]:
    top: dict[str, Any] = alpha_data["top_alpha"]
    if symbol:
        all_scores = alpha_data.get("all_scores", [])
        matched = next((s for s in all_scores if s["symbol"] == symbol), None)
        if matched:
            top = matched
    return top


def _strategy_row(strategy_data: dict[str, Any], symbol: str, action: str | None) -> tuple[str, float, str]:
    effective_action = action if action else "OBSERVER"
    impact_pct = 0.0
    regime = "unknown"
    for row in strategy_data.get("rows", []):
        if row["symbol"] == symbol:
            if not action:
                effective_action = row["action"]
            impact_pct = row["impact_pct"]
            regime = row["regime"]
            break
    return effective_action, impact_pct, regime


def _risk_label(ruin_delta: float) -> str:
    if ruin_delta < -1:
        return "Diminuée"
    if ruin_delta > 1:
        return "Augmentée"
    return "Stable"


def _btc_correlation(top: dict[str, Any]) -> float | None:
    for reason in top.get("reasons", []):
        if "corrélation" in reason.get("label", "").lower() or "décorr" in reason.get("label", "").lower():
            detail = reason.get("detail", "")
            match = re.search(r"[-+]?\d*\.?\d+", detail.split("=")[-1] if "=" in detail else detail)
            if match:
                return float(match.group())
            return None
    return None


def _rebalance_suggestion(
    alpha_data: dict[str, Any], symbol: str, order_eur: float, new_weight: float
) -> dict[str, Any] | None:
    if new_weight > 60:
        all_scores = alpha_data.get("all_scores", [])
        candidates = [s for s in all_scores if s["symbol"] != symbol and s.get("value", 0) > 0]
        if candidates:
            worst = min(candidates, key=lambda s: s.get("score", 100))
            return {
                "trim_symbol": worst["symbol"],
                "trim_eur": round(order_eur * 0.5, 2),
                "reason": f"Réduire {worst['symbol']} (score {worst.get('score', 0):.0f}) pour financer l'achat",
            }
    return None


def _concentration_status(new_weight: float) -> str:
    return "ALERTE" if new_weight > 60 else ("VIGILANCE" if new_weight > 50 else "SÉCURISÉE")


def _mc_summary(mc: MonteCarloResult) -> dict[str, Any]:
    return {
        "expected_return": mc.expected_return,
        "prob_positive": mc.prob_positive,
        "prob_loss_10": mc.prob_loss_10,
    }


async def _monte_carlo_pair(
    db: AsyncSession, user_id: str, symbol: str, order_eur: float
) -> tuple[MonteCarloResult, MonteCarloResult]:
    vol_regime = await current_vol_regime()
    before = await analytics_service.monte_carlo(
        db, user_id, horizon_days=MC_HORIZON_DAYS, num_simulations=MC_SIMULATIONS, vol_regime=vol_regime
    )
    after = await analytics_service.monte_carlo(
        db,
        user_id,
        horizon_days=MC_HORIZON_DAYS,
        num_simulations=MC_SIMULATIONS,
        contribution={symbol: order_eur} if order_eur > 0 else None,
        vol_regime=vol_regime,
    )
    return before, after


async def validate_top_alpha(
    db: AsyncSession, user_id: str, alpha_data: dict[str, Any], symbol: str | None, action: str | None
) -> dict[str, Any]:
    """Valide le signal alpha (ou l'actif demandé) : ordre suggéré par la matrice de stratégie, probabilité de ruine
    Monte-Carlo avant et après l'achat, poids post-achat et écart au total du dashboard."""
    top = _target(alpha_data, symbol)
    symbol = top["symbol"]
    total_value = alpha_data.get("total_portfolio_value", 0)
    concentration_risk = alpha_data.get("concentration_risk", False)

    strategy_data = await prediction_service.get_strategy_map(db, user_id)
    action, impact_pct, regime = _strategy_row(strategy_data, symbol, action)

    order_eur = round(total_value * abs(impact_pct) / 100, 2) if total_value > 0 else 0.0
    current_weight = top.get("weight_pct", 0)
    current_value = top.get("value", 0)
    new_weight = round((current_value + order_eur) / (total_value + order_eur) * 100, 1) if total_value > 0 else 0
    weight_overflow = bool(new_weight > 50)

    mc_before, mc_after = await _monte_carlo_pair(db, user_id, symbol, order_eur)
    prob_ruin_before = mc_before.prob_ruin
    prob_ruin_after = mc_after.prob_ruin
    btc_correlation = _btc_correlation(top)
    rebalance_suggestion = _rebalance_suggestion(alpha_data, symbol, order_eur, new_weight)

    cycle_data = await prediction_service.get_market_cycle(db, user_id)
    dashboard_total = sum(a.get("value", 0) for a in cycle_data.get("per_asset", []))

    score = top.get("score", 0)
    return {
        "validated": bool(score > 85 and impact_pct > 0 and not weight_overflow),
        "symbol": symbol,
        "score": round(score, 1),
        "predicted_7d_pct": top.get("predicted_7d_pct", 0),
        "prediction_source": top.get("prediction_source", "none"),
        "regime": regime,
        "action": action,
        "order_eur": order_eur,
        "impact_pct": impact_pct,
        "current_weight_pct": current_weight,
        "post_purchase_weight_pct": new_weight,
        "weight_overflow": weight_overflow,
        "concentration_risk": concentration_risk,
        "concentration_status": _concentration_status(new_weight),
        "btc_correlation": btc_correlation,
        "prob_ruin_before": round(prob_ruin_before, 2),
        "prob_ruin_after": round(prob_ruin_after, 2),
        "risk_impact": _risk_label(prob_ruin_after - prob_ruin_before),
        "mc_before": _mc_summary(mc_before),
        "mc_after": _mc_summary(mc_after),
        "total_portfolio_value": total_value,
        "ecart_eur": round(abs(total_value - dashboard_total), 2),
        "reasons": top.get("reasons", []),
        "divergence_log": top.get("divergence_log"),
        "rebalance_suggestion": rebalance_suggestion,
    }
