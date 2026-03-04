"""Predictions endpoints for ML-based forecasting."""

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.ml import adaptive_thresholds as at
from app.models.asset import AssetType
from app.models.user import User
from app.services.prediction_service import prediction_service

router = APIRouter()


class PredictionPoint(BaseModel):
    """Single prediction point."""

    date: str
    price: float
    confidence_low: float
    confidence_high: float


class RegimeInfo(BaseModel):
    """Market regime detection result."""

    dominant_regime: str
    confidence: float
    probabilities: Dict[str, float] = {}
    timeframe_alignment: str = "unknown"
    weekly_regime: Optional[str] = None
    note: str = ""
    liquidity_warning: Optional[str] = None
    regime_price_adjustment: Optional[bool] = None
    adjustment_factor: Optional[float] = None


class AssetPredictionResponse(BaseModel):
    """Asset prediction response."""

    symbol: str
    current_price: float
    predictions: List[PredictionPoint]
    trend: str
    trend_strength: float
    support_level: float
    resistance_level: float
    recommendation: str
    model_used: str
    regime_info: Optional[RegimeInfo] = None
    display_thresholds: Optional[Dict] = None


class AnomalyResponse(BaseModel):
    """Anomaly detection response."""

    symbol: str
    is_anomaly: bool
    anomaly_type: Optional[str]
    severity: str
    description: str
    detected_at: str
    price_change_percent: float


class SignalResponse(BaseModel):
    """Market signal."""

    type: str
    message: str
    action: str


class MarketSentimentResponse(BaseModel):
    """Market sentiment response."""

    overall_sentiment: str
    sentiment_score: float
    fear_greed_index: int
    market_phase: str
    signals: List[SignalResponse]
    display_thresholds: Optional[Dict] = None


class ModelDetail(BaseModel):
    """Detail of a single model in the ensemble."""

    name: str
    weight_pct: float
    trend: str
    mape: Optional[float] = None


class FeatureExplanation(BaseModel):
    """SHAP feature explanation."""

    feature_name: str
    importance: float
    direction: str


class PortfolioAssetPrediction(BaseModel):
    """Prediction for a single asset in the portfolio."""

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
    predictions: List[PredictionPoint]
    support_level: float
    resistance_level: float
    # New scoring fields (replaces old accuracy/consensus_score)
    skill_score: float = 50.0
    hit_rate: float = 50.0
    hit_rate_significant: bool = False
    hit_rate_n_samples: int = 0
    reliability_score: float = 50.0
    model_confidence: str = "uncertain"
    models_agree: bool = True
    models_detail: Optional[List[ModelDetail]] = None
    explanations: List[FeatureExplanation] = Field(default_factory=list)
    regime_info: Optional[RegimeInfo] = None


class PortfolioPredictionSummary(BaseModel):
    """Portfolio prediction summary."""

    total_current_value: float
    total_predicted_value: float
    expected_change_percent: float
    overall_sentiment: str
    bullish_assets: int
    bearish_assets: int
    neutral_assets: int
    days_ahead: int


class PortfolioPredictionResponse(BaseModel):
    """Portfolio predictions response."""

    predictions: List[PortfolioAssetPrediction]
    summary: PortfolioPredictionSummary
    display_thresholds: Optional[Dict] = None


