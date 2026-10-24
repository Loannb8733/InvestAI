from typing import Any

import numpy as np
from numpy.typing import NDArray

from app.ml import adaptive_thresholds as adaptive_th

_BETA_LABELS = {
    "very_aggressive": "Très agressif — amplifie les mouvements du marché",
    "aggressive": "Agressif — plus volatil que le marché",
    "neutral": "Neutre — suit le marché",
    "defensive": "Défensif — moins volatil que le marché",
    "very_defensive": "Très défensif — quasi décorrélé du marché",
    "inverse": "Inversement corrélé — se comporte à l'inverse du marché",
}

_SHORT_HISTORY_DAYS = 20


def hhi(allocation: dict[str, float]) -> float:
    """Indice de Herfindahl-Hirschman en fraction (0 à 1) à partir de poids en %."""
    if not allocation:
        return 0
    return round(sum((w / 100) ** 2 for w in allocation.values()), 4)


def diversification_score(asset_count: int, type_count: int, concentration: float) -> float:
    """Note sur 100 : 30 points pour le nombre d'actifs, 30 pour les types, 40 pour une faible concentration."""
    a = min(asset_count * 3, 30)
    t = min(type_count * 10, 30)
    c = max(0, 40 * (1 - concentration * 2))
    return round(a + t + c, 1)


def diversification_rating(score: float) -> str:
    if score >= 80:
        return "Excellent"
    elif score >= 60:
        return "Bon"
    elif score >= 40:
        return "Moyen"
    elif score >= 20:
        return "Faible"
    return "Très faible"


def calc_beta(asset_returns: NDArray[np.float64], bench_returns: NDArray[np.float64]) -> float | None:
    """Bêta = Cov(actif, indice) / Var(indice) sur la fenêtre commune la plus récente ; None sous dix points."""
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


def interpret_beta(beta: float | None) -> str:
    if beta is None:
        return "Données insuffisantes"
    category = adaptive_th.beta_classification(beta)
    return _BETA_LABELS.get(category, "Données insuffisantes")


def _min_history_days(asset_data: list[dict[str, Any]]) -> int:
    data_lengths = [
        len(d.get("returns", []))
        for d in asset_data
        if not d.get("is_stablecoin", False) and len(d.get("returns", [])) > 0
    ]
    return min(data_lengths) if data_lengths else 0


def _sharpe_text(sharpe: float) -> str:
    if sharpe > 3:
        return (
            "Performance atypique (Sharpe > 3) : probablement liée à une volatilité "
            "extrême ou un pump récent. Ne pas extrapoler."
        )
    if sharpe >= 2:
        return "Excellent rapport rendement/risque. Vérifiez que la période est représentative."
    if sharpe >= 1:
        return "Bon ratio — le portefeuille rémunère correctement le risque pris."
    if sharpe >= 0:
        return "Rendement positif mais faible par rapport au risque. Marge d'optimisation possible."
    return "Rendement inférieur au taux sans risque. Le portefeuille ne compense pas sa volatilité."


def _sortino_text(sortino: float, sharpe: float) -> str:
    if sortino > sharpe + 0.5 and sortino > 0:
        return (
            "Sortino nettement supérieur au Sharpe : votre volatilité est principalement "
            "positive (hausses). C'est un signe de force — le Sortino est plus pertinent "
            "en crypto car il ne punit pas les gains explosifs."
        )
    if sortino > 0:
        return (
            "Ratio positif. Le Sortino est le ratio de référence en crypto car il "
            "ne pénalise que la volatilité baissière, pas les hausses brutales."
        )
    return "Sortino négatif : les pertes dominent. Le risque baissier dépasse le rendement."


def _calmar_text(calmar: float) -> str:
    if calmar > 2:
        return "Excellente récupération : le rendement compense largement le pire drawdown subi."
    if calmar > 1:
        return "Le rendement annualisé dépasse le max drawdown. Bonne résilience."
    if calmar > 0:
        return "Rendement positif mais inférieur au max drawdown. Récupération lente."
    return "Le portefeuille n'a pas récupéré de sa plus grosse perte."


def build_interpretations(
    sharpe: float,
    sortino: float,
    calmar: float,
    volatility: float,
    max_dd: float,
    asset_data: list[dict[str, Any]],
) -> dict[str, str]:
    """Lecture en clair des ratios ; sous vingt jours d'historique hors stablecoins, un avertissement les remplace."""
    if _min_history_days(asset_data) < _SHORT_HISTORY_DAYS:
        short_msg = (
            "Donnée non significative (échantillon < 20 jours). "
            "Les ratios nécessitent au moins 30 jours d'historique pour être fiables."
        )
        return {
            "sharpe": short_msg,
            "sortino": short_msg,
            "calmar": short_msg,
            "global": "Historique trop court pour des conclusions fiables.",
        }
    return {
        "sharpe": _sharpe_text(sharpe),
        "sortino": _sortino_text(sortino, sharpe),
        "calmar": _calmar_text(calmar),
    }
