import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any

import pytest
import redis
from starlette.testclient import TestClient, WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

from app.core.redis_client import PRICE_UPDATES_CHANNEL, redis_async_url
from app.domains.identity.tokens import create_token
from app.domains.system import price_socket
from app.main import app

GOLDEN = Path(__file__).parent / "golden" / "price_socket.json"
UPDATE = os.environ.get("GOLDEN_UPDATE") == "1"
URL = "/api/v1/ws/prices"
TICK = {"symbol": "btc", "price": 42000.5, "change_24h_percent": 1.5, "asset_type": "crypto"}


class _Transcript:
    def __init__(self) -> None:
        self.lines: list[dict[str, Any]] = []

    def send(self, ws: WebSocketTestSession, text: str, shown: str | None = None) -> None:
        self.lines.append({"sent": shown or text})
        ws.send_text(text)

    def receive(self, ws: WebSocketTestSession) -> Any:
        try:
            message = json.loads(ws.receive_text())
        except WebSocketDisconnect as closed:
            self.lines.append({"closed": closed.code, "reason": closed.reason})
            return None
        if isinstance(message.get("symbols"), list):
            message["symbols"] = sorted(message["symbols"])
        self.lines.append({"received": message})
        return message


def _auth(token: str) -> str:
    return json.dumps({"action": "auth", "token": token})


def _refused(transcript: _Transcript, client: TestClient, first: str, shown: str | None = None) -> None:
    with client.websocket_connect(URL) as ws:
        transcript.send(ws, first, shown)
        while transcript.receive(ws) is not None:
            pass


def _publish_until_stopped(stop: threading.Event) -> None:
    publisher = redis.Redis.from_url(redis_async_url())
    while not stop.wait(0.05):
        publisher.publish(PRICE_UPDATES_CHANNEL, json.dumps(TICK))
    publisher.close()


def _session(transcript: _Transcript, client: TestClient, token: str) -> None:
    with client.websocket_connect(URL) as ws:
        transcript.send(ws, _auth(token), _auth("<access>"))
        transcript.receive(ws)
        for message in (
            "pas du json",
            json.dumps({"action": "subscribe", "symbols": []}),
            json.dumps({"action": "subscribe", "symbols": ["btc", "AAPL"]}),
            json.dumps({"action": "unsubscribe", "symbols": ["aapl"]}),
            json.dumps({"action": "dance"}),
        ):
            transcript.send(ws, message)
            transcript.receive(ws)
        transcript.send(ws, json.dumps({"action": "pong"}))
        stop = threading.Event()
        publisher = threading.Thread(target=_publish_until_stopped, args=(stop,))
        publisher.start()
        try:
            transcript.receive(ws)
        finally:
            stop.set()
            publisher.join()


@pytest.mark.usefixtures("empty_test_redis")
def test_price_socket_matches_golden(monkeypatch: pytest.MonkeyPatch) -> None:
    streamed: list[list[str]] = []

    async def binance_stream(symbols: set[str]) -> None:
        streamed.append(sorted(symbols))

    monkeypatch.setattr(price_socket, "binance_prices", binance_stream)
    monkeypatch.setattr(price_socket, "price_hub", price_socket.PriceHub())
    subject = str(uuid.uuid4())
    transcript = _Transcript()
    client = TestClient(app)
    _refused(transcript, client, "pas du json")
    _refused(transcript, client, _auth("faux"))
    _refused(transcript, client, _auth(create_token(subject, "refresh")), _auth("<refresh>"))
    _session(transcript, client, create_token(subject))
    rendered = json.dumps({"transcript": transcript.lines, "binance_streams": streamed}, indent=2, ensure_ascii=False)
    if UPDATE or not GOLDEN.exists():
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(rendered + "\n", encoding="utf-8")
    assert GOLDEN.read_text(encoding="utf-8") == rendered + "\n", "golden price_socket différent (GOLDEN_UPDATE=1)"
