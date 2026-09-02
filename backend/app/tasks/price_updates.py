"""Price update tasks.

After updating prices in the Redis cache, each task publishes price updates
to the Redis pub/sub channel ``price_updates`` so that the WebSocket endpoint
can broadcast them to connected clients in real time.
"""


import json
import logging
from typing import Dict, Set

from redis import Redis
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.asset import Asset, AssetType
from app.services.price_service import PriceService
from app.tasks.async_runner import run_async
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# Initialize price service
price_service = PriceService()

# Redis pub/sub channel (must match the channel in websocket.py)
PRICE_UPDATES_CHANNEL = "price_updates"


def _get_sync_redis() -> Redis:
    """Get a synchronous Redis client for publishing from Celery workers."""
    return Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        decode_responses=True,
    )


def publish_price_update(
    symbol: str,
    price: float,
    change_24h_percent: float,
    asset_type: str,
) -> None:
    """Publish a single price update to the Redis pub/sub channel.

    Args:
        symbol: Asset symbol (e.g. "BTC", "AAPL").
        price: Current price.
        change_24h_percent: 24-hour change percentage.
        asset_type: One of "crypto", "stock", "etf".
    """
    try:
        r = _get_sync_redis()
        payload = json.dumps(
            {
                "symbol": symbol.upper(),
                "price": price,
                "change_24h_percent": change_24h_percent,
                "asset_type": asset_type,
            }
        )
        r.publish(PRICE_UPDATES_CHANNEL, payload)
        r.close()
    except Exception as e:
        logger.debug("Failed to publish price update for %s: %s", symbol, e)


