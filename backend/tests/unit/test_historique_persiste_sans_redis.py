"""L'historique des cours atteint PostgreSQL même quand Redis refuse d'écrire.

`asset_price_history` est la copie durable : c'est elle qui sert le tableau de
bord quand Redis est indisponible. Or le pré-chargement écrivait Redis *avant*
de persister en base, dans le même bloc : une écriture Redis refusée sautait la
persistance. Journaux Render du 2026-09-15, quota Upstash épuisé :
« Fetched 366 data points for TAO from CoinGecko » puis « Failed to fetch
history for TAO: max requests limit exceeded » — les données étaient là, et
perdues. Pendant toute la panne, la copie durable n'a plus été rafraîchie,
et le repli servait un historique qui vieillissait (NEW-85).

Une lecture Redis refusée faisait de même tomber tout le pré-chargement de
démarrage au premier symbole, au lieu de le traiter comme « pas en cache ».
"""

import logging
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks import history_cache

_DATES = [datetime(2026, 9, 1), datetime(2026, 9, 2)]
_PRIX = [50000.0, 51000.0]


class _RedisQuiRefuse:
    """Accepte la connexion, refuse chaque commande — un quota Upstash épuisé."""

    def get(self, key):
        raise ConnectionError("max requests limit exceeded")

    def setex(self, key, ttl, value):
        raise ConnectionError("max requests limit exceeded")


@pytest.fixture
def redis_en_panne():
    with patch.object(history_cache, "_get_redis", return_value=_RedisQuiRefuse()):
        yield


@pytest.fixture
def coingecko():
    fetcher = MagicMock()
    fetcher.get_history = AsyncMock(return_value=(_DATES, _PRIX))
    fetcher.close = AsyncMock()
    with patch.object(history_cache, "HistoricalDataFetcher", return_value=fetcher):
        yield fetcher


@pytest.fixture
def base():
    with patch.object(history_cache, "_persist_prices_to_db", new=AsyncMock()) as persist:
        yield persist


@pytest.mark.asyncio
async def test_le_prechargement_unitaire_persiste_malgre_redis(redis_en_panne, coingecko, base):
    assert await history_cache._cache_single("TAO", "crypto") is True

    base.assert_awaited_once_with("TAO", _DATES, _PRIX)


@pytest.mark.asyncio
async def test_le_prechargement_de_demarrage_persiste_chaque_symbole(redis_en_panne, coingecko, base, caplog):
    caplog.set_level(logging.WARNING, logger="app.tasks.history_cache")
    with patch.object(
        history_cache, "_get_all_crypto_symbols", new=AsyncMock(return_value=[("BTC", "crypto"), ("ETH", "crypto")])
    ), patch.object(history_cache.asyncio, "sleep", new=AsyncMock()):
        assert await history_cache._fetch_and_cache_all() == 2

    assert [appel.args[0] for appel in base.await_args_list] == ["BTC", "ETH"]
    assert any("Redis" in r.getMessage() for r in caplog.records), "la panne du cache doit se voir"


@pytest.mark.asyncio
async def test_un_cache_valide_est_toujours_ecrit(coingecko, base):
    redis = MagicMock()
    redis.get.return_value = None
    with patch.object(history_cache, "_get_redis", return_value=redis):
        assert await history_cache._cache_single("TAO", "crypto") is True

    assert redis.setex.call_count == 2, "clé principale et copie de secours"
    base.assert_awaited_once()
