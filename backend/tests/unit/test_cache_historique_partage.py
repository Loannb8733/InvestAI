"""Le cache alimenté par Celery doit être lu par ceux qui en ont besoin.

Pourquoi c'est une règle et pas un détail
-----------------------------------------
Deux caches d'historique coexistaient sans se connaître :

- ``core/redis_client.py`` écrivait ``hist:<sym>:<type>:<jours>`` à la demande,
  TTL 1 h, sans repli ;
- ``tasks/history_cache.py`` écrit ``hist:<SYM>_<jours>`` (plus une copie
  ``:fallback`` à 24 h), toutes les 30 minutes, avec persistance PostgreSQL.

La tâche tournait donc en permanence pour rien : aucun lecteur du premier format
ne la voyait. `get_market_cycle` repartait chercher les mêmes données chez
CoinGecko dans le chemin d'une requête HTTP — jusqu'à 65 secondes (NEW-13).

Une fois la lecture réconciliée : 1,2 s, et 7 actifs analysés au lieu de 1.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.core import redis_client
from app.tasks import history_cache


class TestConventionsDeCles:
    def test_le_lecteur_connait_le_format_de_la_tache(self):
        source = Path(redis_client.__file__).read_text(encoding="utf-8")
        # La clé de la tâche est `hist:<SYM>_<jours>` : le lecteur doit la construire.
        assert (
            "_{days}" in source or "_{_JOURS_CACHE_TACHE}" in source
        ), "get_cached_history ne cherche pas les clés écrites par la tâche périodique"

    def test_la_couverture_annuelle_est_alignee_sur_la_tache(self):
        assert redis_client._JOURS_CACHE_TACHE == history_cache.DEFAULT_CACHE_DAYS, (
            "le lecteur cherche une couverture que la tâche n'écrit pas : "
            f"{redis_client._JOURS_CACHE_TACHE} vs {history_cache.DEFAULT_CACHE_DAYS}"
        )

    def test_la_tache_reste_planifiee(self):
        from app.tasks.celery_app import celery_app

        planning = celery_app.conf.beat_schedule
        entrees = [c for c in planning.values() if "history_cache" in c.get("task", "")]
        assert entrees, "la tâche de pré-chargement n'est plus planifiée : le cache ne serait plus alimenté"
        # Le TTL Redis est d'1 h : passer au-delà laisserait des trous.
        assert (
            min(e["schedule"] for e in entrees) <= history_cache.REDIS_HISTORY_TTL
        ), "la tâche passe moins souvent que le TTL du cache : des trous apparaîtraient"


class TestLectureReconciliee:
    """Le lecteur doit servir une clé de la tâche, et retailler si besoin."""

    @pytest.mark.asyncio
    async def test_sert_la_cle_ecrite_par_la_tache(self):
        stockage = {"hist:BTC_365": json.dumps({"dates": ["2026-01-01"] * 365, "prices": list(range(365))})}

        faux = AsyncMock()
        faux.get = AsyncMock(side_effect=lambda cle: stockage.get(cle))
        with patch.object(redis_client, "_get_redis_txt", AsyncMock(return_value=faux)):
            res = await redis_client.get_cached_history("BTC", "crypto", 365)

        assert res is not None, "la clé de la tâche n'a pas été lue"
        assert len(res["prices"]) == 365

    @pytest.mark.asyncio
    async def test_retaille_une_serie_annuelle_pour_une_demande_courte(self):
        stockage = {"hist:BTC_365": json.dumps({"dates": [str(i) for i in range(365)], "prices": list(range(365))})}

        faux = AsyncMock()
        faux.get = AsyncMock(side_effect=lambda cle: stockage.get(cle))
        with patch.object(redis_client, "_get_redis_txt", AsyncMock(return_value=faux)):
            res = await redis_client.get_cached_history("BTC", "crypto", 90)

        assert len(res["prices"]) == 90, "la série annuelle doit être retaillée, pas rendue telle quelle"
        # On garde la fin : les 90 derniers jours, pas les 90 premiers.
        assert res["prices"][-1] == 364

    @pytest.mark.asyncio
    async def test_le_format_natif_reste_prioritaire(self):
        stockage = {
            "hist:BTC:crypto:90": json.dumps({"prices": [1, 2, 3]}),
            "hist:BTC_365": json.dumps({"prices": list(range(365))}),
        }
        faux = AsyncMock()
        faux.get = AsyncMock(side_effect=lambda cle: stockage.get(cle))
        with patch.object(redis_client, "_get_redis_txt", AsyncMock(return_value=faux)):
            res = await redis_client.get_cached_history("BTC", "crypto", 90)

        assert res["prices"] == [1, 2, 3], "la clé la plus précise doit primer sur le repli annuel"

    @pytest.mark.asyncio
    async def test_une_entree_vide_ne_masque_pas_les_suivantes(self):
        # Une clé présente mais sans prix ne doit pas court-circuiter le repli.
        stockage = {
            "hist:BTC:crypto:90": json.dumps({"prices": []}),
            "hist:BTC_90": json.dumps({"prices": [7, 8, 9]}),
        }
        faux = AsyncMock()
        faux.get = AsyncMock(side_effect=lambda cle: stockage.get(cle))
        with patch.object(redis_client, "_get_redis_txt", AsyncMock(return_value=faux)):
            res = await redis_client.get_cached_history("BTC", "crypto", 90)

        assert res["prices"] == [7, 8, 9]


class TestBudgetGlobal:
    def test_le_budget_est_partage_entre_tous_les_appels(self):
        import app.services.prediction_cycles as pc

        source = Path(pc.__file__).read_text(encoding="utf-8")
        assert "budget_restant" in source, "aucun compte à rebours partagé"
        # Appliqué appel par appel, le budget s'additionnait au lieu de borner.
        assert source.count("timeout=_BUDGET_APPELS_EXTERNES") == 0, (
            "un appel utilise le budget entier au lieu du temps restant : "
            "les délais s'additionnent et ne bornent plus rien"
        )
