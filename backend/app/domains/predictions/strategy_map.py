from typing import Any

from app.domains.portfolio.classification import is_safe_haven
from app.ml.regime_detector import RegimeConfig

StrategyDecision = tuple[str, str, float]

STRATEGY_MATRIX: dict[tuple[str, str], StrategyDecision] = {
    ("high", "bottoming"): (
        "ACHAT FORT",
        "Alpha élevé + Bottoming : signal d'achat optimal (RSI survente + divergence)",
        5.0,
    ),
    ("medium", "bottoming"): ("DCA", "Signal moyen + Bottoming : DCA conservateur", 3.0),
    ("low", "bottoming"): ("OBSERVER", "Faible alpha + Bottoming : surveiller les signaux", 0.0),
    ("high", "accumulation"): ("DCA", "Alpha élevé + Accumulation : accumuler progressivement", 4.0),
    ("medium", "accumulation"): ("DCA", "Signal moyen + Accumulation : fenêtre d'entrée progressive", 2.0),
    ("low", "accumulation"): ("OBSERVER", "Faible alpha + Accumulation : pas encore de signal clair", 0.0),
    ("high", "markup"): ("MAINTENIR", "Alpha élevé + Mark-up : laisser courir les gains", 0.0),
    ("medium", "markup"): ("MAINTENIR", "Signal moyen + Mark-up : conserver les positions", 0.0),
    ("low", "markup"): ("CONSERVER", "Faible alpha en Mark-up : ne pas vendre", 0.0),
    ("high", "topping"): ("PRENDRE PROFITS", "Alpha élevé mais Topping : sécuriser 20-30%", -2.0),
    ("medium", "topping"): ("ALLÉGER", "Signal moyen + Topping : réduire l'exposition", -3.0),
    ("low", "topping"): ("VENDRE", "Faible alpha + Topping : signal de vente prioritaire", -5.0),
    ("high", "distribution"): ("ALLÉGER", "Alpha élevé + Distribution : sécuriser une partie", -2.0),
    ("medium", "distribution"): ("VENDRE", "Signal moyen + Distribution : réduire avant le markdown", -4.0),
    ("low", "distribution"): ("VENDRE", "Faible alpha + Distribution : sortir avant la chute", -5.0),
    ("high", "markdown"): ("DCA", "Alpha élevé en Markdown : accumuler progressivement (contrarian)", 3.0),
    ("medium", "markdown"): ("ATTENDRE", "Signal moyen en Markdown : patience, pas de renforcement", 0.0),
    ("low", "markdown"): ("ÉVITER", "Faible alpha en Markdown : ne pas renforcer", 0.0),
    ("high", "bottom"): ("ACHAT FORT", "Alpha élevé + creux de marché : signal d'achat optimal", 5.0),
    ("high", "bearish"): ("DCA", "Alpha élevé en bear market : accumuler progressivement", 3.0),
    ("high", "bullish"): ("MAINTENIR", "Alpha élevé en bull : laisser courir", 0.0),
    ("high", "top"): ("PRENDRE PROFITS", "Alpha élevé mais sommet : sécuriser 20-30%", -2.0),
    ("medium", "bottom"): ("DCA", "Signal moyen + creux : DCA conservateur", 3.0),
    ("medium", "bearish"): ("ATTENDRE", "Signal moyen en bear : patience", 0.0),
    ("medium", "bullish"): ("MAINTENIR", "Signal moyen en bull : conserver les positions", 0.0),
    ("medium", "top"): ("ALLÉGER", "Signal moyen au sommet : réduire l'exposition", -3.0),
    ("low", "bottom"): ("OBSERVER", "Faible alpha + creux : surveiller les signaux", 0.0),
    ("low", "bearish"): ("ÉVITER", "Faible alpha en bear : ne pas renforcer", 0.0),
    ("low", "bullish"): ("CONSERVER", "Faible alpha en bull : ne pas vendre non plus", 0.0),
    ("low", "top"): ("VENDRE", "Faible alpha + sommet : signal de vente prioritaire", -5.0),
}

