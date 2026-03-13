"""Predictions endpoints for ML-based forecasting."""

import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.ml import adaptive_thresholds as at
from app.models.asset import AssetType
from app.models.user import User
from app.services.prediction_service import prediction_service

logger = logging.getLogger(__name__)

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

    model_config = {"protected_namespaces": ()}

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
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """Get market cycle analysis with regime detection for BTC and portfolio assets."""
    result = await prediction_service.get_market_cycle(db, str(current_user.id))

    # Send Telegram alert for critical cycle advice (bottom zone, concentration)
    if current_user.telegram_enabled and current_user.telegram_chat_id:
        critical_advice = [
            a
            for a in result.get("cycle_advice", [])
            if a.get("priority") in ("critical", "high") and a.get("action") in ("DCA", "DIVERSIFIER")
        ]
        if critical_advice:
            background_tasks.add_task(
                _send_cycle_alert,
                chat_id=current_user.telegram_chat_id,
                user_id=str(current_user.id),
                advice=critical_advice[0],
                regime=result.get("market_regime", {}).get("dominant_regime", "unknown")
                if result.get("market_regime")
                else "unknown",
                fear_greed=result.get("fear_greed"),
            )

        # Euphoria alert: BTC regime "top" + Fear & Greed > 80
        btc_regime = result.get("market_regime")
        fg = result.get("fear_greed")
        if btc_regime and btc_regime.get("dominant_regime") == "top" and fg is not None and fg > 80:
            portfolio_value = sum(a.get("value", 0) for a in result.get("per_asset", []))
            background_tasks.add_task(
                _send_euphoria_alert,
                chat_id=current_user.telegram_chat_id,
                user_id=str(current_user.id),
                fear_greed=fg,
                portfolio_value=portfolio_value,
            )

    return result


async def _send_cycle_alert(
    chat_id: str,
    user_id: str,
    advice: dict,
    regime: str,
    fear_greed: Optional[int],
) -> None:
    """Send Telegram alert for actionable cycle insight."""
    try:
        from app.services.telegram_service import telegram_service

        fg_str = f" | Fear & Greed: {fear_greed}" if fear_greed is not None else ""
        message = (
            f"🎯 <b>{advice['title']}</b>\n\n"
            f"{advice['description']}\n\n"
            f"📊 Régime: <b>{regime}</b>{fg_str}\n"
            f"Action: <b>{advice['action']}</b>"
        )

        await telegram_service.send_smart_alert(
            message=message,
            chat_id=chat_id,
            user_id=user_id,
            priority="high" if advice.get("action") == "DIVERSIFIER" else "normal",
            symbol="MARKET",
            alert_type="CYCLE_INSIGHT",
        )
    except Exception as exc:
        logger.warning("Telegram cycle alert failed: %s", exc)


async def _send_euphoria_alert(
    chat_id: str,
    user_id: str,
    fear_greed: int,
    portfolio_value: float,
) -> None:
    """Send Telegram alert when BTC enters euphoria zone (top + F&G > 80)."""
    try:
        from app.services.telegram_service import telegram_service

        pv_str = f"{portfolio_value:,.0f} €".replace(",", " ")
        message = (
            "⚠️ <b>Alerte Cycle : Zone d'Euphorie</b>\n\n"
            "Le marché entre en zone d'Euphorie (BTC en régime Sommet, "
            f"Fear & Greed à {fear_greed}/100).\n\n"
            f"💰 Votre portefeuille : <b>{pv_str}</b>\n\n"
            "📌 Envisagez de sécuriser une partie de vos gains :\n"
            "• Prise de profits partielle (20-30%)\n"
            "• Stop-loss protecteurs\n"
            "• Évitez les nouveaux achats"
        )

        await telegram_service.send_smart_alert(
            message=message,
            chat_id=chat_id,
            user_id=user_id,
            priority="high",
            symbol="BTC",
            alert_type="EUPHORIA_WARNING",
        )
    except Exception as exc:
        logger.warning("Telegram euphoria alert failed: %s", exc)


