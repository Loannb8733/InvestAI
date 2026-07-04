"""Smart-insights value types (severity/category enums + result dataclasses).

Separate module so both smart_insights_service and smart_insights_analyzers can
import them without a circular import.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from app.ml.regime_detector import MarketRegime


class InsightSeverity(str, Enum):
    """Severity level for insights."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class InsightCategory(str, Enum):
    """Category of insight."""

    PERFORMANCE = "performance"
    RISK = "risk"
    DIVERSIFICATION = "diversification"
    REBALANCING = "rebalancing"
    ANOMALY = "anomaly"
    OPPORTUNITY = "opportunity"


@dataclass
class SmartInsight:
    """A single smart insight/recommendation."""

    category: InsightCategory
    severity: InsightSeverity
    title: str
    message: str
    metric_name: Optional[str] = None
    current_value: Optional[float] = None
    target_value: Optional[float] = None
    potential_improvement: Optional[str] = None
    actions: List[Dict] = field(default_factory=list)
    # Actions format: [{"type": "buy/sell/hold", "symbol": "BTC", "amount_eur": 500, "reason": "..."}]


@dataclass
class RebalancingOrder:
    """A suggested rebalancing order."""

    symbol: str
    name: str
    action: str  # "buy" or "sell"
    current_weight: float
    target_weight: float
    current_value_eur: float
    target_value_eur: float
    amount_eur: float  # Amount to buy (positive) or sell (negative)
    reason: str


@dataclass
class AnomalyImpact:
    """Anomaly with calculated EUR impact."""

    symbol: str
    anomaly_type: str
    severity: str
    description: str
    price_change_percent: float
    position_value_eur: float
    impact_eur: float  # Gain or loss in EUR
    detected_at: datetime


@dataclass
class PortfolioHealthReport:
    """Complete portfolio health analysis."""

    overall_score: int  # 0-100
    overall_status: str  # "excellent", "good", "fair", "poor", "critical"
    insights: List[SmartInsight]
    rebalancing_orders: List[RebalancingOrder]
    anomaly_impacts: List[AnomalyImpact]
    metrics_summary: Dict[str, float]
    market_regime: Optional[MarketRegime] = None
    generated_at: datetime = field(default_factory=datetime.utcnow)
