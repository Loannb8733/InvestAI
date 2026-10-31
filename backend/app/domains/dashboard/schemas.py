from typing import Any

from pydantic import BaseModel


class HistoricalDataPoint(BaseModel):
    """Un point de la courbe de valeur."""

    date: str
    full_date: str | None = None
    value: float
    invested: float | None = None
    net_capital: float | None = None
    gain_loss: float | None = None
    is_estimated: bool = False


class RecentTransaction(BaseModel):
    """Une transaction récente."""

    id: str
    symbol: str
    asset_type: str
    transaction_type: str
    quantity: float
    price: float
    total: float
    executed_at: str


class ActiveAlert(BaseModel):
    """Une alerte active."""

    id: str
    name: str
    symbol: str | None
    condition: str
    threshold: float
    current_price: float | None = None


class UpcomingEvent(BaseModel):
    """Une échéance à venir."""

    id: str
    title: str
    event_type: str
    event_date: str
    amount: float | None = None


class AssetAllocation(BaseModel):
    """Part d'un actif dans le patrimoine."""

    symbol: str
    name: str | None
    asset_type: str
    value: float
    percentage: float
    gain_loss_percent: float
    avg_buy_price: float | None = None
    staked_quantity: float | None = None


class CurrencyExposure(BaseModel):
    """Part d'une devise dans le patrimoine."""

    currency: str
    value: float
    percentage: float


class EarnAsset(BaseModel):
    """Une position en staking."""

    symbol: str
    staked_quantity: float
    current_value: float


class EarnSummary(BaseModel):
    """Synthèse du staking."""

    total_staked_value: float
    total_rewards: float
    apr: float | None = None
    assets: list[EarnAsset]


class IndexComparison(BaseModel):
    """Variation d'un indice de référence."""

    name: str
    symbol: str
    change_percent: float
    price: float


class MaxDrawdown(BaseModel):
    """Plus forte baisse depuis un sommet."""

    max_drawdown_percent: float
    peak_date: str | None = None
    trough_date: str | None = None
    peak_value: float | None = None
    trough_value: float | None = None


class ValueAtRisk(BaseModel):
    """Perte potentielle à un niveau de confiance."""

    var_percent: float
    var_amount: float
    confidence_level: float


class ConcentrationMetrics(BaseModel):
    """Concentration du portefeuille (HHI)."""

    hhi: float
    interpretation: str
    is_concentrated: bool
    top_asset: str | None = None
    top_concentration: float | None = None


class StressTest(BaseModel):
    """Scénario de baisse."""

    scenario_name: str
    current_value: float
    stressed_value: float
    potential_loss: float
    potential_loss_percent: float


class PnLBreakdown(BaseModel):
    """Gains réalisés et latents."""

    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    total_fees: float
    net_pnl: float


class RiskMetrics(BaseModel):
    """Indicateurs de risque."""

    volatility: float
    sharpe_ratio: float
    max_drawdown: MaxDrawdown
    var_95: ValueAtRisk
    beta: float | None = None
    alpha: float | None = None


class AdvancedMetrics(BaseModel):
    """Indicateurs d'analyse du portefeuille."""

    roi_annualized: float | None = None
    risk_metrics: RiskMetrics
    concentration: ConcentrationMetrics
    stress_tests: list[StressTest]
    pnl_breakdown: PnLBreakdown


class EnhancedDashboardResponse(BaseModel):
    """Réponse complète du tableau de bord."""

    total_value: float
    total_invested: float
    net_capital: float
    total_gain_loss: float
    total_gain_loss_percent: float
    net_gain_loss: float
    net_gain_loss_percent: float
    daily_change: float
    daily_change_percent: float
    period_change: float = 0.0
    period_change_percent: float = 0.0
    period_twr_percent: float | None = None
    portfolios_count: int
    assets_count: int
    allocation: list[dict[str, Any]]
    asset_allocation: list[AssetAllocation]
    top_performers: list[dict[str, Any]]
    worst_performers: list[dict[str, Any]]
    historical_data: list[HistoricalDataPoint]
    is_data_estimated: bool
    recent_transactions: list[RecentTransaction]
    active_alerts: list[ActiveAlert]
    upcoming_events: list[UpcomingEvent]
    index_comparison: list[IndexComparison]
    advanced_metrics: AdvancedMetrics
    available_liquidity: float = 0.0
    earn_summary: EarnSummary | None = None
    currency_exposure: list[CurrencyExposure] = []
    total_dividend_income: float = 0.0
    total_return: float = 0.0
    period_days: int = 30
    period_label: str = "30j"
    unpriced_symbols: list[str] = []
    forex_stale: bool = False
    last_updated: str


class MunitionsResponse(BaseModel):
    """Capacité de déploiement."""

    available_liquidity: float
    total_value: float
    liquidity_pct: float
    invested_pct: float
    next_signal_symbol: str | None = None
    next_signal_action: str | None = None
    next_signal_amount: float = 0.0
    can_execute: bool = True
    shortfall: float = 0.0
    message: str | None = None
    profile: str = "moderate"
    deploy_to_risk: float = 0.0
    keep_in_reserve: float = 0.0


class SparklineData(BaseModel):
    """Mini-courbe d'un symbole, normalisée entre 0 et 1."""

    symbol: str
    prices: list[float]
    change_pct: float


class BenchmarkDataPoint(BaseModel):
    """Un point d'indice, en base 100."""

    date: str
    value: float


class BenchmarkSeries(BaseModel):
    """Une série de comparaison en base 100."""

    name: str
    symbol: str
    data: list[BenchmarkDataPoint]
