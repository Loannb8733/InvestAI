from dataclasses import dataclass, field


@dataclass
class AssetPerformance:
    """Performance d'un actif ; les pourcentages et ratios sont annualisés sauf daily_return."""

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
    """Vue d'ensemble du portefeuille ; cvar_95 est l'Expected Shortfall au seuil de 95 %."""

    total_value: float
    total_invested: float
    total_gain_loss: float
    total_gain_loss_percent: float
    portfolio_volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown: float
    var_95: float
    cvar_95: float
    diversification_score: float
    concentration_risk: float
    asset_count: int
    allocation_by_type: dict[str, float]
    allocation_by_asset: dict[str, float]
    assets: list[AssetPerformance]
    best_performer: str | None
    worst_performer: str | None
    var_95_description: str = ""
    interpretations: dict[str, str] = field(default_factory=dict)


@dataclass
class CorrelationData:
    """Corrélations ; benchmark_correlations vaut {indice: {symbole: corrélation}}, bêta mesuré contre le S&P 500."""

    symbols: list[str]
    matrix: list[list[float]]
    strongly_correlated: list[tuple[str, str, float]]
    negatively_correlated: list[tuple[str, str, float]]
    benchmark_correlations: dict[str, dict[str, float]] | None = None
    portfolio_beta: float | None = None
    is_beta_heavy: bool = False


@dataclass
class MonteCarloResult:
    """Distribution simulée du rendement total en % ; prob_ruin est la part des trajectoires tombées à zéro."""

    percentiles: dict[str, float]
    expected_return: float
    prob_positive: float
    prob_loss_10: float
    prob_ruin: float
    simulations: int
    horizon_days: int


@dataclass
class RebalanceOrder:
    """Ordre de rééquilibrage : diff_value positif pour un achat, négatif pour une vente."""

    symbol: str
    name: str
    asset_type: str
    current_weight: float
    target_weight: float
    diff_weight: float
    current_value: float
    target_value: float
    diff_value: float
    action: str


@dataclass
class OptimizationResult:
    """Allocation optimale au sens de Markowitz."""

    weights: dict[str, float]
    expected_return: float
    expected_volatility: float
    sharpe_ratio: float
