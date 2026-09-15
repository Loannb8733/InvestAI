"""Le client de publication des cours vise le même Redis que le reste de l'application.

`price_updates` construisait son client à partir de REDIS_HOST/REDIS_PORT, qui
n'existent que dans docker-compose. Sur Render, où seul REDIS_URL (Upstash, TLS)
est défini, il visait localhost:6379 : chaque publication échouait au niveau
DEBUG et aucun cours en direct n'atteignait le websocket.
"""

from app.core import redis_client
from app.tasks import price_updates


def test_le_client_suit_redis_url(monkeypatch):
    monkeypatch.setattr(redis_client, "redis_async_url", lambda: "redis://cache.exemple:6380/2")
    # raising=False : sur un client qui ignorerait REDIS_URL, c'est l'assertion qui doit échouer.
    monkeypatch.setattr(price_updates, "redis_async_url", lambda: "redis://cache.exemple:6380/2", raising=False)

    options = price_updates._get_sync_redis().connection_pool.connection_kwargs

    assert (options["host"], options["port"], options["db"]) == ("cache.exemple", 6380, 2)


def test_le_client_a_un_delai_reseau():
    options = price_updates._get_sync_redis().connection_pool.connection_kwargs

    assert options["socket_timeout"] == redis_client.REDIS_DELAI_RESEAU
    assert options["socket_connect_timeout"] == redis_client.REDIS_DELAI_RESEAU


def test_les_publications_partagent_une_connexion(monkeypatch):
    """Une connexion par cours coûtait quatre commandes Upstash au lieu d'une."""
    crees = []

    class _Client:
        def __init__(self):
            self.publies = []
            crees.append(self)

        def publish(self, canal, message):
            self.publies.append(canal)

    monkeypatch.setattr(price_updates, "_client_de_publication", None)
    monkeypatch.setattr(price_updates, "_get_sync_redis", _Client)

    for symbole in ("BTC", "ETH", "SOL"):
        price_updates.publish_price_update(symbole, 1.0, 0.0, "crypto")

    assert len(crees) == 1
    assert len(crees[0].publies) == 3
