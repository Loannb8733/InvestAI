"""Pure rule-based portfolio insight analyzers (Sharpe, risk, diversification,
correlation), extracted from smart_insights_service. Each takes plain metrics
and returns a list of SmartInsight — no I/O, no class state (mixed into
SmartInsightsService for call-site compatibility)."""

from __future__ import annotations

from typing import Dict, List, Tuple

from app.ml import adaptive_thresholds as adaptive_th
from app.services.smart_insights_types import InsightCategory, InsightSeverity, SmartInsight


class SmartInsightAnalyzersMixin:
    """Mixed into SmartInsightsService — the rule-based insight analyzers."""

    def _analyze_sharpe(self, sharpe: float, sortino: float) -> List[SmartInsight]:
        """Analyze Sharpe and Sortino ratios."""
        insights = []
        s_exc, s_good, s_fair, s_poor = adaptive_th.sharpe_classification()

        if sharpe < s_poor:
            insights.append(
                SmartInsight(
                    category=InsightCategory.PERFORMANCE,
                    severity=InsightSeverity.CRITICAL,
                    title="Performance très faible",
                    message=f"Votre ratio de Sharpe ({sharpe:.2f}) est négatif. Votre portfolio sous-performe un placement sans risque.",
                    metric_name="sharpe_ratio",
                    current_value=sharpe,
                    target_value=s_good,
                    potential_improvement="Diversifiez vers des actifs moins corrélés ou réduisez les positions perdantes.",
                )
            )
        elif sharpe < s_fair:
            insights.append(
                SmartInsight(
                    category=InsightCategory.PERFORMANCE,
                    severity=InsightSeverity.WARNING,
                    title="Performance à améliorer",
                    message=f"Votre ratio de Sharpe ({sharpe:.2f}) est faible. Le rendement ne compense pas suffisamment le risque pris.",
                    metric_name="sharpe_ratio",
                    current_value=sharpe,
                    target_value=s_good,
                    potential_improvement=f"Ciblez un Sharpe > {s_good} via une meilleure allocation.",
                )
            )
        elif sharpe < s_good:
            insights.append(
                SmartInsight(
                    category=InsightCategory.PERFORMANCE,
                    severity=InsightSeverity.INFO,
                    title="Performance correcte",
                    message=f"Votre ratio de Sharpe ({sharpe:.2f}) est acceptable mais peut être optimisé.",
                    metric_name="sharpe_ratio",
                    current_value=sharpe,
                    target_value=s_exc,
                )
            )
        else:
            insights.append(
                SmartInsight(
                    category=InsightCategory.PERFORMANCE,
                    severity=InsightSeverity.INFO,
                    title="Excellente performance",
                    message=f"Votre ratio de Sharpe ({sharpe:.2f}) est excellent. Votre rendement ajusté au risque est très bon.",
                    metric_name="sharpe_ratio",
                    current_value=sharpe,
                )
            )

        return insights

    def _analyze_risk(self, volatility: float, var_95: float, max_drawdown: float) -> List[SmartInsight]:
        """Analyze risk metrics."""
        insights = []
        vol_high, vol_extreme = adaptive_th.volatility_warning_thresholds()
        vol_high_frac, vol_extreme_frac = vol_high / 100, vol_extreme / 100
        var_warn, var_crit = adaptive_th.var_warning_thresholds()

        # Volatility analysis
        if volatility > vol_extreme_frac:
            insights.append(
                SmartInsight(
                    category=InsightCategory.RISK,
                    severity=InsightSeverity.CRITICAL,
                    title="Volatilité extrême",
                    message=f"Votre portfolio a une volatilité de {volatility*100:.0f}%. C'est très risqué.",
                    metric_name="volatility",
                    current_value=volatility,
                    target_value=0.30,
                    potential_improvement="Ajoutez des actifs stables (ETF obligataires, stablecoins) pour réduire la volatilité.",
                )
            )
        elif volatility > vol_high_frac:
            insights.append(
                SmartInsight(
                    category=InsightCategory.RISK,
                    severity=InsightSeverity.WARNING,
                    title="Volatilité élevée",
                    message=f"Votre portfolio a une volatilité de {volatility*100:.0f}%. Préparez-vous à des variations importantes.",
                    metric_name="volatility",
                    current_value=volatility,
                    target_value=0.30,
                )
            )

        # VaR analysis
        if var_95 > var_crit:
            insights.append(
                SmartInsight(
                    category=InsightCategory.RISK,
                    severity=InsightSeverity.CRITICAL,
                    title="Risque de perte élevé",
                    message=f"Votre VaR 95% est de {var_95*100:.1f}%. Vous pouvez perdre cette proportion en une journée (5% de chance).",
                    metric_name="var_95",
                    current_value=var_95,
                    target_value=0.05,
                )
            )
        elif var_95 > var_warn:
            insights.append(
                SmartInsight(
                    category=InsightCategory.RISK,
                    severity=InsightSeverity.WARNING,
                    title="VaR à surveiller",
                    message=f"Votre VaR 95% est de {var_95*100:.1f}%. Le risque journalier est notable.",
                    metric_name="var_95",
                    current_value=var_95,
                )
            )

        # Max drawdown
        if max_drawdown > 0.25:
            insights.append(
                SmartInsight(
                    category=InsightCategory.RISK,
                    severity=InsightSeverity.CRITICAL,
                    title="Drawdown severe",
                    message=(
                        f"Votre portfolio a subi une baisse de {max_drawdown*100:.0f}% depuis son pic. "
                        f"Reduisez l'exposition aux actifs les plus volatils et "
                        f"constituez une reserve de liquidites."
                    ),
                    metric_name="max_drawdown",
                    current_value=max_drawdown,
                    target_value=0.15,
                    potential_improvement="Diversifiez avec des actifs stables pour reduire le drawdown futur.",
                )
            )
        elif max_drawdown > 0.15:
            insights.append(
                SmartInsight(
                    category=InsightCategory.RISK,
                    severity=InsightSeverity.WARNING,
                    title="Drawdown important",
                    message=f"Votre portfolio a subi une baisse de {max_drawdown*100:.0f}% depuis son pic.",
                    metric_name="max_drawdown",
                    current_value=max_drawdown,
                    target_value=0.10,
                )
            )

        return insights

    def _analyze_diversification(self, hhi: float, top_holdings: List[Dict]) -> List[SmartInsight]:
        """Analyze portfolio diversification."""
        insights = []
        conc_warn, conc_crit = adaptive_th.concentration_thresholds()

        # Check concentration in top holdings
        if top_holdings:
            top_weight = top_holdings[0].get("weight", 0) if top_holdings else 0
            top_symbol = top_holdings[0].get("symbol", "?") if top_holdings else "?"

            if top_weight > conc_crit:
                insights.append(
                    SmartInsight(
                        category=InsightCategory.DIVERSIFICATION,
                        severity=InsightSeverity.CRITICAL,
                        title="Concentration excessive",
                        message=f"{top_symbol} représente {top_weight*100:.0f}% de votre portfolio. C'est trop concentré.",
                        metric_name="top_holding_weight",
                        current_value=top_weight,
                        target_value=conc_warn,
                        potential_improvement=f"Réduisez {top_symbol} à max {conc_warn*100:.0f}% et diversifiez.",
                        actions=[
                            {
                                "type": "sell",
                                "symbol": top_symbol,
                                "reason": "Réduire la concentration",
                            }
                        ],
                    )
                )
            elif top_weight > conc_warn:
                insights.append(
                    SmartInsight(
                        category=InsightCategory.DIVERSIFICATION,
                        severity=InsightSeverity.WARNING,
                        title="Concentration élevée",
                        message=f"{top_symbol} représente {top_weight*100:.0f}% de votre portfolio.",
                        metric_name="top_holding_weight",
                        current_value=top_weight,
                        target_value=conc_warn,
                    )
                )

        # HHI analysis
        if hhi > conc_warn:
            insights.append(
                SmartInsight(
                    category=InsightCategory.DIVERSIFICATION,
                    severity=InsightSeverity.WARNING,
                    title="Portfolio peu diversifié",
                    message=f"Votre indice HHI ({hhi:.2f}) indique une concentration élevée.",
                    metric_name="hhi",
                    current_value=hhi,
                    target_value=0.15,
                    potential_improvement="Ajoutez des actifs décorrélés (actions, ETF, or).",
                )
            )
        elif hhi < 0.10:
            insights.append(
                SmartInsight(
                    category=InsightCategory.DIVERSIFICATION,
                    severity=InsightSeverity.INFO,
                    title="Bonne diversification",
                    message=f"Votre portfolio est bien diversifié (HHI: {hhi:.2f}).",
                    metric_name="hhi",
                    current_value=hhi,
                )
            )

        return insights

    def _analyze_correlation(
        self,
        corr_data,
        top_holdings: List[Dict],
    ) -> Tuple[List[SmartInsight], float, List[Dict]]:
        """Analyze correlation matrix for risk clusters and diversification illusions.

        Returns (insights, avg_top5_correlation, risk_clusters).
        risk_clusters format: [{"assets": ["BTC", "ETH"], "avg_corr": 0.91}, ...]
        """
        insights: List[SmartInsight] = []
        risk_clusters: List[Dict] = []

        symbols = corr_data.symbols
        matrix = corr_data.matrix
        strongly_correlated = corr_data.strongly_correlated

        if len(symbols) < 2:
            return insights, 0.0, risk_clusters

        # 1. Compute average pairwise correlation for top 5 holdings
        top5_symbols = [h.get("symbol", "") for h in top_holdings[:5]]
        top5_corrs = []
        for i, s1 in enumerate(symbols):
            if s1 not in top5_symbols:
                continue
            for j, s2 in enumerate(symbols):
                if j <= i or s2 not in top5_symbols:
                    continue
                top5_corrs.append(matrix[i][j])

        avg_top5_corr = sum(top5_corrs) / len(top5_corrs) if top5_corrs else 0.0

        # 2. Build risk clusters (assets with corr > 0.85)
        cluster_threshold = 0.85
        cluster_map: Dict[str, set] = {}
        for s1, s2, corr in strongly_correlated:
            if corr >= cluster_threshold:
                # Merge into existing cluster or create new
                c1 = cluster_map.get(s1)
                c2 = cluster_map.get(s2)
                if c1 and c2:
                    # Merge
                    merged = c1 | c2
                    for sym in merged:
                        cluster_map[sym] = merged
                elif c1:
                    c1.add(s2)
                    cluster_map[s2] = c1
                elif c2:
                    c2.add(s1)
                    cluster_map[s1] = c2
                else:
                    new_cluster = {s1, s2}
                    cluster_map[s1] = new_cluster
                    cluster_map[s2] = new_cluster

        # Deduplicate clusters
        seen_clusters: List[frozenset] = []
        for cluster_set in cluster_map.values():
            fs = frozenset(cluster_set)
            if fs not in seen_clusters:
                seen_clusters.append(fs)
                # Compute average correlation within cluster
                cluster_corrs = []
                cluster_list = sorted(cluster_set)
                for ci, cs1 in enumerate(cluster_list):
                    for cj, cs2 in enumerate(cluster_list):
                        if cj <= ci:
                            continue
                        if cs1 in symbols and cs2 in symbols:
                            idx_i = symbols.index(cs1)
                            idx_j = symbols.index(cs2)
                            cluster_corrs.append(matrix[idx_i][idx_j])
                avg_cluster_corr = sum(cluster_corrs) / len(cluster_corrs) if cluster_corrs else 0.0
                risk_clusters.append(
                    {
                        "assets": cluster_list,
                        "avg_corr": round(avg_cluster_corr, 3),
                    }
                )

        # 3. Generate insights
        if avg_top5_corr > 0.7:
            # Find the highest correlated pair among top 5
            max_pair = None
            max_corr = 0.0
            for s1, s2, corr in strongly_correlated:
                if s1 in top5_symbols and s2 in top5_symbols and corr > max_corr:
                    max_pair = (s1, s2)
                    max_corr = corr

            pair_text = f" entre {max_pair[0]} et {max_pair[1]}" if max_pair else ""
            insights.append(
                SmartInsight(
                    category=InsightCategory.DIVERSIFICATION,
                    severity=InsightSeverity.CRITICAL if avg_top5_corr > 0.85 else InsightSeverity.WARNING,
                    title="Diversification illusoire",
                    message=(
                        f"Forte corrélation{pair_text} "
                        f"(moyenne top 5 : {avg_top5_corr:.0%}). "
                        f"Vos actifs principaux bougent ensemble — "
                        f"votre diversification est illusoire. "
                        f"Ajoutez des actifs décorrélés (or, obligations, immobilier)."
                    ),
                    metric_name="avg_top5_correlation",
                    current_value=avg_top5_corr,
                    target_value=0.5,
                    potential_improvement="Réduisez la corrélation sous 0.5 avec des actifs alternatifs.",
                )
            )

        if risk_clusters:
            for cluster in risk_clusters[:3]:  # Top 3 clusters
                assets_str = ", ".join(cluster["assets"])
                insights.append(
                    SmartInsight(
                        category=InsightCategory.RISK,
                        severity=InsightSeverity.WARNING,
                        title="Cluster de risque détecté",
                        message=(
                            f"Les actifs {assets_str} forment un cluster "
                            f"(corrélation moyenne : {cluster['avg_corr']:.0%}). "
                            f"En cas de chute, ils baisseront simultanément."
                        ),
                        metric_name="risk_cluster_corr",
                        current_value=cluster["avg_corr"],
                    )
                )

        return insights, avg_top5_corr, risk_clusters
