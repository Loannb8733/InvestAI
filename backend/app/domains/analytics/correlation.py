import logging
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.stats import spearmanr
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.analytics.metrics import compute_returns
from app.domains.analytics.portfolio import AnalyticsPortfolio
from app.domains.analytics.results import CorrelationData, PortfolioAnalytics
from app.domains.analytics.scoring import diversification_rating
from app.domains.market_data.history.benchmarks import ANALYTICS_BENCHMARKS
from app.ml import adaptive_thresholds as adaptive_th

logger = logging.getLogger(__name__)

FloatArray = NDArray[np.float64]
Pair = tuple[str, str, float]

MIN_RETURNS = 5
BETA_HEAVY_CORRELATION = 0.70
OVERWEIGHT_PCT = 70


def _rank_matrix(valid_symbols: list[str], aligned: dict[str, FloatArray]) -> list[list[float]]:
    stacked = np.array([aligned[s] for s in valid_symbols])
    matrix_np = spearmanr(stacked, axis=1).statistic
    if np.ndim(matrix_np) == 0:
        matrix_np = np.array([[1.0, float(matrix_np)], [float(matrix_np), 1.0]])
    n = len(valid_symbols)
    values = [[float(matrix_np[vi, vj]) for vj in range(n)] for vi in range(n)]
    return [[0.0 if np.isnan(c) else c for c in row] for row in values]


def _correlated_pairs(valid_symbols: list[str], values: list[list[float]]) -> tuple[list[Pair], list[Pair]]:
    strongly: list[Pair] = []
    negatively: list[Pair] = []
    for vi, s1 in enumerate(valid_symbols):
        for vj in range(vi + 1, len(valid_symbols)):
            corr = values[vi][vj]
            strong_pos, neg_th = adaptive_th.correlation_thresholds()
            if corr > strong_pos:
                strongly.append((s1, valid_symbols[vj], round(corr, 3)))
            elif corr < neg_th:
                negatively.append((s1, valid_symbols[vj], round(corr, 3)))
    return sorted(strongly, key=lambda x: -x[2]), sorted(negatively, key=lambda x: x[2])


def _full_matrix(symbols: list[str], valid_symbols: list[str], values: list[list[float]]) -> list[list[float]]:
    full_n = len(symbols)
    matrix = [[0.0] * full_n for _ in range(full_n)]
    valid_idx = {s: symbols.index(s) for s in valid_symbols}
    for vi, s1 in enumerate(valid_symbols):
        for vj, s2 in enumerate(valid_symbols):
            matrix[valid_idx[s1]][valid_idx[s2]] = round(values[vi][vj], 3)
    for i in range(full_n):
        matrix[i][i] = 1.0
    return matrix


def _correlations_with(
    bench_rets: FloatArray, valid_symbols: list[str], aligned: dict[str, FloatArray]
) -> dict[str, float]:
    corr_map: dict[str, float] = {}
    for sym in valid_symbols:
        sym_rets = aligned[sym]
        common = min(len(sym_rets), len(bench_rets))
        if common >= MIN_RETURNS:
            c, _ = spearmanr(sym_rets[-common:], bench_rets[-common:])
            corr_map[sym] = round(float(c) if not np.isnan(c) else 0.0, 3)
    return corr_map


def _market_exposure(
    benchmark_correlations: dict[str, dict[str, float]], valid_symbols: list[str]
) -> tuple[float | None, bool]:
    sp500_corrs = benchmark_correlations.get("S&P500", {})
    if sp500_corrs and valid_symbols:
        avg_sp_corr = sum(sp500_corrs.values()) / len(sp500_corrs)
        return round(avg_sp_corr, 3), avg_sp_corr > BETA_HEAVY_CORRELATION
    return None, False


def _recommendations(analytics: PortfolioAnalytics) -> list[dict[str, str]]:
    conc_warn, conc_crit = adaptive_th.concentration_thresholds()
    recs: list[dict[str, str]] = []
    if analytics.concentration_risk > conc_warn:
        top = sorted(analytics.allocation_by_asset.items(), key=lambda x: -x[1])[:3]
        recs.append(
            {
                "type": "concentration",
                "severity": "high" if analytics.concentration_risk > conc_crit else "medium",
                "message": f"Concentration élevée: {top[0][0]} représente {top[0][1]:.1f}% du portefeuille",
                "action": "Envisagez de diversifier vers d'autres actifs",
            }
        )
    if len(analytics.allocation_by_type) < 3:
        recs.append(
            {
                "type": "asset_types",
                "severity": "medium",
                "message": f"Seulement {len(analytics.allocation_by_type)} classe(s) d'actifs",
                "action": "Diversifiez entre crypto, actions, ETF et immobilier",
            }
        )
    recs.extend(
        {
            "type": "overweight",
            "severity": "medium",
            "message": f"{at} représente {w:.1f}% du portefeuille",
            "action": f"Réduisez l'exposition à {at}",
        }
        for at, w in analytics.allocation_by_type.items()
        if w > OVERWEIGHT_PCT
    )
    if analytics.asset_count < 5:
        recs.append(
            {
                "type": "asset_count",
                "severity": "low",
                "message": f"Seulement {analytics.asset_count} actif(s) en portefeuille",
                "action": "Un portefeuille diversifié contient généralement 10-20 actifs",
            }
        )
    return recs