async def get_unique_symbols_by_type() -> Dict[str, Set[str]]:
    """Get unique asset symbols grouped by type from database."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Asset.symbol, Asset.asset_type)
            .where(
                Asset.quantity > 0,
            )
            .distinct()
        )
        rows = result.all()

        symbols_by_type: Dict[str, Set[str]] = {
            "crypto": set(),
            "stock": set(),
            "etf": set(),
        }

        for symbol, asset_type in rows:
            if asset_type == AssetType.CRYPTO:
                symbols_by_type["crypto"].add(symbol.upper())
            elif asset_type == AssetType.STOCK:
                symbols_by_type["stock"].add(symbol.upper())
            elif asset_type == AssetType.ETF:
                symbols_by_type["etf"].add(symbol.upper())

        return symbols_by_type


# Corps asynchrones sortis des tâches : `update_all_prices` peut ainsi les
# enchaîner dans une seule boucle. Imbriqués, chaque tâche créait la sienne
# via `run_async`, et l'engine SQLAlchemy async gardait ses connexions liées
# à la première — d'où « Task attached to a different loop » (NEW-14).


async def _maj_crypto():
    symbols_by_type = await get_unique_symbols_by_type()
    crypto_symbols = list(symbols_by_type.get("crypto", set()))

    if not crypto_symbols:
        logger.info("No crypto assets to update")
        return {"updated": 0, "symbols": []}

    logger.info(f"Updating prices for {len(crypto_symbols)} crypto assets: {crypto_symbols[:10]}...")

    # Fetch prices in batches of 50 (CoinGecko limit)
    updated_count = 0
    batch_size = 50

    for i in range(0, len(crypto_symbols), batch_size):
        batch = crypto_symbols[i : i + batch_size]
        try:
            prices = await price_service.get_multiple_crypto_prices(batch)
            for symbol, price_data in prices.items():
                if price_data is not None:
                    updated_count += 1
                    # Publish to Redis pub/sub for WebSocket broadcast
                    publish_price_update(
                        symbol=symbol,
                        price=float(price_data.get("price", 0)),
                        change_24h_percent=float(price_data.get("change_percent_24h", 0)),
                        asset_type="crypto",
                    )
            logger.info(f"Batch {i // batch_size + 1}: Updated {len(prices)} prices")
        except Exception as e:
            logger.error(f"Error fetching crypto prices batch: {e}")

    logger.info(f"Crypto price update complete: {updated_count} prices updated")
    return {"updated": updated_count, "symbols": crypto_symbols[:20]}


async def _maj_actions():
    symbols_by_type = await get_unique_symbols_by_type()
    stock_symbols = list(symbols_by_type.get("stock", set()))
    etf_symbols = list(symbols_by_type.get("etf", set()))

    if not stock_symbols and not etf_symbols:
        logger.info("No stock/ETF assets to update")
        return {"updated": 0, "symbols": []}

    all_symbols = stock_symbols + etf_symbols
    logger.info(f"Updating prices for {len(all_symbols)} stock/ETF assets...")

    updated_count = 0
    for symbol in stock_symbols:
        try:
            price_data = await price_service.get_stock_price(symbol)
            if price_data:
                updated_count += 1
                publish_price_update(
                    symbol=symbol,
                    price=float(price_data.get("price", 0)),
                    change_24h_percent=float(price_data.get("change_percent_24h", 0)),
                    asset_type="stock",
                )
        except Exception as e:
            logger.warning(f"Error fetching price for {symbol}: {e}")

    for symbol in etf_symbols:
        try:
            price_data = await price_service.get_stock_price(symbol)
            if price_data:
                updated_count += 1
                publish_price_update(
                    symbol=symbol,
                    price=float(price_data.get("price", 0)),
                    change_24h_percent=float(price_data.get("change_percent_24h", 0)),
                    asset_type="etf",
                )
        except Exception as e:
            logger.warning(f"Error fetching price for {symbol}: {e}")

    logger.info(f"Stock/ETF price update complete: {updated_count} prices updated")
    return {"updated": updated_count, "symbols": all_symbols[:20]}


async def _maj_taux_change():
    # Common currency pairs
    currencies = ["USD", "GBP", "CHF", "JPY", "CAD", "AUD"]
    base_currency = "EUR"

    updated_count = 0
    for currency in currencies:
        try:
            # `get_exchange_rate` n'a jamais existé : la méthode s'appelle
            # `get_forex_rate`. L'AttributeError était rattrapé par le `except`
            # ci-dessous, si bien que la tâche rapportait « 0 mis à jour » sans
            # jamais rien tenter — et personne ne l'a vu, car elle n'est pas
            # planifiée et son seul appelant plantait avant d'y arriver (NEW-14).
            rate = await price_service.get_forex_rate(base_currency, currency)
            if rate:
                updated_count += 1
                logger.debug(f"Updated {base_currency}/{currency}: {rate}")
        except Exception as e:
            logger.warning(f"Error fetching exchange rate {base_currency}/{currency}: {e}")

    logger.info(f"Exchange rate update complete: {updated_count} rates updated")
    return {
        "updated": updated_count,
        "base": base_currency,
        "currencies": currencies,
    }


@celery_app.task(name="app.tasks.price_updates.update_crypto_prices")
def update_crypto_prices():
    """Update cryptocurrency prices from CoinGecko and publish to pub/sub."""
    logger.info("Starting crypto price update...")

    return run_async(_maj_crypto())


@celery_app.task(name="app.tasks.price_updates.update_stock_prices")
def update_stock_prices():
    """Update stock/ETF prices from Yahoo Finance and publish to pub/sub."""
    logger.info("Starting stock/ETF price update...")

    return run_async(_maj_actions())


@celery_app.task(name="app.tasks.price_updates.update_exchange_rates")
def update_exchange_rates():
    """Update currency exchange rates."""
    logger.info("Starting exchange rate update...")

    return run_async(_maj_taux_change())


@celery_app.task(name="app.tasks.price_updates.update_all_prices")
def update_all_prices():
    """Met à jour tous les prix (crypto, actions, changes) en une seule boucle.

    Appeler les trois tâches en direct créait trois boucles successives, alors
    que l'engine SQLAlchemy async garde ses connexions attachées à la première :
    la deuxième échouait sur « Task attached to a different loop ». Le défaut
    était latent — seules `update_crypto_prices` et `update_stock_prices` sont
    planifiées, séparément, donc chacune avait bien sa propre boucle — mais il
    piégeait quiconque déclenchait celle-ci à la main.
    """
    logger.info("Starting full price update...")

    async def _tout():
        return {
            "crypto": await _maj_crypto(),
            "stocks": await _maj_actions(),
            "forex": await _maj_taux_change(),
        }

    results = run_async(_tout())
    logger.info(f"Full price update complete: {results}")
    return results
