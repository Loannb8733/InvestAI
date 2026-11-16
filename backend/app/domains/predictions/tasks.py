import asyncio
import logging
from collections.abc import Sequence
from datetime import UTC, datetime

import numpy as np
from sqlalchemy import Row, and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import session_factory
from app.core.redis_client import cache_hyperparams
from app.domains.identity.models import User
from app.domains.market_data.history.reader import local_history, local_series
from app.domains.notifications.telegram.client import telegram_service
from app.domains.portfolio.classification import is_stablecoin
from app.domains.portfolio.models import Asset, AssetType
from app.domains.predictions.accuracy import LOOKBACK_DAYS, SETTLE_DELAY, give_up, price_on, record_outcome
from app.domains.predictions.bottom_zones import bottom_zone_alerts
from app.domains.predictions.forecast import PRECOMPUTED_TTL_S
from app.domains.predictions.models import PredictionLog
from app.domains.predictions.service import prediction_service
from app.domains.predictions.types import AnomalyDetection
from app.ml.drift_detector import check_drift
from app.ml.hyperparameter_tuner import tune_prophet, tune_xgboost
from app.tasks.async_runner import run_async
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

ACCURACY_BATCH = 100
BATCH_HORIZONS = (7, 14, 30)
BATCH_TIME_LIMIT_S = 3600
TUNING_TIME_LIMIT_S = 7200


async def _held_assets(db: AsyncSession) -> Sequence[Row[str, AssetType]]:
    result = await db.execute(select(Asset.symbol, Asset.asset_type).where(Asset.quantity > 0).distinct())
    return result.all()


@celery_app.task(  # type: ignore[untyped-decorator]
    name="app.domains.predictions.tasks.run_daily_predictions", time_limit=BATCH_TIME_LIMIT_S
)
def run_daily_predictions() -> None:
    """Calcul par lots des prévisions à 7, 14 et 30 jours de chaque actif détenu hors stablecoins : mises en cache
    pour la journée, servies telles quelles aux pages, et journalisées pour le suivi de précision."""
    run_async(_run_daily_predictions())


async def _run_daily_predictions() -> dict[str, int]:
    async with session_factory() as db:
        assets = [(s, t) for s, t in await _held_assets(db) if not is_stablecoin(s)]
    logger.info("Running batch predictions for %d unique assets", len(assets))

    success = 0
    errors = 0
    for symbol, asset_type in assets:
        for days in BATCH_HORIZONS:
            try:
                prediction = await prediction_service.get_price_prediction(
                    symbol, asset_type, days, refresh=True, cache_ttl=PRECOMPUTED_TTL_S
                )
                logger.info("Prediction %s %dd: model=%s", symbol, days, prediction.model_used)
                success += 1
            except Exception as e:  # noqa: BLE001
                logger.error("Failed prediction for %s %dd: %s", symbol, days, e)
                errors += 1

    logger.info("Batch predictions complete: %d success, %d errors", success, errors)
    return {"assets": len(assets), "success": success, "errors": errors}


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
    """Confronte les prédictions échues au cours enregistré à leur date cible : MAPE, direction, couverture de
    l'intervalle, alerte de dérive au-delà de 20 % (crypto) ou 10 % de MAPE. Une prédiction n'est contrôlée qu'un
    jour après sa date cible, quand le cours de ce jour est définitif ; sans cours une semaine plus tard, elle est
    close sans mesure. Échéance et date de contrôle sont stockées en UTC sans fuseau."""
    run_async(_check_prediction_accuracy())


async def _check_prediction_accuracy() -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    async with session_factory() as db:
        result = await db.execute(
            select(PredictionLog)
            .where(and_(PredictionLog.target_date <= now - SETTLE_DELAY, PredictionLog.accuracy_checked.is_(None)))
            .order_by(PredictionLog.target_date)
            .limit(ACCURACY_BATCH)
        )
        logs = result.scalars().all()
        if not logs:
            logger.info("No predictions to check")
            return

        oldest = min(log.target_date for log in logs if log.target_date is not None)
        history = await local_history({log.symbol for log in logs}, (now - oldest).days + LOOKBACK_DAYS + 1, db)
        checked = 0
        drift_alerts = 0
        expired = 0
        for log in logs:
            try:
                actual = price_on(history[log.symbol.upper()], log.target_date.date()) if log.target_date else None
                if actual is None:
                    expired += give_up(log, now)
                    continue
                threshold = record_outcome(log, actual, now)
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
        logger.info(
            "Prediction accuracy check: %d checked, %d drift alerts, %d closed without price",
            checked,
            drift_alerts,
            expired,
        )


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


@celery_app.task(  # type: ignore[untyped-decorator]
    name="app.domains.predictions.tasks.tune_hyperparameters", time_limit=TUNING_TIME_LIMIT_S
)
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

            xgb_params = await asyncio.to_thread(tune_xgboost, prices, 20)
            await cache_hyperparams(symbol, "xgboost", xgb_params)
            if len(prices) >= 30:
                prophet_params = await asyncio.to_thread(tune_prophet, prices, dates, 10)
                await cache_hyperparams(symbol, "prophet", prophet_params)

            logger.info("Tuned hyperparameters for %s", symbol)
        except Exception as e:  # noqa: BLE001
            logger.error("Tuning failed for %s: %s", symbol, e)


@celery_app.task(name="app.domains.predictions.tasks.check_bottom_zones")  # type: ignore[untyped-decorator]
def check_bottom_zones() -> None:
    """Alerte Telegram aux détenteurs d'un actif à moins de 5 % d'un creux estimé avec plus de 80 % de confiance."""
    run_async(_check_bottom_zones())


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
                async for _ in bottom_zone_alerts(db, symbol, current_price, estimate.get("next_bottom", {})):
                    alerts_sent += 1
            except Exception as e:  # noqa: BLE001
                logger.debug("Bottom zone check failed for %s: %s", symbol, e)

    logger.info("Bottom zone check complete: %d alerts sent", alerts_sent)
