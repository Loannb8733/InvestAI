"""Exchange synchronization tasks."""

import asyncio
import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.security import decrypt_api_key
from app.models.api_key import APIKey
from app.models.asset import Asset, AssetType
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction, TransactionType
from app.services.exchanges import get_exchange_service
from app.services.exchanges.pair_utils import quote_fx_currency, split_pair
from app.services.fx_history_service import FxHistoryService
from app.services.metrics_service import invalidate_dashboard_cache
from app.services.price_service import PriceService
from app.tasks.celery_app import celery_app

# Earliest plausible trade date for FX seeding. Frankfurter (ECB) data starts 1999;
# crypto exchanges predate none of our users, so 2017 covers all real history with margin.
_FX_EARLIEST = date(2017, 1, 1)

logger = logging.getLogger(__name__)


async def _resolve_trade_fx(
    fx_svc: Optional[FxHistoryService],
    quote: Optional[str],
    executed_at: datetime,
) -> Tuple[str, Optional[Decimal]]:
    """Resolve the (currency, conversion_rate) to store on a trade.

    The cost-basis engine reads ``conversion_rate`` = EUR per 1 unit of ``currency``.
    We only ever return a non-EUR currency when we have a *valid* historical rate for it;
    otherwise we fall back to EUR/None (the legacy behaviour). This guarantees we never
    mislabel a row with a foreign currency while implicitly using rate=1 — which would
    re-introduce the exact ~8-9% error FIN-01 fixes.

    Returns:
        ("EUR", None) when the quote is EUR, unknown, crypto, or its rate is unavailable.
        (anchor, rate) when the quote maps to a fiat with a resolvable EUR rate.
    """
    anchor = quote_fx_currency(quote) if quote else None
    if anchor is None or anchor == "EUR":
        return "EUR", None
    if fx_svc is None:
        logger.warning("No FX service available; storing %s trade as EUR fallback", anchor)
        return "EUR", None
    rate = await fx_svc.get_rate(executed_at.date(), anchor, "EUR")
    if rate is None:
        logger.warning(
            "No historical FX rate for %s->EUR on %s; storing as EUR fallback",
            anchor,
            executed_at.date(),
        )
        return "EUR", None
    return anchor, rate


async def _add_transaction_if_new(db: AsyncSession, transaction: Transaction) -> bool:
    """Add transaction only if its internal_hash doesn't already exist.

    Returns True if added, False if duplicate.
    """
    transaction.compute_hash()
    existing = await db.execute(select(Transaction.id).where(Transaction.internal_hash == transaction.internal_hash))
    if existing.scalar_one_or_none() is not None:
        logger.debug("Skipping duplicate transaction hash=%s", transaction.internal_hash)
        return False
    db.add(transaction)
    return True


async def _heal_transaction_fx(
    db: AsyncSession,
    external_ids: List[str],
    raw_price: float,
    tx_currency: str,
    tx_rate: Optional[Decimal],
) -> bool:
    """Repair an already-imported transaction's FX fields in place (FIN-01 heal).

    The dedup logic normally *skips* trades that already exist, so the FIN-01 fix only
    reaches new imports — legacy rows keep their wrong cost basis. This re-derives
    ``(price, currency, conversion_rate)`` from authoritative exchange data and updates
    the matching row(s) without deleting anything. It converges both legacy shapes:
    a raw quote-currency price mislabelled as EUR, and a price pre-converted with a
    single spot rate. Only price/currency/conversion_rate are touched; quantity, type,
    fees, dates and notes are preserved.

    Args:
        external_ids: candidate ``external_id`` values to match (e.g. ``["fiat_123", "123"]``).
        raw_price: the trade's price in its quote currency, as reported by the exchange.
        tx_currency: resolved storage currency ("EUR" or a fiat anchor like "USD").
        tx_rate: EUR-per-1-unit-of-currency rate, or None for EUR/unresolvable.

    Returns:
        True if at least one row was modified.
    """
    candidates = [eid for eid in external_ids if eid]
    if not candidates:
        return False
    result = await db.execute(select(Transaction).where(Transaction.external_id.in_(candidates)))
    rows = result.scalars().all()
    changed = False
    for row in rows:
        if raw_price and abs(float(row.price) - raw_price) > 1e-9:
            row.price = raw_price
            changed = True
        if row.currency != tx_currency:
            row.currency = tx_currency
            changed = True
        old_rate = None if row.conversion_rate is None else Decimal(str(row.conversion_rate))
        new_rate = None if tx_rate is None else Decimal(str(tx_rate))
        if old_rate != new_rate:
            row.conversion_rate = tx_rate
            changed = True
    return changed


