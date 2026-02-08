"""Celery application configuration."""

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "investai",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.price_updates",
        "app.tasks.sync_exchanges",
        "app.tasks.predictions",
        "app.tasks.alerts",
        "app.tasks.history_cache",
        "app.tasks.snapshots",
        "app.tasks.emails",
        "app.tasks.cleanup",
    ],
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)

# Scheduled tasks (Celery Beat)
celery_app.conf.beat_schedule = {
    "update-crypto-prices": {
        "task": "app.tasks.price_updates.update_crypto_prices",
        "schedule": 300.0,  # Every 5 minutes (was 60s, too aggressive for free tier)
    },
    "update-stock-prices": {
        "task": "app.tasks.price_updates.update_stock_prices",
        "schedule": 300.0,  # Every 5 minutes
    },
    "sync-exchanges": {
        "task": "app.tasks.sync_exchanges.sync_all_exchanges",
        "schedule": 3600.0,  # Every hour
    },
    "run-daily-predictions": {
        "task": "app.tasks.predictions.run_daily_predictions",
        "schedule": 86400.0,  # Every 24 hours
    },
    "detect-anomalies": {
        "task": "app.tasks.predictions.detect_anomalies",
        "schedule": 43200.0,  # Every 12 hours
    },
    "check-alerts": {
        "task": "app.tasks.alerts.check_all_alerts",
        "schedule": 300.0,  # Every 5 minutes
    },
    "check-prediction-accuracy": {
        "task": "app.tasks.predictions.check_prediction_accuracy",
        "schedule": 86400.0,  # Every 24 hours
    },
    "cache-historical-data": {
        "task": "app.tasks.history_cache.cache_historical_data",
        "schedule": 1800.0,  # Every 30 minutes
    },
    "tune-hyperparameters": {
        "task": "app.tasks.predictions.tune_hyperparameters",
        "schedule": 604800.0,  # Every 7 days
    },
    # === Snapshots ===
    "create-daily-snapshots": {
        "task": "tasks.create_daily_snapshots",
        "schedule": crontab(hour=0, minute=0),  # Every day at 00:00 UTC
    },
    "cleanup-old-snapshots": {
        "task": "tasks.cleanup_old_snapshots",
        "schedule": crontab(hour=1, minute=0, day_of_month=1),  # 1st of each month at 01:00 UTC
    },
    # === Email Reports ===
    "send-weekly-reports": {
        "task": "tasks.send_weekly_reports",
        "schedule": crontab(hour=18, minute=0, day_of_week=0),  # Sunday at 18:00 UTC (19:00 Paris)
    },
    "send-monthly-reports": {
        "task": "tasks.send_monthly_reports",
        "schedule": crontab(hour=8, minute=0, day_of_month=1),  # 1st of month at 08:00 UTC
    },
    "send-daily-digest": {
        "task": "tasks.send_daily_digest",
        "schedule": crontab(hour=7, minute=0),  # Every day at 07:00 UTC (08:00 Paris)
    },
    # === Data Cleanup ===
    "run-weekly-cleanup": {
        "task": "tasks.run_weekly_cleanup",
        "schedule": crontab(hour=3, minute=0, day_of_week=1),  # Monday at 03:00 UTC
    },
    "validate-portfolio-consistency": {
        "task": "tasks.validate_portfolio_consistency",
        "schedule": crontab(hour=4, minute=0),  # Every day at 04:00 UTC
    },
}
