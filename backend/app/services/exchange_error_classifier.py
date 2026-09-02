"""Classification des erreurs d'exchange, en un seul endroit.

Pourquoi ce module existe
-------------------------
La même fonction vivait en double : dans la tâche de synchronisation et dans les
endpoints de clés API. Les deux copies avaient déjà commencé à diverger — celle
des endpoints avait perdu le ``logger.error`` final, si bien qu'une erreur
générique n'y laissait **aucune trace**, là où la tâche la journalisait.

C'est le défaut habituel de la duplication : elle ne se voit pas tant que les
copies restent identiques, et quand elles divergent, rien ne signale laquelle a
raison.
"""

import logging
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)


class CleAPI(Protocol):
    """Ce que le classifieur attend d'une clé API, sans dépendre du modèle."""

    id: object

    def mark_auth_failure(self, message: str) -> None:
        ...

    def mark_rate_limited(self, message: str) -> None:
        ...

    def mark_error(self, message: str) -> None:
        ...


def classify_and_mark_error(api_key: CleAPI, exc: Exception) -> None:
    """Qualifie l'erreur et marque la clé en conséquence.

    Trois issues, de la plus précise à la plus générale : échec
    d'authentification (la clé est désactivée), limite de débit atteinte (elle
    reste valide), ou erreur quelconque.
    """
    error_msg = str(exc)

    # Erreurs HTTP remontées par `raise_for_status`.
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (401, 403):
            api_key.mark_auth_failure(error_msg)
            logger.warning("API key %s: auth failure (%d), disabling", api_key.id, code)
            return
        if code == 429:
            api_key.mark_rate_limited(error_msg)
            logger.warning("API key %s: rate limited (429)", api_key.id)
            return

    # Kraken signale ses erreurs d'authentification dans le corps JSON, pas dans
    # le statut HTTP : sans ce second passage, elles seraient prises pour des
    # erreurs génériques et la clé resterait active.
    lower_msg = error_msg.lower()
    if "invalid key" in lower_msg or "invalid signature" in lower_msg or "permission denied" in lower_msg:
        api_key.mark_auth_failure(error_msg)
        logger.warning("API key %s: auth failure (json), disabling", api_key.id)
        return

    api_key.mark_error(error_msg)
    logger.error("API key %s: sync error: %s", api_key.id, error_msg[:200])
