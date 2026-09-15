"""Les deux caches de taux de change ne se marchent plus dessus.

`price_service` (valeur brute, 1 h) et `redis_client` (JSON « dernier taux
connu », 24 h) rangeaient leur taux sous la même clé `forex:{de}:{vers}`.
Mesuré le 2026-09-15 : chaque lecture échouait sur le format de l'autre —
`price_service` rappelait exchangerate-api (1 500 requêtes/mois gratuites) et
réécrivait sa valeur, `get_cached_forex_rate` rendait un float que l'appelant
traitait en dictionnaire. Un tableau de bord relisait en outre le même taux sept
fois dans Redis (NEW-81).
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core import redis_client
from app.services.price_service import PriceService


class _FauxRedis:
    def __init__(self):
        self.valeurs: dict = {}
        self.lectures = 0
        self.ecritures = 0

    async def get(self, cle):
        self.lectures += 1
        return self.valeurs.get(cle)

    async def setex(self, cle, ttl, valeur):
        self.ecritures += 1
        self.valeurs[cle] = valeur


@pytest.fixture
def redis_partage(monkeypatch):
    faux = _FauxRedis()
    lecteur = AsyncMock(return_value=faux)
    monkeypatch.setattr(redis_client, "_get_redis_txt", lecteur)
    monkeypatch.setattr(redis_client, "_forex_ecrits", {})
    with patch("app.services.price_service._get_redis_txt", lecteur):
        yield faux


@pytest.fixture
def service():
    ps = PriceService()
    reponse = MagicMock()
    reponse.json.return_value = {"rates": {"EUR": 0.866}}
    ps.http_client = MagicMock()
    ps.http_client.get = AsyncMock(return_value=reponse)
    return ps


@pytest.mark.asyncio
async def test_le_cache_du_tableau_de_bord_n_efface_plus_celui_des_cours(redis_partage, service):
    await redis_client.cache_forex_rate("USD", "EUR", 0.86)
    await service.get_forex_rate("USD", "EUR")  # remplit son propre cache via l'API
    service._forex_memo.clear()
    service.http_client.get.reset_mock()

    taux = await service.get_forex_rate("USD", "EUR")

    service.http_client.get.assert_not_awaited()  # relu en cache, pas redemandé à l'API
    assert taux == Decimal("0.866")
    dernier = await redis_client.get_cached_forex_rate("USD", "EUR")
    assert isinstance(dernier, dict) and dernier["rate"] == 0.86


@pytest.mark.asyncio
async def test_une_valeur_brute_ne_fait_plus_lever_l_appelant(redis_partage):
    redis_partage.valeurs["forex:USD:EUR"] = "0.866"

    assert await redis_client.get_cached_forex_rate("USD", "EUR") is None


@pytest.mark.asyncio
async def test_un_taux_recent_n_est_pas_relu_dans_redis(redis_partage, service):
    redis_partage.valeurs["forex:spot:USD:EUR"] = "0.866"

    for _ in range(7):
        assert await service.get_forex_rate("USD", "EUR") == Decimal("0.866")

    assert redis_partage.lectures == 1


@pytest.mark.asyncio
async def test_le_memo_est_partage_entre_instances(redis_partage):
    """Le tableau de bord crée un PriceService par requête : un mémo d'instance
    laissait relire le même taux trois fois dans une seule requête."""
    redis_partage.valeurs["forex:spot:USD:EUR"] = "0.866"

    for _ in range(3):
        assert await PriceService().get_forex_rate("USD", "EUR") == Decimal("0.866")

    assert redis_partage.lectures == 1


@pytest.mark.asyncio
async def test_un_taux_inchange_n_est_pas_reecrit(redis_partage):
    await redis_client.cache_forex_rate("USD", "EUR", 0.86)
    await redis_client.cache_forex_rate("USD", "EUR", 0.86)
    assert redis_partage.ecritures == 1

    await redis_client.cache_forex_rate("USD", "EUR", 0.87)
    assert redis_partage.ecritures == 2, "un taux qui change est bien écrit"
