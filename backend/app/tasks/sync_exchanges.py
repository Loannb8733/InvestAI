"""Exchange synchronization tasks."""

import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.security import decrypt_api_key
from app.models.api_key import APIKey
from app.models.asset import Asset, AssetType
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction, TransactionType
from app.services.exchanges import get_exchange_service
from app.services.price_service import PriceService
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

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
) -> Asset:
    """Get or create an asset in the portfolio."""
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
            return symbol[len(prefix):]

    # Common earn suffixes: U (flexible), S (staking), KA (Kaito rewards), etc.
    # ADAU -> ADA, SUIU -> SUI, XRPU -> XRP, FETU -> FET, OMKA -> OM
    # But don't change real coins like TAO, OM, KAITO
    known_bases = ["ADA", "SUI", "XRP", "FET", "ETH", "BTC", "SOL", "TAO",
                   "OM", "PENDLE", "LINK", "ONDO", "INJ", "KAITO", "DOGE",
                   "USDC", "USDT"]

    for base in known_bases:
        if symbol.startswith(base) and len(symbol) > len(base):
            suffix = symbol[len(base):]
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
) -> int:
    """Sync detailed transactions: trades, conversions, rewards."""
    synced_count = 0
    fiat_currencies = {"USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF"}

    # Get existing transaction external_ids to avoid duplicates
    existing_result = await db.execute(
        select(Transaction.external_id).where(
            Transaction.asset_id.in_([a.id for a in existing_assets.values()]),
            Transaction.external_id.isnot(None),
        )
    )
    existing_external_ids: Set[str] = {row[0] for row in existing_result.fetchall()}

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
                asset = await _get_or_create_asset(db, portfolio.id, base_asset, existing_assets)

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
                        notes=f"Conversion {base_asset} -> autre crypto",
                    )
                    db.add(transaction)
                    asset.quantity = max(0, float(asset.quantity) - qty)
                    logger.info(f"Created CONVERSION_OUT: {base_asset} qty={qty}")
                else:
                    # CONVERSION_IN: increase asset quantity
                    trans_type = TransactionType.CONVERSION_IN

                    # Note: price from conversion is a crypto ratio, not EUR price
                    # Don't use it for avg_buy_price calculation (set to 0)
                    transaction = Transaction(
                        asset_id=asset.id,
                        transaction_type=trans_type,
                        quantity=qty,
                        price=0,  # No EUR price available for conversions
                        fee=float(trade.fee) if trade.fee else 0,
                        fee_currency=trade.fee_currency,
                        currency="EUR",
                        executed_at=trade.timestamp,
                        external_id=trade.trade_id,
                        exchange=service.exchange_name,
                        notes=f"Conversion autre crypto -> {base_asset}",
                    )
                    db.add(transaction)
                    asset.quantity = float(asset.quantity) + qty
                    logger.info(f"Created CONVERSION_IN: {base_asset} qty={qty}")

                synced_count += 1

    except Exception as e:
        logger.warning(f"Failed to sync conversions: {e}")

    # === 2. Sync Instant Buys (Kraken specific) ===
    try:
        if hasattr(service, "get_instant_buys"):
            instant_buys = await service.get_instant_buys(limit=500)
            logger.info(f"Found {len(instant_buys)} instant buys from {service.exchange_name}")

            for trade in instant_buys:
                if trade.trade_id in existing_external_ids:
                    continue

                # Extract base asset from symbol (e.g., "PAXGEUR" -> "PAXG")
                base_asset = None
                for quote in ["EUR", "USD", "GBP"]:
                    if trade.symbol.endswith(quote):
                        base_asset = trade.symbol[:-len(quote)]
                        break

                if not base_asset or base_asset in fiat_currencies:
                    continue

                asset = await _get_or_create_asset(db, portfolio.id, base_asset, existing_assets)

                qty = float(trade.quantity)
                price = float(trade.price) if trade.price else 0

                transaction = Transaction(
                    asset_id=asset.id,
                    transaction_type=TransactionType.BUY,
                    quantity=qty,
                    price=price,
                    fee=float(trade.fee) if trade.fee else 0,
                    fee_currency=trade.fee_currency,
                    currency="EUR",
                    executed_at=trade.timestamp,
                    external_id=trade.trade_id,
                    exchange=service.exchange_name,
                    notes="Instant Buy",
                )
                db.add(transaction)

                # Update asset quantity and avg price
                old_qty = float(asset.quantity)
                old_avg = float(asset.avg_buy_price)
                if old_qty + qty > 0 and price > 0:
                    asset.avg_buy_price = (old_qty * old_avg + qty * price) / (old_qty + qty)
                asset.quantity = old_qty + qty

                synced_count += 1
                logger.info(f"Created BUY (Instant): {base_asset} qty={qty} price={price}")

    except Exception as e:
        logger.warning(f"Failed to sync instant buys: {e}")

    # === 3. Sync fiat orders (card/bank purchases - Binance specific) ===
    try:
        if hasattr(service, "get_fiat_orders"):
            fiat_orders = await service.get_fiat_orders()
            logger.info(f"Found {len(fiat_orders)} fiat orders from {service.exchange_name}")

            for order in fiat_orders:
                if order.order_id in existing_external_ids:
                    continue

                base_asset = order.crypto_symbol
                if not base_asset or base_asset in fiat_currencies:
                    continue

                asset = await _get_or_create_asset(db, portfolio.id, base_asset, existing_assets)

                trans_type = TransactionType.BUY if order.side == "buy" else TransactionType.SELL
                qty = float(order.crypto_amount)
                price = float(order.price) if order.price else 0

                transaction = Transaction(
                    asset_id=asset.id,
                    transaction_type=trans_type,
                    quantity=qty,
                    price=price,
                    fee=float(order.fee) if order.fee else 0,
                    fee_currency=order.fiat_currency,
                    currency="EUR",
                    executed_at=order.timestamp,
                    external_id=order.order_id,
                    exchange=service.exchange_name,
                    notes="Fiat Order",
                )
                db.add(transaction)

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
                if order.order_id in existing_external_ids:
                    continue

                base_asset = order.crypto_symbol
                if not base_asset or base_asset in fiat_currencies:
                    continue

                asset = await _get_or_create_asset(db, portfolio.id, base_asset, existing_assets)

                qty = float(order.crypto_amount)
                price = float(order.price) if order.price else 0

                transaction = Transaction(
                    asset_id=asset.id,
                    transaction_type=TransactionType.BUY,
                    quantity=qty,
                    price=price,
                    fee=float(order.fee) if order.fee else 0,
                    fee_currency=order.fiat_currency,
                    currency="EUR",
                    executed_at=order.timestamp,
                    external_id=order.order_id,
                    exchange=service.exchange_name,
                    notes="Auto-Invest DCA",
                )
                db.add(transaction)

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
            if trade.trade_id in existing_external_ids:
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
                        potential_base = trade.symbol[:-len(quote)]
                        if potential_base and potential_base not in fiat_currencies:
                            base_asset = potential_base
                            break

            if not base_asset or base_asset in fiat_currencies:
                continue

            # Get or create asset
            asset = await _get_or_create_asset(db, portfolio.id, base_asset, existing_assets)

            trans_type = TransactionType.BUY if trade.side == "buy" else TransactionType.SELL
            qty = float(trade.quantity)
            price = float(trade.price) if trade.price else 0

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
            )
            db.add(transaction)

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
                        reward_asset = reward_asset[:-len(quote)]
                        break

                if reward_asset in fiat_currencies:
                    continue

                asset = await _get_or_create_asset(db, portfolio.id, reward_asset, existing_assets)

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
                db.add(transaction)

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

                asset = await _get_or_create_asset(db, portfolio.id, base_asset, existing_assets)

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
                db.add(transaction)

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

    return synced_count


