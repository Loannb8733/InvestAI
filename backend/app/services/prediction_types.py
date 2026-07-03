"""Result dataclasses for the prediction service.

Extracted from the prediction god-module so consumers can import the shapes
without pulling in the whole service. ``prediction_service`` re-exports them.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class PricePrediction:
    """Price prediction for an asset."""

    symbol: str
    current_price: float
    predictions: List[Dict]  # [{date, price, confidence_low, confidence_high}]
    trend: str  # "bullish", "bearish", "neutral"
    trend_strength: float  # 0-100
    support_level: float
    resistance_level: float
    recommendation: str
    model_used: str
    models_detail: List[Dict] = None  # [{name, weight_pct, mape, trend}]
    explanations: List[Dict] = None  # SHAP explanations from XGBoost
    regime_info: Optional[Dict] = None  # {dominant_regime, confidence, probabilities}
    display_thresholds: Optional[Dict] = None  # adaptive thresholds for frontend
    _history_dates: List = None  # internal: cached for accuracy calc
    _history_prices: List[float] = None  # internal: cached for accuracy calc


@dataclass
class AnomalyDetection:
    """Anomaly detection result."""

    symbol: str
    is_anomaly: bool
    anomaly_type: Optional[str]
    severity: str
    description: str
    detected_at: datetime
    price_change_percent: float


@dataclass
class MarketSentiment:
    """Market sentiment analysis."""

    overall_sentiment: str
    sentiment_score: float
    fear_greed_index: int
    market_phase: str
    signals: List[Dict]