def _classify_and_mark_error(api_key: APIKey, exc: Exception) -> None:
    """Classify an exchange error and update api_key status accordingly."""
    import httpx

    error_msg = str(exc)

    # httpx HTTP errors (raise_for_status)
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (401, 403):
            api_key.mark_auth_failure(error_msg)
            logger.warning("API key %s: auth failure (%d), disabling", api_key.id, code)
            return
        if code == 429:
            api_key.mark_rate_limited(error_msg)
            logger.warning("API key %s: rate limited (429)", api_key.id)
            return

    # Kraken returns auth errors in JSON (not HTTP status)
    lower_msg = error_msg.lower()
    if "invalid key" in lower_msg or "invalid signature" in lower_msg or "permission denied" in lower_msg:
        api_key.mark_auth_failure(error_msg)
        logger.warning("API key %s: auth failure (json), disabling", api_key.id)
        return

    # Generic error
    api_key.mark_error(error_msg)
    logger.error("API key %s: sync error: %s", api_key.id, error_msg[:200])


# Global price service instance (reused across sync operations)
_price_service: Optional[PriceService] = None


async def _get_current_price(symbol: str) -> float:
    """Get current market price for a crypto symbol in EUR."""
    global _price_service
    if _price_service is None:
        _price_service = PriceService()

    try:
        result = await _price_service.get_price(symbol, "crypto", "eur")
        if result and result.get("price"):
            return float(result["price"])
    except Exception as e:
        logger.warning(f"Could not fetch price for {symbol}: {e}")

    return 0.0


async def _get_or_create_asset(
    db: AsyncSession,
    portfolio_id: str,
    symbol: str,
    existing_assets: Dict[str, Asset],
    exchange: str = "",
) -> Asset:
    """Get or create an asset in the portfolio."""
    # Normalize Earn variants (ADAU → ADA, SUIU → SUI, etc.)
    normalized = _normalize_earn_variant(symbol)
    if normalized and normalized != symbol:
        symbol = normalized
    if symbol in existing_assets:
        return existing_assets[symbol]

    asset = Asset(
        portfolio_id=portfolio_id,
        symbol=symbol,
        name=symbol,
        asset_type=AssetType.CRYPTO,
        quantity=0,
        avg_buy_price=0,
        currency="EUR",
        exchange=exchange,
    )
    db.add(asset)
    await db.flush()
    existing_assets[symbol] = asset

    # Pre-cache historical data
    try:
        from app.tasks.history_cache import cache_single_asset

        cache_single_asset.delay(symbol, "crypto")
    except Exception:
        pass

    return asset


def _normalize_earn_variant(symbol: str) -> Optional[str]:
    """
    Normalize Binance Earn variant names to base asset symbol.
    e.g., ADAU -> ADA, SUIU -> SUI, LDBTC -> BTC, BFUSD -> USD (skip)
    """
    if not symbol:
        return None

    # Skip obvious earn/wrapped products that shouldn't be tracked as separate assets
    skip_prefixes = ["LD", "BF", "W"]  # LDBTC, BFUSD, WBTC
    for prefix in skip_prefixes:
        if symbol.startswith(prefix) and len(symbol) > len(prefix) + 2:
            return symbol[len(prefix) :]

    # Common earn suffixes: U (flexible), S (staking), KA (Kaito rewards), etc.
    # ADAU -> ADA, SUIU -> SUI, XRPU -> XRP, FETU -> FET, OMKA -> OM
    # But don't change real coins like TAO, OM, KAITO
    known_bases = [
        "ADA",
        "SUI",
        "XRP",
        "FET",
        "ETH",
        "BTC",
        "SOL",
        "TAO",
        "OM",
        "PENDLE",
        "LINK",
        "ONDO",
        "INJ",
        "KAITO",
        "DOGE",
        "USDC",
        "USDT",
    ]

    for base in known_bases:
        if symbol.startswith(base) and len(symbol) > len(base):
            suffix = symbol[len(base) :]
            # If suffix is short alphanumeric (U, S, KA, US, etc.), it's likely an earn variant
            if len(suffix) <= 2 and suffix.isalnum():
                return base

    return symbol  # Return original if no transformation needed


def _is_earn_variant(symbol: str) -> bool:
    """Check if a symbol is a Binance Earn variant that should be skipped."""
    if not symbol:
        return False
    normalized = _normalize_earn_variant(symbol)
    return normalized != symbol


