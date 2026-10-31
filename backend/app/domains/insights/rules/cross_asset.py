"""Conseils tirés des corrélations aux grands marchés : S&P 500, Nasdaq, or, VIX."""

from typing import Any

from app.domains.analytics.results import CorrelationData
from app.domains.insights.results import InsightCategory, InsightSeverity, SmartInsight
from app.ml.regime_detector import MarketRegime

_HIGH_BETA_CORRELATION = 0.60
_HIGH_NASDAQ_CORRELATION = 0.70
_LOW_GOLD_CORRELATION = 0.20
_MIN_GOLD_HEDGED_ASSETS = 2
_STRESSED_VIX = 25


def _beta_heavy(data: CorrelationData, sp500: dict[str, float]) -> list[SmartInsight]:
    if not data.is_beta_heavy or data.portfolio_beta is None:
        return []
    exposed = sorted(
        ((symbol, corr) for symbol, corr in sp500.items() if corr > _HIGH_BETA_CORRELATION), key=lambda x: -x[1]
    )
    listed = ", ".join(f"{symbol} ({corr:.0%})" for symbol, corr in exposed[:4])
    return [
        SmartInsight(
            category=InsightCategory.RISK,
            severity=InsightSeverity.WARNING,
            title="Portefeuille Beta-Heavy",
            message=(
                f"Votre portefeuille est correle a {data.portfolio_beta:.0%} "
                f"avec le S&P 500. Les actifs les plus exposes : {listed}. "
                "Un choc macroeconomique (hausse des taux, recession) impactera "
                "l'ensemble de vos positions simultanement."
            ),
            metric_name="portfolio_beta",
            current_value=data.portfolio_beta,
            target_value=0.50,
            potential_improvement="Diversifier avec des actifs decorrelés (or, obligations, immobilier)",
            actions=[
                {
                    "type": "buy",
                    "symbol": "PAXG",
                    "reason": "Or tokenise — decorrelation historique avec les marches actions",
                }
            ],
        )
    ]


def _hidden_tech(nasdaq: dict[str, float], top_holdings: list[dict[str, Any]]) -> list[SmartInsight]:
    held = {holding.get("symbol", "").upper() for holding in top_holdings}
    exposed = [
        (symbol, corr) for symbol, corr in nasdaq.items() if corr > _HIGH_NASDAQ_CORRELATION and symbol.upper() in held
    ]
    if not exposed:
        return []
    listed = ", ".join(f"{symbol} ({corr:.0%})" for symbol, corr in exposed[:3])
    return [
        SmartInsight(
            category=InsightCategory.RISK,
            severity=InsightSeverity.WARNING,
            title="Correlation cachee Tech/Crypto",
            message=(
                f"Attention : {listed} sont correles a plus de 70% avec le Nasdaq. "
                "Un choc sur les taux d'interet ou une rotation sectorielle "
                "impactera ces positions et vos eventuelles expositions tech "
                "simultanement."
            ),
            metric_name="nasdaq_correlation",
            current_value=max(corr for _, corr in exposed),
        )
    ]


def _gold_hedge(gold: dict[str, float]) -> list[SmartInsight]:
    hedged = [corr for corr in gold.values() if corr < _LOW_GOLD_CORRELATION]
    if len(hedged) < _MIN_GOLD_HEDGED_ASSETS:
        return []
    average = sum(hedged) / len(hedged)
    return [
        SmartInsight(
            category=InsightCategory.DIVERSIFICATION,
            severity=InsightSeverity.INFO,
            title="Or : couverture naturelle active",
            message=(
                f"L'or (PAXG/XAU) affiche une correlation moyenne de "
                f"{average:.0%} avec vos positions, confirmant son role "
                "de couverture. En regime baissier, cette decorrelation "
                "stabilise la volatilite globale de votre portefeuille."
            ),
            metric_name="gold_avg_correlation",
            current_value=average,
        )
    ]


def _vix_alert(data: CorrelationData, market_regime: MarketRegime | None) -> list[SmartInsight]:
    if market_regime is None or not data.is_beta_heavy:
        return []
    levels = [signal.value for signal in market_regime.market.signals if signal.name == "VIX (TradFi)"]
    if not levels or levels[0] <= _STRESSED_VIX:
        return []
    return [
        SmartInsight(
            category=InsightCategory.RISK,
            severity=InsightSeverity.CRITICAL,
            title="Alerte VIX + Beta eleve",
            message=(
                f"Le VIX est a {levels[0]:.0f} (stress eleve) et votre "
                f"portefeuille est Beta-Heavy ({data.portfolio_beta:.0%} "
                "correle au S&P500). Risque d'impact severe. "
                "Envisagez de renforcer vos couvertures ou reduire "
                "l'exposition aux actifs les plus correles."
            ),
            metric_name="vix",
            current_value=levels[0],
            actions=[
                {"type": "hold", "symbol": "PORTFOLIO", "reason": "Reduire l'exposition beta en periode de stress"}
            ],
        )
    ]


def cross_asset_insights(
    data: CorrelationData, top_holdings: list[dict[str, Any]], market_regime: MarketRegime | None
) -> list[SmartInsight]:
    """Exposition au marché actions, corrélation cachée à la tech, couverture par l'or, alerte VIX."""
    benchmarks = data.benchmark_correlations or {}
    return [
        *_beta_heavy(data, benchmarks.get("S&P500", {})),
        *_hidden_tech(benchmarks.get("Nasdaq", {}), top_holdings),
        *_gold_hedge(benchmarks.get("Gold", {})),
        *_vix_alert(data, market_regime),
    ]
