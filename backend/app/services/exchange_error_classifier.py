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
from typing import Any, Protocol
from uuid import UUID

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


async def rollback_puis_marquer(db: Any, modele_cle: Any, cle_id: UUID, exc: Exception) -> None:
    """Annule le travail en cours, puis ne persiste que le marquage de la clé.

    Pourquoi un rollback avant de marquer
    -------------------------------------
    Les gestionnaires d'erreur appelaient ``classify_and_mark_error`` puis
    ``db.commit()``. L'intention était de garder la trace de l'échec sur la clé
    — mais ``commit()`` valide **toute la session**, pas seulement ce marquage.

    Or ces blocs enveloppent des imports qui écrivent au fil de l'eau : quinze
    ``add``/``flush`` dans un ``try`` de 1 147 lignes pour l'import d'historique.
    Une erreur survenant en cours de route faisait donc valider les écritures
    déjà en attente : un import interrompu laissait en base une moitié de
    transactions, sans que rien ne le signale. C'est la mécanique qui avait
    produit les écritures fantômes de NEW-02/NEW-03.

    Le rollback rend l'échec propre : soit l'import aboutit en entier, soit il
    ne laisse rien. Le marquage de la clé, lui, a besoin de survivre — il est
    donc réappliqué **après**, sur une instance rechargée, puisque le rollback
    expire les objets de la session.
    """
    await db.rollback()

    # `db.get` recharge depuis la base : après un rollback, toucher l'ancienne
    # instance déclencherait un chargement paresseux hors contexte async.
    cle = await db.get(modele_cle, cle_id)
    if cle is None:
        # La clé a disparu entre-temps (suppression concurrente) : il n'y a plus
        # rien à marquer, et l'erreur d'origine reste journalisée par l'appelant.
        logger.warning("Clé API %s introuvable après rollback : marquage ignoré", cle_id)
        return

    classify_and_mark_error(cle, exc)
    await db.commit()
