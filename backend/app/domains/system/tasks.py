from typing import Any

from app.domains.system.maintenance import check_holdings, weekly_cleanup
from app.tasks.async_runner import run_async
from app.tasks.celery_app import celery_app


@celery_app.task(name="app.domains.system.tasks.validate_portfolio_consistency")  # type: ignore[untyped-decorator]
def validate_portfolio_consistency() -> dict[str, Any]:
    """Compare chaque actif à ses transactions et recale les actifs sans exchange."""
    result: dict[str, Any] = run_async(check_holdings())
    return result


@celery_app.task(name="app.domains.system.tasks.run_weekly_cleanup")  # type: ignore[untyped-decorator]
def run_weekly_cleanup() -> dict[str, Any]:
    """Nettoyage hebdomadaire : notifications lues, vieilles prédictions, transactions en double."""
    result: dict[str, Any] = run_async(weekly_cleanup())
    return result
