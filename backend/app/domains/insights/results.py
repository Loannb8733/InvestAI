"""Résultats de l'analyse de santé d'un portefeuille."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from app.ml.regime_detector import MarketRegime


class InsightSeverity(StrEnum):
    """Gravité d'un conseil."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class InsightCategory(StrEnum):
    """Famille d'un conseil."""

    PERFORMANCE = "performance"
    RISK = "risk"
    DIVERSIFICATION = "diversification"
    REBALANCING = "rebalancing"
    ANOMALY = "anomaly"
    OPPORTUNITY = "opportunity"


@dataclass
class SmartInsight:
    """Un conseil ; chaque action porte `type`, `symbol` et, selon le cas, `amount_eur` et `reason`."""

    category: InsightCategory
    severity: InsightSeverity
    title: str
    message: str
    metric_name: str | None = None
    current_value: float | None = None
    target_value: float | None = None
    potential_improvement: str | None = None
    actions: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RebalancingOrder:
    """Un ordre de rééquilibrage suggéré ; `action` vaut buy, sell ou hold."""

    symbol: str
    name: str
    action: str
    current_weight: float
    target_weight: float
    current_value_eur: float
    target_value_eur: float
    amount_eur: float
    reason: str


@dataclass
class AnomalyImpact:
    """Une anomalie de cours et son effet en euros sur la position."""

    symbol: str
    anomaly_type: str
    severity: str
    description: str
    price_change_percent: float
    position_value_eur: float
    impact_eur: float
    detected_at: datetime


@dataclass
class PortfolioHealthReport:
    """Rapport de santé complet ; `overall_score` va de 0 à 100."""

    overall_score: int
    overall_status: str
    insights: list[SmartInsight]
    rebalancing_orders: list[RebalancingOrder]
    anomaly_impacts: list[AnomalyImpact]
    metrics_summary: dict[str, Any]
    generated_at: datetime
    market_regime: MarketRegime | None = None
