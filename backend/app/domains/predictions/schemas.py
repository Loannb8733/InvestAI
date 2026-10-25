from typing import Any

from pydantic import BaseModel, Field


class PredictionPoint(BaseModel):
    date: str
    price: float
    confidence_low: float
    confidence_high: float


class RegimeInfo(BaseModel):
    dominant_regime: str
    confidence: float
    probabilities: dict[str, float] = {}
    timeframe_alignment: str = "unknown"
    weekly_regime: str | None = None
    note: str = ""
    liquidity_warning: str | None = None
    regime_price_adjustment: bool | None = None
    adjustment_factor: float | None = None


class AnomalyResponse(BaseModel):
    symbol: str
    is_anomaly: bool
    anomaly_type: str | None
    severity: str
    description: str
    detected_at: str
    price_change_percent: float


class SignalResponse(BaseModel):
    type: str
    message: str
    action: str


class MarketSentimentResponse(BaseModel):
    overall_sentiment: str
    sentiment_score: float
    fear_greed_index: int
    market_phase: str
    signals: list[SignalResponse]
    display_thresholds: dict[Any, Any] | None = None


class ModelDetail(BaseModel):
    name: str
    weight_pct: float
    trend: str
    mape: float | None = None


class FeatureExplanation(BaseModel):
    feature_name: str
    importance: float
    direction: str


class PortfolioAssetPrediction(BaseModel):
    model_config = {"protected_namespaces": ()}

    symbol: str
    name: str
    asset_type: str
    current_price: float
    predicted_price: float
    change_percent: float
    trend: str
    trend_strength: float
    recommendation: str
    model_used: str
    predictions: list[PredictionPoint]
    support_level: float
    resistance_level: float
    skill_score: float = 50.0
    hit_rate: float = 50.0
    hit_rate_significant: bool = False
    hit_rate_n_samples: int = 0
    reliability_score: float = 50.0
    model_confidence: str = "uncertain"
    models_agree: bool = True
    models_detail: list[ModelDetail] | None = None
    explanations: list[FeatureExplanation] = Field(default_factory=list)
    regime_info: RegimeInfo | None = None


class PortfolioPredictionSummary(BaseModel):
    total_current_value: float
    total_predicted_value: float
    expected_change_percent: float
    overall_sentiment: str
    bullish_assets: int
    bearish_assets: int
    neutral_assets: int
    days_ahead: int


class PortfolioPredictionResponse(BaseModel):
    predictions: list[PortfolioAssetPrediction]
    summary: PortfolioPredictionSummary
    display_thresholds: dict[Any, Any] | None = None


class WhatIfScenario(BaseModel):
    symbol: str
    change_percent: float = Field(ge=-100, le=500)


class WhatIfRequest(BaseModel):
    scenarios: list[WhatIfScenario]


class PlannedOrderCreate(BaseModel):
    """Ordre planifié saisi depuis le frontend (ex. rééquilibrage MPT)."""

    symbol: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9.\-]{1,20}$")
    side: str = Field(pattern="^(buy|sell)$")
    amount_eur: float = Field(gt=0, le=10_000_000)
    notes: str | None = Field(None, max_length=1000)
    source: str = Field("frontend", pattern="^(frontend|telegram)$")