BEARISH_MARKETS = ("bearish", "top", "markdown", "distribution")


def _global_regime(market_regime: dict[str, Any] | None) -> str:
    return market_regime.get("dominant_regime", "") if market_regime else ""


def _alpha_level(score: float, market_regime: dict[str, Any] | None) -> str:
    high_thresh = RegimeConfig.from_regime(_global_regime(market_regime)).alpha_threshold
    mid_thresh = max(30, high_thresh - 30)
    if score >= high_thresh:
        return "high"
    if score >= mid_thresh:
        return "medium"
    return "low"


def _cycle_phase(cycle_info: dict[str, Any], market_regime: dict[str, Any] | None) -> Any:
    return cycle_info.get(
        "regime_6phase",
        cycle_info.get(
            "dominant_regime",
            market_regime.get("dominant_regime", "bullish") if market_regime else "bullish",
        ),
    )


def _decision(
    alpha_level: str, regime: str, scored: dict[str, Any], market_regime: dict[str, Any] | None
) -> StrategyDecision:
    action, description, impact_pct = STRATEGY_MATRIX.get(
        (alpha_level, regime), ("OBSERVER", "Données insuffisantes", 0.0)
    )
    if action == "ACHAT FORT" and _global_regime(market_regime) in BEARISH_MARKETS:
        has_divergence = any(r.get("label", "") == "Divergence Haussière" for r in scored.get("reasons", []))
        if not has_divergence:
            action = "DCA"
            description = "Bear market : ACHAT FORT dégradé en DCA (divergence RSI non confirmée)"
            impact_pct = 2.0
    return action, description, impact_pct


def _summary_bucket(action: str) -> str:
    if "ACHAT" in action or action == "DCA":
        return "buys"
    if "VENDRE" in action or "PROFITS" in action or "ALLÉGER" in action:
        return "sells"
    return "holds"


def _strategy_row(
    scored: dict[str, Any], regime_map: dict[str, dict[str, Any]], market_regime: dict[str, Any] | None
) -> dict[str, Any]:
    sym = scored["symbol"]
    score = scored["score"]
    value = scored.get("value", 0)
    weight_pct = scored.get("weight_pct", 0)

    alpha_level = _alpha_level(score, market_regime)
    cycle_info = regime_map.get(sym, {})
    regime = _cycle_phase(cycle_info, market_regime)
    action, description, impact_pct = _decision(alpha_level, regime, scored, market_regime)

    trailing_stop = None
    if regime in ("markup", "bullish") and action in ("MAINTENIR", "CONSERVER"):
        trailing_stop = "EMA-20 trailing stop recommandé — remonter le stop-loss sous l'EMA-20"

    return {
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
        "impact_eur": round(value * impact_pct / 100, 2) if value > 0 else 0.0,
        "predicted_7d_pct": scored.get("predicted_7d_pct", 0),
        "is_resilient": is_safe_haven(sym),
        "trailing_stop": trailing_stop,
    }


def strategy_map(alpha_data: dict[str, Any], cycle_data: dict[str, Any]) -> dict[str, Any]:
    """Croise scores alpha et phase de cycle ; en marché baissier, un ACHAT FORT sans divergence RSI devient DCA."""
    market_regime = cycle_data.get("market_regime", {})
    regime_map = {a["symbol"]: a for a in cycle_data.get("per_asset", [])}

    rows: list[dict[str, Any]] = []
    summary = {"buys": 0, "sells": 0, "holds": 0}
    for scored in alpha_data.get("all_scores", []):
        row = _strategy_row(scored, regime_map, market_regime)
        summary[_summary_bucket(row["action"])] += 1
        rows.append(row)

    return {
        "rows": rows,
        "total_portfolio_value": round(alpha_data.get("total_portfolio_value", 0.0), 2),
        "market_regime": market_regime.get("dominant_regime", "unknown") if market_regime else "unknown",
        "fear_greed": cycle_data.get("fear_greed"),
        "summary": summary,
    }
