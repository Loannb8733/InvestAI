"""Structures de données des analyses de portefeuille.

Six dataclasses partagées par le service d'analyse, ses modules de calcul et
les endpoints qui les sérialisent. Elles vivaient en tête d'`analytics_service`,
ce qui obligeait tout module de calcul à importer le service entier — donc à
créer un cycle dès qu'il en rendait une.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class AssetPerformance:
    """Performance metrics for a single asset."""

    symbol: str
    name: str
    asset_type: str
    current_value: float
    total_invested: float
    gain_loss: float
    gain_loss_percent: float
    weight: float
    daily_return: float
    volatility_30d: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float


@dataclass
class PortfolioAnalytics:
    """Comprehensive portfolio analytics."""

    total_value: float
    total_invested: float
    total_gain_loss: float
    total_gain_loss_percent: float

    # Risk metrics
    portfolio_volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown: float
    var_95: float
    cvar_95: float  # Conditional VaR / Expected Shortfall

    # Diversification
    diversification_score: float
    concentration_risk: float
    asset_count: int

    # Allocation
    allocation_by_type: Dict[str, float]
    allocation_by_asset: Dict[str, float]

    # Performance
    assets: List[AssetPerformance]
    best_performer: Optional[str]
    worst_performer: Optional[str]

    # Human-readable VaR explanation (P12)
    var_95_description: str = ""

    # Contextual interpretations for ratios
    interpretations: Dict[str, str] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.interpretations is None:
            self.interpretations = {}


@dataclass
class CorrelationData:
    """Correlation matrix data."""

    symbols: List[str]
    matrix: List[List[float]]
    strongly_correlated: List[Tuple[str, str, float]]
    negatively_correlated: List[Tuple[str, str, float]]
    # Cross-asset analysis (P1)
    benchmark_correlations: Optional[Dict[str, Dict[str, float]]] = None  # {benchmark: {symbol: corr}}
    portfolio_beta: Optional[float] = None  # vs S&P500
    is_beta_heavy: bool = False  # True if portfolio is overly correlated with market


@dataclass
class MonteCarloResult:
    """Monte Carlo simulation result."""

    percentiles: Dict[str, float]  # p5, p25, p50, p75, p95
    expected_return: float
    prob_positive: float  # probability of positive return
    prob_loss_10: float  # probability of >10% loss
    prob_ruin: float  # probability of portfolio reaching zero
    simulations: int
    horizon_days: int


@dataclass
class RebalanceOrder:
    """Single rebalancing order."""

    symbol: str
    name: str
    asset_type: str
    current_weight: float
    target_weight: float
    diff_weight: float
    current_value: float
    target_value: float
    diff_value: float  # positive = buy, negative = sell
    action: str  # "buy" | "sell" | "hold"


@dataclass
class OptimizationResult:
    """Portfolio optimization (MPT) result."""

    weights: Dict[str, float]
    expected_return: float
    expected_volatility: float
    sharpe_ratio: float
