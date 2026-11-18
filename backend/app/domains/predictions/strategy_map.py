"""Lecture croisée score alpha et phase de cycle, en information générale.

Chaque ligne décrit la configuration technique d'un actif (``tone`` : favorable, neutre ou défavorable, et un
constat descriptif). Elle ne contient ni verbe d'action, ni montant, ni impact chiffré : l'application ne formule
pas de recommandation d'achat ou de vente personnalisée.
"""

from typing import Any

from app.domains.portfolio.classification import is_safe_haven
from app.ml.regime.types import RegimeConfig

FAVORABLE = "favorable"
NEUTRAL = "neutre"
UNFAVORABLE = "défavorable"
TONES = (FAVORABLE, NEUTRAL, UNFAVORABLE)

Reading = tuple[str, str]

STRATEGY_MATRIX: dict[tuple[str, str], Reading] = {
    ("high", "bottoming"): (
        FAVORABLE,
        "Alpha élevé en phase de creux : RSI en survente et divergence haussière",
    ),
    ("medium", "bottoming"): (FAVORABLE, "Alpha moyen en phase de creux"),
    ("low", "bottoming"): (NEUTRAL, "Alpha faible en phase de creux : pas de signal technique net"),
    ("high", "accumulation"): (FAVORABLE, "Alpha élevé en phase d'accumulation"),
    ("medium", "accumulation"): (FAVORABLE, "Alpha moyen en phase d'accumulation"),
    ("low", "accumulation"): (NEUTRAL, "Alpha faible en phase d'accumulation : pas de signal technique net"),
    ("high", "markup"): (NEUTRAL, "Alpha élevé en phase de hausse"),
    ("medium", "markup"): (NEUTRAL, "Alpha moyen en phase de hausse"),
    ("low", "markup"): (NEUTRAL, "Alpha faible en phase de hausse"),
    ("high", "topping"): (UNFAVORABLE, "Alpha élevé mais phase de sommet : momentum qui s'essouffle"),
    ("medium", "topping"): (UNFAVORABLE, "Alpha moyen en phase de sommet"),
    ("low", "topping"): (UNFAVORABLE, "Alpha faible en phase de sommet"),
    ("high", "distribution"): (UNFAVORABLE, "Alpha élevé mais phase de distribution"),
    ("medium", "distribution"): (UNFAVORABLE, "Alpha moyen en phase de distribution"),
    ("low", "distribution"): (UNFAVORABLE, "Alpha faible en phase de distribution"),
    ("high", "markdown"): (NEUTRAL, "Alpha élevé en phase de baisse : signal contrarien, tendance encore baissière"),
    ("medium", "markdown"): (UNFAVORABLE, "Alpha moyen en phase de baisse"),
    ("low", "markdown"): (UNFAVORABLE, "Alpha faible en phase de baisse"),
    ("high", "bottom"): (FAVORABLE, "Alpha élevé en zone de creux de marché"),
    ("high", "bearish"): (NEUTRAL, "Alpha élevé en marché baissier : signal contrarien, tendance encore baissière"),
    ("high", "bullish"): (NEUTRAL, "Alpha élevé en marché haussier"),
    ("high", "top"): (UNFAVORABLE, "Alpha élevé mais zone de sommet"),
    ("medium", "bottom"): (FAVORABLE, "Alpha moyen en zone de creux"),
    ("medium", "bearish"): (NEUTRAL, "Alpha moyen en marché baissier"),
    ("medium", "bullish"): (NEUTRAL, "Alpha moyen en marché haussier"),
    ("medium", "top"): (UNFAVORABLE, "Alpha moyen en zone de sommet"),
    ("low", "bottom"): (NEUTRAL, "Alpha faible en zone de creux : pas de signal technique net"),
    ("low", "bearish"): (UNFAVORABLE, "Alpha faible en marché baissier"),
    ("low", "bullish"): (NEUTRAL, "Alpha faible en marché haussier"),
    ("low", "top"): (UNFAVORABLE, "Alpha faible en zone de sommet"),
}

BEARISH_MARKETS = ("bearish", "top", "markdown", "distribution")

_SUMMARY_KEYS = {FAVORABLE: "favorable", NEUTRAL: "neutral", UNFAVORABLE: "unfavorable"}


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


def _reading(alpha_level: str, regime: str, scored: dict[str, Any], market_regime: dict[str, Any] | None) -> Reading:
    """Configuration de l'actif ; en marché baissier global, une configuration favorable sans divergence RSI
    confirmée est ramenée à neutre."""
    tone, description = STRATEGY_MATRIX.get((alpha_level, regime), (NEUTRAL, "Données insuffisantes"))
    if tone == FAVORABLE and _global_regime(market_regime) in BEARISH_MARKETS:
        has_divergence = any(r.get("label", "") == "Divergence Haussière" for r in scored.get("reasons", []))
        if not has_divergence:
            return NEUTRAL, f"{description} ; marché global baissier, divergence RSI non confirmée"
    return tone, description


def _strategy_row(
    scored: dict[str, Any], regime_map: dict[str, dict[str, Any]], market_regime: dict[str, Any] | None
) -> dict[str, Any]:
    sym = scored["symbol"]
    alpha_level = _alpha_level(scored["score"], market_regime)
    cycle_info = regime_map.get(sym, {})
    regime = _cycle_phase(cycle_info, market_regime)
    tone, description = _reading(alpha_level, regime, scored, market_regime)

    return {
        "symbol": sym,
        "name": scored.get("name", sym),
        "alpha_score": round(scored["score"], 1),
        "alpha_level": alpha_level,
        "regime": regime,
        "regime_confidence": round(cycle_info.get("confidence", 0.5), 2),
        "tone": tone,
        "description": description,
        "value": round(scored.get("value", 0), 2),
        "weight_pct": round(scored.get("weight_pct", 0), 1),
        "predicted_7d_pct": scored.get("predicted_7d_pct", 0),
        "is_resilient": is_safe_haven(sym),
    }


def strategy_map(alpha_data: dict[str, Any], cycle_data: dict[str, Any]) -> dict[str, Any]:
    """Croise scores alpha et phase de cycle en une lecture descriptive par actif détenu, sans recommandation."""
    market_regime = cycle_data.get("market_regime", {})
    regime_map = {a["symbol"]: a for a in cycle_data.get("per_asset", [])}

    rows: list[dict[str, Any]] = []
    summary = {"favorable": 0, "neutral": 0, "unfavorable": 0}
    for scored in alpha_data.get("all_scores", []):
        row = _strategy_row(scored, regime_map, market_regime)
        summary[_SUMMARY_KEYS[row["tone"]]] += 1
        rows.append(row)

    return {
        "rows": rows,
        "total_portfolio_value": round(alpha_data.get("total_portfolio_value", 0.0), 2),
        "market_regime": market_regime.get("dominant_regime", "unknown") if market_regime else "unknown",
        "fear_greed": cycle_data.get("fear_greed"),
        "summary": summary,
    }
