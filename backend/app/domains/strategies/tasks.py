from typing import Any

from app.domains.strategies.contrarian import refresh_contrarian_stats as refresh
from app.tasks.celery_app import celery_app


@celery_app.task(name="app.domains.strategies.tasks.refresh_contrarian_stats")  # type: ignore[untyped-decorator]
def refresh_contrarian_stats() -> dict[str, Any]:
    """Tâche Celery planifiée : recalcule chaque nuit les statistiques contrariennes Fear & Greed."""
    return refresh()
