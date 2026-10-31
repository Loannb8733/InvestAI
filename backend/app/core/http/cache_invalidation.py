import logging

from fastapi import Request, Response
from starlette.middleware.base import RequestResponseEndpoint

logger = logging.getLogger(__name__)

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


async def _invalidate_dashboard(user_id: str) -> None:
    from app.core.redis_client import invalidate_dashboard_cache as invalidate_redis_dashboard
    from app.domains.dashboard.metrics.cache import invalidate_dashboard_cache as invalidate_inmem_dashboard

    invalidate_inmem_dashboard(user_id)
    await invalidate_redis_dashboard(user_id)


async def dashboard_cache_invalidation(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """Vide le cache du dashboard de l'utilisateur après toute écriture réussie."""
    response = await call_next(request)
    user_id = getattr(request.state, "user_id", None)
    if request.method in MUTATING_METHODS and 200 <= response.status_code < 300 and user_id:
        try:
            await _invalidate_dashboard(user_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Dashboard cache invalidation after write failed (stale figures possible): %s", exc)
    return response
