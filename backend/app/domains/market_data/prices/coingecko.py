import logging
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any

import httpx

from app.core.redis_client import _get_redis_txt
from app.core.symbol_map import COINGECKO_SYMBOL_MAP
from app.domains.market_data.prices.quote import PriceQuote

logger = logging.getLogger(__name__)

BASE_URL = "https://api.coingecko.com/api/v3"
TIMEOUT_S = 3.0
ID_TTL_S = 7 * 24 * 3600
HISTORICAL_TTL_S = 24 * 3600


async def _cached_id(key: str) -> str | None:
    try:
        cached = await (await _get_redis_txt()).get(key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Cache des identifiants CoinGecko illisible : %s", exc)
        return None
    return str(cached) if cached else None


class CoinGecko:
    """Client CoinGecko : identifiant d'un symbole, cours courants, cours d'un jour passé."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=TIMEOUT_S, headers={"Accept": "application/json"})
        self._ids: dict[str, str] = dict(COINGECKO_SYMBOL_MAP)

    async def _get(self, path: str, params: dict[str, str]) -> Any:
        response = await self._client.get(f"{BASE_URL}{path}", params=params)
        response.raise_for_status()
        return response.json()

    async def coin_id(self, symbol: str) -> str:
        """Identifiant CoinGecko : table connue, Redis, recherche ; à défaut le symbole en minuscules.

        Redis indisponible, la recherche a quand même lieu.
        """
        if symbol in self._ids:
            return self._ids[symbol]
        key = f"coingecko_id:{symbol}"
        found = await _cached_id(key) or await self._searched_id(symbol, key)
        if not found:
            return symbol.lower()
        self._ids[symbol] = found
        return found

    async def _searched_id(self, symbol: str, key: str) -> str | None:
        try:
            found = await self._search(symbol)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Identifiant CoinGecko introuvable pour %s : %s", symbol, exc)
            return None
        if found:
            try:
                await (await _get_redis_txt()).set(key, found, ex=ID_TTL_S)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Identifiant CoinGecko de %s non mis en cache : %s", symbol, exc)
        return found

    async def _search(self, symbol: str) -> str | None:
        coins = (await self._get("/search", {"query": symbol})).get("coins", [])
        return next((str(c["id"]) for c in coins if c.get("id") and str(c.get("symbol", "")).upper() == symbol), None)

    async def quotes(self, symbols: Sequence[str], currency: str) -> dict[str, PriceQuote]:
        """Cours de ``symbols`` (en majuscules) ; un symbole sans cours positif est absent du résultat."""
        ids = {await self.coin_id(s): s for s in symbols}
        ccy = currency.lower()
        params = {
            "ids": ",".join(ids),
            "vs_currencies": ccy,
            "include_24hr_change": "true",
            "include_24hr_vol": "true",
            "include_market_cap": "true",
        }
        try:
            data = await self._get("/simple/price", params)
        except Exception as exc:  # noqa: BLE001
            logger.warning("CoinGecko indisponible pour %s : %s", ",".join(symbols), exc)
            return {}
        found: dict[str, PriceQuote] = {}
        for coin, symbol in ids.items():
            row = data.get(coin) or {}
            price = Decimal(str(row.get(ccy) or 0))
            if price <= 0:
                continue
            change = float(row.get(f"{ccy}_24h_change") or 0)
            found[symbol] = PriceQuote(
                price=price,
                change_percent_24h=change,
                change_24h=float(price) * change / 100,
                volume_24h=float(row.get(f"{ccy}_24h_vol") or 0),
                market_cap=float(row.get(f"{ccy}_market_cap") or 0),
            )
        return found

    async def price_on(self, symbol: str, day: date, currency: str) -> Decimal | None:
        """Cours de ``symbol`` le jour ``day`` ; None si CoinGecko n'en a pas."""
        coin = await self.coin_id(symbol)
        ccy = currency.lower()
        stamp = day.strftime("%d-%m-%Y")
        key = f"price:historical:{coin}:{stamp}:{ccy}"
        try:
            cached = await (await _get_redis_txt()).get(key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Lecture du cache de cours historique impossible : %s", exc)
            cached = None
        if cached:
            return Decimal(str(cached))
        try:
            data = await self._get(f"/coins/{coin}/history", {"date": stamp, "localization": "false"})
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cours historique indisponible pour %s le %s : %s", symbol, stamp, exc)
            return None
        value = data.get("market_data", {}).get("current_price", {}).get(ccy)
        if not value:
            return None
        price = Decimal(str(value))
        try:
            await (await _get_redis_txt()).set(key, str(price), ex=HISTORICAL_TTL_S)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Écriture du cache de cours historique impossible : %s", exc)
        return price

    async def btc_dominance(self) -> float | None:
        """Part du bitcoin dans la capitalisation totale, en pourcentage ; None si CoinGecko ne répond pas."""
        try:
            data = await self._get("/global", {})
        except Exception as exc:  # noqa: BLE001
            logger.warning("Dominance BTC indisponible : %s", exc)
            return None
        value = data.get("data", {}).get("market_cap_percentage", {}).get("btc")
        return float(value) if value is not None else None
