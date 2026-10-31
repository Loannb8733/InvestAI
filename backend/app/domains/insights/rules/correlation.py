"""Corrélations entre lignes : moyenne des cinq premières, grappes de risque, diversification illusoire."""

from typing import Any

from app.domains.analytics.results import CorrelationData
from app.domains.insights.results import InsightCategory, InsightSeverity, SmartInsight

_CLUSTER_THRESHOLD = 0.85
_ILLUSION_THRESHOLD = 0.7
_CRITICAL_ILLUSION = 0.85
_MAX_CLUSTER_INSIGHTS = 3


def _top5_average(symbols: list[str], matrix: list[list[float]], top5: list[str]) -> float:
    pairs = [
        matrix[i][j]
        for i, first in enumerate(symbols)
        if first in top5
        for j, second in enumerate(symbols)
        if j > i and second in top5
    ]
    return sum(pairs) / len(pairs) if pairs else 0.0


def _join_pair(clusters: dict[str, set[str]], first: str, second: str) -> None:
    left = clusters.get(first)
    right = clusters.get(second)
    if left and right:
        merged = left | right
        for symbol in merged:
            clusters[symbol] = merged
    elif left:
        left.add(second)
        clusters[second] = left
    elif right:
        right.add(first)
        clusters[first] = right
    else:
        created = {first, second}
        clusters[first] = created
        clusters[second] = created


def _cluster_average(members: list[str], symbols: list[str], matrix: list[list[float]]) -> float:
    pairs = [
        matrix[symbols.index(first)][symbols.index(second)]
        for i, first in enumerate(members)
        for j, second in enumerate(members)
        if j > i and first in symbols and second in symbols
    ]
    return sum(pairs) / len(pairs) if pairs else 0.0


def _risk_clusters(data: CorrelationData) -> list[dict[str, Any]]:
    clusters: dict[str, set[str]] = {}
    for first, second, correlation in data.strongly_correlated:
        if correlation >= _CLUSTER_THRESHOLD:
            _join_pair(clusters, first, second)
    seen: list[frozenset[str]] = []
    result: list[dict[str, Any]] = []
    for members in clusters.values():
        frozen = frozenset(members)
        if frozen not in seen:
            seen.append(frozen)
            ordered = sorted(members)
            average = _cluster_average(ordered, data.symbols, data.matrix)
            result.append({"assets": ordered, "avg_corr": round(average, 3)})
    return result


def _illusion_insight(data: CorrelationData, top5: list[str], average: float) -> SmartInsight:
    best_pair: tuple[str, str] | None = None
    best = 0.0
    for first, second, correlation in data.strongly_correlated:
        if first in top5 and second in top5 and correlation > best:
            best_pair = (first, second)
            best = correlation
    pair_text = f" entre {best_pair[0]} et {best_pair[1]}" if best_pair else ""
    return SmartInsight(
        category=InsightCategory.DIVERSIFICATION,
        severity=InsightSeverity.CRITICAL if average > _CRITICAL_ILLUSION else InsightSeverity.WARNING,
        title="Diversification illusoire",
        message=(
            f"Forte corrélation{pair_text} "
            f"(moyenne top 5 : {average:.0%}). "
            "Vos actifs principaux bougent ensemble — "
            "votre diversification est illusoire. "
            "Ajoutez des actifs décorrélés (or, obligations, immobilier)."
        ),
        metric_name="avg_top5_correlation",
        current_value=average,
        target_value=0.5,
        potential_improvement="Réduisez la corrélation sous 0.5 avec des actifs alternatifs.",
    )


def _cluster_insight(cluster: dict[str, Any]) -> SmartInsight:
    assets = ", ".join(cluster["assets"])
    return SmartInsight(
        category=InsightCategory.RISK,
        severity=InsightSeverity.WARNING,
        title="Cluster de risque détecté",
        message=(
            f"Les actifs {assets} forment un cluster "
            f"(corrélation moyenne : {cluster['avg_corr']:.0%}). "
            "En cas de chute, ils baisseront simultanément."
        ),
        metric_name="risk_cluster_corr",
        current_value=cluster["avg_corr"],
    )


def correlation_insights(
    data: CorrelationData, top_holdings: list[dict[str, Any]]
) -> tuple[list[SmartInsight], float, list[dict[str, Any]]]:
    """Conseils, corrélation moyenne des cinq premières lignes, et grappes `{assets, avg_corr}`."""
    if len(data.symbols) < 2:
        return [], 0.0, []
    top5 = [holding.get("symbol", "") for holding in top_holdings[:5]]
    average = _top5_average(data.symbols, data.matrix, top5)
    clusters = _risk_clusters(data)
    insights = [_illusion_insight(data, top5, average)] if average > _ILLUSION_THRESHOLD else []
    insights.extend(_cluster_insight(cluster) for cluster in clusters[:_MAX_CLUSTER_INSIGHTS])
    return insights, average, clusters