@router.get("/asset/{symbol}", response_model=AssetPredictionResponse)
async def get_asset_prediction(
    symbol: str,
    asset_type: str = Query("crypto", regex="^(crypto|stock|etf)$"),
    days: int = Query(7, ge=1, le=30),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AssetPredictionResponse:
    """Get price predictions for a specific asset."""
    type_map = {
        "crypto": AssetType.CRYPTO,
        "stock": AssetType.STOCK,
        "etf": AssetType.ETF,
    }

    prediction = await prediction_service.get_price_prediction(
        symbol.upper(),
        type_map[asset_type],
        days,
    )

    return AssetPredictionResponse(
        symbol=prediction.symbol,
        current_price=prediction.current_price,
        predictions=[PredictionPoint(**p) for p in prediction.predictions],
        trend=prediction.trend,
        trend_strength=prediction.trend_strength,
        support_level=prediction.support_level,
        resistance_level=prediction.resistance_level,
        recommendation=prediction.recommendation,
        model_used=prediction.model_used,
        regime_info=RegimeInfo(**prediction.regime_info) if prediction.regime_info else None,
        display_thresholds=prediction.display_thresholds,
    )


@router.get("/portfolio", response_model=PortfolioPredictionResponse)
async def get_portfolio_predictions(
    days: int = Query(7, ge=1, le=30),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PortfolioPredictionResponse:
    """Get predictions for all assets in user's portfolio."""
    result = await prediction_service.get_portfolio_predictions(db, str(current_user.id), days)

    return PortfolioPredictionResponse(
        predictions=result["predictions"],
        summary=PortfolioPredictionSummary(**result["summary"]),
        display_thresholds=result.get("display_thresholds"),
    )


@router.get("/anomalies", response_model=List[AnomalyResponse])
async def get_anomalies(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[AnomalyResponse]:
    """Detect anomalies in user's portfolio assets."""
    anomalies = await prediction_service.detect_anomalies(db, str(current_user.id))

    return [
        AnomalyResponse(
            symbol=a.symbol,
            is_anomaly=a.is_anomaly,
            anomaly_type=a.anomaly_type,
            severity=a.severity,
            description=a.description,
            detected_at=a.detected_at.isoformat(),
            price_change_percent=a.price_change_percent,
        )
        for a in anomalies
    ]


@router.get("/sentiment", response_model=MarketSentimentResponse)
async def get_market_sentiment(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MarketSentimentResponse:
    """Get market sentiment analysis."""
    sentiment = await prediction_service.get_market_sentiment(db, str(current_user.id))

    return MarketSentimentResponse(
        overall_sentiment=sentiment.overall_sentiment,
        sentiment_score=sentiment.sentiment_score,
        fear_greed_index=sentiment.fear_greed_index,
        market_phase=sentiment.market_phase,
        signals=[SignalResponse(**s) for s in sentiment.signals],
        display_thresholds=at.build_display_thresholds(None),
    )


class WhatIfScenario(BaseModel):
    """Single what-if scenario."""

    symbol: str
    change_percent: float = Field(ge=-100, le=500)


class WhatIfRequest(BaseModel):
    """What-if request body."""

    scenarios: List[WhatIfScenario]


@router.post("/what-if", response_model=dict)
async def what_if_simulation(
    request: WhatIfRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Simulate what-if scenarios on the portfolio."""
    result = await prediction_service.get_what_if(
        db,
        str(current_user.id),
        [s.model_dump() for s in request.scenarios],
    )
    return result


@router.get("/market-cycle", response_model=dict)
async def get_market_cycle(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get market cycle analysis with regime detection for BTC and portfolio assets."""
    return await prediction_service.get_market_cycle(db, str(current_user.id))


@router.get("/events", response_model=list)
async def get_market_events(
    current_user: User = Depends(get_current_user),
):
    """Get upcoming market events that may impact predictions."""
    events = await prediction_service.get_market_events()
    return events


@router.get("/backtest", response_model=dict)
async def get_portfolio_backtest(
    days: int = Query(7, ge=1, le=30),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Compare past predictions with actual prices across the portfolio.

    Returns per-asset and aggregate MAPE, direction accuracy, and a
    flag indicating whether model retraining is recommended (MAPE > 10%).
    """
    return await prediction_service.get_portfolio_backtest(db, str(current_user.id), days)


@router.get("/track-record/{symbol}", response_model=dict)
async def get_track_record(
    symbol: str,
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    """Get prediction track record for a specific asset.

    Returns past predictions with actual outcomes for transparency.
    """
    return await prediction_service.get_track_record(symbol.upper(), limit)
