"""Predictions endpoints for ML-based forecasting."""

from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.asset import Asset, AssetType
from app.models.portfolio import Portfolio
from app.models.user import User
from app.services.prediction_service import prediction_service

router = APIRouter()


class PredictionPoint(BaseModel):
    """Single prediction point."""

    date: str
    price: float
    confidence_low: float
    confidence_high: float


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

    predictions: List[Dict]
    summary: PortfolioPredictionSummary


@router.get("/asset/{symbol}")
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
        predictions=[
            PredictionPoint(**p) for p in prediction.predictions
        ],
        trend=prediction.trend,
        trend_strength=prediction.trend_strength,
        support_level=prediction.support_level,
        resistance_level=prediction.resistance_level,
        recommendation=prediction.recommendation,
        model_used=prediction.model_used,
    )


@router.get("/portfolio")
async def get_portfolio_predictions(
    days: int = Query(7, ge=1, le=30),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PortfolioPredictionResponse:
    """Get predictions for all assets in user's portfolio."""
    result = await prediction_service.get_portfolio_predictions(
        db, str(current_user.id), days
    )

    return PortfolioPredictionResponse(
        predictions=result["predictions"],
        summary=PortfolioPredictionSummary(**result["summary"]),
    )


@router.get("/anomalies", response_model=List[AnomalyResponse])
async def get_anomalies(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[AnomalyResponse]:
    """Detect anomalies in user's portfolio assets."""
    anomalies = await prediction_service.detect_anomalies(
        db, str(current_user.id)
    )

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
    sentiment = await prediction_service.get_market_sentiment(
        db, str(current_user.id)
    )

    return MarketSentimentResponse(
        overall_sentiment=sentiment.overall_sentiment,
        sentiment_score=sentiment.sentiment_score,
        fear_greed_index=sentiment.fear_greed_index,
        market_phase=sentiment.market_phase,
        signals=[SignalResponse(**s) for s in sentiment.signals],
    )


class WhatIfScenario(BaseModel):
    """Single what-if scenario."""

    symbol: str
    change_percent: float = Field(ge=-100, le=500)


class WhatIfRequest(BaseModel):
    """What-if request body."""

    scenarios: List[WhatIfScenario]


@router.post("/what-if")
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


@router.get("/events")
async def get_market_events(
    current_user: User = Depends(get_current_user),
):
    """Get upcoming market events that may impact predictions."""
    events = await prediction_service.get_market_events()
    return events
