import json
from decimal import Decimal
from typing import Any

import pytest

from app.domains.market_data.fx.spot import spot_rates
from app.domains.system import price_socket

RATES = {("USD", "EUR"): Decimal("0.9"), ("EUR", "USD"): Decimal("1.1")}


class _Socket:
    def __init__(self) -> None:
        self.received: list[dict[str, Any]] = []

    async def send_text(self, text: str) -> None:
        self.received.append(json.loads(text))


async def _rate(from_ccy: str, to_ccy: str) -> Decimal | None:
    return Decimal("1") if from_ccy == to_ccy else RATES.get((from_ccy, to_ccy))


async def _held(symbols: set[str]) -> set[str]:
    return set()


@pytest.fixture
def hub(monkeypatch: pytest.MonkeyPatch) -> price_socket.PriceHub:
    hub = price_socket.PriceHub()
    monkeypatch.setattr(price_socket, "price_hub", hub)
    monkeypatch.setattr(price_socket, "crypto_symbols", _held)
    monkeypatch.setattr(spot_rates, "get", _rate)
    return hub


async def _client(hub: price_socket.PriceHub, subscription: dict[str, Any]) -> _Socket:
    socket = _Socket()
    hub.clients[socket] = set()  # type: ignore[index]
    await price_socket._handle(socket, json.dumps({"action": "subscribe", **subscription}))  # type: ignore[arg-type]
    socket.received.clear()
    return socket


def _prices(socket: _Socket) -> list[tuple[float, str]]:
    return [(message["price"], message["currency"]) for message in socket.received if message["type"] == "price"]


async def test_each_client_receives_its_own_currency(hub: price_socket.PriceHub) -> None:
    euros = await _client(hub, {"symbols": ["btc"]})
    dollars = await _client(hub, {"symbols": ["BTC"], "currency": "usd"})
    await hub.broadcast("BTC", 100.0, 1.5, "crypto", "USD")
    await hub.broadcast("BTC", 90.0, 1.5, "crypto", "EUR")
    assert _prices(euros) == [(90.0, "EUR"), (90.0, "EUR")]
    assert _prices(dollars) == [(100.0, "USD"), (99.0, "USD")]


async def test_a_price_without_rate_is_not_sent(hub: price_socket.PriceHub) -> None:
    francs = await _client(hub, {"symbols": ["BTC"], "currency": "CHF"})
    await hub.broadcast("BTC", 100.0, 1.5, "crypto", "USD")
    assert _prices(francs) == []


async def test_an_unknown_currency_is_refused(hub: price_socket.PriceHub) -> None:
    socket = _Socket()
    hub.clients[socket] = set()  # type: ignore[index]
    await price_socket._handle(socket, json.dumps({"action": "subscribe", "symbols": ["BTC"], "currency": "XYZ"}))  # type: ignore[arg-type]
    assert socket.received[0]["type"] == "error"
    assert hub.clients[socket] == set()  # type: ignore[index]


async def test_binance_ticks_are_quoted_in_dollars(hub: price_socket.PriceHub) -> None:
    euros = await _client(hub, {"symbols": ["BTC"]})
    await price_socket._relay_ticker({"data": {"s": "BTCUSDT", "c": "100", "P": "1.5"}})
    assert _prices(euros) == [(90.0, "EUR")]


async def test_published_ticks_keep_their_currency(hub: price_socket.PriceHub) -> None:
    dollars = await _client(hub, {"symbols": ["AAPL"], "currency": "USD"})
    tick = {"symbol": "AAPL", "price": 100.0, "change_24h_percent": 0.5, "asset_type": "stock", "currency": "EUR"}
    await hub._relay({"data": json.dumps(tick)})
    assert _prices(dollars) == [(110.0, "USD")]