async def _sync_detailed_transactions(
    db: AsyncSession,
    service,
    portfolio: Portfolio,
    existing_assets: Dict[str, Asset],
    heal_fx: bool = False,
) -> Tuple[int, int]:
    """Sync detailed transactions: trades, conversions, rewards.

    When ``heal_fx`` is True, trades that already exist are NOT skipped: their stored
    FX fields are repaired in place via :func:`_heal_transaction_fx` (no new rows, no
    quantity/avg-price mutation). Returns ``(synced_count, healed_count)``.
    """
    synced_count = 0
    healed_count = 0
    fiat_currencies = {"USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF"}

    # Get existing transaction external_ids to avoid duplicates
    existing_result = await db.execute(
        select(Transaction.external_id).where(
            Transaction.asset_id.in_([a.id for a in existing_assets.values()]),
            Transaction.external_id.isnot(None),
        )
    )
    existing_external_ids: Set[str] = {row[0] for row in existing_result.fetchall()}

    # FX resolution (FIN-01): seed the USD->EUR daily series once, then resolve each
    # trade's rate at its execution date. Seeding failure must not block the sync —
    # _resolve_trade_fx falls back to EUR when no rate is available.
    fx_svc: Optional[FxHistoryService] = FxHistoryService(db)
    try:
        await fx_svc.ensure_seeded("USD", "EUR", _FX_EARLIEST)
    except Exception as e:  # noqa: BLE001 - seeding is best-effort, never fatal
        logger.warning("FX seeding failed (%s); trades will fall back to EUR", e)
        fx_svc = None

    # Helper to extract base asset from symbol like "DOGEPEPE" -> "DOGE"
    def _extract_base_asset(symbol: str) -> Optional[str]:
        """Extract base asset from a trading pair symbol."""
        # First normalize any earn variants
        symbol = _normalize_earn_variant(symbol) or symbol

        # Try matching against known assets first (longest first to avoid partial matches)
        for asset_sym in sorted(existing_assets.keys(), key=lambda x: -len(x)):
            if symbol.startswith(asset_sym):
                return asset_sym
        # Fallback: try common lengths (4, 3, 5, 6 chars)
        for length in [4, 3, 5, 6]:
            if len(symbol) >= length:
                potential = symbol[:length]
                if potential.isupper() and potential.isalpha():
                    return potential
        return None

    # === 1. Sync crypto-to-crypto conversions ===
    try:
        if hasattr(service, "get_crypto_conversions"):
            conversions = await service.get_crypto_conversions(limit=500)
            logger.info(f"Found {len(conversions)} conversion entries from {service.exchange_name}")

            for trade in conversions:
                if trade.trade_id in existing_external_ids:
                    continue

                # Parse base asset from symbol (e.g., "DOGEPEPE" -> "DOGE")
                base_asset = _extract_base_asset(trade.symbol)
                if not base_asset or base_asset in fiat_currencies:
                    logger.warning(f"Could not parse base asset from conversion symbol: {trade.symbol}")
                    continue

                # Get or create the asset
                asset = await _get_or_create_asset(
                    db,
                    portfolio.id,
                    base_asset,
                    existing_assets,
                    exchange=service.exchange_name,
                )

                is_sell = trade.trade_id.startswith("convert_sell_")
                qty = float(trade.quantity)
                price = float(trade.price) if trade.price else 0

                if is_sell:
                    # CONVERSION_OUT: reduce asset quantity
                    trans_type = TransactionType.CONVERSION_OUT
                    transaction = Transaction(
                        asset_id=asset.id,
                        transaction_type=trans_type,
                        quantity=qty,
                        price=price,
                        fee=float(trade.fee) if trade.fee else 0,
                        fee_currency=trade.fee_currency,
                        currency="EUR",
                        executed_at=trade.timestamp,
                        external_id=trade.trade_id,
                        exchange=service.exchange_name,
                        # trade_id in notes enables _match_conversion_in regex matching
                        notes=f"Conversion {base_asset} -> autre crypto (trade_id:{trade.trade_id})",
                    )
                    await _add_transaction_if_new(db, transaction)
                    existing_external_ids.add(trade.trade_id)
                    asset.quantity = max(0, float(asset.quantity) - qty)
                    logger.info(f"Created CONVERSION_OUT: {base_asset} qty={qty}")
                else:
                    # CONVERSION_IN: increase asset quantity
                    trans_type = TransactionType.CONVERSION_IN

                    transaction = Transaction(
                        asset_id=asset.id,
                        transaction_type=trans_type,
                        quantity=qty,
                        price=0,
                        fee=float(trade.fee) if trade.fee else 0,
                        fee_currency=trade.fee_currency,
                        currency="EUR",
                        executed_at=trade.timestamp,
                        external_id=trade.trade_id,
                        exchange=service.exchange_name,
                        notes=f"Conversion autre crypto -> {base_asset} (trade_id:{trade.trade_id})",
                    )
                    await _add_transaction_if_new(db, transaction)
                    existing_external_ids.add(trade.trade_id)
                    asset.quantity = float(asset.quantity) + qty
                    logger.info(f"Created CONVERSION_IN: {base_asset} qty={qty}")

                synced_count += 1

    except Exception as e:
        logger.warning(f"Failed to sync conversions: {e}")

    # === 2. Sync Instant Buys (Kraken specific) ===
    try:
        if hasattr(service, "get_instant_buys"):
            result = await service.get_instant_buys(limit=500)
            # get_instant_buys returns (trades, processed_refids) tuple
            instant_buys = result[0] if isinstance(result, tuple) else result
            logger.info(f"Found {len(instant_buys)} instant buys from {service.exchange_name}")

            for trade in instant_buys:
                # Extract base asset + quote from symbol (e.g., "PAXGUSD" -> base PAXG, quote USD)
                base_asset = None
                trade_quote = None
                for quote in ["EUR", "USD", "GBP"]:
                    if trade.symbol.endswith(quote):
                        base_asset = trade.symbol[: -len(quote)]
                        trade_quote = quote
                        break

                # Resolve FX before the dedup check so existing rows can be healed in place.
                price = float(trade.price) if trade.price else 0
                tx_currency, tx_rate = await _resolve_trade_fx(fx_svc, trade_quote, trade.timestamp)

                if trade.trade_id in existing_external_ids:
                    if heal_fx and await _heal_transaction_fx(db, [trade.trade_id], price, tx_currency, tx_rate):
                        healed_count += 1
                    continue

                if not base_asset or base_asset in fiat_currencies:
                    continue

                asset = await _get_or_create_asset(
                    db,
                    portfolio.id,
                    base_asset,
                    existing_assets,
                    exchange=service.exchange_name,
                )

                qty = float(trade.quantity)

                transaction = Transaction(
                    asset_id=asset.id,
                    transaction_type=TransactionType.BUY,
                    quantity=qty,
                    price=price,
                    fee=float(trade.fee) if trade.fee else 0,
                    fee_currency=trade.fee_currency,
                    currency=tx_currency,
                    conversion_rate=tx_rate,
                    executed_at=trade.timestamp,
                    external_id=trade.trade_id,
                    exchange=service.exchange_name,
                    notes="Instant Buy",
                )
                await _add_transaction_if_new(db, transaction)
                existing_external_ids.add(trade.trade_id)

                # Update asset quantity and avg price
                old_qty = float(asset.quantity)
                old_avg = float(asset.avg_buy_price)
                if old_qty + qty > 0 and price > 0:
                    asset.avg_buy_price = (old_qty * old_avg + qty * price) / (old_qty + qty)
                asset.quantity = old_qty + qty

                synced_count += 1
                logger.info(f"Created BUY (Instant): {base_asset} qty={qty} price={price} ({tx_currency})")

    except Exception as e:
        logger.warning(f"Failed to sync instant buys: {e}")

    # === 3. Sync fiat orders (card/bank purchases - Binance specific) ===
    try:
        if hasattr(service, "get_fiat_orders"):
            fiat_orders = await service.get_fiat_orders()
            logger.info(f"Found {len(fiat_orders)} fiat orders from {service.exchange_name}")

            for order in fiat_orders:
                # Use fiat_ prefix to match api_keys.py format and avoid duplicates
                ext_id = f"fiat_{order.order_id}"
                price = float(order.price) if order.price else 0
                tx_currency, tx_rate = await _resolve_trade_fx(fx_svc, order.fiat_currency, order.timestamp)

                if ext_id in existing_external_ids or order.order_id in existing_external_ids:
                    if heal_fx and await _heal_transaction_fx(
                        db, [ext_id, order.order_id], price, tx_currency, tx_rate
                    ):
                        healed_count += 1
                    continue

                base_asset = order.crypto_symbol
                if not base_asset or base_asset in fiat_currencies:
                    continue

                asset = await _get_or_create_asset(
                    db,
                    portfolio.id,
                    base_asset,
                    existing_assets,
                    exchange=service.exchange_name,
                )

                trans_type = TransactionType.BUY if order.side == "buy" else TransactionType.SELL
                qty = float(order.crypto_amount)

                transaction = Transaction(
                    asset_id=asset.id,
                    transaction_type=trans_type,
                    quantity=qty,
                    price=price,
                    fee=float(order.fee) if order.fee else 0,
                    fee_currency=order.fiat_currency,
                    currency=tx_currency,
                    conversion_rate=tx_rate,
                    executed_at=order.timestamp,
                    external_id=ext_id,
                    exchange=service.exchange_name,
                    notes="Fiat Order",
                )
                await _add_transaction_if_new(db, transaction)
                existing_external_ids.add(ext_id)

                if trans_type == TransactionType.BUY:
                    old_qty = float(asset.quantity)
                    old_avg = float(asset.avg_buy_price)
                    if old_qty + qty > 0 and price > 0:
                        asset.avg_buy_price = (old_qty * old_avg + qty * price) / (old_qty + qty)
                    asset.quantity = old_qty + qty
                else:
                    asset.quantity = max(0, float(asset.quantity) - qty)

                synced_count += 1
                logger.info(f"Created {trans_type.value} (Fiat): {base_asset} qty={qty} price={price}")

    except Exception as e:
        logger.warning(f"Failed to sync fiat orders: {e}")

    # === 4. Sync auto-invest history (DCA - Binance specific) ===
    try:
        if hasattr(service, "get_auto_invest_history"):
            auto_invest = await service.get_auto_invest_history()
            logger.info(f"Found {len(auto_invest)} auto-invest orders from {service.exchange_name}")

            for order in auto_invest:
                # Use fiat_ prefix to match api_keys.py format and avoid duplicates
                ext_id = f"fiat_{order.order_id}"
                price = float(order.price) if order.price else 0
                tx_currency, tx_rate = await _resolve_trade_fx(fx_svc, order.fiat_currency, order.timestamp)

                if ext_id in existing_external_ids or order.order_id in existing_external_ids:
                    if heal_fx and await _heal_transaction_fx(
                        db, [ext_id, order.order_id], price, tx_currency, tx_rate
                    ):
                        healed_count += 1
                    continue

                base_asset = order.crypto_symbol
                if not base_asset or base_asset in fiat_currencies:
                    continue

                asset = await _get_or_create_asset(
                    db,
                    portfolio.id,
                    base_asset,
                    existing_assets,
                    exchange=service.exchange_name,
                )

                qty = float(order.crypto_amount)

                transaction = Transaction(
                    asset_id=asset.id,
                    transaction_type=TransactionType.BUY,
                    quantity=qty,
                    price=price,
                    fee=float(order.fee) if order.fee else 0,
                    fee_currency=order.fiat_currency,
                    currency=tx_currency,
                    conversion_rate=tx_rate,
                    executed_at=order.timestamp,
                    external_id=ext_id,
                    exchange=service.exchange_name,
                    notes="Auto-Invest DCA",
                )
                await _add_transaction_if_new(db, transaction)
                existing_external_ids.add(ext_id)

                old_qty = float(asset.quantity)
                old_avg = float(asset.avg_buy_price)
                if old_qty + qty > 0 and price > 0:
                    asset.avg_buy_price = (old_qty * old_avg + qty * price) / (old_qty + qty)
                asset.quantity = old_qty + qty

                synced_count += 1
                logger.info(f"Created BUY (Auto-Invest): {base_asset} qty={qty} price={price}")

    except Exception as e:
        logger.warning(f"Failed to sync auto-invest: {e}")

    # === 5. Sync normal trades (order book trades) ===
    try:
        trades = await service.get_trades(limit=500)
        logger.info(f"Found {len(trades)} trades from {service.exchange_name}")

        for trade in trades:
            # Resolve FX before the dedup check so existing rows can be healed in place.
            price = float(trade.price) if trade.price else 0
            _, trade_quote = split_pair(trade.symbol)
            tx_currency, tx_rate = await _resolve_trade_fx(fx_svc, trade_quote, trade.timestamp)

            if trade.trade_id in existing_external_ids:
                if heal_fx and await _heal_transaction_fx(db, [trade.trade_id], price, tx_currency, tx_rate):
                    healed_count += 1
                continue

            # Extract base asset from symbol (e.g., "BTCEUR" -> "BTC")
            base_asset = None
            for asset_symbol in list(existing_assets.keys()) + list(fiat_currencies):
                if trade.symbol.startswith(asset_symbol) and asset_symbol not in fiat_currencies:
                    base_asset = asset_symbol
                    break

            if not base_asset:
                # Try to extract from symbol by removing common quote currencies
                for quote in ["EUR", "USD", "USDT", "USDC", "BTC", "ETH"]:
                    if trade.symbol.endswith(quote):
                        potential_base = trade.symbol[: -len(quote)]
                        if potential_base and potential_base not in fiat_currencies:
                            base_asset = potential_base
                            break

            if not base_asset or base_asset in fiat_currencies:
                continue

            # Get or create asset
            asset = await _get_or_create_asset(
                db,
                portfolio.id,
                base_asset,
                existing_assets,
                exchange=service.exchange_name,
            )

            trans_type = TransactionType.BUY if trade.side == "buy" else TransactionType.SELL
            qty = float(trade.quantity)

            transaction = Transaction(
                asset_id=asset.id,
                transaction_type=trans_type,
                quantity=qty,
                price=price,
                fee=float(trade.fee) if trade.fee else 0,
                fee_currency=trade.fee_currency,
                currency=tx_currency,
                conversion_rate=tx_rate,
                executed_at=trade.timestamp,
                external_id=trade.trade_id,
                exchange=service.exchange_name,
            )
            await _add_transaction_if_new(db, transaction)
            existing_external_ids.add(trade.trade_id)

            # Update asset quantity and avg price
            if trans_type == TransactionType.BUY:
                old_qty = float(asset.quantity)
                old_avg = float(asset.avg_buy_price)
                if old_qty + qty > 0 and price > 0:
                    asset.avg_buy_price = (old_qty * old_avg + qty * price) / (old_qty + qty)
                asset.quantity = old_qty + qty
            else:
                asset.quantity = max(0, float(asset.quantity) - qty)

            synced_count += 1

    except Exception as e:
        logger.warning(f"Failed to sync trades: {e}")

    # === 6. Sync rewards (airdrops, staking) ===
    try:
        if hasattr(service, "get_rewards"):
            rewards = await service.get_rewards(limit=500)
            logger.info(f"Found {len(rewards)} rewards from {service.exchange_name}")

            for reward in rewards:
                if reward.trade_id in existing_external_ids:
                    continue

                # Extract asset from symbol
                reward_asset = reward.symbol
                for quote in ["EUR", "USD"]:
                    if reward_asset.endswith(quote):
                        reward_asset = reward_asset[: -len(quote)]
                        break

                if reward_asset in fiat_currencies:
                    continue

                asset = await _get_or_create_asset(
                    db,
                    portfolio.id,
                    reward_asset,
                    existing_assets,
                    exchange=service.exchange_name,
                )

                # Determine transaction type
                if "staking" in reward.trade_id.lower():
                    trans_type = TransactionType.STAKING_REWARD
                else:
                    trans_type = TransactionType.AIRDROP

                qty = float(reward.quantity)
                transaction = Transaction(
                    asset_id=asset.id,
                    transaction_type=trans_type,
                    quantity=qty,
                    price=0,
                    fee=0,
                    currency="EUR",
                    executed_at=reward.timestamp,
                    external_id=reward.trade_id,
                    exchange=service.exchange_name,
                    notes=f"Reward from {service.exchange_name}",
                )
                await _add_transaction_if_new(db, transaction)
                existing_external_ids.add(reward.trade_id)

                # Add to quantity
                asset.quantity = float(asset.quantity) + qty
                synced_count += 1

    except Exception as e:
        logger.warning(f"Failed to sync rewards: {e}")

    # === 7. Sync deposits (external transfers in) ===
    try:
        if hasattr(service, "get_deposits"):
            deposits = await service.get_deposits(limit=500)
            logger.info(f"Found {len(deposits)} deposits from {service.exchange_name}")

            for deposit in deposits:
                # Skip if not successful
                if deposit.status not in ("success", "credited"):
                    continue

                # Use tx_id or deposit_id as external_id
                ext_id = f"deposit_{deposit.deposit_id}"
                if ext_id in existing_external_ids:
                    continue

                base_asset = deposit.symbol
                if not base_asset or base_asset in fiat_currencies:
                    continue

                asset = await _get_or_create_asset(
                    db,
                    portfolio.id,
                    base_asset,
                    existing_assets,
                    exchange=service.exchange_name,
                )

                qty = float(deposit.amount)
                # Get current price for the deposit
                current_price = await _get_current_price(base_asset)

                transaction = Transaction(
                    asset_id=asset.id,
                    transaction_type=TransactionType.TRANSFER_IN,
                    quantity=qty,
                    price=current_price,
                    fee=0,
                    currency="EUR",
                    executed_at=deposit.timestamp,
                    external_id=ext_id,
                    exchange=service.exchange_name,
                    notes=f"Dépôt depuis externe ({deposit.tx_id[:16]}...)" if deposit.tx_id else "Dépôt externe",
                )
                await _add_transaction_if_new(db, transaction)
                existing_external_ids.add(ext_id)

                # Update quantity and avg_buy_price
                old_qty = float(asset.quantity)
                old_avg = float(asset.avg_buy_price)
                if old_qty + qty > 0 and current_price > 0:
                    asset.avg_buy_price = (old_qty * old_avg + qty * current_price) / (old_qty + qty)
                asset.quantity = old_qty + qty

                synced_count += 1
                logger.info(f"Created TRANSFER_IN (Deposit): {base_asset} qty={qty}")

    except Exception as e:
        logger.warning(f"Failed to sync deposits: {e}")

    return synced_count, healed_count


