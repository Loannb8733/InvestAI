from dataclasses import dataclass
from datetime import datetime
from typing import Any

HISTORY_DAYS = 365

ForecastPoint = dict[str, Any]


@dataclass
class PricePrediction:
    """Prévision de cours d'un actif ; `_history_*` gardent la série source, hors cache et hors API."""

    symbol: str
    current_price: float
    predictions: list[ForecastPoint]
    trend: str
    trend_strength: float
    support_level: float
    resistance_level: float
    recommendation: str
    model_used: str
    models_detail: list[dict[str, Any]] | None = None
    explanations: list[dict[str, Any]] | None = None
    regime_info: dict[str, Any] | None = None
    display_thresholds: dict[str, Any] | None = None
    _history_dates: list[datetime] | None = None
    _history_prices: list[float] | None = None


@dataclass
class AnomalyDetection:
    symbol: str
    is_anomaly: bool
    anomaly_type: str | None
    severity: str
    description: str
    detected_at: datetime
    price_change_percent: float


@dataclass
class MarketSentiment:
    overall_sentiment: str
    sentiment_score: float
    fear_greed_index: int
    market_phase: str
    signals: list[dict[str, Any]]