async def _sync_single_exchange(api_key_id: str) -> dict:
    """Sync a single exchange account (async implementation)."""
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
                api_key.last_sync_at = datetime.utcnow().isoformat()
                api_key.last_error = None
                await db.commit()
                return {"success": True, "synced": 0}

            # Get or create portfolio for this exchange
            portfolio_result = await db.execute(
                select(Portfolio).where(
                    Portfolio.user_id == api_key.user_id,
                    Portfolio.name == f"{service.exchange_name}",
                )
            )
            portfolio = portfolio_result.scalar_one_or_none()

            if not portfolio:
                portfolio = Portfolio(
                    user_id=api_key.user_id,
                    name=f"{service.exchange_name}",
                    description=f"Portefeuille synchronisé depuis {service.exchange_name}",
                )
                db.add(portfolio)
                await db.flush()

            # Get existing assets
            assets_result = await db.execute(
                select(Asset).where(
                    Asset.portfolio_id == portfolio.id,
                )
            )
            existing_assets = {a.symbol: a for a in assets_result.scalars().all()}

            # === STEP 1: Sync detailed transactions (trades, conversions, rewards) ===
            detailed_synced = await _sync_detailed_transactions(
                db, service, portfolio, existing_assets
            )
            logger.info(f"Synced {detailed_synced} detailed transactions from {service.exchange_name}")

            # Refresh existing_assets after detailed sync (new assets may have been created)
            assets_result = await db.execute(
                select(Asset).where(Asset.portfolio_id == portfolio.id)
            )
            existing_assets = {a.symbol: a for a in assets_result.scalars().all()}

            # === STEP 2: Sync remaining balance discrepancies ===
            synced_count = detailed_synced
            fiat_currencies = ["USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF"]

            for balance in balances:
                # Skip fiat currencies only
                if balance.symbol in fiat_currencies:
                    continue

                # Skip Binance Earn variants (ADAU, SUIU, etc.) - they're tracked under base asset
                if _is_earn_variant(balance.symbol):
                    logger.debug(f"Skipping earn variant: {balance.symbol}")
                    continue

                if balance.symbol in existing_assets:
                    # Adjust for any remaining discrepancy (deposits/withdrawals not captured by trades)
                    asset = existing_assets[balance.symbol]
                    our_quantity = float(asset.quantity)
                    exchange_quantity = float(balance.total)

                    # Only adjust if there's a significant discrepancy
                    if abs(exchange_quantity - our_quantity) > 0.00000001:
                        diff = exchange_quantity - our_quantity
                        trans_type = (
                            TransactionType.TRANSFER_IN
                            if diff > 0
                            else TransactionType.TRANSFER_OUT
                        )

                        logger.info(
                            f"Balance adjustment for {balance.symbol}: "
                            f"our={our_quantity:.8f} exchange={exchange_quantity:.8f} diff={diff:+.8f}"
                        )

                        # Get current market price for TRANSFER_IN
                        current_price = 0.0
                        if trans_type == TransactionType.TRANSFER_IN:
                            current_price = await _get_current_price(balance.symbol)

                        transaction = Transaction(
                            asset_id=asset.id,
                            transaction_type=trans_type,
                            quantity=abs(diff),
                            price=current_price,
                            fee=0,
                            currency="EUR",
                            notes=f"Ajustement balance {service.exchange_name}",
                        )
                        db.add(transaction)

                        # Update avg_buy_price if it's 0 and we have a price
                        if trans_type == TransactionType.TRANSFER_IN and current_price > 0 and float(asset.avg_buy_price) == 0:
                            asset.avg_buy_price = current_price

                        asset.quantity = exchange_quantity
                        synced_count += 1
                else:
                    # Get current market price for the new asset
                    current_price = await _get_current_price(balance.symbol)

                    # Create new asset with current price as avg_buy_price
                    asset = Asset(
                        portfolio_id=portfolio.id,
                        symbol=balance.symbol,
                        name=balance.symbol,
                        asset_type=AssetType.CRYPTO,
                        quantity=float(balance.total),
                        avg_buy_price=current_price,
                        currency="EUR",
                    )
                    db.add(asset)
                    await db.flush()

                    # Pre-cache historical data for new asset
                    try:
                        from app.tasks.history_cache import cache_single_asset
                        cache_single_asset.delay(asset.symbol, asset.asset_type.value)
                    except Exception:
                        pass

                    # Create initial transfer transaction with market price
                    if float(balance.total) > 0:
                        transaction = Transaction(
                            asset_id=asset.id,
                            transaction_type=TransactionType.TRANSFER_IN,
                            quantity=float(balance.total),
                            price=current_price,
                            fee=0,
                            currency="EUR",
                            notes=f"Import initial depuis {service.exchange_name}",
                        )
                        db.add(transaction)

                    synced_count += 1

            # Update last sync time
            api_key.last_sync_at = datetime.utcnow().isoformat()
            api_key.last_error = None

            await db.commit()

            return {"success": True, "synced": synced_count}

        except Exception as e:
            api_key.last_error = str(e)[:500]
            await db.commit()
            return {"success": False, "error": str(e)}


async def _sync_all_exchanges_async() -> dict:
    """Sync all active exchange accounts (async implementation)."""
    async with AsyncSessionLocal() as db:
        # Get all active API keys
        result = await db.execute(
            select(APIKey).where(APIKey.is_active == True)
        )
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


@celery_app.task(name="app.tasks.sync_exchanges.sync_single_exchange")
def sync_single_exchange(api_key_id: str):
    """Sync a single exchange account."""
    return asyncio.run(_sync_single_exchange(api_key_id))


@celery_app.task(name="app.tasks.sync_exchanges.sync_binance")
def sync_binance(user_id: str, api_key_id: str):
    """Sync Binance account for a user."""
    return asyncio.run(_sync_single_exchange(api_key_id))


@celery_app.task(name="app.tasks.sync_exchanges.sync_kraken")
def sync_kraken(user_id: str, api_key_id: str):
    """Sync Kraken account for a user."""
    return asyncio.run(_sync_single_exchange(api_key_id))


@celery_app.task(name="app.tasks.sync_exchanges.sync_crypto_com")
def sync_crypto_com(user_id: str, api_key_id: str):
    """Sync Crypto.com account for a user."""
    return asyncio.run(_sync_single_exchange(api_key_id))