async def _sync_single_exchange(api_key_id: str, heal_fx: bool = False) -> dict:
    """Sync a single exchange account (async implementation).

    When ``heal_fx`` is True, this runs in repair mode: it re-fetches the trade history
    and corrects the stored FX fields (price/currency/conversion_rate) of already-imported
    transactions in place (FIN-01), without creating new rows or running the balance
    reconciliation step. Used by the "Recalculer les taux FX" action.
    """
    async with AsyncSessionLocal() as db:
        # Get API key
        result = await db.execute(select(APIKey).where(APIKey.id == api_key_id))
        api_key = result.scalar_one_or_none()

        if not api_key or not api_key.is_active:
            return {"success": False, "error": "API key not found or inactive"}

        try:
            # Decrypt credentials
            decrypted_api = decrypt_api_key(api_key.encrypted_api_key)
            decrypted_secret = None
            decrypted_passphrase = None

            if api_key.encrypted_secret_key:
                decrypted_secret = decrypt_api_key(api_key.encrypted_secret_key)
            if api_key.encrypted_passphrase:
                decrypted_passphrase = decrypt_api_key(api_key.encrypted_passphrase)

            # Get exchange service
            service_class = get_exchange_service(api_key.exchange)
            service = service_class(decrypted_api, decrypted_secret, decrypted_passphrase)

            # Get balances
            balances = await service.get_balances()

            if not balances:
                api_key.last_sync_at = datetime.now(timezone.utc)
                api_key.mark_success()
                await db.commit()
                return {"success": True, "synced": 0}

            # Get or create unified "Crypto" portfolio (same logic as import-history)
            portfolio_result = await db.execute(
                select(Portfolio).where(
                    Portfolio.user_id == api_key.user_id,
                    Portfolio.name == "Crypto",
                )
            )
            portfolio = portfolio_result.scalar_one_or_none()

            if not portfolio:
                # Check for legacy per-exchange portfolio
                legacy_result = await db.execute(
                    select(Portfolio).where(
                        Portfolio.user_id == api_key.user_id,
                        Portfolio.name == f"{service.exchange_name}",
                    )
                )
                portfolio = legacy_result.scalar_one_or_none()
                if portfolio:
                    portfolio.name = "Crypto"
                    portfolio.description = "Portefeuille crypto consolidé"

            if not portfolio:
                portfolio = Portfolio(
                    user_id=api_key.user_id,
                    name="Crypto",
                    description="Portefeuille crypto consolidé",
                )
                db.add(portfolio)
                await db.flush()

            # Get existing assets (match by exchange or transferred assets)
            assets_result = await db.execute(
                select(Asset).where(
                    Asset.portfolio_id == portfolio.id,
                )
            )
            all_portfolio_assets = assets_result.scalars().all()
            existing_assets = {}
            for a in all_portfolio_assets:
                # Only include assets belonging to this exchange (or unassigned)
                if a.exchange == service.exchange_name:
                    existing_assets[a.symbol] = a
                elif a.exchange == "" and a.symbol not in existing_assets:
                    existing_assets[a.symbol] = a

            # === STEP 1: Sync detailed transactions (trades, conversions, rewards) ===
            detailed_synced, healed = await _sync_detailed_transactions(
                db, service, portfolio, existing_assets, heal_fx=heal_fx
            )
            logger.info(f"Synced {detailed_synced} detailed transactions from {service.exchange_name}")

            # Repair mode stops here: we only corrected FX fields on existing rows and must
            # NOT run the balance reconciliation (which would create adjustment transactions).
            if heal_fx:
                logger.info(f"FX heal: corrected {healed} transactions for {service.exchange_name}")
                api_key.last_sync_at = datetime.now(timezone.utc)
                api_key.mark_success()
                await db.commit()
                invalidate_dashboard_cache(str(api_key.user_id))
                return {"success": True, "synced": healed, "healed": healed}

            # Refresh existing_assets after detailed sync (new assets may have been created)
            assets_result = await db.execute(select(Asset).where(Asset.portfolio_id == portfolio.id))
            all_portfolio_assets = assets_result.scalars().all()
            existing_assets = {}
            for a in all_portfolio_assets:
                if a.exchange == service.exchange_name:
                    existing_assets[a.symbol] = a
                elif a.exchange == "" and a.symbol not in existing_assets:
                    existing_assets[a.symbol] = a

            # === STEP 2: Sync remaining balance discrepancies ===
            synced_count = detailed_synced
            fiat_currencies = ["USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF"]

            # Aggregate balances by normalized base symbol so Binance Earn
            # variants (LDUSDC, ADAU, ...) fold into their base asset (USDC,
            # ADA) instead of being dropped. Funds parked in Earn would
            # otherwise never reach the base asset quantity, making them vanish
            # from the portfolio (e.g. a Stablecoins card stuck at 0).
            aggregated_balances: Dict[str, float] = {}
            for balance in balances:
                if balance.symbol in fiat_currencies:
                    continue
                normalized = _normalize_earn_variant(balance.symbol) or balance.symbol
                if normalized in fiat_currencies:
                    continue
                aggregated_balances[normalized] = aggregated_balances.get(normalized, 0.0) + float(balance.total)

            for symbol, exchange_quantity in aggregated_balances.items():
                if symbol in existing_assets:
                    # Adjust for any remaining discrepancy (deposits/withdrawals not captured by trades)
                    asset = existing_assets[symbol]

                    # Skip assets transferred to cold wallets (exchange != this exchange)
                    if asset.exchange and asset.exchange != service.exchange_name:
                        continue

                    our_quantity = float(asset.quantity)

                    # Only adjust if there's a significant discrepancy
                    if abs(exchange_quantity - our_quantity) > 0.00000001:
                        diff = exchange_quantity - our_quantity
                        trans_type = TransactionType.TRANSFER_IN if diff > 0 else TransactionType.TRANSFER_OUT

                        logger.info(
                            f"Balance adjustment for {symbol}: "
                            f"our={our_quantity:.8f} exchange={exchange_quantity:.8f} diff={diff:+.8f}"
                        )

                        # Get current market price for TRANSFER_IN
                        current_price = 0.0
                        if trans_type == TransactionType.TRANSFER_IN:
                            current_price = await _get_current_price(symbol)

                        sync_ts = int(datetime.now(timezone.utc).timestamp())
                        transaction = Transaction(
                            asset_id=asset.id,
                            transaction_type=trans_type,
                            quantity=abs(diff),
                            price=current_price,
                            fee=0,
                            currency="EUR",
                            external_id=f"{service.exchange_name}_sync_{symbol}_{sync_ts}",
                            notes=f"Ajustement balance {service.exchange_name}",
                        )
                        await _add_transaction_if_new(db, transaction)

                        # Update avg_buy_price if it's 0 and we have a price
                        if (
                            trans_type == TransactionType.TRANSFER_IN
                            and current_price > 0
                            and float(asset.avg_buy_price) == 0
                        ):
                            asset.avg_buy_price = current_price

                        asset.quantity = exchange_quantity
                        synced_count += 1
                else:
                    # Get current market price for the new asset
                    current_price = await _get_current_price(symbol)

                    # Create new asset with current price as avg_buy_price
                    asset = Asset(
                        portfolio_id=portfolio.id,
                        symbol=symbol,
                        name=symbol,
                        asset_type=AssetType.CRYPTO,
                        quantity=exchange_quantity,
                        avg_buy_price=current_price,
                        currency="EUR",
                        exchange=service.exchange_name,
                    )
                    db.add(asset)
                    await db.flush()
                    existing_assets[symbol] = asset

                    # Pre-cache historical data for new asset
                    try:
                        from app.tasks.history_cache import cache_single_asset

                        cache_single_asset.delay(asset.symbol, asset.asset_type.value)
                    except Exception:
                        pass

                    # Create initial transfer transaction with market price
                    if exchange_quantity > 0:
                        init_ts = int(datetime.now(timezone.utc).timestamp())
                        transaction = Transaction(
                            asset_id=asset.id,
                            transaction_type=TransactionType.TRANSFER_IN,
                            quantity=exchange_quantity,
                            price=current_price,
                            fee=0,
                            currency="EUR",
                            external_id=f"{service.exchange_name}_init_{symbol}_{init_ts}",
                            notes=f"Import initial depuis {service.exchange_name}",
                        )
                        await _add_transaction_if_new(db, transaction)

                    synced_count += 1

            # === STEP 3: Zero out assets no longer on Binance (fully sold/converted) ===
            # Use normalized symbols so an asset whose only on-exchange balance
            # is an Earn variant (e.g. USDC held as LDUSDC) is NOT wrongly zeroed.
            balance_symbols = set(aggregated_balances.keys())
            for symbol, asset in existing_assets.items():
                if (
                    asset.exchange == service.exchange_name
                    and float(asset.quantity) > 0
                    and symbol not in balance_symbols
                    and symbol not in fiat_currencies
                    and not _is_earn_variant(symbol)
                ):
                    logger.info(
                        f"Asset {symbol} no longer on {service.exchange_name} (balance=0), zeroing quantity from {asset.quantity}"
                    )
                    sync_ts = int(datetime.now(timezone.utc).timestamp())
                    transaction = Transaction(
                        asset_id=asset.id,
                        transaction_type=TransactionType.TRANSFER_OUT,
                        quantity=float(asset.quantity),
                        price=0,
                        fee=0,
                        currency="EUR",
                        external_id=f"{service.exchange_name}_zero_{symbol}_{sync_ts}",
                        notes=f"Solde zéro sur {service.exchange_name} (vendu/converti)",
                    )
                    await _add_transaction_if_new(db, transaction)
                    asset.quantity = 0
                    synced_count += 1

            # Update last sync time
            api_key.last_sync_at = datetime.now(timezone.utc)
            api_key.mark_success()

            await db.commit()

            invalidate_dashboard_cache(str(api_key.user_id))

            return {"success": True, "synced": synced_count}

        except Exception as e:
            _classify_and_mark_error(api_key, e)
            await db.commit()
            return {"success": False, "error": str(e)}