@router.get("/top-alpha", response_model=dict)
async def get_top_alpha(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """Detect the held asset with the highest short-term alpha potential."""
    result = await prediction_service.get_top_alpha_asset(db, str(current_user.id))

    # Telegram alert if score > 85 and not over-concentrated
    top = result.get("top_alpha")
    total_value = result.get("total_portfolio_value", 0)
    if (
        top
        and top.get("score", 0) > 85
        and not result.get("concentration_risk")
        and current_user.telegram_enabled
        and current_user.telegram_chat_id
    ):
        # Compute suggested order for keyboard callback
        strategy_data = await prediction_service.get_strategy_map(db, str(current_user.id))
        order_eur = 0.0
        for row in strategy_data.get("rows", []):
            if row["symbol"] == top["symbol"]:
                order_eur = round(total_value * abs(row.get("impact_pct", 0)) / 100, 2)
                break

        background_tasks.add_task(
            _send_alpha_alert,
            chat_id=current_user.telegram_chat_id,
            user_id=str(current_user.id),
            symbol=top["symbol"],
            score=top["score"],
            predicted_pct=top.get("predicted_7d_pct", 0),
            reasons=top.get("reasons", []),
            order_eur=order_eur,
        )

    # Telegram alert if any asset exceeds 60% concentration
    if current_user.telegram_enabled and current_user.telegram_chat_id:
        for scored in result.get("all_scores", []):
            if scored.get("weight_pct", 0) > 60:
                background_tasks.add_task(
                    _send_concentration_alert,
                    chat_id=current_user.telegram_chat_id,
                    user_id=str(current_user.id),
                    symbol=scored["symbol"],
                    weight_pct=scored["weight_pct"],
                )

    return result


async def _send_alpha_alert(
    chat_id: str,
    user_id: str,
    symbol: str,
    score: float,
    predicted_pct: float,
    reasons: list,
    order_eur: float = 0.0,
) -> None:
    """Send Telegram alert for high-alpha signal with interactive buttons."""
    try:
        from app.services.telegram_service import telegram_service

        reason_lines = "\n".join(f"  • {r['label']}: {r['detail']}" for r in reasons[:3])
        sign = "+" if predicted_pct >= 0 else ""
        message = (
            f"🚀 <b>Signal Alpha : {symbol}</b>\n\n"
            f"Score: <b>{score:.0f}/100</b> — configuration de surperformance.\n"
            f"Potentiel 7j: <b>{sign}{predicted_pct:.1f}%</b>\n"
            f"Ordre suggéré: <b>{order_eur:,.2f} €</b>\n\n"
            f"📊 Raisons:\n{reason_lines}"
        )

        # Build InlineKeyboard with action buttons
        keyboard = telegram_service.build_alpha_keyboard(user_id, symbol, order_eur)

        await telegram_service.send_smart_alert(
            message=message,
            chat_id=chat_id,
            user_id=user_id,
            priority="high",
            symbol=symbol,
            alert_type="TOP_ALPHA",
            reply_markup=keyboard,
        )
    except Exception as exc:
        logger.warning("Telegram alpha alert failed for %s: %s", symbol, exc)


async def _send_concentration_alert(
    chat_id: str,
    user_id: str,
    symbol: str,
    weight_pct: float,
) -> None:
    """Send Telegram alert when an asset exceeds 60% portfolio concentration."""
    try:
        from app.services.telegram_service import telegram_service

        message = (
            f"⚠️ <b>Risque de Concentration : {symbol}</b>\n\n"
            f"Poids dans le portefeuille : <b>{weight_pct:.1f}%</b>\n"
            f"Seuil d'alerte : 60%\n\n"
            f"Envisagez de diversifier pour réduire le risque."
        )

        await telegram_service.send_smart_alert(
            message=message,
            chat_id=chat_id,
            user_id=user_id,
            priority="high",
            symbol=symbol,
            alert_type="CONCENTRATION_RISK",
        )
    except Exception as exc:
        logger.warning("Telegram concentration alert failed for %s: %s", symbol, exc)


@router.get("/reconciliation-report", response_model=dict)
async def get_reconciliation_report(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """Run a reconciliation check and send Telegram summary.

    Fetches top-alpha + market-cycle, verifies parity, and optionally
    sends a Telegram message summarising the reconciliation status.
    Also computes the écart (delta) between Alpha total and Dashboard total
    to confirm price source synchronization.
    """
    alpha_data = await prediction_service.get_top_alpha_asset(db, str(current_user.id))
    cycle_data = await prediction_service.get_market_cycle(db, str(current_user.id))

    top = alpha_data.get("top_alpha")
    alpha_total = alpha_data.get("total_portfolio_value", 0)
    market_regime = cycle_data.get("market_regime", {})
    regime_label = market_regime.get("dominant_regime", "unknown") if market_regime else "unknown"
    fear_greed = cycle_data.get("fear_greed")

    # Compute Dashboard total from per-asset cycle values (same price source)
    dashboard_total = sum(a.get("value", 0) for a in cycle_data.get("per_asset", []))
    ecart = round(abs(alpha_total - dashboard_total), 2)

    report = {
        "reconciliation": "ok" if ecart < 0.01 else "drift",
        "alpha_total_value": alpha_total,
        "dashboard_total_value": round(dashboard_total, 2),
        "ecart_eur": ecart,
        "total_portfolio_value": alpha_total,
        "market_regime": regime_label,
        "fear_greed": fear_greed,
        "top_alpha": top,
    }

    # Divergence validation for top asset
    if top and top.get("divergence_log"):
        dlog = top["divergence_log"]
        report["divergence_validation"] = {
            "symbol": top["symbol"],
            **dlog,
            "valid": dlog.get("is_bullish_divergence", False),
        }

    # Send Telegram reconciliation summary
    if current_user.telegram_enabled and current_user.telegram_chat_id and top:
        background_tasks.add_task(
            _send_reconciliation_report,
            chat_id=current_user.telegram_chat_id,
            user_id=str(current_user.id),
            top=top,
            total_value=alpha_total,
            regime=regime_label,
            fear_greed=fear_greed,
            ecart=ecart,
        )

    return report


async def _send_reconciliation_report(
    chat_id: str,
    user_id: str,
    top: dict,
    total_value: float,
    regime: str,
    fear_greed: Optional[int],
    ecart: float = 0.0,
) -> None:
    """Send Telegram reconciliation summary."""
    try:
        from app.services.telegram_service import telegram_service

        symbol = top["symbol"]
        score = top.get("score", 0)
        pct = top.get("predicted_7d_pct", 0)
        source = top.get("prediction_source", "none")
        sign = "+" if pct >= 0 else ""
        pv_str = f"{total_value:,.0f} €".replace(",", " ")
        fg_str = f" | F&G: {fear_greed}" if fear_greed is not None else ""

        # Divergence details
        dlog = top.get("divergence_log", {})
        div_section = ""
        if dlog.get("rsi_t") is not None and dlog.get("rsi_t7") is not None:
            div_label = "✅ Confirmée" if dlog.get("is_bullish_divergence") else "❌ Non détectée"
            div_section = (
                f"\n📉 <b>Divergence RSI</b>: {div_label}\n"
                f"  Prix t-7: {dlog['price_t7']} → t: {dlog['price_t']} ({dlog['price_change_7d_pct']:+.2f}%)\n"
                f"  RSI  t-7: {dlog['rsi_t7']} → t: {dlog['rsi_t']}"
            )

        ecart_str = f"{ecart:.2f} €"
        ecart_icon = "✅" if ecart < 0.01 else "⚠️"

        message = (
            f"✅ <b>InvestAI Synchronisé</b>\n\n"
            f"🏆 Top Alpha : <b>{symbol}</b> ({sign}{pct:.2f}%)\n"
            f"🎯 Score: <b>{score:.0f}/100</b> (source: {source})\n"
            f"🌍 Phase de marché : <b>{regime}</b>{fg_str}\n"
            f"💰 Portefeuille : <b>{pv_str}</b>\n"
            f"{ecart_icon} Écart Dashboard : <b>{ecart_str}</b>"
            f"{div_section}"
        )

        await telegram_service.send_smart_alert(
            message=message,
            chat_id=chat_id,
            user_id=user_id,
            priority="normal",
            symbol=symbol,
            alert_type="RECONCILIATION_REPORT",
        )
    except Exception as exc:
        logger.warning("Telegram reconciliation report failed: %s", exc)


@router.get("/validate-signal", response_model=dict)
async def validate_signal(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """Validate the top Alpha signal with Monte Carlo risk impact analysis.

    1. Identifies the top alpha asset (score > 85).
    2. Computes the suggested order from the strategy matrix.
    3. Runs Monte Carlo BEFORE and AFTER the purchase to compare prob_ruin.
    4. Sends a detailed Telegram report.
    """
    from app.services.analytics_service import analytics_service
    from app.services.smart_insights_service import smart_insights_service

    # ── 1. Top Alpha ──
    alpha_data = await prediction_service.get_top_alpha_asset(db, str(current_user.id))
    if not alpha_data.get("found"):
        return {"validated": False, "reason": "Aucun actif scoré disponible."}

    top = alpha_data["top_alpha"]
    symbol = top["symbol"]
    total_value = alpha_data.get("total_portfolio_value", 0)
    concentration_risk = alpha_data.get("concentration_risk", False)

    # ── 2. Strategy matrix action ──
    strategy_data = await prediction_service.get_strategy_map(db, str(current_user.id))
    action = "OBSERVER"
    impact_pct = 0.0
    regime = "unknown"
    for row in strategy_data.get("rows", []):
        if row["symbol"] == top["symbol"]:
            action = row["action"]
            impact_pct = row["impact_pct"]
            regime = row["regime"]
            break

    order_eur = round(total_value * abs(impact_pct) / 100, 2) if total_value > 0 else 0.0

    # Post-purchase weight check
    current_weight = top.get("weight_pct", 0)
    current_value = top.get("value", 0)
    new_weight = round((current_value + order_eur) / (total_value + order_eur) * 100, 1) if total_value > 0 else 0
    weight_overflow = new_weight > 50

    # ── 3. Monte Carlo before/after ──
    uid = str(current_user.id)
    # Derive vol_regime from market regime for regime-aware Monte Carlo
    _vol_regime = await smart_insights_service.get_current_vol_regime(db, uid)

    mc_before = await analytics_service.monte_carlo(
        db,
        uid,
        horizon_days=90,
        num_simulations=2000,
        vol_regime=_vol_regime,
    )
    prob_ruin_before = mc_before.prob_ruin

    # Simulate "after" by adding the order amount to the target asset's weight
    mc_after = await analytics_service.monte_carlo(
        db,
        uid,
        horizon_days=90,
        num_simulations=2000,
        contribution={symbol: order_eur} if order_eur > 0 else None,
        vol_regime=_vol_regime,
    )
    prob_ruin_after = mc_after.prob_ruin

    # Determine risk impact label
    ruin_delta = prob_ruin_after - prob_ruin_before
    if ruin_delta < -1:
        risk_label = "Diminuée"
    elif ruin_delta > 1:
        risk_label = "Augmentée"
    else:
        risk_label = "Stable"

    # ── 4. BTC correlation from alpha scoring reasons ──
    btc_correlation = None
    for reason in top.get("reasons", []):
        if "corrélation" in reason.get("label", "").lower() or "décorr" in reason.get("label", "").lower():
            detail = reason.get("detail", "")
            # Extract Spearman value from detail like "Spearman 7j = 0.12"
            import re

            match = re.search(r"[-+]?\d*\.?\d+", detail.split("=")[-1] if "=" in detail else detail)
            if match:
                btc_correlation = float(match.group())
            break

    # ── 5. Concentration rebalance suggestion ──
    rebalance_suggestion = None
    if new_weight > 60:
        # Find the worst-performing asset to suggest trimming
        all_scores = alpha_data.get("all_scores", [])
        candidates = [s for s in all_scores if s["symbol"] != symbol and s.get("value", 0) > 0]
        if candidates:
            worst = min(candidates, key=lambda s: s.get("score", 100))
            trim_eur = round(order_eur * 0.5, 2)  # Suggest trimming half the order amount
            rebalance_suggestion = {
                "trim_symbol": worst["symbol"],
                "trim_eur": trim_eur,
                "reason": f"Réduire {worst['symbol']} (score {worst.get('score', 0):.0f}) pour financer l'achat",
            }

    # ── 6. Build reconciliation écart ──
    cycle_data = await prediction_service.get_market_cycle(db, uid)
    dashboard_total = sum(a.get("value", 0) for a in cycle_data.get("per_asset", []))
    ecart = round(abs(total_value - dashboard_total), 2)

    # ── 7. Build response ──
    predicted_pct = top.get("predicted_7d_pct", 0)
    score = top.get("score", 0)

    validated = score > 85 and impact_pct > 0 and not weight_overflow
    concentration_status = "ALERTE" if new_weight > 60 else ("VIGILANCE" if new_weight > 50 else "SÉCURISÉE")

    result = {
        "validated": validated,
        "symbol": symbol,
        "score": round(score, 1),
        "predicted_7d_pct": predicted_pct,
        "prediction_source": top.get("prediction_source", "none"),
        "regime": regime,
        "action": action,
        "order_eur": order_eur,
        "impact_pct": impact_pct,
        "current_weight_pct": current_weight,
        "post_purchase_weight_pct": new_weight,
        "weight_overflow": weight_overflow,
        "concentration_risk": concentration_risk,
        "concentration_status": concentration_status,
        "btc_correlation": btc_correlation,
        "prob_ruin_before": round(prob_ruin_before, 2),
        "prob_ruin_after": round(prob_ruin_after, 2),
        "risk_impact": risk_label,
        "mc_before": {
            "expected_return": mc_before.expected_return,
            "prob_positive": mc_before.prob_positive,
            "prob_loss_10": mc_before.prob_loss_10,
        },
        "mc_after": {
            "expected_return": mc_after.expected_return,
            "prob_positive": mc_after.prob_positive,
            "prob_loss_10": mc_after.prob_loss_10,
        },
        "total_portfolio_value": total_value,
        "ecart_eur": ecart,
        "reasons": top.get("reasons", []),
        "divergence_log": top.get("divergence_log"),
        "rebalance_suggestion": rebalance_suggestion,
    }

    # ── 6. Telegram report ──
    if current_user.telegram_enabled and current_user.telegram_chat_id:
        background_tasks.add_task(
            _send_signal_report,
            chat_id=current_user.telegram_chat_id,
            user_id=str(current_user.id),
            result=result,
        )

    return result


async def _send_signal_report(
    chat_id: str,
    user_id: str,
    result: dict,
) -> None:
    """Send detailed Telegram report for a validated (or rejected) Alpha signal."""
    try:
        from app.services.telegram_service import telegram_service

        symbol = result["symbol"]
        score = result["score"]
        pct = result["predicted_7d_pct"]
        sign = "+" if pct >= 0 else ""
        order = result["order_eur"]
        risk_label = result["risk_impact"]
        ecart = result["ecart_eur"]
        validated = result["validated"]
        prob_before = result["prob_ruin_before"]
        prob_after = result["prob_ruin_after"]
        conc_status = result.get("concentration_status", "SÉCURISÉE")
        btc_corr = result.get("btc_correlation")

        status_icon = "✅" if validated else "⚠️"
        status_text = "Simulation Alpha Terminée" if validated else "Signal Alpha Non Validé"
        verdict = f"Achat validé pour {order:.2f} €" if validated else "Achat non recommandé"

        # BTC correlation line
        corr_line = ""
        if btc_corr is not None:
            corr_label = "faible" if abs(btc_corr) < 0.3 else ("modérée" if abs(btc_corr) < 0.6 else "forte")
            corr_line = f"🔗 Corrélation BTC : <b>{btc_corr:.2f}</b> ({corr_label})\n"

        # Concentration icon
        conc_icon = "✅" if conc_status == "SÉCURISÉE" else ("⚠️" if conc_status == "VIGILANCE" else "🚨")

        reason_lines = "\n".join(f"  • {r['label']}: {r['detail']}" for r in result.get("reasons", [])[:3])

        message = (
            f"{status_icon} <b>{status_text} : {symbol}</b>\n\n"
            f"📊 Score : <b>{score:.0f}/100</b> | Potentiel : <b>{sign}{pct:.1f}%</b>\n"
            f"{corr_line}"
            f"🛡️ Risque : Prob. Ruine {prob_before:.1f}% → {prob_after:.1f}% (<b>{risk_label}</b>)\n"
            f"{conc_icon} Concentration : <b>{conc_status}</b> ({result.get('post_purchase_weight_pct', 0):.1f}%)\n"
            f"🚀 Verdict : <b>{verdict}</b>\n"
            f"✅ Précision Dashboard : <b>{ecart:.2f} €</b> d'écart\n"
        )
        if reason_lines:
            message += f"\n📊 Raisons:\n{reason_lines}"

        # Rebalance suggestion
        rebal = result.get("rebalance_suggestion")
        if rebal:
            message += (
                f"\n\n💡 Suggestion : {rebal['reason']}" f" (−{rebal['trim_eur']:.2f} € sur {rebal['trim_symbol']})"
            )

        await telegram_service.send_smart_alert(
            message=message,
            chat_id=chat_id,
            user_id=user_id,
            priority="high" if validated else "normal",
            symbol=symbol,
            alert_type="SIGNAL_VALIDATED",
        )
    except Exception as exc:
        logger.warning("Telegram signal report failed for %s: %s", result.get("symbol"), exc)


@router.get("/strategy-map", response_model=dict)
async def get_strategy_map(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """Build a strategy decision table crossing Alpha scores with Cycle phases."""
    result = await prediction_service.get_strategy_map(db, str(current_user.id))

    # Telegram weekly recap — send if user has Telegram + there are actionable items
    if current_user.telegram_enabled and current_user.telegram_chat_id:
        summary = result.get("summary", {})
        if summary.get("buys", 0) > 0 or summary.get("sells", 0) > 0:
            background_tasks.add_task(
                _send_strategy_recap,
                chat_id=current_user.telegram_chat_id,
                user_id=str(current_user.id),
                summary=summary,
                rows=result.get("rows", []),
                total_value=result.get("total_portfolio_value", 0),
            )

    return result


async def _send_strategy_recap(
    chat_id: str,
    user_id: str,
    summary: dict,
    rows: list,
    total_value: float,
) -> None:
    """Send Telegram recap of strategy recommendations."""
    try:
        from app.services.telegram_service import telegram_service

        buy_rows = [r for r in rows if "ACHAT" in r["action"] or r["action"] == "DCA"]
        sell_rows = [r for r in rows if "VENDRE" in r["action"] or "PROFITS" in r["action"] or "ALLÉGER" in r["action"]]

        lines = []
        if buy_rows:
            buy_syms = ", ".join(r["symbol"] for r in buy_rows[:3])
            lines.append(f"🟢 {summary['buys']} Achat(s) suggéré(s) : {buy_syms}")
        if sell_rows:
            sell_syms = ", ".join(r["symbol"] for r in sell_rows[:3])
            lines.append(f"🔴 {summary['sells']} Vente(s) conseillée(s) : {sell_syms}")
        if summary.get("holds", 0) > 0:
            lines.append(f"⚪ {summary['holds']} position(s) à maintenir")

        pv_str = f"{total_value:,.0f} €".replace(",", " ")
        message = "📅 <b>Stratégie Hebdo</b>\n\n" + "\n".join(lines) + f"\n\n💰 Portefeuille : <b>{pv_str}</b>"

        await telegram_service.send_smart_alert(
            message=message,
            chat_id=chat_id,
            user_id=user_id,
            priority="normal",
            symbol="STRATEGY",
            alert_type="WEEKLY_STRATEGY",
        )
    except Exception as exc:
        logger.warning("Telegram strategy recap failed: %s", exc)


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


# ── Planned Orders ──────────────────────────────────────────────


@router.get("/planned-orders", response_model=list)
async def list_planned_orders(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List pending planned orders for the current user."""
    from sqlalchemy import select

    from app.models.planned_order import PlannedOrder, PlannedOrderStatus

    result = await db.execute(
        select(PlannedOrder)
        .where(
            PlannedOrder.user_id == current_user.id,
            PlannedOrder.status == PlannedOrderStatus.PENDING,
        )
        .order_by(PlannedOrder.created_at.desc())
    )
    orders = result.scalars().all()

    return [
        {
            "id": str(o.id),
            "symbol": o.symbol,
            "action": o.action,
            "order_eur": o.order_eur,
            "alpha_score": o.alpha_score,
            "regime": o.regime,
            "prob_ruin_before": o.prob_ruin_before,
            "prob_ruin_after": o.prob_ruin_after,
            "source": o.source,
            "status": o.status.value if o.status else "pending",
            "notes": o.notes,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        }
        for o in orders
    ]


@router.patch("/planned-orders/{order_id}", response_model=dict)
async def update_planned_order(
    order_id: str,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a planned order status (executed/cancelled)."""
    from sqlalchemy import select

    from app.models.planned_order import PlannedOrder, PlannedOrderStatus

    result = await db.execute(
        select(PlannedOrder).where(
            PlannedOrder.id == order_id,
            PlannedOrder.user_id == current_user.id,
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Ordre non trouvé")

    new_status = body.get("status")
    if new_status in ("executed", "cancelled"):
        order.status = PlannedOrderStatus(new_status)
        await db.commit()

    return {"id": str(order.id), "status": order.status.value}
