from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_session
from app.core.rate_limit import limiter
from app.domains.identity.dependencies import CurrentUser
from app.domains.identity.models import User
from app.domains.predictions.alerts import (
    send_alpha_alert,
    send_concentration_alert,
    send_cycle_alert,
    send_euphoria_alert,
    send_signal_report,
    send_strategy_recap,
)
from app.domains.predictions.planned_orders import apply_status, create_pending, find_owned, list_pending
from app.domains.predictions.schemas import (
    AnomalyResponse,
    MarketSentimentResponse,
    PlannedOrderCreate,
    PortfolioPredictionResponse,
    PortfolioPredictionSummary,
    SignalResponse,
    WhatIfRequest,
)
from app.domains.predictions.service import prediction_service
from app.domains.predictions.signal import validate_top_alpha
from app.ml import adaptive_thresholds as at

router = APIRouter()

Session = Annotated[AsyncSession, Depends(get_session)]
Days = Annotated[int, Query(ge=1, le=30)]

ALPHA_ALERT_SCORE = 85
CONCENTRATION_ALERT_PCT = 60
EUPHORIA_FEAR_GREED = 80


def _telegram_chat(user: User) -> str | None:
    return user.telegram_chat_id if user.telegram_enabled and user.telegram_chat_id else None


def _queue_cycle_alerts(tasks: BackgroundTasks, chat_id: str, user_id: str, result: dict[str, Any]) -> None:
    critical_advice = [
        a
        for a in result.get("cycle_advice", [])
        if a.get("priority") in ("critical", "high") and a.get("action") in ("DCA", "DIVERSIFIER")
    ]
    if critical_advice:
        tasks.add_task(
            send_cycle_alert,
            chat_id=chat_id,
            user_id=user_id,
            advice=critical_advice[0],
            regime=result.get("market_regime", {}).get("dominant_regime", "unknown")
            if result.get("market_regime")
            else "unknown",
            fear_greed=result.get("fear_greed"),
        )

    btc_regime = result.get("market_regime")
    fg = result.get("fear_greed")
    if btc_regime and btc_regime.get("dominant_regime") == "top" and fg is not None and fg > EUPHORIA_FEAR_GREED:
        portfolio_value = sum(a.get("value", 0) for a in result.get("per_asset", []))
        tasks.add_task(
            send_euphoria_alert, chat_id=chat_id, user_id=user_id, fear_greed=fg, portfolio_value=portfolio_value
        )


async def _queue_alpha_alert(
    tasks: BackgroundTasks, db: AsyncSession, chat_id: str, user_id: str, result: dict[str, Any]
) -> None:
    top = result["top_alpha"]
    total_value = result.get("total_portfolio_value", 0)
    strategy_data = await prediction_service.get_strategy_map(db, user_id)
    order_eur = 0.0
    for row in strategy_data.get("rows", []):
        if row["symbol"] == top["symbol"]:
            order_eur = round(total_value * abs(row.get("impact_pct", 0)) / 100, 2)
            break

    tasks.add_task(
        send_alpha_alert,
        chat_id=chat_id,
        user_id=user_id,
        symbol=top["symbol"],
        score=top["score"],
        predicted_pct=top.get("predicted_7d_pct", 0),
        reasons=top.get("reasons", []),
        order_eur=order_eur,
    )


def _is_alpha_alert(result: dict[str, Any]) -> bool:
    top = result.get("top_alpha")
    return bool(top and top.get("score", 0) > ALPHA_ALERT_SCORE and not result.get("concentration_risk"))


@router.get("/portfolio", response_model=PortfolioPredictionResponse)
async def get_portfolio_predictions(user: CurrentUser, session: Session, days: Days = 7) -> PortfolioPredictionResponse:
    result = await prediction_service.get_portfolio_predictions(session, str(user.id), days)
    return PortfolioPredictionResponse(
        predictions=result["predictions"],
        summary=PortfolioPredictionSummary(**result["summary"]),
        display_thresholds=result.get("display_thresholds"),
    )


@router.get("/anomalies", response_model=list[AnomalyResponse])
async def get_anomalies(user: CurrentUser, session: Session) -> list[AnomalyResponse]:
    anomalies = await prediction_service.detect_anomalies(session, str(user.id))
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
async def get_market_sentiment(user: CurrentUser, session: Session) -> MarketSentimentResponse:
    sentiment = await prediction_service.get_market_sentiment(session, str(user.id))
    return MarketSentimentResponse(
        overall_sentiment=sentiment.overall_sentiment,
        sentiment_score=sentiment.sentiment_score,
        fear_greed_index=sentiment.fear_greed_index,
        market_phase=sentiment.market_phase,
        signals=[SignalResponse(**s) for s in sentiment.signals],
        display_thresholds=at.build_display_thresholds(None),
    )


@router.post("/what-if", response_model=dict)
async def what_if_simulation(request: WhatIfRequest, user: CurrentUser, session: Session) -> dict[str, Any]:
    return await prediction_service.get_what_if(session, str(user.id), [s.model_dump() for s in request.scenarios])


