import asyncio
import json
import os
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import parse_qsl

import httpx
import pytest

FROZEN_NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
GOLDEN_DIR = Path(__file__).parent / "golden"
UPDATE = os.environ.get("GOLDEN_UPDATE") == "1"
SECRET_PARAMS = frozenset({"signature", "sign", "timestamp", "recvWindow", "nonce", "sig", "api_key", "apiKey", "key"})

Payload = Any | Callable[[httpx.Request], Any]


class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz: Any = None) -> "FrozenDatetime":
        moment = FROZEN_NOW if tz is not None else FROZEN_NOW.replace(tzinfo=None)
        return cls.fromtimestamp(moment.timestamp(), tz) if tz is not None else cls(*moment.timetuple()[:6])

    @classmethod
    def utcnow(cls) -> "FrozenDatetime":
        return cls(*FROZEN_NOW.timetuple()[:6])


class ScriptedApi:
    """Réponses par (méthode, chemin) servies dans l'ordre ; la dernière se répète, un chemin inconnu rend 404."""

    def __init__(self) -> None:
        self.scripts: dict[tuple[str, str], list[tuple[int, Payload]]] = {}
        self.calls: list[str] = []

    def on(self, method: str, path: str, *payloads: Payload, status: int = 200) -> None:
        self.scripts.setdefault((method, path), []).extend((status, p) for p in payloads)

    def respond(self, request: httpx.Request) -> httpx.Response:
        params = sorted({k for k, _ in parse_qsl(request.url.query.decode())} - SECRET_PARAMS)
        body_keys: list[str] = []
        if request.content:
            try:
                body = json.loads(request.content)
                body_keys = sorted(set(body) - SECRET_PARAMS) if isinstance(body, dict) else []
            except ValueError:
                body_keys = sorted({k for k, _ in parse_qsl(request.content.decode())} - SECRET_PARAMS)
        self.calls.append(f"{request.method} {request.url.host}{request.url.path} q={params} b={body_keys}")
        queue = self.scripts.get((request.method, request.url.path))
        if not queue:
            return httpx.Response(404, json={"error": "not scripted"}, request=request)
        status, payload = queue.pop(0) if len(queue) > 1 else queue[0]
        content = payload(request) if callable(payload) else payload
        return httpx.Response(status, json=content, request=request)


def install(monkeypatch: pytest.MonkeyPatch, *modules: ModuleType) -> ScriptedApi:
    api = ScriptedApi()

    async def handle_async(_: Any, request: httpx.Request) -> httpx.Response:
        return api.respond(request)

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", handle_async)
    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    for module in modules:
        if hasattr(module, "datetime"):
            monkeypatch.setattr(module, "datetime", FrozenDatetime)
        if hasattr(module, "asyncio"):
            monkeypatch.setattr(module.asyncio, "sleep", no_sleep)
    return api


def plain(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {k: plain(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [plain(v) for v in value]
    if isinstance(value, set | frozenset):
        return sorted(plain(v) for v in value)
    if isinstance(value, Decimal):
        return str(value.normalize())
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


async def record(api: ScriptedApi, call: Callable[[], Awaitable[Any]]) -> dict[str, Any]:
    """Résultat d'un appel et résumé des requêtes qu'il a émises."""
    api.calls.clear()
    try:
        result: Any = plain(await call())
    except Exception as exc:  # noqa: BLE001
        result = {"raised": type(exc).__name__}
    return {"result": result, "requests": dict(sorted(Counter(api.calls).items()))}


def assert_golden(name: str, observed: dict[str, Any]) -> None:
    path = GOLDEN_DIR / f"{name}.json"
    rendered = json.dumps(observed, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if UPDATE or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
        return
    assert path.read_text(encoding="utf-8") == rendered, f"golden {name} différent (GOLDEN_UPDATE=1 pour accepter)"
