import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from app.domains.alerts.tasks import _check as check_alerts
from app.domains.alerts.tasks import _seed as seed_risk_weights
from app.domains.crowdfunding.tasks import _flag_delays as flag_crowdfunding_delays
from app.domains.exchanges.sync.runner import sync_all
from app.domains.market_data.fx.tasks import refresh_reference_rates
from app.domains.market_data.history.tasks import backfill_all, refresh_all
from app.domains.notifications.tasks import run_daily_digest, run_monthly_reports, run_weekly_reports
from app.domains.predictions import tasks as predictions
from app.domains.system.maintenance import check_holdings, weekly_cleanup
from app.services.regime_alert_service import regime_alert_service
from app.tasks import price_updates, snapshots
from app.tasks.contrarian_stats import refresh_contrarian_stats

Job = Callable[[], Awaitable[Any]]


async def _contrarian_stats() -> dict[str, Any]:
    return await asyncio.to_thread(refresh_contrarian_stats)


JOBS: dict[str, Job] = {
    "app.tasks.price_updates.update_crypto_prices": price_updates._maj_crypto,
    "app.tasks.price_updates.update_stock_prices": price_updates._maj_actions,
    "app.domains.exchanges.sync.tasks.sync_all_exchanges": sync_all,
    "app.domains.predictions.tasks.run_daily_predictions": predictions._run_daily_predictions,
    "app.domains.predictions.tasks.detect_anomalies": predictions._detect_anomalies,
    "app.domains.alerts.tasks.check_all_alerts": check_alerts,
    "app.domains.market_data.fx.tasks.refresh_fx_rates": refresh_reference_rates,
    "app.domains.alerts.tasks.seed_risk_weight_snapshots": seed_risk_weights,
    "app.domains.predictions.tasks.check_prediction_accuracy": predictions._check_prediction_accuracy,
    "app.domains.market_data.history.tasks.refresh_history": refresh_all,
    "app.domains.market_data.history.tasks.backfill_history": backfill_all,
    "app.domains.predictions.tasks.tune_hyperparameters": predictions._tune_hyperparameters,
    "app.domains.predictions.tasks.check_data_drift": predictions._check_data_drift,
    "app.domains.predictions.tasks.check_bottom_zones": predictions._check_bottom_zones,
    "app.tasks.snapshots.create_daily_snapshots": snapshots._create_all_snapshots_async,
    "app.tasks.snapshots.cleanup_old_snapshots": snapshots._cleanup_old_snapshots_async,
    "app.domains.notifications.tasks.send_weekly_reports": run_weekly_reports,
    "app.domains.notifications.tasks.send_monthly_reports": run_monthly_reports,
    "app.domains.notifications.tasks.send_daily_digest": run_daily_digest,
    "app.tasks.regime_alerts.check_regime_mutation": regime_alert_service.check_and_alert,
    "app.domains.system.tasks.run_weekly_cleanup": weekly_cleanup,
    "app.domains.system.tasks.validate_portfolio_consistency": check_holdings,
    "app.domains.crowdfunding.tasks.check_crowdfunding_delays": flag_crowdfunding_delays,
    "app.tasks.contrarian_stats.refresh_contrarian_stats": _contrarian_stats,
}
HEAVY_PREFIX = "app.domains.predictions.tasks."
