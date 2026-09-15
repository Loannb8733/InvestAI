"""Sans worker Celery, une mise en file ne sert à rien et coûte des commandes.

Render (offre gratuite) ne fait tourner que le service web. `cache_single_asset
.delay()` y empilait pourtant la tâche dans Upstash — 8 commandes mesurées par
appel (4 LLEN, MULTI, SADD, LPUSH, EXEC) — sans que personne ne la consomme :
la file `celery` grossissait à chaque tableau de bord recalculé avec un symbole
sans historique (NEW-83). Le travail est alors confié à la boucle du processus.
"""

import logging
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings
from app.tasks import history_cache
from app.tasks.history_cache import planifier_cache_historique


@pytest.fixture(autouse=True)
def _etat_vierge(monkeypatch):
    monkeypatch.setattr(history_cache, "_prechargements_en_cours", {})
    monkeypatch.setattr(history_cache, "_dernier_essai", {})


@pytest.fixture
def mise_en_file():
    with patch.object(history_cache.cache_single_asset, "delay") as delay:
        yield delay


@pytest.fixture
def travail():
    """Le vrai pré-chargement interroge CoinGecko : remplacé par un double."""
    with patch.object(history_cache, "_cache_single", new=AsyncMock(return_value=True)) as double:
        yield double


class TestAvecWorker:
    @pytest.mark.asyncio
    async def test_la_tache_part_dans_la_file(self, monkeypatch, mise_en_file, travail):
        monkeypatch.setattr(settings, "CELERY_WORKER_AVAILABLE", True)

        assert planifier_cache_historique("BTC", "crypto") == "file"

        mise_en_file.assert_called_once_with("BTC", "crypto")
        travail.assert_not_called()


class TestSansWorker:
    @pytest.mark.asyncio
    async def test_le_travail_part_dans_la_boucle_pas_dans_redis(self, monkeypatch, mise_en_file, travail):
        monkeypatch.setattr(settings, "CELERY_WORKER_AVAILABLE", False)

        assert planifier_cache_historique("BTC", "crypto") == "boucle"
        tache = history_cache._prechargements_en_cours["BTC"]
        await tache

        mise_en_file.assert_not_called()
        travail.assert_awaited_once_with("BTC", "crypto")
        assert "BTC" not in history_cache._prechargements_en_cours, "la tâche finie se retire"

    @pytest.mark.asyncio
    async def test_le_meme_symbole_n_est_pas_relance_dans_l_heure(self, monkeypatch, mise_en_file, travail):
        """Un symbole sans historique (OM) revenait à chaque recalcul du tableau
        de bord : sans garde, autant d'appels à CoinGecko."""
        monkeypatch.setattr(settings, "CELERY_WORKER_AVAILABLE", False)

        assert planifier_cache_historique("OM", "crypto") == "boucle"
        await history_cache._prechargements_en_cours["OM"]
        assert planifier_cache_historique("om", "crypto") == "deja"

        assert travail.await_count == 1

    def test_hors_de_toute_boucle_rien_ne_casse(self, monkeypatch, mise_en_file, travail, caplog):
        monkeypatch.setattr(settings, "CELERY_WORKER_AVAILABLE", False)
        caplog.set_level(logging.WARNING, logger="app.tasks.history_cache")

        assert planifier_cache_historique("BTC", "crypto") == "ignore"

        mise_en_file.assert_not_called()
        assert any("non planifié" in r.getMessage() for r in caplog.records)


def test_le_reglage_est_faux_par_defaut():
    """Render ne pose pas la variable : le défaut doit être « pas de worker »."""
    assert type(settings).model_fields["CELERY_WORKER_AVAILABLE"].default is False
