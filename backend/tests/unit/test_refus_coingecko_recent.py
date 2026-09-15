"""Un refus récent de CoinGecko vaut pour tous les symboles d'une requête HTTP.

Le 429 était déjà traité en « abandon immédiat » quand un humain attend, mais
chaque symbole suivant repassait par le throttle (1,2 s) pour obtenir le même
refus : journaux Render du 2026-09-15, huit symboles, dix secondes par tableau
de bord recalculé, pour rien. Le refus est désormais mémorisé (Retry-After ou
30 s) et une requête HTTP qui tombe dans la fenêtre n'appelle pas. Les tâches
de fond gardent leur attente (NEW-87).
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.ml.historical_data as hd
from app.core.contexte_execution import sert_une_requete_http


def _reponse(code: int, retry_after: str | None = None):
    r = MagicMock()
    r.status_code = code
    r.headers = {"Retry-After": retry_after} if retry_after else {}
    r.json.return_value = {"prices": []}
    r.raise_for_status = MagicMock()
    return r


@pytest.fixture
def fetcher(monkeypatch):
    monkeypatch.setattr(hd, "_refus_coingecko_jusqua", 0.0)
    monkeypatch.setattr(hd, "_last_coingecko_call", 0.0)
    f = hd.HistoricalDataFetcher(coingecko_api_key=None)
    f.http_client = MagicMock()
    return f


@pytest.fixture
def un_humain_attend():
    jeton = sert_une_requete_http.set(True)
    yield
    sert_une_requete_http.reset(jeton)


@pytest.mark.asyncio
async def test_le_second_symbole_n_appelle_pas_apres_un_refus(fetcher, un_humain_attend):
    fetcher.http_client.get = AsyncMock(return_value=_reponse(429, "60"))

    assert await fetcher._coingecko_get("u", {}, "FET", max_retries=1, fast=True) is None
    debut = time.monotonic()
    assert await fetcher._coingecko_get("u", {}, "LINK", max_retries=1, fast=True) is None
    duree = time.monotonic() - debut

    assert fetcher.http_client.get.await_count == 1, "le refus est acquis : pas de second appel"
    assert duree < 0.5, "ni throttle ni attente pour un refus déjà connu"


@pytest.mark.asyncio
async def test_la_fenetre_de_refus_expire(fetcher, un_humain_attend):
    fetcher.http_client.get = AsyncMock(side_effect=[_reponse(429), _reponse(200)])

    await fetcher._coingecko_get("u", {}, "FET", max_retries=1, fast=True)
    hd._refus_coingecko_jusqua = asyncio.get_event_loop().time() - 1  # fenêtre passée

    assert await fetcher._coingecko_get("u", {}, "LINK", max_retries=1, fast=True) == {"prices": []}
    assert fetcher.http_client.get.await_count == 2


@pytest.mark.asyncio
async def test_sans_retry_after_la_fenetre_vaut_trente_secondes(fetcher, un_humain_attend):
    fetcher.http_client.get = AsyncMock(return_value=_reponse(429))

    avant = asyncio.get_event_loop().time()
    await fetcher._coingecko_get("u", {}, "FET", max_retries=1, fast=True)

    assert hd._refus_coingecko_jusqua == pytest.approx(avant + hd._REFUS_PAR_DEFAUT, abs=1.0)


@pytest.mark.asyncio
async def test_une_tache_de_fond_n_est_pas_privee_d_appel(fetcher, monkeypatch):
    """Personne n'attend : la tâche de fond appelle, quitte à patienter."""
    monkeypatch.setattr(hd, "_refus_coingecko_jusqua", asyncio.get_event_loop().time() + 60)
    fetcher.http_client.get = AsyncMock(return_value=_reponse(200))

    assert await fetcher._coingecko_get("u", {}, "FET", max_retries=1, fast=True) == {"prices": []}
    assert fetcher.http_client.get.await_count == 1
