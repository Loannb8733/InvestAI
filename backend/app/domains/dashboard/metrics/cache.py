"""Cache mémoire des métriques du tableau de bord, borné, avec un seul calcul à la fois par clé."""

import asyncio
from typing import Any

from app.core import redis_client

DashboardKey = tuple[str, int, str]

DASHBOARD_CACHE_TTL = 120
_MAX_DASHBOARD_CACHE = 200

dashboard_cache: dict[DashboardKey, tuple[float, dict[str, Any]]] = {}
dashboard_inflight: dict[DashboardKey, asyncio.Future[dict[str, Any]]] = {}
_background_tasks: set[asyncio.Task[Any]] = set()


def put_dashboard(key: DashboardKey, value: tuple[float, dict[str, Any]]) -> None:
    """Range une entrée en retirant le plus ancien quart quand le cache est plein."""
    if len(dashboard_cache) >= _MAX_DASHBOARD_CACHE:
        oldest_first = sorted(dashboard_cache, key=lambda cached: dashboard_cache[cached][0])
        for cached in oldest_first[: max(1, _MAX_DASHBOARD_CACHE // 4)]:
            del dashboard_cache[cached]
    dashboard_cache[key] = value


def invalidate_dashboard_cache(user_id: str) -> None:
    """Vide le cache de l'utilisateur dans ce processus et, si une boucle tourne, celui partagé dans Redis."""
    for key in [key for key in dashboard_cache if key[0] == user_id]:
        del dashboard_cache[key]
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(redis_client.invalidate_dashboard_cache(user_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
