"""Réponses HTTP de la santé du portefeuille."""

from pydantic import BaseModel


class ActionResponse(BaseModel):
    """Une action suggérée."""

    type: str
    symbol: str
    amount_eur: float | None = None
    reason: str | None = None


class InsightResponse(BaseModel):
    """Un conseil."""

    category: str
    severity: str
    title: str
    message: str
    metric_name: str | None = None
    current_value: float | None = None
    target_value: float | None = None
    potential_improvement: str | None = None
    actions: list[ActionResponse] = []


class RebalancingOrderResponse(BaseModel):
    """Un ordre de rééquilibrage suggéré."""

    symbol: str
    name: str
    action: str
    current_weight: float
    target_weight: float
    current_value_eur: float
    target_value_eur: float
    amount_eur: float
    reason: str


class AnomalyImpactResponse(BaseModel):
    """Une anomalie et son effet en euros."""

    symbol: str
    anomaly_type: str
    severity: str
    description: str
    price_change_percent: float
    position_value_eur: float
    impact_eur: float
    detected_at: str


class RegimeConfigResponse(BaseModel):
    """Paramètres du cycle de marché."""

    risk_multiplier: float
    alpha_threshold: int
    gold_relevance: str
    mode_label: str
    vol_regime: str


class RiskClusterResponse(BaseModel):
    """Grappe d'actifs très corrélés."""

    assets: list[str]
    avg_corr: float


class MetricsSummaryResponse(BaseModel):
    """Métriques clés."""

    sharpe_ratio: float
    sortino_ratio: float
    volatility: float
    var_95: float
    max_drawdown: float
    hhi: float | None
    total_value: float
    regime_config: RegimeConfigResponse | None = None
    avg_top5_correlation: float | None = None
    risk_clusters: list[RiskClusterResponse] | None = None


class IndicatorSignalResponse(BaseModel):
    """Un indicateur du détecteur de régime."""

    name: str
    value: float
    signal: str
    strength: float
    description: str


class RegimeResultResponse(BaseModel):
    """Régime détecté pour un symbole."""

    symbol: str
    probabilities: dict[str, float]
    dominant_regime: str
    confidence: float
    signals: list[IndicatorSignalResponse]
    description: str


class MarketRegimeResponse(BaseModel):
    """Régime du marché et des premières lignes."""

    market: RegimeResultResponse
    per_asset: list[RegimeResultResponse]
    generated_at: str


class PortfolioHealthResponse(BaseModel):
    """Rapport de santé complet."""

    overall_score: int
    overall_status: str
    insights: list[InsightResponse]
    rebalancing_orders: list[RebalancingOrderResponse]
    anomaly_impacts: list[AnomalyImpactResponse]
    metrics_summary: MetricsSummaryResponse
    market_regime: MarketRegimeResponse | None = None
    generated_at: str


class TopInsightResponse(BaseModel):
    """Premier conseil du résumé."""

    title: str
    message: str
    severity: str
    category: str


class DashboardSummaryResponse(BaseModel):
    """Résumé du widget du tableau de bord."""

    health_score: int
    health_status: str
    top_insight: TopInsightResponse | None = None
    breakeven_pct: float | None = None
    anomaly_count: int
    regime: str | None = None
    generated_at: str
