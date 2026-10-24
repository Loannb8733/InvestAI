import logging
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from typing import Any

import numpy as np
from sqlalchemy import Row, and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import session_factory
from app.core.redis_client import cache_hyperparams
from app.domains.identity.models import User
from app.domains.market_data.history.reader import local_series
from app.domains.market_data.prices.service import price_feed
from app.domains.portfolio.models import Asset, AssetType, Portfolio
from app.domains.predictions.accuracy import record_outcome
from app.domains.predictions.models import PredictionLog
from app.domains.predictions.service import prediction_service
from app.domains.predictions.types import AnomalyDetection
from app.ml.drift_detector import check_drift
from app.ml.hyperparameter_tuner import tune_prophet, tune_xgboost
from app.services.telegram_service import telegram_service
from app.tasks.async_runner import run_async
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

ACCURACY_BATCH = 100
BOTTOM_CONFIDENCE = 0.80
BOTTOM_DISTANCE_PCT = 5.0


async def _held_assets(db: AsyncSession) -> Sequence[Row[str, AssetType]]:
    result = await db.execute(select(Asset.symbol, Asset.asset_type).where(Asset.quantity > 0).distinct())
    return result.all()


@celery_app.task(name="app.domains.predictions.tasks.run_daily_predictions")  # type: ignore[untyped-decorator]
def run_daily_predictions() -> None:
    """Prévision à 7 jours de chaque actif détenu, pour alimenter le journal des prédictions."""
    run_async(_run_daily_predictions())


async def _run_daily_predictions() -> None:
    async with session_factory() as db:
        assets = await _held_assets(db)
        logger.info("Running daily predictions for %d unique assets", len(assets))

        success = 0
        errors = 0
        for symbol, asset_type in assets:
            try:
                prediction = await prediction_service.get_price_prediction(symbol, asset_type, days_ahead=7)
                logger.info("Prediction for %s: trend=%s, model=%s", symbol, prediction.trend, prediction.model_used)
                success += 1
            except Exception as e:  # noqa: BLE001
                logger.error("Failed prediction for %s: %s", symbol, e)
                errors += 1

        logger.info("Daily predictions complete: %d success, %d errors", success, errors)


@celery_app.task(name="app.domains.predictions.tasks.detect_anomalies")  # type: ignore[untyped-decorator]
def detect_anomalies() -> None:
    """Détection d'anomalies de cours pour chaque utilisateur actif, avec alerte Telegram au mieux."""
    run_async(_detect_anomalies())


async def _alert_anomalies(user: User, user_id: str, anomalies: Sequence[AnomalyDetection]) -> None:
    for a in anomalies:
        logger.warning(
            "Anomaly detected for user %s: %s %s (%.1f%%)", user_id, a.symbol, a.anomaly_type, a.price_change_percent
        )
        try:
            if user.telegram_enabled and user.telegram_chat_id:
                await telegram_service.alert_anomaly(
                    symbol=a.symbol,
                    anomaly_type=a.anomaly_type,  # type: ignore[arg-type]
                    severity=a.severity,
                    description=a.description,
                    price_change_pct=a.price_change_percent,
                    chat_id=user.telegram_chat_id,
                    user_id=user_id,
                )
        except Exception as tg_err:  # noqa: BLE001
            logger.debug("Telegram anomaly alert failed: %s", tg_err)


async def _detect_anomalies() -> None:
    async with session_factory() as db:
        result = await db.execute(select(User).where(User.is_active.is_(True)))
        users = result.scalars().all()

        total_anomalies = 0
        for user in users:
            user_id = str(user.id)
            try:
                anomalies = await prediction_service.detect_anomalies(db, user_id)
                total_anomalies += len(anomalies)
                await _alert_anomalies(user, user_id, anomalies)
            except Exception as e:  # noqa: BLE001
                logger.error("Anomaly detection failed for user %s: %s", user_id, e)

        logger.info("Anomaly detection complete: %d anomalies found", total_anomalies)


@celery_app.task(name="app.domains.predictions.tasks.check_prediction_accuracy")  # type: ignore[untyped-decorator]
def check_prediction_accuracy() -> None:
    """Confronte les prédictions échues au cours réel : MAPE, direction, couverture de l'intervalle, alerte de dérive
    au-delà de 20 % (crypto) ou 10 % de MAPE."""
    run_async(_check_prediction_accuracy())


async def _check_prediction_accuracy() -> None:
    now = datetime.now(UTC)
    async with session_factory() as db:
        result = await db.execute(
            select(PredictionLog)
            .where(and_(PredictionLog.target_date <= now, PredictionLog.accuracy_checked.is_(None)))
            .limit(ACCURACY_BATCH)
        )
        logs = result.scalars().all()
        if not logs:
            logger.info("No predictions to check")
            return

        checked = 0
        drift_alerts = 0
        for log in logs:
            try:
                asset_type = AssetType(log.asset_type) if log.asset_type else AssetType.CRYPTO
                quote = await price_feed.quote(log.symbol, asset_type)
                if quote is None:
                    continue
                threshold = record_outcome(log, float(quote.price), now)
                if threshold is not None:
                    drift_alerts += 1
                    logger.warning(
                        "DRIFT ALERT: %s MAPE=%.1f%% ci_covered=%s (threshold=%.0f%%)",
                        log.symbol,
                        log.mape,
                        log.ci_covered,
                        threshold,
                    )
                checked += 1
            except Exception as e:  # noqa: BLE001
                logger.error("Failed to check prediction for %s: %s", log.symbol, e)

        await db.commit()
        logger.info("Prediction accuracy check: %d checked, %d drift alerts", checked, drift_alerts)


