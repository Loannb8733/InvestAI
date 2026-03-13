"""WebSocket endpoint for real-time price streaming.

Supports all asset types via Redis pub/sub integration:
- Crypto: Direct Binance WS stream + Celery pub/sub fallback
- Stocks/ETF: Celery price_updates pub/sub channel
- Heartbeat every 30s to detect stale connections
"""

import asyncio
import json
from typing import Dict, Optional, Set

import aiohttp
import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

# Active connections: ws -> set of symbols
active_connections: Dict[WebSocket, Set[str]] = {}

BINANCE_WS_URL = "wss://stream.binance.com:9443/ws"

# Redis pub/sub channel name (must match what Celery tasks publish to)
PRICE_UPDATES_CHANNEL = "price_updates"

# Heartbeat interval in seconds
HEARTBEAT_INTERVAL = 30

# Redis pub/sub subscriber singleton
_pubsub_task: Optional[asyncio.Task] = None
_pubsub_redis: Optional[aioredis.Redis] = None


async def get_pubsub_redis() -> aioredis.Redis:
    """Get or create the async Redis client for pub/sub."""
    global _pubsub_redis
    if _pubsub_redis is None:
        from app.core.redis_client import redis_ssl_kwargs

        _pubsub_redis = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            **redis_ssl_kwargs(),
        )
    return _pubsub_redis


