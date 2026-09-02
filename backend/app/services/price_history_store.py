"""Lecture d'historique de prix **sans appel réseau**.

Pourquoi ce module existe
-------------------------
Servir une requête HTTP ne doit jamais dépendre d'une API tierce : c'est ce qui
faisait répondre ``/predictions/market-cycle`` en 65 secondes quand le quota
CoinGecko était épuisé (NEW-13). Le réseau est le travail de la tâche Celery
``cache_historical_data`` ; le chemin web se contente de lire ce qu'elle a
déposé.

Deux sources locales, dans l'ordre :

1. **Redis** — les clés des deux conventions historiques (voir
   ``core.redis_client.get_cached_history``) ;
2. **PostgreSQL** — ``asset_price_history``, alimentée par la même tâche et
   conservée sans expiration. C'est le filet : Redis peut être vide après un
   redémarrage, la base non.

La fonction ne renvoie jamais d'exception réseau puisqu'elle n'en fait aucun.
Une série absente est une série absente : l'appelant dégrade son analyse.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.redis_client import get_cached_history
from app.models.asset_price_history import AssetPriceHistory

logger = logging.getLogger(__name__)


async def charger_depuis_postgres(symbol: str, days: int) -> Tuple[List[datetime], List[float]]:
    """Historique persistant en base. Retourne ([], []) si rien n'est connu."""
    try:
        limite = datetime.now(timezone.utc).date() - timedelta(days=days)
        async with AsyncSessionLocal() as db:
            resultat = await db.execute(
                select(AssetPriceHistory.price_date, AssetPriceHistory.price_eur)
                .where(
                    AssetPriceHistory.symbol == symbol.upper(),
                    AssetPriceHistory.price_date >= limite,
                )
                .order_by(AssetPriceHistory.price_date)
            )
            lignes = resultat.all()
            if not lignes:
                return [], []
            return (
                [datetime.combine(ligne[0], datetime.min.time()) for ligne in lignes],
                [float(ligne[1]) for ligne in lignes],
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Historique PostgreSQL indisponible pour %s : %s", symbol, exc)
        return [], []


async def prix_locaux(symbol: str, asset_type: str, days: int) -> Optional[List[float]]:
    """Série de prix depuis Redis puis PostgreSQL, sans jamais toucher au réseau.

    Retourne ``None`` quand aucune source locale ne connaît ce symbole — à
    l'appelant de décider ce qu'il fait d'une analyse incomplète.
    """
    cache = await get_cached_history(symbol, asset_type, days)
    if cache and cache.get("prices"):
        return cache["prices"]

    _, prix = await charger_depuis_postgres(symbol, days)
    if prix:
        logger.debug("Historique de %s servi par PostgreSQL (Redis vide)", symbol)
        return prix

    return None
