from dataclasses import asdict
from typing import Any

from app.domains.exchanges.sync.runner import active_key_ids, sync_account
from app.tasks.async_runner import run_async
from app.tasks.celery_app import celery_app


@celery_app.task(name="app.domains.exchanges.sync.tasks.sync_all_exchanges")  # type: ignore[untyped-decorator]
def sync_all_exchanges() -> dict[str, int]:
    """Tâche Celery planifiée : une synchronisation par clé active, chacune dans sa propre tâche."""
    key_ids = run_async(active_key_ids())
    for key_id in key_ids:
        sync_exchange.delay(key_id)
    return {"dispatched": len(key_ids)}


@celery_app.task(name="app.domains.exchanges.sync.tasks.sync_exchange")  # type: ignore[untyped-decorator]
def sync_exchange(api_key_id: str) -> dict[str, Any]:
    """Tâche Celery : synchronise un compte d'exchange."""
    return asdict(run_async(sync_account(api_key_id)))
