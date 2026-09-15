"""Le pré-chargement de démarrage ne demande pas à CoinGecko ce que la base a déjà.

Le test « déjà en cache ? » ne regardait que Redis. Dès que Redis ne répondait
plus (quota Upstash, 2026-09-15), chaque démarrage relançait un appel CoinGecko
par actif : sept déploiements ce jour-là, 22 actifs, des 429 dans les journaux
— alors que la base avait le cours du jour pour 20 d'entre eux (NEW-86).
"""

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks import history_cache

_DATES = [datetime(2026, 9, 1), datetime(2026, 9, 2)]
_PRIX = [50000.0, 51000.0]


class _RedisVide:
    def get(self, key):
        return None

    def setex(self, key, ttl, value):
        pass


@pytest.fixture
def environnement():
    fetcher = MagicMock()
    fetcher.get_history = AsyncMock(return_value=(_DATES, _PRIX))
    fetcher.close = AsyncMock()
    with patch.object(history_cache, "_get_redis", return_value=_RedisVide()), patch.object(
        history_cache, "HistoricalDataFetcher", return_value=fetcher
    ), patch.object(history_cache, "_persist_prices_to_db", new=AsyncMock()), patch.object(
        history_cache, "_get_all_crypto_symbols", new=AsyncMock(return_value=[("BTC", "crypto"), ("ETH", "crypto")])
    ), patch.object(
        history_cache.asyncio, "sleep", new=AsyncMock()
    ):
        yield fetcher


def _base_qui_connait(jours: dict):
    return patch.object(history_cache, "_dernier_jour_en_base", new=AsyncMock(return_value=jours))


@pytest.mark.asyncio
async def test_un_cours_du_jour_en_base_epargne_coingecko(environnement):
    with _base_qui_connait({"BTC": date.today(), "ETH": date.today() - timedelta(days=1)}):
        assert await history_cache._fetch_and_cache_all() == 2

    symboles_demandes = [appel.args[0] for appel in environnement.get_history.await_args_list]
    assert symboles_demandes == ["ETH"], "BTC a son cours du jour en base, ETH est en retard d'un jour"


@pytest.mark.asyncio
async def test_une_base_illisible_n_empeche_rien(environnement):
    with patch.object(
        history_cache, "_dernier_jour_en_base", new=AsyncMock(side_effect=RuntimeError("base injoignable"))
    ):
        assert await history_cache._fetch_and_cache_all() == 2

    assert environnement.get_history.await_count == 2


@pytest.mark.asyncio
async def test_la_couverture_se_lit_en_une_requete(environnement):
    with _base_qui_connait({}) as lecture:
        await history_cache._fetch_and_cache_all()

    assert lecture.await_count == 1