@router.get("/market-cycle", response_model=dict)
async def get_market_cycle(background_tasks: BackgroundTasks, user: CurrentUser, session: Session) -> dict[str, Any]:
    """Cycle de marché (régime BTC et par actif) ; les conseils DCA/diversification critiques et l'euphorie (régime
    sommet, Fear & Greed > 80) partent en alerte Telegram de fond."""
    result = await prediction_service.get_market_cycle(session, str(user.id))
    chat_id = _telegram_chat(user)
    if chat_id:
        _queue_cycle_alerts(background_tasks, chat_id, str(user.id), result)
    return result


@router.get("/top-alpha", response_model=dict)
async def get_top_alpha(background_tasks: BackgroundTasks, user: CurrentUser, session: Session) -> dict[str, Any]:
    """Actif détenu au plus fort potentiel alpha ; alerte Telegram au-delà d'un score de 85 sans risque de
    concentration, et pour chaque actif au-delà de 60 % du portefeuille."""
    result = await prediction_service.get_top_alpha_asset(session, str(user.id))
    chat_id = _telegram_chat(user)
    if chat_id and _is_alpha_alert(result):
        await _queue_alpha_alert(background_tasks, session, chat_id, str(user.id), result)

    if chat_id:
        for scored in result.get("all_scores", []):
            if scored.get("weight_pct", 0) > CONCENTRATION_ALERT_PCT:
                background_tasks.add_task(
                    send_concentration_alert,
                    chat_id=chat_id,
                    user_id=str(user.id),
                    symbol=scored["symbol"],
                    weight_pct=scored["weight_pct"],
                )
    return result


@router.get("/validate-signal", response_model=dict)
async def validate_signal(
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    session: Session,
    symbol: Annotated[str | None, Query()] = None,
    action: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    """Valide le signal alpha (ou ``symbol``/``action`` imposés) par l'impact Monte-Carlo sur la probabilité de
    ruine, puis envoie le rapport sur Telegram."""
    alpha_data = await prediction_service.get_top_alpha_asset(session, str(user.id))
    if not alpha_data.get("found"):
        return {"validated": False, "reason": "Aucun actif scoré disponible."}

    result = await validate_top_alpha(session, str(user.id), alpha_data, symbol, action)
    chat_id = _telegram_chat(user)
    if chat_id:
        background_tasks.add_task(send_signal_report, chat_id=chat_id, user_id=str(user.id), result=result)
    return result


@router.get("/strategy-map", response_model=dict)
async def get_strategy_map(background_tasks: BackgroundTasks, user: CurrentUser, session: Session) -> dict[str, Any]:
    """Matrice de décision croisant scores alpha et phases de cycle ; récapitulatif Telegram s'il y a des achats ou
    des ventes."""
    result = await prediction_service.get_strategy_map(session, str(user.id))
    chat_id = _telegram_chat(user)
    if chat_id:
        summary = result.get("summary", {})
        if summary.get("buys", 0) > 0 or summary.get("sells", 0) > 0:
            background_tasks.add_task(
                send_strategy_recap,
                chat_id=chat_id,
                user_id=str(user.id),
                summary=summary,
                rows=result.get("rows", []),
                total_value=result.get("total_portfolio_value", 0),
            )
    return result


@router.get("/events", response_model=list)
async def get_market_events(user: CurrentUser) -> list[dict[str, Any]]:
    return await prediction_service.get_market_events()


@router.get("/backtest", response_model=dict)
async def get_portfolio_backtest(user: CurrentUser, session: Session, days: Days = 7) -> dict[str, Any]:
    """Prédictions passées confrontées aux cours réels : MAPE et justesse de direction par actif et au global."""
    return await prediction_service.get_portfolio_backtest(session, str(user.id), days)


@router.get("/track-record/{symbol}", response_model=dict)
async def get_track_record(
    symbol: str, user: CurrentUser, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> dict[str, Any]:
    return await prediction_service.get_track_record(symbol.upper(), limit, str(user.id))


@router.get("/planned-orders", response_model=list)
async def list_planned_orders(user: CurrentUser, session: Session) -> list[dict[str, Any]]:
    return await list_pending(session, user.id)


@router.post("/planned-orders", response_model=dict, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def create_planned_order(
    request: Request, data: PlannedOrderCreate, user: CurrentUser, session: Session
) -> dict[str, Any]:
    """Ordre planifié en attente, issu des suggestions de rééquilibrage, consommé par la page Signaux Alpha."""
    return await create_pending(session, user.id, data)


@router.patch("/planned-orders/{order_id}", response_model=dict)
async def update_planned_order(
    order_id: UUID, body: dict[Any, Any], user: CurrentUser, session: Session
) -> dict[str, Any]:
    """Passe un ordre en ``executed`` ou ``cancelled`` ; 404 si l'ordre n'appartient pas à l'utilisateur."""
    order = await find_owned(session, order_id, user.id)
    if not order:
        raise HTTPException(status_code=404, detail="Ordre non trouvé")
    return await apply_status(session, order, body.get("status"))