async def _sync_all_exchanges_async() -> dict:
    """Sync all active exchange accounts (async implementation)."""
    async with AsyncSessionLocal() as db:
        # Get all active API keys
        result = await db.execute(select(APIKey).where(APIKey.is_active == True))
        api_keys = result.scalars().all()

        if not api_keys:
            return {"total": 0, "success": 0, "failed": 0}

        success_count = 0
        failed_count = 0

        for api_key in api_keys:
            try:
                result = await _sync_single_exchange(str(api_key.id))
                if result.get("success"):
                    success_count += 1
                else:
                    failed_count += 1
            except Exception:
                failed_count += 1

        return {
            "total": len(api_keys),
            "success": success_count,
            "failed": failed_count,
        }


@celery_app.task(name="app.tasks.sync_exchanges.sync_all_exchanges")
def sync_all_exchanges():
    """Sync all user exchange accounts."""
    return asyncio.run(_sync_all_exchanges_async())


@celery_app.task(
    name="app.tasks.sync_exchanges.sync_single_exchange",
    autoretry_for=(Exception,),
    max_retries=3,
    default_retry_delay=120,
    retry_backoff=True,
)
def sync_single_exchange(api_key_id: str):
    """Sync a single exchange account."""
    return asyncio.run(_sync_single_exchange(api_key_id))


@celery_app.task(
    name="app.tasks.sync_exchanges.sync_binance",
    autoretry_for=(Exception,),
    max_retries=3,
    default_retry_delay=120,
    retry_backoff=True,
)
def sync_binance(user_id: str, api_key_id: str):
    """Sync Binance account for a user."""
    return asyncio.run(_sync_single_exchange(api_key_id))


@celery_app.task(
    name="app.tasks.sync_exchanges.sync_kraken",
    autoretry_for=(Exception,),
    max_retries=3,
    default_retry_delay=120,
    retry_backoff=True,
)
def sync_kraken(user_id: str, api_key_id: str):
    """Sync Kraken account for a user."""
    return asyncio.run(_sync_single_exchange(api_key_id))


@celery_app.task(
    name="app.tasks.sync_exchanges.sync_crypto_com",
    autoretry_for=(Exception,),
    max_retries=3,
    default_retry_delay=120,
    retry_backoff=True,
)
def sync_crypto_com(user_id: str, api_key_id: str):
    """Sync Crypto.com account for a user."""
    return asyncio.run(_sync_single_exchange(api_key_id))