async def verify_ws_token(token: str) -> bool:
    """Verify JWT token for WebSocket auth.

    Only accepts access tokens (type="access"). Refresh tokens are
    long-lived (7 days) and must not grant WebSocket access.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        # Reject refresh tokens — only access tokens should grant WS access
        if payload.get("type") != "access":
            return False
        return True
    except JWTError:
        return False


async def broadcast_price_update(
    symbol: str,
    price: float,
    change_24h_percent: float,
    asset_type: str = "crypto",
) -> None:
    """Broadcast a price update to all clients watching the given symbol."""
    payload = json.dumps(
        {
            "type": "price",
            "symbol": symbol,
            "price": price,
            "change_24h_percent": change_24h_percent,
            "asset_type": asset_type,
        }
    )

    disconnected = []
    for client, client_symbols in active_connections.items():
        if symbol in client_symbols:
            try:
                await client.send_text(payload)
            except Exception:
                disconnected.append(client)

    for client in disconnected:
        active_connections.pop(client, None)


# ============== Redis Pub/Sub Listener ==============


async def redis_pubsub_listener() -> None:
    """Subscribe to Redis price_updates channel and broadcast to WebSocket clients.

    This captures price updates published by Celery tasks for ALL asset types
    (crypto, stocks, ETFs) and forwards them to connected WebSocket clients.
    """
    while True:
        try:
            r = await get_pubsub_redis()
            pubsub = r.pubsub()
            await pubsub.subscribe(PRICE_UPDATES_CHANNEL)
            logger.info("Redis pub/sub listener started on channel: %s", PRICE_UPDATES_CHANNEL)

            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue

                try:
                    data = json.loads(message["data"])
                    symbol = data.get("symbol", "").upper()
                    price = float(data.get("price", 0))
                    change_pct = float(data.get("change_24h_percent", 0))
                    asset_type = data.get("asset_type", "crypto")

                    if symbol and price > 0:
                        await broadcast_price_update(symbol, price, change_pct, asset_type)
                except (json.JSONDecodeError, ValueError, KeyError) as e:
                    logger.debug("Invalid pub/sub message: %s", e)

        except asyncio.CancelledError:
            logger.info("Redis pub/sub listener cancelled")
            break
        except Exception as e:
            logger.warning("Redis pub/sub listener error: %s — retrying in 5s", e)
            await asyncio.sleep(5)


async def ensure_pubsub_listener() -> None:
    """Ensure the Redis pub/sub listener background task is running."""
    global _pubsub_task
    if _pubsub_task is None or _pubsub_task.done():
        _pubsub_task = asyncio.create_task(redis_pubsub_listener())


# ============== Binance WS Stream (crypto-specific) ==============


async def binance_price_stream(symbols: Set[str]) -> None:
    """Connect to Binance WS and broadcast prices to all connected clients."""
    if not symbols:
        return

    streams = "/".join(f"{s.lower()}usdt@miniTicker" for s in symbols)
    url = f"wss://stream.binance.com:9443/stream?streams={streams}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(url, heartbeat=20) as ws:
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        if "data" in data:
                            ticker = data["data"]
                            symbol = ticker.get("s", "").replace("USDT", "")
                            price = float(ticker.get("c", 0))
                            change_pct = float(ticker.get("P", 0))

                            await broadcast_price_update(symbol, price, change_pct, asset_type="crypto")

                    elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED):
                        break
    except Exception as e:
        logger.warning("Binance WS stream error: %s", e)


# Background task reference for Binance stream
_stream_task: Optional[asyncio.Task] = None
_current_symbols: Set[str] = set()


async def ensure_stream(symbols: Set[str]) -> None:
    """Start or restart the Binance stream if symbols changed."""
    global _stream_task, _current_symbols

    new_symbols = symbols - _current_symbols
    if not new_symbols and _stream_task and not _stream_task.done():
        return

    _current_symbols = symbols.copy()

    if _stream_task and not _stream_task.done():
        _stream_task.cancel()
        try:
            await _stream_task
        except (asyncio.CancelledError, Exception):
            pass

    if _current_symbols:
        _stream_task = asyncio.create_task(binance_price_stream(_current_symbols))


def get_all_watched_symbols() -> Set[str]:
    """Collect all symbols watched by any client."""
    result: Set[str] = set()
    for symbols in active_connections.values():
        result.update(symbols)
    return result


# ============== Heartbeat ==============


async def heartbeat_loop(websocket: WebSocket) -> None:
    """Send heartbeat ping every 30s to detect stale connections."""
    try:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            try:
                await websocket.send_text(json.dumps({"type": "ping"}))
            except Exception:
                # Connection is dead, exit loop
                break
    except asyncio.CancelledError:
        pass


# ============== WebSocket Endpoint ==============


@router.websocket("/ws/prices")
async def websocket_prices(
    websocket: WebSocket,
) -> None:
    """WebSocket endpoint for real-time asset prices (all types).

    Connect with: ws://host/api/v1/ws/prices
    First message must be auth: {"action": "auth", "token": "JWT_TOKEN"}
    Send JSON to subscribe: {"action": "subscribe", "symbols": ["BTC", "ETH", "AAPL"]}
    Send JSON to unsubscribe: {"action": "unsubscribe", "symbols": ["BTC"]}
    Responds to: {"action": "pong"} for heartbeat acknowledgement

    Receives price updates:
      {"type": "price", "symbol": "BTC", "price": 45000.5, "change_24h_percent": 2.5, "asset_type": "crypto"}

    Heartbeat: Server sends {"type": "ping"} every 30s.
    Client should respond with {"action": "pong"}.
    """
    await websocket.accept()

    # Auth: expect token as first message (avoids JWT in URL / server logs)
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=10)
        msg = json.loads(raw)
        token = msg.get("token", "")
        if not token or not await verify_ws_token(token):
            await websocket.send_text(json.dumps({"type": "error", "message": "Unauthorized"}))
            await websocket.close(code=4001, reason="Unauthorized")
            return
        await websocket.send_text(json.dumps({"type": "auth", "status": "ok"}))
    except (asyncio.TimeoutError, json.JSONDecodeError, Exception):
        await websocket.close(code=4001, reason="Auth timeout or invalid")
        return
    active_connections[websocket] = set()

    # Ensure Redis pub/sub listener is running (for Celery price updates)
    await ensure_pubsub_listener()

    # Start heartbeat for this connection
    heartbeat_task = asyncio.create_task(heartbeat_loop(websocket))

    try:
        while True:
            text = await websocket.receive_text()
            try:
                msg = json.loads(text)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"error": "Invalid JSON"}))
                continue

            action = msg.get("action")
            symbols = set(s.upper() for s in msg.get("symbols", []))

            if action == "subscribe":
                if not symbols:
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "error",
                                "message": 'No symbols provided. Send {"action": "subscribe", "symbols": ["BTC", "AAPL"]}',
                            }
                        )
                    )
                    continue

                active_connections[websocket].update(symbols)
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "subscribed",
                            "symbols": list(active_connections[websocket]),
                        }
                    )
                )
                # Start/update Binance stream for crypto symbols
                # (non-crypto symbols are handled by Redis pub/sub from Celery)
                await ensure_stream(get_all_watched_symbols())

            elif action == "unsubscribe":
                active_connections[websocket] -= symbols
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "unsubscribed",
                            "symbols": list(symbols),
                        }
                    )
                )

            elif action == "pong":
                # Heartbeat acknowledgement from client — no action needed
                pass

            else:
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "error",
                            "message": f"Unsupported action: {action}. Use 'subscribe', 'unsubscribe', or 'pong'.",
                        }
                    )
                )

    except WebSocketDisconnect:
        pass
    finally:
        heartbeat_task.cancel()
        active_connections.pop(websocket, None)
        # If no more clients, symbols will be empty on next ensure_stream call
