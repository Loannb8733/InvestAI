import ast
from pathlib import Path

import pytest

from app.core import redis_client
from app.domains.market_data.prices import tasks
from app.domains.market_data.prices.service import PriceService

URL = "redis://cache.exemple:6380/2"


class _RecordingClient:
    def __init__(self) -> None:
        self.published: list[str] = []

    def publish(self, channel: str, message: str) -> None:
        self.published.append(channel)


def test_publisher_follows_redis_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """REDIS_HOST/REDIS_PORT n'existent que dans docker-compose : sur Render, seul REDIS_URL est défini."""
    monkeypatch.setattr(redis_client, "redis_async_url", lambda: URL)
    monkeypatch.setattr(tasks, "redis_async_url", lambda: URL)

    options = tasks.sync_redis().connection_pool.connection_kwargs

    assert (options["host"], options["port"], options["db"]) == ("cache.exemple", 6380, 2)


def test_publisher_has_network_timeouts() -> None:
    options = tasks.sync_redis().connection_pool.connection_kwargs

    assert options["socket_timeout"] == redis_client.REDIS_DELAI_RESEAU
    assert options["socket_connect_timeout"] == redis_client.REDIS_DELAI_RESEAU


def test_publications_share_one_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    """Une connexion par cours coûtait quatre commandes Upstash au lieu d'une."""
    created: list[_RecordingClient] = []

    def client() -> _RecordingClient:
        created.append(_RecordingClient())
        return created[-1]

    monkeypatch.setattr(tasks, "_publisher", None)
    monkeypatch.setattr(tasks, "sync_redis", client)

    for symbol in ("BTC", "ETH", "SOL"):
        tasks.publish_price_update(symbol, 1.0, 0.0, "crypto")

    assert len(created) == 1
    assert len(created[0].published) == 3


def test_only_existing_price_feed_methods_are_called() -> None:
    """Le `except` voisin transformait une AttributeError en « 0 mis à jour »."""
    tree = ast.parse(Path(tasks.__file__).read_text(encoding="utf-8"))
    called = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "price_feed"
    }
    assert called
    assert not [name for name in called if not hasattr(PriceService, name)]
