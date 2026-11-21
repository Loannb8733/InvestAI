from pydantic import BaseModel


class AssetPerformanceResponse(BaseModel):
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


class PortfolioAnalyticsResponse(BaseModel):
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
    var_95_description: str = ""
    diversification_score: float
    concentration_risk: float
    asset_count: int
    allocation_by_type: dict[str, float]
    allocation_by_asset: dict[str, float]
    assets: list[AssetPerformanceResponse]
    best_performer: str | None
    worst_performer: str | None
    interpretations: dict[str, str] = {}


class CorrelationResponse(BaseModel):
    symbols: list[str]
    matrix: list[list[float]]
    strongly_correlated: list[tuple[str, str, float]]
    negatively_correlated: list[tuple[str, str, float]]


class RecommendationResponse(BaseModel):
    type: str
    severity: str
    message: str
    action: str


class DiversificationResponse(BaseModel):
    score: float
    concentration_risk: float
    asset_count: int
    type_count: int
    allocation_by_type: dict[str, float]
    recommendations: list[RecommendationResponse]
    rating: str


class MonteCarloResponse(BaseModel):
    percentiles: dict[str, float]
    expected_return: float
    prob_positive: float
    prob_loss_10: float
    prob_ruin: float
    simulations: int
    horizon_days: int


class RebalanceOrderResponse(BaseModel):
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


class OptimizationResponse(BaseModel):
    weights: dict[str, float]
    expected_return: float
    expected_volatility: float
    sharpe_ratio: float


class PerformanceSummaryItem(BaseModel):
    symbol: str
    name: str
    asset_type: str
    gain_loss_percent: float | None = None
    current_value: float | None = None
    weight: float | None = None
    volatility: float | None = None


class PerformanceSummaryMetrics(BaseModel):
    total_value: float
    total_gain_loss: float
    total_gain_loss_percent: float
    volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown: float
    cvar_95: float


class PerformanceSummaryResponse(BaseModel):
    period: str
    summary: PerformanceSummaryMetrics
    top_gainers: list[PerformanceSummaryItem]
    top_losers: list[PerformanceSummaryItem]
    largest_positions: list[PerformanceSummaryItem]
    most_volatile: list[PerformanceSummaryItem]


class RebalanceResponse(BaseModel):
    orders: list[RebalanceOrderResponse]


class StressAssetImpact(BaseModel):
    symbol: str
    name: str | None
    current_value: float
    stressed_value: float
    loss: float
    shock_pct: float | int
    risk_weight: float


class StressScenarioResponse(BaseModel):
    id: str
    name: str
    description: str
    duration_days: int
    stressed_value: float
    total_loss: float
    total_loss_pct: float
    estimated_recovery_months: int
    per_asset: list[StressAssetImpact]


class StressDrawdown(BaseModel):
    value: float
    scenario: str
    estimated_recovery_months: int


class PortfolioStressTestResponse(BaseModel):
    total_value: float | int
    currency: str
    scenarios: list[StressScenarioResponse]
    max_drawdown: StressDrawdown | None


class AssetBetaResponse(BaseModel):
    symbol: str
    asset_type: str
    beta: float | None
    benchmark: str
    interpretation: str
    value: float


class BetaResponse(BaseModel):
    assets: list[AssetBetaResponse]
    portfolio_beta_crypto: float | None
    portfolio_beta_stock: float | None
    benchmarks: dict[str, str] = {}


class XIRRResponse(BaseModel):
    xirr: float | None
    currency: str = "EUR"
    description: str


class PlatformDistributionItem(BaseModel):
    name: str
    value: float
    percentage: float
    trust_score: int