class AnalyticsCorrelation(AnalyticsPortfolio):
    async def _returns_by_symbol(self, symbols: list[str], days: int) -> dict[str, FloatArray]:
        returns_map: dict[str, FloatArray] = {}
        for sym in symbols:
            rets = compute_returns(await self._history_prices(sym, days=days))
            if len(rets) >= MIN_RETURNS:
                returns_map[sym] = rets
        return returns_map

    async def _benchmark_correlations(
        self, valid_symbols: list[str], aligned: dict[str, FloatArray], days: int
    ) -> dict[str, dict[str, float]]:
        benchmark_correlations: dict[str, dict[str, float]] = {}
        for bench_label, bench_sym, _ in ANALYTICS_BENCHMARKS:
            try:
                bench_rets = compute_returns(await self._history_prices(bench_sym, days=days))
                if len(bench_rets) >= MIN_RETURNS:
                    corr_map = _correlations_with(bench_rets, valid_symbols, aligned)
                    if corr_map:
                        benchmark_correlations[bench_label] = corr_map
            except Exception as e:  # noqa: BLE001
                logger.debug("Benchmark %s fetch failed: %s", bench_label, e)
        return benchmark_correlations

    async def get_correlation_matrix(
        self,
        db: AsyncSession,
        user_id: str,
        portfolio_id: str | None = None,
        days: int = 60,
    ) -> CorrelationData:
        """Corrélations de Spearman des rendements journaliers, plus robustes que Pearson aux queues épaisses
        de la crypto ; le bêta de portefeuille est la corrélation moyenne au S&P500."""
        assets = await self._get_user_assets(db, user_id, portfolio_id=portfolio_id)
        symbols = list(dict.fromkeys(a.symbol for a in assets))

        if len(symbols) < 2:
            return CorrelationData(
                symbols=symbols,
                matrix=[[1.0]] if symbols else [],
                strongly_correlated=[],
                negatively_correlated=[],
            )

        returns_map = await self._returns_by_symbol(symbols, days)
        valid_symbols = [s for s in symbols if s in returns_map]
        if len(valid_symbols) < 2:
            return CorrelationData(
                symbols=symbols,
                matrix=[[1.0 if i == j else 0.0 for j in range(len(symbols))] for i in range(len(symbols))],
                strongly_correlated=[],
                negatively_correlated=[],
            )

        min_len = min(len(returns_map[s]) for s in valid_symbols)
        aligned = {s: returns_map[s][-min_len:] for s in valid_symbols}
        values = _rank_matrix(valid_symbols, aligned)
        strongly, negatively = _correlated_pairs(valid_symbols, values)
        benchmark_correlations = await self._benchmark_correlations(valid_symbols, aligned, days)
        portfolio_beta, is_beta_heavy = _market_exposure(benchmark_correlations, valid_symbols)

        return CorrelationData(
            symbols=symbols,
            matrix=_full_matrix(symbols, valid_symbols, values),
            strongly_correlated=strongly,
            negatively_correlated=negatively,
            benchmark_correlations=benchmark_correlations or None,
            portfolio_beta=portfolio_beta,
            is_beta_heavy=is_beta_heavy,
        )

    async def get_diversification_analysis(
        self,
        db: AsyncSession,
        user_id: str,
        portfolio_id: str | None = None,
        days: int = 60,
    ) -> dict[str, Any]:
        """Score de diversification et recommandations ; `concentration_risk` est le HHI en fraction (0-1)."""
        if portfolio_id:
            analytics = await self.get_portfolio_analytics(db, portfolio_id, days=days)
        else:
            analytics = await self.get_user_analytics(db, user_id, days=days)

        return {
            "score": analytics.diversification_score,
            "concentration_risk": analytics.concentration_risk,
            "asset_count": analytics.asset_count,
            "type_count": len(analytics.allocation_by_type),
            "allocation_by_type": analytics.allocation_by_type,
            "recommendations": _recommendations(analytics),
            "rating": diversification_rating(analytics.diversification_score),
        }
