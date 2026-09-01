"""Rafraîchissement quotidien des taux de change de référence (BCE).

Pourquoi cette tâche existe
---------------------------
``FxHistoryService.ensure_seeded`` alimente la table ``fx_daily_rates`` en ne
récupérant que la fenêtre manquante — conçue pour être « cheap to call on every
sync ». Elle n'était appelée que par la synchronisation d'exchange, l'import de clé
API et le script de backfill : **trois déclencheurs liés à une action de
l'utilisateur**.

Les taux de change de l'euro n'ont aucune raison de dépendre du fait qu'on consulte
ses exchanges. Constaté le 2026-09-01 : la table s'arrêtait au vendredi 28/08 —
faute de synchronisation depuis, et non par une panne. Le coût de base d'un futur
actif en devise étrangère aurait été figé sur le dernier taux qu'une synchronisation
aurait bien voulu rapatrier.

Cette tâche coupe la dépendance : les taux se tiennent à jour d'eux-mêmes.
"""


import logging
from datetime import date

from app.core.database import AsyncSessionLocal
from app.services.fx_history_service import FxHistoryService
from app.tasks.async_runner import run_async
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# La BCE publie depuis 1999 ; 2017 couvre tout l'historique crypto réel. Sert
# uniquement au tout premier amorçage : ensuite seule la fenêtre manquante est lue.
_EARLIEST = date(2017, 1, 1)

# Paires tenues à jour. USD/EUR est la seule utilisée aujourd'hui ; les autres sont
# amorcées d'avance pour qu'un actif dans l'une de ces devises ne tombe jamais sur
# les constantes de dernier recours de metrics_service.
_PAIRS = (("USD", "EUR"), ("GBP", "EUR"), ("CHF", "EUR"))


@celery_app.task(name="app.tasks.fx_rates.refresh_fx_rates")
def refresh_fx_rates():
    """Complète la table des taux BCE jusqu'à aujourd'hui, paire par paire."""

    async def _refresh():
        resultats: dict[str, int] = {}
        async with AsyncSessionLocal() as db:
            svc = FxHistoryService(db)
            for base, quote in _PAIRS:
                paire = f"{base}->{quote}"
                try:
                    inserees = await svc.ensure_seeded(base, quote, _EARLIEST)
                    resultats[paire] = inserees
                    if inserees:
                        logger.info("FX %s : %d taux ajoutés", paire, inserees)
                except Exception as exc:  # noqa: BLE001
                    # Une paire indisponible ne doit pas empêcher les autres : c'est
                    # tout l'intérêt d'avoir plusieurs devises amorcées d'avance.
                    logger.warning("FX %s : rafraîchissement échoué (%s)", paire, exc)
                    resultats[paire] = -1
        return resultats

    return run_async(_refresh())
