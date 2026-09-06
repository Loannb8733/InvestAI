"""Notation et interprétation des indicateurs de risque.

Concentration, diversification, bêta, VaR paramétrique et mise en mots des
ratios : cinq calculs purs extraits d'`AnalyticsService`, où ils étaient
mêlés à l'orchestration. Aucun ne touche la base ni le réseau.

Les seuils qu'ils portent — ce qui fait qu'un portefeuille est « Bon » plutôt
que « Moyen », qu'un bêta est « défensif » — sont des décisions produit. Les
sortir les rend lisibles et vérifiables une à une.
"""

from typing import Dict, Optional

import numpy as np

from app.ml import adaptive_thresholds as adaptive_th
from app.services.analytics_math import _cvar_historical, _var_historical, _var_parametric


def _hhi(allocation: Dict[str, float]) -> float:
    if not allocation:
        return 0
    return round(sum((w / 100) ** 2 for w in allocation.values()), 4)


def _diversification_score(asset_count: int, type_count: int, concentration: float) -> float:
    a = min(asset_count * 3, 30)
    t = min(type_count * 10, 30)
    c = max(0, 40 * (1 - concentration * 2))
    return round(a + t + c, 1)


def _diversification_rating(score: float) -> str:
    if score >= 80:
        return "Excellent"
    elif score >= 60:
        return "Bon"
    elif score >= 40:
        return "Moyen"
    elif score >= 20:
        return "Faible"
    return "Très faible"


def _calc_beta(asset_returns: np.ndarray, bench_returns: np.ndarray) -> Optional[float]:
    """Compute beta = Cov(asset, bench) / Var(bench)."""
    if len(asset_returns) < 10 or len(bench_returns) < 10:
        return None
    min_len = min(len(asset_returns), len(bench_returns))
    a = asset_returns[-min_len:]
    b = bench_returns[-min_len:]
    var_b = float(np.var(b, ddof=1))
    if var_b == 0:
        return None
    cov = float(np.cov(a, b)[0, 1])
    return cov / var_b


def _interpret_beta(beta: Optional[float]) -> str:
    """Interpret beta value in French using centralized classification."""
    if beta is None:
        return "Données insuffisantes"
    category = adaptive_th.beta_classification(beta)
    labels = {
        "very_aggressive": "Très agressif — amplifie les mouvements du marché",
        "aggressive": "Agressif — plus volatil que le marché",
        "neutral": "Neutre — suit le marché",
        "defensive": "Défensif — moins volatil que le marché",
        "very_defensive": "Très défensif — quasi décorrélé du marché",
        "inverse": "Inversement corrélé — se comporte à l'inverse du marché",
    }
    return labels.get(category, "Données insuffisantes")


def _build_portfolio_var_parametric(port_returns: np.ndarray, total_value: float) -> dict:
    """Compute parametric VaR alongside historical VaR for comparison."""
    var_hist = _var_historical(port_returns) if len(port_returns) >= 5 else 0.0
    var_param = _var_parametric(port_returns) if len(port_returns) >= 5 else 0.0
    cvar = _cvar_historical(port_returns) if len(port_returns) >= 5 else 0.0

    return {
        "var_95_historical_pct": round(var_hist, 2),
        "var_95_parametric_pct": round(var_param, 2),
        "var_95_historical_eur": round(total_value * var_hist / 100, 2),
        "var_95_parametric_eur": round(total_value * var_param / 100, 2),
        "cvar_95_pct": round(cvar, 2),
        "cvar_95_eur": round(total_value * cvar / 100, 2),
    }


def _build_interpretations(
    sharpe: float,
    sortino: float,
    calmar: float,
    volatility: float,
    max_dd: float,
    asset_data: list,
) -> Dict[str, str]:
    """Build contextual, human-readable interpretations for portfolio ratios."""
    interp: Dict[str, str] = {}

    # Detect actual data depth (min data points across non-stablecoin assets)
    data_lengths = [
        len(d.get("returns", []))
        for d in asset_data
        if not d.get("is_stablecoin", False) and len(d.get("returns", [])) > 0
    ]
    min_days = min(data_lengths) if data_lengths else 0

    # ── Short history warning ──
    if min_days < 20:
        short_msg = (
            "Donnée non significative (échantillon < 20 jours). "
            "Les ratios nécessitent au moins 30 jours d'historique pour être fiables."
        )
        interp["sharpe"] = short_msg
        interp["sortino"] = short_msg
        interp["calmar"] = short_msg
        interp["global"] = "Historique trop court pour des conclusions fiables."
        return interp

    # ── Sharpe ──
    if sharpe > 3:
        interp["sharpe"] = (
            "Performance atypique (Sharpe > 3) : probablement liée à une volatilité "
            "extrême ou un pump récent. Ne pas extrapoler."
        )
    elif sharpe >= 2:
        interp["sharpe"] = "Excellent rapport rendement/risque. Vérifiez que la période est représentative."
    elif sharpe >= 1:
        interp["sharpe"] = "Bon ratio — le portefeuille rémunère correctement le risque pris."
    elif sharpe >= 0:
        interp["sharpe"] = "Rendement positif mais faible par rapport au risque. Marge d'optimisation possible."
    else:
        interp["sharpe"] = "Rendement inférieur au taux sans risque. Le portefeuille ne compense pas sa volatilité."

    # ── Sortino vs Sharpe ──
    if sortino > sharpe + 0.5 and sortino > 0:
        interp["sortino"] = (
            "Sortino nettement supérieur au Sharpe : votre volatilité est principalement "
            "positive (hausses). C'est un signe de force — le Sortino est plus pertinent "
            "en crypto car il ne punit pas les gains explosifs."
        )
    elif sortino > 0:
        interp["sortino"] = (
            "Ratio positif. Le Sortino est le ratio de référence en crypto car il "
            "ne pénalise que la volatilité baissière, pas les hausses brutales."
        )
    else:
        interp["sortino"] = "Sortino négatif : les pertes dominent. Le risque baissier dépasse le rendement."

    # ── Calmar ──
    if calmar > 2:
        interp["calmar"] = "Excellente récupération : le rendement compense largement le pire drawdown subi."
    elif calmar > 1:
        interp["calmar"] = "Le rendement annualisé dépasse le max drawdown. Bonne résilience."
    elif calmar > 0:
        interp["calmar"] = "Rendement positif mais inférieur au max drawdown. Récupération lente."
    else:
        interp["calmar"] = "Le portefeuille n'a pas récupéré de sa plus grosse perte."

    return interp
