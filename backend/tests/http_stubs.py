from collections.abc import Callable
from typing import Any

import httpx
import pytest

Handler = Callable[[httpx.Request], httpx.Response]


class HttpStub:
    """Remplace tout le réseau httpx : seules les routes déclarées répondent."""

    def __init__(self) -> None:
        self.routes: dict[str, Handler] = {}
        self.requests: list[httpx.Request] = []

    def on(self, host: str, handler: Handler) -> None:
        self.routes[host] = handler

    def json(self, host: str, payload: Any, status_code: int = 200) -> None:
        self.on(host, lambda request: httpx.Response(status_code, json=payload, request=request))

    def respond(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        handler = self.routes.get(request.url.host)
        if handler is None:
            raise httpx.ConnectError(f"no network in tests: {request.url}", request=request)
        return handler(request)


def install(monkeypatch: pytest.MonkeyPatch) -> HttpStub:
    stub = HttpStub()

    async def handle_async(_: Any, request: httpx.Request) -> httpx.Response:
        return stub.respond(request)

    def handle_sync(_: Any, request: httpx.Request) -> httpx.Response:
        return stub.respond(request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", handle_async)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handle_sync)
    return stub
