"""Un Redis qui ne répond plus ne doit pas suspendre l'API.

Chaque jeton d'accès porte un `jti` : chaque requête authentifiée demande donc
à Redis si le jeton a été révoqué. Le contrôle est prévu pour « laisser passer »
quand Redis est en panne — mais ce repli ne se déclenche que sur une erreur.
Un Redis qui a accepté la connexion et ne répond plus (connexion à moitié
ouverte, réseau qui avale les paquets) ne lève rien : sans délai réseau, le
client redis-py attend indéfiniment, et la requête avec lui.

Mesuré avant correction : la requête était toujours suspendue au bout de 10 s.
"""

import asyncio
import time

import pytest
import pytest_asyncio
import redis.asyncio as aioredis
from httpx import AsyncClient

from app.core import redis_client
from app.core.security import create_access_token
from app.models.user import User

# Au-delà, la requête est considérée comme suspendue.
_DELAI_DE_GARDE = 10.0


@pytest_asyncio.fixture
async def redis_muet(monkeypatch):
    """Un serveur qui accepte les connexions et ne répond jamais."""
    connexions: list = []

    async def _ne_rien_repondre(reader, writer):
        connexions.append(writer)
        await asyncio.sleep(3600)

    serveur = await asyncio.start_server(_ne_rien_repondre, "127.0.0.1", 0)
    port = serveur.sockets[0].getsockname()[1]
    url = f"redis://127.0.0.1:{port}/0"
    monkeypatch.setattr(redis_client, "redis_async_url", lambda: url)
    monkeypatch.setattr(redis_client, "redis_ssl_kwargs", lambda: {})
    monkeypatch.setattr(redis_client, "_redis_txt", None)
    monkeypatch.setattr(redis_client, "_redis_bin", None)
    yield
    for client in (redis_client._redis_txt, redis_client._redis_bin):
        if isinstance(client, aioredis.Redis):
            await client.aclose()
    for writer in connexions:
        writer.close()
    serveur.close()


@pytest.mark.asyncio
async def test_une_requete_authentifiee_aboutit_malgre_un_redis_muet(
    client: AsyncClient, regular_user: User, redis_muet
):
    entetes = {"Authorization": f"Bearer {create_access_token(subject=str(regular_user.id))}"}

    debut = time.monotonic()
    try:
        reponse = await asyncio.wait_for(client.get("/api/v1/portfolios", headers=entetes), _DELAI_DE_GARDE)
    except asyncio.TimeoutError:
        pytest.fail(f"requête toujours suspendue après {_DELAI_DE_GARDE:.0f} s : Redis muet bloque l'API")
    duree = time.monotonic() - debut

    assert reponse.status_code == 200, "le contrôle de révocation doit laisser passer, comme prévu"
    assert duree < _DELAI_DE_GARDE


def test_les_clients_redis_de_l_application_ont_un_delai_reseau():
    """Les délais passent par un seul point : un client créé sans eux
    retrouverait l'attente indéfinie."""
    options = redis_client.redis_client_kwargs()

    assert 0 < options["socket_timeout"] <= 5
    assert 0 < options["socket_connect_timeout"] <= 5
