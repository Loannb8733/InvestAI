import asyncio
import contextlib
import json
from typing import Any

import aiohttp
import jwt
import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import func, select

from app.core.config import settings
from app.core.db.session import session_factory
from app.core.logging import get_logger
from app.core.redis_client import PRICE_UPDATES_CHANNEL, redis_async_url, redis_ssl_kwargs
from app.domains.portfolio.models import Asset, AssetType

logger = get_logger(__name__)

router = APIRouter()

BINANCE_STREAM_URL = "wss://stream.binance.com:9443/stream?streams={streams}"
HEARTBEAT_S = 30
AUTH_TIMEOUT_S = 10
LISTENER_RETRY_S = 5
SUBSCRIBE_HELP = 'No symbols provided. Send {"action": "subscribe", "symbols": ["BTC", "AAPL"]}'


def is_access_token(token: str) -> bool:
    """Vrai pour un jeton d'accès valide ; un jeton de rafraîchissement, valable 7 jours, n'ouvre pas le flux."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except jwt.InvalidTokenError:
        return False
    return bool(payload.get("type") == "access")


class PriceHub:
    """Clients abonnés aux cours, et le flux Binance et l'écoute Redis qu'ils partagent."""

    def __init__(self) -> None:
        self.clients: dict[WebSocket, set[str]] = {}
        self._redis: aioredis.Redis | None = None
        self._listener: asyncio.Task[None] | None = None
        self._stream: asyncio.Task[None] | None = None
        self._streamed: set[str] = set()

    async def broadcast(self, symbol: str, price: float, change_24h_percent: float, asset_type: str) -> None:
        """Envoie un cours aux clients abonnés au symbole ; un client injoignable est retiré."""
        payload = json.dumps(
            {
                "type": "price",
                "symbol": symbol,
                "price": price,
                "change_24h_percent": change_24h_percent,
                "asset_type": asset_type,
            }
        )
        gone = []
        for client, symbols in self.clients.items():
            if symbol in symbols:
                try:
                    await client.send_text(payload)
                except Exception:  # noqa: BLE001
                    gone.append(client)
        for client in gone:
            self.clients.pop(client, None)

    async def _relay(self, message: dict[str, Any]) -> None:
        try:
            data = json.loads(message["data"])
            symbol = data.get("symbol", "").upper()
            price = float(data.get("price", 0))
            change = float(data.get("change_24h_percent", 0))
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            logger.debug("Invalid pub/sub message: %s", exc)
            return
        if symbol and price > 0:
            await self.broadcast(symbol, price, change, data.get("asset_type", "crypto"))

    async def _redis_client(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(
                redis_async_url(), encoding="utf-8", decode_responses=True, **redis_ssl_kwargs()
            )
        return self._redis

    async def _listen(self) -> None:
        while True:
            try:
                pubsub = (await self._redis_client()).pubsub()
                await pubsub.subscribe(PRICE_UPDATES_CHANNEL)
                logger.info("Redis pub/sub listener started on channel: %s", PRICE_UPDATES_CHANNEL)
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        await self._relay(message)
            except asyncio.CancelledError:
                logger.info("Redis pub/sub listener cancelled")
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning("Redis pub/sub listener error: %s — retrying in 5s", exc)
                await asyncio.sleep(LISTENER_RETRY_S)

    def listen(self) -> None:
        """Démarre l'écoute des cours publiés dans Redis, si elle ne tourne pas déjà."""
        if self._listener is None or self._listener.done():
            self._listener = asyncio.create_task(self._listen())

    def watched(self) -> set[str]:
        """Symboles suivis par au moins un client."""
        return set().union(*self.clients.values())

    async def stream(self, symbols: set[str]) -> None:
        """Aligne le flux Binance sur ``symbols`` : relancé quand la liste change ou que le flux s'est arrêté, coupé
        quand elle est vide."""
        if symbols == self._streamed and self._stream and not self._stream.done():
            return
        self._streamed = set(symbols)
        if self._stream and not self._stream.done():
            self._stream.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._stream
        if self._streamed:
            self._stream = asyncio.create_task(binance_prices(self._streamed))


price_hub = PriceHub()


async def crypto_symbols(symbols: set[str]) -> set[str]:
    """Symboles qui désignent une crypto détenue dans l'application : seuls ceux-là ont un cours Binance."""
    if not symbols:
        return set()
    upper = func.upper(Asset.symbol)
    query = select(upper).where(Asset.asset_type == AssetType.CRYPTO, upper.in_(symbols)).distinct()
    async with session_factory() as db:
        return set((await db.execute(query)).scalars().all())


