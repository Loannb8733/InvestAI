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
        result = await db.execute(select(Asset.symbol, Asset.asset_type).where(Asset.quantity > 0).distinct())
        assets = result.all()

        logger.info("Running daily predictions for %d unique assets", len(assets))

        success = 0
        errors = 0

        for symbol, asset_type in assets:
            try:
                prediction = await prediction_service.get_price_prediction(symbol, asset_type, days_ahead=7)
                logger.info(
                    "Prediction for %s: trend=%s, model=%s",
                    symbol,
                    prediction.trend,
                    prediction.model_used,
                )
                success += 1
            except Exception as e:
                logger.error("Failed prediction for %s: %s", symbol, e)
                errors += 1

        logger.info(
            "Daily predictions complete: %d success, %d errors",
            success,
            errors,
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

    result = run_async(prediction_service.get_price_prediction(symbol, at, horizon_days))

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
        result = await db.execute(select(User).where(User.is_active.is_(True)))
        users = result.scalars().all()

        total_anomalies = 0

        for user in users:
            user_id = str(user.id)
            try:
                anomalies = await prediction_service.detect_anomalies(db, user_id)
                total_anomalies += len(anomalies)

                for anomaly in anomalies:
                    logger.warning(
                        "Anomaly detected for user %s: %s %s (%.1f%%)",
                        user_id,
                        anomaly.symbol,
                        anomaly.anomaly_type,
                        anomaly.price_change_percent,
                    )

                    # Send Telegram alert (best-effort, per-user, with cooldown)
                    try:
                        if user.telegram_enabled and user.telegram_chat_id:
                            from app.services.telegram_service import telegram_service

                            await telegram_service.alert_anomaly(
                                symbol=anomaly.symbol,
                                anomaly_type=anomaly.anomaly_type,
                                severity=anomaly.severity,
                                description=anomaly.description,
                                price_change_pct=anomaly.price_change_percent,
                                chat_id=user.telegram_chat_id,
                                user_id=user_id,
                            )
                    except Exception as tg_err:
                        logger.debug("Telegram anomaly alert failed: %s", tg_err)
            except Exception as e:
                logger.error("Anomaly detection failed for user %s: %s", user_id, e)

        logger.info("Anomaly detection complete: %d anomalies found", total_anomalies)


@celery_app.task(name="app.tasks.predictions.check_prediction_accuracy")
def check_prediction_accuracy():
    """Check yesterday's predictions against actual prices."""
    run_async(_check_prediction_accuracy())


async def _check_prediction_accuracy():
    """Compare past predictions with actual prices to monitor drift.

    Fills: actual_price, mape, direction_correct, ci_covered, accuracy_checked.
    """
    from datetime import datetime

    from sqlalchemy import and_, select

    from app.models.prediction_log import PredictionLog
    from app.services.price_service import PriceService

    price_service = PriceService()
    now = datetime.utcnow()

    async with async_session_factory() as db:
        # Find predictions whose target_date has passed but haven't been checked
        result = await db.execute(
            select(PredictionLog)
            .where(
                and_(
                    PredictionLog.target_date <= now,
                    PredictionLog.accuracy_checked.is_(None),
                )
            )
            .limit(100)
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

                if actual_price > 0 and log.predicted_price:
                    log.mape = abs(log.predicted_price - actual_price) / actual_price * 100

                    # Direction correctness: did price move in predicted direction?
                    if log.price_at_creation is not None:
                        baseline = float(log.price_at_creation)
                        if baseline > 0:
                            predicted_up = log.predicted_price > baseline
                            actual_up = actual_price > baseline
                            log.direction_correct = predicted_up == actual_up
                        else:
                            log.direction_correct = None
                    else:
                        # Legacy entries without price_at_creation
                        log.direction_correct = None

                    # CI coverage: was actual price within the confidence interval?
                    if log.confidence_low is not None and log.confidence_high is not None:
                        log.ci_covered = log.confidence_low <= actual_price <= log.confidence_high
                    else:
                        log.ci_covered = None

                    # Alert if MAPE too high
                    threshold = 20.0 if log.asset_type == "crypto" else 10.0
                    if log.mape > threshold:
                        drift_alerts += 1
                        logger.warning(
                            "DRIFT ALERT: %s MAPE=%.1f%% ci_covered=%s (threshold=%.0f%%)",
                            log.symbol,
                            log.mape,
                            log.ci_covered,
                            threshold,
                        )

                checked += 1
            except Exception as e:
                logger.error("Failed to check prediction for %s: %s", log.symbol, e)

        await db.commit()
        logger.info(
            "Prediction accuracy check: %d checked, %d drift alerts",
            checked,
            drift_alerts,
        )


@celery_app.task(name="app.tasks.predictions.check_data_drift")
def check_data_drift():
    """Check for data drift across all tracked assets (PSI-based)."""
    run_async(_check_data_drift())


async def _check_data_drift():
    """Compute PSI-based data drift for each tracked symbol."""
    import numpy as np

    from app.ml.drift_detector import check_drift
    from app.ml.historical_data import HistoricalDataFetcher

    fetcher = HistoricalDataFetcher()

    async with async_session_factory() as db:
        result = await db.execute(select(Asset.symbol, Asset.asset_type).where(Asset.quantity > 0).distinct())
        assets = result.all()

    drift_count = 0
    warning_count = 0

    for symbol, asset_type in assets:
        try:
            dates, prices = await fetcher.get_history(symbol, asset_type.value, days=180)
            if not prices or len(prices) < 60:
                continue

            prices_arr = np.array(prices, dtype=float)

            # Reference = first 80%, current = last 20%
            split = max(int(len(prices_arr) * 0.8), 30)
            ref = prices_arr[:split]
            cur = prices_arr[split:]

            if len(cur) < 10:
                continue

            dr = check_drift(ref, cur, symbol=symbol)
            if dr.status == "drift":
                drift_count += 1
            elif dr.status == "warning":
                warning_count += 1
        except Exception as e:
            logger.error("Drift check failed for %s: %s", symbol, e)

    logger.info(
        "Data drift check complete: %d drift, %d warning, %d total assets",
        drift_count,
        warning_count,
        len(assets),
    )


@celery_app.task(name="app.tasks.predictions.tune_hyperparameters")
def tune_hyperparameters():
    """Weekly hyperparameter tuning for ML models."""
    run_async(_tune_hyperparameters())


async def _tune_hyperparameters():
    """Async hyperparameter tuning."""
    from app.core.redis_client import cache_hyperparams
    from app.ml.historical_data import HistoricalDataFetcher
    from app.ml.hyperparameter_tuner import tune_prophet, tune_xgboost

    fetcher = HistoricalDataFetcher()

    async with async_session_factory() as db:
        result = await db.execute(select(Asset.symbol, Asset.asset_type).where(Asset.quantity > 0).distinct())
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


@celery_app.task(name="app.tasks.predictions.check_bottom_zones")
def check_bottom_zones():
    """Check for bottom zone opportunities and send Telegram alerts."""
    run_async(_check_bottom_zones())


async def _check_bottom_zones():
    """Detect assets in bottom zone with confidence > 80% and alert via Telegram."""
    from app.ml.historical_data import HistoricalDataFetcher
    from app.models.portfolio import Portfolio
    from app.models.user import User
    from app.services.telegram_service import telegram_service

    fetcher = HistoricalDataFetcher()

    async with async_session_factory() as db:
        result = await db.execute(select(Asset.symbol, Asset.asset_type).where(Asset.quantity > 0).distinct())
        assets = result.all()

        alerts_sent = 0

        for symbol, asset_type in assets:
            try:
                dates, prices = await fetcher.get_history(symbol, asset_type.value, days=180)
                if not prices or len(prices) < 30:
                    continue

                current_price = prices[-1]

                estimate = prediction_service.estimate_top_bottom(
                    symbol=symbol,
                    prices=prices,
                    current_price=current_price,
                )

                bottom = estimate.get("next_bottom", {})
                confidence = bottom.get("confidence", 0)
                distance_pct = abs(bottom.get("distance_pct", 100))

                # Alert if confidence > 80% AND price is close to bottom (< 5%)
                if confidence > 0.80 and distance_pct < 5.0:
                    # Fan-out: send to all users holding this asset with Telegram enabled
                    holders_result = await db.execute(
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
                    holders = holders_result.scalars().all()

                    for holder in holders:
                        sent = await telegram_service.alert_bottom_zone(
                            symbol=symbol,
                            current_price=current_price,
                            estimated_bottom=bottom.get("estimated_price", 0),
                            confidence=confidence,
                            distance_pct=distance_pct,
                            chat_id=holder.telegram_chat_id,
                            user_id=str(holder.id),
                        )
                        if sent:
                            alerts_sent += 1
                            logger.info(
                                "Bottom zone alert sent for %s to user %s (conf=%.0f%%, dist=%.1f%%)",
                                symbol,
                                holder.id,
                                confidence * 100,
                                distance_pct,
                            )
            except Exception as e:
                logger.debug("Bottom zone check failed for %s: %s", symbol, e)

    logger.info("Bottom zone check complete: %d alerts sent", alerts_sent)