@celery_app.task(name="app.domains.predictions.tasks.check_data_drift")  # type: ignore[untyped-decorator]
def check_data_drift() -> None:
    """Dérive des données par PSI : 80 % les plus anciens de 180 jours de cours en référence, le reste en courant."""
    run_async(_check_data_drift())


async def _drift_status(symbol: str) -> str | None:
    prices = (await local_series(symbol, 180)).prices
    if not prices or len(prices) < 60:
        return None
    prices_arr = np.array(prices, dtype=float)
    split = max(int(len(prices_arr) * 0.8), 30)
    ref = prices_arr[:split]
    cur = prices_arr[split:]
    if len(cur) < 10:
        return None
    status: str = check_drift(ref, cur, symbol=symbol).status
    return status


async def _check_data_drift() -> None:
    async with session_factory() as db:
        assets = await _held_assets(db)

    drift_count = 0
    warning_count = 0
    for symbol, _asset_type in assets:
        try:
            status = await _drift_status(symbol)
            if status == "drift":
                drift_count += 1
            elif status == "warning":
                warning_count += 1
        except Exception as e:  # noqa: BLE001
            logger.error("Drift check failed for %s: %s", symbol, e)

    logger.info(
        "Data drift check complete: %d drift, %d warning, %d total assets", drift_count, warning_count, len(assets)
    )


@celery_app.task(name="app.domains.predictions.tasks.tune_hyperparameters")  # type: ignore[untyped-decorator]
def tune_hyperparameters() -> None:
    """Réglage hebdomadaire des hyperparamètres XGBoost et Prophet sur 90 jours, mis en cache par symbole."""
    run_async(_tune_hyperparameters())


async def _tune_hyperparameters() -> None:
    async with session_factory() as db:
        assets = await _held_assets(db)

    logger.info("Starting hyperparameter tuning for %d assets", len(assets))
    for symbol, _asset_type in assets:
        try:
            history = await local_series(symbol, 90)
            dates, prices = history.dates, history.prices
            if not prices or len(prices) < 40:
                continue

            xgb_params = tune_xgboost(prices, n_trials=20)
            await cache_hyperparams(symbol, "xgboost", xgb_params)
            if len(prices) >= 30:
                prophet_params = tune_prophet(prices, dates, n_trials=10)
                await cache_hyperparams(symbol, "prophet", prophet_params)

            logger.info("Tuned hyperparameters for %s", symbol)
        except Exception as e:  # noqa: BLE001
            logger.error("Tuning failed for %s: %s", symbol, e)


@celery_app.task(name="app.domains.predictions.tasks.check_bottom_zones")  # type: ignore[untyped-decorator]
def check_bottom_zones() -> None:
    """Alerte Telegram aux détenteurs d'un actif à moins de 5 % d'un creux estimé avec plus de 80 % de confiance."""
    run_async(_check_bottom_zones())


async def _holders(db: AsyncSession, symbol: str) -> Sequence[User]:
    result = await db.execute(
        select(User)
        .join(Portfolio, Portfolio.user_id == User.id)
        .join(Asset, Asset.portfolio_id == Portfolio.id)
        .where(
            Asset.symbol == symbol,
            Asset.quantity > 0,
            User.telegram_enabled.is_(True),
            User.telegram_chat_id.isnot(None),
        )
        .distinct()
    )
    return result.scalars().all()


async def _bottom_zone_alerts(
    db: AsyncSession, symbol: str, current_price: float, bottom: dict[str, Any]
) -> AsyncIterator[None]:
    confidence = bottom.get("confidence", 0)
    distance_pct = abs(bottom.get("distance_pct", 100))
    if not (confidence > BOTTOM_CONFIDENCE and distance_pct < BOTTOM_DISTANCE_PCT):
        return

    for holder in await _holders(db, symbol):
        sent = await telegram_service.alert_bottom_zone(
            symbol=symbol,
            current_price=current_price,
            estimated_bottom=bottom.get("estimated_price", 0),
            confidence=confidence,
            distance_pct=distance_pct,
            chat_id=holder.telegram_chat_id or "",
            user_id=str(holder.id),
        )
        if sent:
            yield
            logger.info(
                "Bottom zone alert sent for %s to user %s (conf=%.0f%%, dist=%.1f%%)",
                symbol,
                holder.id,
                confidence * 100,
                distance_pct,
            )


async def _check_bottom_zones() -> None:
    async with session_factory() as db:
        assets = await _held_assets(db)

        alerts_sent = 0
        for symbol, _asset_type in assets:
            try:
                prices = (await local_series(symbol, 180)).prices
                if not prices or len(prices) < 30:
                    continue
                current_price = prices[-1]
                estimate = prediction_service.estimate_top_bottom(
                    symbol=symbol, prices=prices, current_price=current_price
                )
                async for _ in _bottom_zone_alerts(db, symbol, current_price, estimate.get("next_bottom", {})):
                    alerts_sent += 1
            except Exception as e:  # noqa: BLE001
                logger.debug("Bottom zone check failed for %s: %s", symbol, e)

    logger.info("Bottom zone check complete: %d alerts sent", alerts_sent)
