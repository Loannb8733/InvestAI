"""ML prediction tasks."""

import asyncio
import logging

from sqlalchemy import select

from app.core.database import AsyncSessionLocal as async_session_factory
from app.models.asset import Asset
from app.services.prediction_service import prediction_service
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def run_async(coro):
    """Run an async coroutine from sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="app.tasks.predictions.run_daily_predictions")
def run_daily_predictions():
    """Run daily price predictions for all tracked assets."""
    run_async(_run_daily_predictions())


async def _run_daily_predictions():
    """Async implementation of daily predictions."""
    async with async_session_factory() as db:
        # Get all unique symbols across all portfolios
        result = await db.execute(
            select(Asset.symbol, Asset.asset_type)
            .where(Asset.quantity > 0)
            .distinct()
        )
        assets = result.all()

        logger.info("Running daily predictions for %d unique assets", len(assets))

        success = 0
        errors = 0

        for symbol, asset_type in assets:
            try:
                prediction = await prediction_service.get_price_prediction(
                    symbol, asset_type, days_ahead=7
                )
                logger.info(
                    "Prediction for %s: trend=%s, model=%s",
                    symbol, prediction.trend, prediction.model_used,
                )
                success += 1
            except Exception as e:
                logger.error("Failed prediction for %s: %s", symbol, e)
                errors += 1

        logger.info(
            "Daily predictions complete: %d success, %d errors",
            success, errors,
        )


@celery_app.task(name="app.tasks.predictions.predict_price")
def predict_price(symbol: str, asset_type: str, horizon_days: int = 7):
    """Generate price prediction for a specific asset."""
    from app.models.asset import AssetType

    type_map = {
        "crypto": AssetType.CRYPTO,
        "stock": AssetType.STOCK,
        "etf": AssetType.ETF,
    }

    at = type_map.get(asset_type)
    if not at:
        logger.error("Unknown asset type: %s", asset_type)
        return None

    result = run_async(
        prediction_service.get_price_prediction(symbol, at, horizon_days)
    )

    return {
        "symbol": result.symbol,
        "trend": result.trend,
        "trend_strength": result.trend_strength,
        "model_used": result.model_used,
        "predictions_count": len(result.predictions),
    }


@celery_app.task(name="app.tasks.predictions.detect_anomalies")
def detect_anomalies():
    """Detect price anomalies across all users' assets."""
    run_async(_detect_anomalies())


async def _detect_anomalies():
    """Async implementation of anomaly detection."""
    from app.models.user import User

    async with async_session_factory() as db:
        result = await db.execute(
            select(User.id).where(User.is_active.is_(True))
        )
        user_ids = [str(uid) for (uid,) in result.all()]

        total_anomalies = 0

        for user_id in user_ids:
            try:
                anomalies = await prediction_service.detect_anomalies(db, user_id)
                total_anomalies += len(anomalies)

                for anomaly in anomalies:
                    logger.warning(
                        "Anomaly detected for user %s: %s %s (%.1f%%)",
                        user_id, anomaly.symbol, anomaly.anomaly_type,
                        anomaly.price_change_percent,
                    )
            except Exception as e:
                logger.error("Anomaly detection failed for user %s: %s", user_id, e)

        logger.info("Anomaly detection complete: %d anomalies found", total_anomalies)


@celery_app.task(name="app.tasks.predictions.check_prediction_accuracy")
def check_prediction_accuracy():
    """Check yesterday's predictions against actual prices."""
    run_async(_check_prediction_accuracy())


async def _check_prediction_accuracy():
    """Compare past predictions with actual prices to monitor drift."""
    from datetime import datetime, timedelta
    from sqlalchemy import select, and_
    from app.models.prediction_log import PredictionLog
    from app.services.price_service import PriceService

    price_service = PriceService()
    now = datetime.utcnow()

    async with async_session_factory() as db:
        # Find predictions whose target_date has passed but haven't been checked
        result = await db.execute(
            select(PredictionLog).where(
                and_(
                    PredictionLog.target_date <= now,
                    PredictionLog.accuracy_checked.is_(None),
                )
            ).limit(100)
        )
        logs = result.scalars().all()

        if not logs:
            logger.info("No predictions to check")
            return

        checked = 0
        drift_alerts = 0

        for log in logs:
            try:
                # Get actual price
                from app.models.asset import AssetType
                asset_type = AssetType(log.asset_type) if log.asset_type else AssetType.CRYPTO

                if asset_type == AssetType.CRYPTO:
                    data = await price_service.get_crypto_price(log.symbol)
                else:
                    data = await price_service.get_stock_price(log.symbol)

                if not data or "price" not in data:
                    continue

                actual_price = float(data["price"])
                log.actual_price = actual_price
                log.accuracy_checked = now

                if actual_price > 0:
                    log.mape = abs(log.predicted_price - actual_price) / actual_price * 100

                    # Alert if MAPE too high
                    threshold = 20.0 if log.asset_type == "crypto" else 10.0
                    if log.mape > threshold:
                        drift_alerts += 1
                        logger.warning(
                            "DRIFT ALERT: %s prediction MAPE=%.1f%% (threshold=%.0f%%)",
                            log.symbol, log.mape, threshold,
                        )

                checked += 1
            except Exception as e:
                logger.error("Failed to check prediction for %s: %s", log.symbol, e)

        await db.commit()
        logger.info(
            "Prediction accuracy check: %d checked, %d drift alerts",
            checked, drift_alerts,
        )


@celery_app.task(name="app.tasks.predictions.tune_hyperparameters")
def tune_hyperparameters():
    """Weekly hyperparameter tuning for ML models."""
    run_async(_tune_hyperparameters())


async def _tune_hyperparameters():
    """Async hyperparameter tuning."""
    from app.ml.hyperparameter_tuner import tune_xgboost, tune_prophet
    from app.ml.historical_data import HistoricalDataFetcher
    from app.core.redis_client import cache_hyperparams

    fetcher = HistoricalDataFetcher()

    async with async_session_factory() as db:
        result = await db.execute(
            select(Asset.symbol, Asset.asset_type)
            .where(Asset.quantity > 0)
            .distinct()
        )
        assets = result.all()

    logger.info("Starting hyperparameter tuning for %d assets", len(assets))

    for symbol, asset_type in assets:
        try:
            dates, prices = await fetcher.get_history(symbol, asset_type.value, days=90)
            if not prices or len(prices) < 40:
                continue

            # Tune XGBoost
            xgb_params = tune_xgboost(prices, n_trials=20)
            await cache_hyperparams(symbol, "xgboost", xgb_params)

            # Tune Prophet
            if len(prices) >= 30:
                prophet_params = tune_prophet(prices, dates, n_trials=10)
                await cache_hyperparams(symbol, "prophet", prophet_params)

            logger.info("Tuned hyperparameters for %s", symbol)
        except Exception as e:
            logger.error("Tuning failed for %s: %s", symbol, e)