async def _follow_clients() -> None:
    await price_hub.stream(await crypto_symbols(price_hub.watched()))


async def _relay_ticker(data: dict[str, Any]) -> None:
    ticker = data["data"]
    symbol = ticker.get("s", "").replace("USDT", "")
    await price_hub.broadcast(symbol, float(ticker.get("c", 0)), float(ticker.get("P", 0)), "crypto")


async def binance_prices(symbols: set[str]) -> None:
    """Relaie aux clients les cours Binance des symboles, cotés en USDT."""
    if not symbols:
        return
    streams = "/".join(f"{symbol.lower()}usdt@miniTicker" for symbol in symbols)
    try:
        async with (
            aiohttp.ClientSession() as session,
            session.ws_connect(BINANCE_STREAM_URL.format(streams=streams), heartbeat=20) as ws,
        ):
            async for message in ws:
                if message.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(message.data)
                    if "data" in data:
                        await _relay_ticker(data)
                elif message.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED):
                    break
    except Exception as exc:  # noqa: BLE001
        logger.warning("Binance WS stream error: %s", exc)


async def _heartbeat(websocket: WebSocket) -> None:
    with contextlib.suppress(asyncio.CancelledError):
        while True:
            await asyncio.sleep(HEARTBEAT_S)
            try:
                await websocket.send_text(json.dumps({"type": "ping"}))
            except Exception:  # noqa: BLE001
                break


async def _authenticate(websocket: WebSocket) -> bool:
    try:
        message = json.loads(await asyncio.wait_for(websocket.receive_text(), timeout=AUTH_TIMEOUT_S))
        token = message.get("token", "")
        if not token or not is_access_token(token):
            await websocket.send_text(json.dumps({"type": "error", "message": "Unauthorized"}))
            await websocket.close(code=4001, reason="Unauthorized")
            return False
        await websocket.send_text(json.dumps({"type": "auth", "status": "ok"}))
    except Exception:  # noqa: BLE001
        await websocket.close(code=4001, reason="Auth timeout or invalid")
        return False
    return True


async def _subscribe(websocket: WebSocket, symbols: set[str]) -> None:
    if not symbols:
        await websocket.send_text(json.dumps({"type": "error", "message": SUBSCRIBE_HELP}))
        return
    price_hub.clients[websocket].update(symbols)
    await websocket.send_text(json.dumps({"type": "subscribed", "symbols": list(price_hub.clients[websocket])}))
    await _follow_clients()


async def _handle(websocket: WebSocket, text: str) -> None:
    try:
        message = json.loads(text)
    except json.JSONDecodeError:
        await websocket.send_text(json.dumps({"error": "Invalid JSON"}))
        return
    action = message.get("action")
    symbols = {symbol.upper() for symbol in message.get("symbols", [])}
    if action == "subscribe":
        await _subscribe(websocket, symbols)
    elif action == "unsubscribe":
        price_hub.clients[websocket] -= symbols
        await websocket.send_text(json.dumps({"type": "unsubscribed", "symbols": list(symbols)}))
        await _follow_clients()
    elif action != "pong":
        unsupported = f"Unsupported action: {action}. Use 'subscribe', 'unsubscribe', or 'pong'."
        await websocket.send_text(json.dumps({"type": "error", "message": unsupported}))


@router.websocket("/ws/prices")
async def websocket_prices(websocket: WebSocket) -> None:
    """Cours en temps réel, tous types d'actifs.

    Le premier message authentifie : ``{"action": "auth", "token": JWT}``. Ensuite ``subscribe`` et ``unsubscribe``
    avec ``symbols``, et ``pong`` en réponse au ``{"type": "ping"}`` envoyé toutes les 30 s. Chaque cours arrive en
    ``{"type": "price", "symbol", "price", "change_24h_percent", "asset_type"}``.
    """
    await websocket.accept()
    if not await _authenticate(websocket):
        return
    price_hub.clients[websocket] = set()
    price_hub.listen()
    heartbeat = asyncio.create_task(_heartbeat(websocket))
    try:
        while True:
            await _handle(websocket, await websocket.receive_text())
    except WebSocketDisconnect:
        pass
    finally:
        heartbeat.cancel()
        price_hub.clients.pop(websocket, None)
        await _follow_clients()
