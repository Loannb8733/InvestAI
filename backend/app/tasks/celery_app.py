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
        "app.domains.predictions.tasks",
        "app.domains.alerts.tasks",
        "app.tasks.snapshots",
        "app.domains.notifications.tasks",
        "app.domains.system.tasks",
        "app.domains.crowdfunding.tasks",
        "app.tasks.contrarian_stats",
        "app.tasks.regime_alerts",
        "app.domains.market_data.fx.tasks",
        "app.domains.market_data.history.tasks",
        "app.domains.exchanges.sync.tasks",
    ],
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Aucun code ne lit le résultat d'une tâche (ni AsyncResult, ni .get()) :
    # chaque exécution écrivait pourtant son état dans Redis (MULTI, HSET,
    # EXPIRE, EXEC, PUBLISH), deux fois avec l'état STARTED. Mesuré : l'essentiel
    # des commandes restantes une fois le worker au repos.
    task_track_started=False,
    task_ignore_result=True,
    task_time_limit=300,  # 5 minutes
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    # Upstash (plan gratuit) facture chaque commande : 500 000 par mois. Au
    # repos, un worker interrogeait la file toutes les secondes (BRPOP, délai 1 s)
    # et publiait un battement toutes les 2 s — 94 commandes/minute mesurées,
    # soit ~4 millions par mois, huit fois le quota (épuisé le 2026-09-15).
    # kombu reprend `polling_interval` comme délai du BRPOP : une tâche qui
    # arrive le débloque aussitôt, seule la relance à vide s'espace.
    # `health_check_interval` : un PING par connexion toutes les 25 s par défaut,
    # soit la moitié des commandes restantes au repos.
    broker_transport_options={"polling_interval": 30, "health_check_interval": 120},
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
        "task": "app.domains.exchanges.sync.tasks.sync_all_exchanges",
        "schedule": 3600.0,  # Every hour
    },
    "run-daily-predictions": {
        "task": "app.domains.predictions.tasks.run_daily_predictions",
        "schedule": 86400.0,  # Every 24 hours
    },
    "detect-anomalies": {
        "task": "app.domains.predictions.tasks.detect_anomalies",
        "schedule": 43200.0,  # Every 12 hours
    },
    "check-alerts": {
        "task": "app.domains.alerts.tasks.check_all_alerts",
        "schedule": 300.0,  # Every 5 minutes
    },
    "refresh-fx-rates": {
        "task": "app.domains.market_data.fx.tasks.refresh_fx_rates",
        # 16h05 UTC : la BCE publie ses taux vers 16h00 CET les jours ouvrés. Une
        # seule passe par jour suffit — ensure_seeded ne lit que la fenêtre manquante,
        # et rattrape donc tout seul les jours sautés.
        "schedule": crontab(hour=16, minute=5),
    },
    "seed-risk-weight-snapshots": {
        "task": "app.domains.alerts.tasks.seed_risk_weight_snapshots",
        "schedule": crontab(hour=0, minute=5),  # Daily at 00:05 UTC
    },
    "check-prediction-accuracy": {
        "task": "app.domains.predictions.tasks.check_prediction_accuracy",
        "schedule": 86400.0,  # Every 24 hours
    },
    "refresh-history": {
        "task": "app.domains.market_data.history.tasks.refresh_history",
        "schedule": 1800.0,  # Every 30 minutes
    },
    "backfill-history": {
        "task": "app.domains.market_data.history.tasks.backfill_history",
        "schedule": 86400.0,  # Every 24 hours — fills gaps + refreshes recent data
    },
    "tune-hyperparameters": {
        "task": "app.domains.predictions.tasks.tune_hyperparameters",
        "schedule": 604800.0,  # Every 7 days
    },
    "check-data-drift": {
        "task": "app.domains.predictions.tasks.check_data_drift",
        "schedule": 86400.0,  # Every 24 hours
    },
    "check-bottom-zones": {
        "task": "app.domains.predictions.tasks.check_bottom_zones",
        "schedule": 21600.0,  # Every 6 hours
    },
    # === Snapshots ===
    "create-daily-snapshots": {
        "task": "app.tasks.snapshots.create_daily_snapshots",
        "schedule": crontab(hour=0, minute=0),  # Every day at 00:00 UTC
    },
    "cleanup-old-snapshots": {
        "task": "app.tasks.snapshots.cleanup_old_snapshots",
        "schedule": crontab(hour=1, minute=0, day_of_month=1),  # 1st of each month at 01:00 UTC
    },
    # === Email Reports ===
    "send-weekly-reports": {
        "task": "app.domains.notifications.tasks.send_weekly_reports",
        "schedule": crontab(hour=18, minute=0, day_of_week=0),  # Sunday at 18:00 UTC (19:00 Paris)
    },
    "send-monthly-reports": {
        "task": "app.domains.notifications.tasks.send_monthly_reports",
        "schedule": crontab(hour=8, minute=0, day_of_month=1),  # 1st of month at 08:00 UTC
    },
    "send-daily-digest": {
        "task": "app.domains.notifications.tasks.send_daily_digest",
        "schedule": crontab(hour=7, minute=0),  # Every day at 07:00 UTC (08:00 Paris)
    },
    # === Regime Mutation Detection ===
    "check-regime-mutation": {
        "task": "app.tasks.regime_alerts.check_regime_mutation",
        "schedule": 43200.0,  # Every 12 hours
    },
    # === Data Cleanup ===
    "run-weekly-cleanup": {
        "task": "app.domains.system.tasks.run_weekly_cleanup",
        "schedule": crontab(hour=3, minute=0, day_of_week=1),  # Monday at 03:00 UTC
    },
    "validate-portfolio-consistency": {
        "task": "app.domains.system.tasks.validate_portfolio_consistency",
        "schedule": crontab(hour=4, minute=0),  # Every day at 04:00 UTC
    },
    # === Crowdfunding Delay Monitoring ===
    "check-crowdfunding-delays": {
        "task": "app.domains.crowdfunding.tasks.check_crowdfunding_delays",
        "schedule": crontab(hour=8, minute=30),  # Daily at 08:30 UTC (09:30 Paris)
    },
    # === Contrarian (Fear & Greed) backtest stats ===
    "refresh-contrarian-stats": {
        "task": "app.tasks.contrarian_stats.refresh_contrarian_stats",
        "schedule": crontab(hour=2, minute=15),  # Daily at 02:15 UTC (off-peak)
    },
}
