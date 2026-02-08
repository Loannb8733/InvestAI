"""WebSocket endpoint for real-time price streaming."""

import asyncio
import json
from typing import Dict, Set

import aiohttp
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from jose import jwt, JWTError

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

# Active connections: ws -> set of symbols
active_connections: Dict[WebSocket, Set[str]] = {}

BINANCE_WS_URL = "wss://stream.binance.com:9443/ws"


async def verify_ws_token(token: str) -> bool:
    """Verify JWT token for WebSocket auth."""
    try:
        jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return True
    except JWTError:
        return False


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

                            payload = json.dumps({
                                "type": "price",
                                "symbol": symbol,
                                "price": price,
                                "change_24h_percent": change_pct,
                            })

                            # Broadcast to all clients watching this symbol
                            disconnected = []
                            for client, client_symbols in active_connections.items():
                                if symbol in client_symbols:
                                    try:
                                        await client.send_text(payload)
                                    except Exception:
                                        disconnected.append(client)

                            for client in disconnected:
                                active_connections.pop(client, None)

                    elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED):
                        break
    except Exception as e:
        logger.warning("Binance WS stream error: %s", e)


# Background task reference
_stream_task: asyncio.Task | None = None
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


@router.websocket("/ws/prices")
async def websocket_prices(
    websocket: WebSocket,
    token: str = Query(default=""),
):
    """WebSocket endpoint for real-time crypto prices.

    Connect with: ws://host/api/v1/ws/prices?token=JWT_TOKEN
    Send JSON to subscribe: {"action": "subscribe", "symbols": ["BTC", "ETH"]}
    Send JSON to unsubscribe: {"action": "unsubscribe", "symbols": ["BTC"]}
    """
    # Auth
    if not token or not await verify_ws_token(token):
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await websocket.accept()
    active_connections[websocket] = set()

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
                active_connections[websocket].update(symbols)
                await websocket.send_text(json.dumps({
                    "type": "subscribed",
                    "symbols": list(active_connections[websocket]),
                }))
                await ensure_stream(get_all_watched_symbols())

            elif action == "unsubscribe":
                active_connections[websocket] -= symbols
                await websocket.send_text(json.dumps({
                    "type": "unsubscribed",
                    "symbols": list(symbols),
                }))

    except WebSocketDisconnect:
        pass
    finally:
        active_connections.pop(websocket, None)
        # If no more clients, symbols will be empty on next ensure_stream call
