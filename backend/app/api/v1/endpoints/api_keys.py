"""API Keys endpoints for exchange connections."""

import logging
from datetime import datetime, timedelta, timezone
from typing import List
from uuid import UUID

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.security import decrypt_api_key, encrypt_api_key
from app.models.api_key import APIKey
from app.models.user import User
from app.schemas.api_key import APIKeyCreate, APIKeyResponse, APIKeyTestResult, APIKeyUpdate, ExchangeInfo
from app.services.exchanges import SUPPORTED_EXCHANGES, get_exchange_service
from app.services.metrics_service import invalidate_dashboard_cache

router = APIRouter()


def _classify_and_mark_error(api_key, exc: Exception) -> None:
    """Classify an exchange error and update api_key status accordingly."""
    import httpx

    error_msg = str(exc)

    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (401, 403):
            api_key.mark_auth_failure(error_msg)
            logger.warning("API key %s: auth failure (%d)", api_key.id, code)
            return
        if code == 429:
            api_key.mark_rate_limited(error_msg)
            logger.warning("API key %s: rate limited (429)", api_key.id)
            return

    lower_msg = error_msg.lower()
    if "invalid key" in lower_msg or "invalid signature" in lower_msg or "permission denied" in lower_msg:
        api_key.mark_auth_failure(error_msg)
        logger.warning("API key %s: auth failure (json)", api_key.id)
        return

    api_key.mark_error(error_msg)


@router.get("/exchanges", response_model=List[ExchangeInfo])
async def list_supported_exchanges() -> List[ExchangeInfo]:
    """List all supported exchanges."""
    return [ExchangeInfo(**exchange) for exchange in SUPPORTED_EXCHANGES]


@router.get("", response_model=List[APIKeyResponse])
async def list_api_keys(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[APIKeyResponse]:
    """List all API keys for the current user."""
    result = await db.execute(select(APIKey).where(APIKey.user_id == current_user.id))
    api_keys = result.scalars().all()
    return api_keys


@router.post("", response_model=APIKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    api_key_in: APIKeyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIKeyResponse:
    """Create a new API key for an exchange."""
    # Verify exchange is supported
    exchange_lower = api_key_in.exchange.lower()
    supported_ids = [e["id"] for e in SUPPORTED_EXCHANGES]
    if exchange_lower not in supported_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Exchange non supporté. Exchanges supportés: {', '.join(supported_ids)}",
        )

    # Encrypt sensitive data
    encrypted_api = encrypt_api_key(api_key_in.api_key)
    encrypted_secret = None
    encrypted_passphrase = None

    if api_key_in.secret_key:
        encrypted_secret = encrypt_api_key(api_key_in.secret_key)
    if api_key_in.passphrase:
        encrypted_passphrase = encrypt_api_key(api_key_in.passphrase)

    # Create API key
    api_key = APIKey(
        user_id=current_user.id,
        exchange=exchange_lower,
        label=api_key_in.label,
        encrypted_api_key=encrypted_api,
        encrypted_secret_key=encrypted_secret,
        encrypted_passphrase=encrypted_passphrase,
        is_active=True,
    )

    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    return api_key


@router.get("/{api_key_id}", response_model=APIKeyResponse)
async def get_api_key(
    api_key_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIKeyResponse:
    """Get a specific API key."""
    result = await db.execute(
        select(APIKey).where(
            APIKey.id == api_key_id,
            APIKey.user_id == current_user.id,
        )
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clé API non trouvée",
        )

    return api_key


@router.patch("/{api_key_id}", response_model=APIKeyResponse)
async def update_api_key(
    api_key_id: UUID,
    api_key_in: APIKeyUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIKeyResponse:
    """Update an API key."""
    result = await db.execute(
        select(APIKey).where(
            APIKey.id == api_key_id,
            APIKey.user_id == current_user.id,
        )
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clé API non trouvée",
        )

    # Update fields
    if api_key_in.label is not None:
        api_key.label = api_key_in.label
    if api_key_in.is_active is not None:
        api_key.is_active = api_key_in.is_active
    if api_key_in.api_key:
        api_key.encrypted_api_key = encrypt_api_key(api_key_in.api_key)
    if api_key_in.secret_key:
        api_key.encrypted_secret_key = encrypt_api_key(api_key_in.secret_key)
    if api_key_in.passphrase:
        api_key.encrypted_passphrase = encrypt_api_key(api_key_in.passphrase)

    await db.commit()
    await db.refresh(api_key)

    return api_key


@router.delete("/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    api_key_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an API key."""
    result = await db.execute(
        select(APIKey).where(
            APIKey.id == api_key_id,
            APIKey.user_id == current_user.id,
        )
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clé API non trouvée",
        )

    await db.delete(api_key)
    await db.commit()


@router.post("/{api_key_id}/test", response_model=APIKeyTestResult)
@limiter.limit("5/minute")
async def test_api_key(
    request: Request,
    api_key_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIKeyTestResult:
    """Test an API key connection."""
    result = await db.execute(
        select(APIKey).where(
            APIKey.id == api_key_id,
            APIKey.user_id == current_user.id,
        )
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clé API non trouvée",
        )

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

        # Test connection
        success = await service.test_connection()

        if success:
            # Get balances for display
            balances = await service.get_balances()
            balance_dict = {b.symbol: float(b.total) for b in balances[:10]}

            # Update last sync
            api_key.last_sync_at = datetime.now(timezone.utc)
            api_key.last_error = None
            await db.commit()

            return APIKeyTestResult(
                success=True,
                message="Connexion réussie",
                balance=balance_dict if balance_dict else None,
            )
        else:
            api_key.last_error = "Échec de la connexion"
            await db.commit()

            return APIKeyTestResult(
                success=False,
                message="Échec de la connexion. Vérifiez vos identifiants.",
            )

    except Exception as e:
        api_key.last_error = str(e)[:500]
        await db.commit()

        return APIKeyTestResult(
            success=False,
            message="Erreur de connexion. Vérifiez vos identifiants et réessayez.",
        )


class _FiatTrade:
    """Trade-like wrapper for fiat orders."""

    def __init__(self, order):
        self.trade_id = f"fiat_{order.order_id}"
        self.symbol = f"{order.crypto_symbol}{order.fiat_currency}"
        self.side = order.side
        self.quantity = order.crypto_amount
        self.price = order.price
        self.fee = order.fee
        self.fee_currency = order.fiat_currency
        self.timestamp = order.timestamp


class _WithdrawalTrade:
    """Trade-like wrapper for withdrawal records."""

    def __init__(self, w, quote_currency: str = "EUR"):
        self.trade_id = f"withdrawal_{w.withdrawal_id}"
        self.symbol = f"{w.symbol}{quote_currency}"
        self.side = "withdrawal"
        self.quantity = w.amount
        self.price = 0
        self.fee = w.fee
        self.fee_currency = w.symbol
        self.timestamp = w.timestamp


@router.post("/{api_key_id}/import-history", response_model=dict)
@limiter.limit("5/minute")
async def import_trade_history(
    request: Request,
    api_key_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import full trade history from exchange with actual prices."""
    from collections import defaultdict

    from app.models.asset import Asset, AssetType
    from app.models.portfolio import Portfolio
    from app.models.transaction import Transaction, TransactionType

    result = await db.execute(
        select(APIKey).where(
            APIKey.id == api_key_id,
            APIKey.user_id == current_user.id,
        )
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clé API non trouvée",
        )

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

        # Get or create a single "Crypto" portfolio (all exchanges go into one portfolio)
        portfolio_result = await db.execute(
            select(Portfolio).where(
                Portfolio.user_id == current_user.id,
                Portfolio.name == "Crypto",
            )
        )
        portfolio = portfolio_result.scalar_one_or_none()

        # Also check for legacy per-exchange portfolios to reuse
        if not portfolio:
            legacy_result = await db.execute(
                select(Portfolio).where(
                    Portfolio.user_id == current_user.id,
                    Portfolio.name == f"{service.exchange_name}",
                )
            )
            portfolio = legacy_result.scalar_one_or_none()
            if portfolio:
                # Rename legacy portfolio to "Crypto"
                portfolio.name = "Crypto"
                portfolio.description = "Portefeuille crypto consolidé"

        if not portfolio:
            portfolio = Portfolio(
                user_id=current_user.id,
                name="Crypto",
                description="Portefeuille crypto consolidé",
            )
            db.add(portfolio)
            await db.flush()

        # Merge assets from other exchange portfolios into this one
        other_portfolios_result = await db.execute(
            select(Portfolio).where(
                Portfolio.user_id == current_user.id,
                Portfolio.id != portfolio.id,
                Portfolio.name.in_(["Binance", "Kraken", "Crypto.com"]),
            )
        )
        other_portfolios = other_portfolios_result.scalars().all()
        for other_portfolio in other_portfolios:
            # Move all assets to the Crypto portfolio
            other_assets_result = await db.execute(select(Asset).where(Asset.portfolio_id == other_portfolio.id))
            for other_asset in other_assets_result.scalars().all():
                other_asset.portfolio_id = portfolio.id
            # Move snapshots
            from app.models.portfolio_snapshot import PortfolioSnapshot

            snapshot_result = await db.execute(
                select(PortfolioSnapshot).where(PortfolioSnapshot.portfolio_id == other_portfolio.id)
            )
            for snapshot in snapshot_result.scalars().all():
                snapshot.portfolio_id = portfolio.id
            # Merge cash_balances
            if other_portfolio.cash_balances:
                if not portfolio.cash_balances:
                    portfolio.cash_balances = {}
                for key, val in other_portfolio.cash_balances.items():
                    portfolio.cash_balances[key] = portfolio.cash_balances.get(key, 0) + val
            # Delete empty portfolio
            await db.delete(other_portfolio)
            logger.info(f"Merged portfolio '{other_portfolio.name}' into 'Crypto'")

        await db.flush()

        # Get current balances first
        balances = await service.get_balances()
        balance_map = {b.symbol: b for b in balances}

        # Normalize Binance Earn variants (LDUSDC → USDC, etc.)
        # Merge earn balances into base symbol and track staked amounts
        from app.tasks.sync_exchanges import _normalize_earn_variant

        earn_staked: dict = {}  # {base_symbol: staked_qty}
        normalized_balance_map: dict = {}
        for b in balances:
            norm = _normalize_earn_variant(b.symbol)
            if norm != b.symbol:
                # This is an earn variant — track staked amount
                earn_staked[norm] = earn_staked.get(norm, 0) + float(b.total)
                logger.info(f"Earn variant: {b.symbol} ({float(b.total)}) → staked {norm}")
                # Merge into base symbol balance for reconciliation
                if norm in normalized_balance_map:
                    existing = normalized_balance_map[norm]
                    from app.services.exchanges.base import ExchangeBalance

                    normalized_balance_map[norm] = ExchangeBalance(
                        symbol=norm,
                        free=existing.free + b.free,
                        locked=existing.locked + b.locked,
                        total=existing.total + b.total,
                    )
                else:
                    from app.services.exchanges.base import ExchangeBalance

                    base_balance = balance_map.get(norm)
                    if base_balance:
                        normalized_balance_map[norm] = ExchangeBalance(
                            symbol=norm,
                            free=base_balance.free + b.free,
                            locked=base_balance.locked + b.locked,
                            total=base_balance.total + b.total,
                        )
                    else:
                        normalized_balance_map[norm] = ExchangeBalance(
                            symbol=norm, free=b.free, locked=b.locked, total=b.total
                        )
            else:
                if b.symbol not in normalized_balance_map:
                    normalized_balance_map[b.symbol] = b
        balance_map = normalized_balance_map

        # Get all trades (no arbitrary cap — paginate fully)
        trades = await service.get_trades(limit=10000)

        # Pre-fetch ledgers once for Kraken (used by instant_buys + conversions)
        _cached_ledgers = None
        if hasattr(service, "get_ledgers"):
            logger.info("Fetching Kraken ledger entries...")
            _cached_ledgers = await service.get_ledgers(limit=10000)
            logger.info(f"Ledger entries fetched: {len(_cached_ledgers)}")

        # Get Instant Buy transactions from Kraken ledgers
        instant_buys = []
        instant_buy_refids = set()
        if hasattr(service, "get_instant_buys"):
            logger.info("Querying Kraken Instant Buy history from ledgers...")
            instant_buys, instant_buy_refids = await service.get_instant_buys(limit=500, ledgers=_cached_ledgers)
            logger.info(f"Instant Buy orders found: {len(instant_buys)} (refids: {len(instant_buy_refids)})")
            # Add instant buys to trades list
            trades.extend(instant_buys)

        # Get staking rewards from Kraken ledgers
        rewards = []
        if hasattr(service, "get_rewards"):
            logger.info("Querying Kraken rewards/staking history from ledgers...")
            rewards = await service.get_rewards(limit=500, ledgers=_cached_ledgers)
            logger.info(f"Rewards found: {len(rewards)}")

            # Fetch historical prices for rewards
            if rewards:
                import asyncio

                from app.services.price_service import price_service

                logger.info("Fetching historical prices for rewards (this may take a moment)...")

                # Group rewards by symbol and date to minimize API calls
                price_cache = {}
                for reward in rewards:
                    # Extract symbol from pair (e.g., BTCEUR -> BTC)
                    symbol = reward.symbol.replace("EUR", "").replace("USD", "")
                    date_key = f"{symbol}_{reward.timestamp.strftime('%Y-%m-%d')}"

                    if date_key not in price_cache:
                        try:
                            price = await price_service.get_historical_crypto_price(symbol, reward.timestamp, "eur")
                            price_cache[date_key] = price
                            if price:
                                logger.debug(f"{symbol} @ {reward.timestamp.date()}: {float(price):.2f} EUR")
                            # Delay to avoid CoinGecko rate limiting (50 req/min)
                            await asyncio.sleep(1.5)
                        except Exception as e:
                            logger.error(f"Error getting price for {symbol}: {e}")
                            price_cache[date_key] = None

                    # Update reward price
                    if price_cache.get(date_key):
                        reward.price = price_cache[date_key]

            # Add rewards to trades list
            trades.extend(rewards)

        # Get crypto-to-crypto conversions (Kraken, Crypto.com)
        # Skip for Binance: get_convert_history already covers crypto-to-crypto conversions
        # and calling both causes duplicates since they use the same API endpoint
        conversions = []
        if hasattr(service, "get_crypto_conversions") and service.exchange_name != "Binance":
            logger.info(f"Querying {service.exchange_name} crypto-to-crypto conversions...")
            # Pass exclude_refids for Kraken to avoid duplicates with instant buys
            if instant_buy_refids:
                conversions = await service.get_crypto_conversions(
                    limit=500, exclude_refids=instant_buy_refids, ledgers=_cached_ledgers
                )
            else:
                conversions = await service.get_crypto_conversions(limit=500, ledgers=_cached_ledgers)
            logger.info(f"Crypto conversions found: {len(conversions)}")

            # Fetch historical EUR prices for conversions
            if conversions:
                import asyncio

                from app.services.price_service import price_service

                logger.info("Fetching historical EUR prices for conversions...")

                price_cache = {}
                for conversion in conversions:
                    # Extract base symbol from pair (now always xxxEUR format)
                    symbol = conversion.symbol
                    for quote in ["EUR", "USD", "USDT", "BTC", "ETH"]:
                        if symbol.endswith(quote) and len(symbol) > len(quote):
                            symbol = symbol[: -len(quote)]
                            break

                    date_key = f"{symbol}_{conversion.timestamp.strftime('%Y-%m-%d')}"

                    if date_key not in price_cache:
                        try:
                            price = await price_service.get_historical_crypto_price(symbol, conversion.timestamp, "eur")
                            price_cache[date_key] = price
                            if price:
                                logger.debug(f"{symbol} @ {conversion.timestamp.date()}: {float(price):.2f} EUR")
                            # Delay to avoid rate limiting
                            await asyncio.sleep(1.5)
                        except Exception as e:
                            logger.error(f"Error getting price for {symbol}: {e}")
                            price_cache[date_key] = None

                    # Update conversion price with actual EUR price
                    if price_cache.get(date_key):
                        conversion.price = price_cache[date_key]

            # Add conversions to trades list
            trades.extend(conversions)

        # Get fiat orders (direct EUR/USD purchases via card/bank)
        # Query full history (from 2017 when Binance started)
        fiat_orders = await service.get_fiat_orders(limit=500)
        logger.info(f"Fiat orders found: {len(fiat_orders)}")

        # Get convert history (EUR -> BTC conversions)
        # Query in 30-day chunks from 2017 to now (API requires time ranges)
        convert_orders = []
        if hasattr(service, "get_convert_history"):
            # Start from 2017 (Binance launch) to now
            target_start = datetime(2017, 7, 1, 0, 0, 0)  # Binance launched July 2017
            target_end = datetime.now()

            logger.info(f"Querying FULL convert history from {target_start} to {target_end}")

            # Query in 30-day chunks going backwards
            chunk_end = target_end

            while chunk_end > target_start:
                chunk_start = max(chunk_end - timedelta(days=30), target_start)

                try:
                    chunk = await service.get_convert_history(start_time=chunk_start, end_time=chunk_end, limit=1000)

                    if chunk:
                        convert_orders.extend(chunk)
                        logger.info(f"Found {len(chunk)} conversions from {chunk_start.date()} to {chunk_end.date()}")
                except Exception as e:
                    logger.error(f"Error querying convert history {chunk_start.date()} to {chunk_end.date()}: {e}")

                chunk_end = chunk_start - timedelta(seconds=1)

            logger.info(f"Total convert orders found: {len(convert_orders)}")

        # Get Auto-Invest (DCA) history
        auto_invest_orders = []
        if hasattr(service, "get_auto_invest_history"):
            logger.info("Querying Auto-Invest history...")
            # Query in 90-day chunks
            chunk_end = datetime.now()
            target_start = datetime(2020, 1, 1)  # Auto-invest launched around 2020

            while chunk_end > target_start:
                chunk_start = max(chunk_end - timedelta(days=90), target_start)
                try:
                    chunk = await service.get_auto_invest_history(start_time=chunk_start, end_time=chunk_end, limit=100)
                    if chunk:
                        auto_invest_orders.extend(chunk)
                        logger.info(
                            f"Found {len(chunk)} auto-invest orders from {chunk_start.date()} to {chunk_end.date()}"
                        )
                except Exception as e:
                    logger.error(f"Error querying auto-invest: {e}")
                chunk_end = chunk_start - timedelta(seconds=1)

            logger.info(f"Total auto-invest orders found: {len(auto_invest_orders)}")

        # Get withdrawals (transfers out to cold wallets, etc.)
        withdrawals = []
        if hasattr(service, "get_withdrawals"):
            logger.info(f"Querying {service.exchange_name} withdrawal history...")
            withdrawals = await service.get_withdrawals(limit=500)
            logger.info(f"Withdrawals found: {len(withdrawals)}")

        # Deduplicate convert_orders against fiat_orders
        # Both APIs (fiat/payments and convert/tradeFlow) return the same EUR->crypto
        # purchases with different IDs. Match by (symbol, quantity, timestamp±60s).
        fiat_order_keys = set()
        for fo in fiat_orders:
            # Round timestamp to nearest minute for fuzzy matching
            ts_key = int(fo.timestamp.timestamp()) // 60
            normalized_amount = (
                str(fo.crypto_amount.normalize()) if hasattr(fo.crypto_amount, "normalize") else str(fo.crypto_amount)
            )
            fiat_order_keys.add((fo.crypto_symbol, normalized_amount, ts_key))
            # Also add adjacent minute to handle boundary cases
            fiat_order_keys.add((fo.crypto_symbol, normalized_amount, ts_key + 1))
            fiat_order_keys.add((fo.crypto_symbol, normalized_amount, ts_key - 1))

        deduped_convert_orders = []
        for co in convert_orders:
            ts_key = int(co.timestamp.timestamp()) // 60
            co_normalized = (
                str(co.crypto_amount.normalize()) if hasattr(co.crypto_amount, "normalize") else str(co.crypto_amount)
            )
            key = (co.crypto_symbol, co_normalized, ts_key)
            if key in fiat_order_keys:
                logger.debug(
                    f"Skipping duplicate convert order: {co.crypto_symbol} {co.crypto_amount} at {co.timestamp}"
                )
                continue
            deduped_convert_orders.append(co)

        if len(convert_orders) != len(deduped_convert_orders):
            logger.info(
                f"Deduplicated {len(convert_orders) - len(deduped_convert_orders)} convert orders "
                f"that overlap with fiat orders"
            )

        # Combine all orders
        all_fiat_orders = fiat_orders + deduped_convert_orders + auto_invest_orders

        # Debug info
        debug_info = {
            "balances_count": len(balances),
            "spot_trades_count": max(0, len(trades) - len(instant_buys) - len(rewards) - len(conversions)),
            "instant_buys_count": len(instant_buys),
            "rewards_count": len(rewards),
            "conversions_count": len(conversions),
            "withdrawals_count": len(withdrawals),
            "fiat_orders_count": len(fiat_orders),
            "convert_orders_count": len(convert_orders),
            "auto_invest_count": len(auto_invest_orders),
            "total_fiat_orders": len(all_fiat_orders),
            "balances_symbols": [b.symbol for b in balances[:10]],
        }

        # Group trades by base asset (extract from pair like BTCUSDT -> BTC)
        asset_trades = defaultdict(list)
        for trade in trades:
            # Extract base asset from trading pair (e.g., BTCUSDT -> BTC)
            symbol = trade.symbol
            for quote in ["USDT", "FDUSD", "USDC", "BUSD", "EUR", "USD", "BTC", "ETH", "BNB"]:
                if symbol.endswith(quote):
                    base_asset = symbol[: -len(quote)]
                    asset_trades[base_asset].append(trade)
                    break

        # Add fiat orders to asset_trades (convert to trade-like objects)
        # Build a set of order IDs already imported via conversions to avoid duplicates
        conversion_base_ids = set()
        for conv in conversions:
            # Extract base ID from convert_buy_XXX or convert_sell_XXX
            base_id = conv.trade_id
            for prefix in ["convert_buy_", "convert_sell_"]:
                if base_id.startswith(prefix):
                    base_id = base_id[len(prefix) :]
                    break
            conversion_base_ids.add(base_id)

        fiat_order_ids = set()
        for fiat_order in all_fiat_orders:
            symbol = fiat_order.crypto_symbol
            if symbol:
                # Skip if this order was already imported as a conversion
                # BUT only skip buy-side: crypto conversions from get_crypto_conversions
                # misattribute the base asset on sell-side (e.g., OM->USDC sell shows as USDC sell).
                # The sell-side from get_convert_history has the correct asset, so we keep it.
                base_order_id = fiat_order.order_id
                if base_order_id.startswith("sell_"):
                    base_order_id = base_order_id[len("sell_") :]
                elif base_order_id.startswith("buy_"):
                    base_order_id = base_order_id[len("buy_") :]

                is_crypto_sell = fiat_order.order_id.startswith("sell_") or (
                    fiat_order.side == "sell"
                    and fiat_order.fiat_currency
                    not in ["EUR", "USD", "GBP", "TRY", "RUB", "UAH", "BRL", "AUD", "CAD", "JPY"]
                )
                if base_order_id in conversion_base_ids and not is_crypto_sell:
                    logger.debug(f"Skipping fiat order {fiat_order.order_id} (already imported as conversion)")
                    continue

                asset_trades[symbol].append(_FiatTrade(fiat_order))
                fiat_order_ids.add(f"fiat_{fiat_order.order_id}")

        # Add withdrawals to asset_trades as TRANSFER_OUT
        fiat_currencies = ["USD", "EUR", "GBP", "TRY", "RUB", "UAH", "BRL", "AUD", "CAD", "JPY"]
        for withdrawal in withdrawals:
            if withdrawal.status.lower() not in ("success", "complete", "completed", "settled"):
                continue  # Skip pending/failed withdrawals
            symbol = withdrawal.symbol
            if symbol in fiat_currencies:
                continue

            asset_trades[symbol].append(_WithdrawalTrade(withdrawal))

        # Get all portfolio assets
        assets_result = await db.execute(
            select(Asset).where(
                Asset.portfolio_id == portfolio.id,
            )
        )
        all_portfolio_assets = assets_result.scalars().all()

        # Get existing transaction IDs from ALL portfolio assets to avoid duplicates
        existing_trade_ids = set()
        all_asset_ids = [a.id for a in all_portfolio_assets]
        if all_asset_ids:
            trans_result = await db.execute(
                select(Transaction.notes, Transaction.external_id).where(
                    Transaction.asset_id.in_(all_asset_ids),
                )
            )
            for row in trans_result.fetchall():
                note, ext_id = row
                if ext_id:
                    existing_trade_ids.add(ext_id)
                if note and "trade_id:" in note:
                    existing_trade_ids.add(note.split("trade_id:")[1])

        # Build asset lookup for this exchange import
        # Key: (symbol, exchange) for multi-platform support
        existing_assets = {}
        transferred_symbols = set()  # Symbols where user changed exchange (don't overwrite)

        # First pass: exact exchange match or unassigned
        for a in all_portfolio_assets:
            if a.exchange == service.exchange_name:
                existing_assets[a.symbol] = a
            elif a.exchange == "" and a.symbol not in existing_assets:
                existing_assets[a.symbol] = a

        # Second pass: find transferred assets by checking if their trade IDs
        # overlap with trades we're about to import (same trade = same source exchange)
        for a in all_portfolio_assets:
            if a.symbol in existing_assets:
                continue
            if a.symbol not in asset_trades:
                continue
            # Check if any of this asset's transactions match trades from this import
            asset_trade_ids_result = await db.execute(
                select(Transaction.notes).where(
                    Transaction.asset_id == a.id,
                    Transaction.notes.isnot(None),
                )
            )
            asset_trade_ids = set()
            for note in asset_trade_ids_result.scalars().all():
                if note and "trade_id:" in note:
                    asset_trade_ids.add(note.split("trade_id:")[1])

            # If any incoming trade already exists on this asset, it's from our exchange
            for trade in asset_trades[a.symbol]:
                if trade.trade_id in asset_trade_ids:
                    existing_assets[a.symbol] = a
                    transferred_symbols.add(a.symbol)
                    logger.info(
                        f"{a.symbol}: found transferred asset (now on {a.exchange}, originally from {service.exchange_name})"
                    )
                    break

        # Remove sync-created adjustment transactions (init/sync) since
        # the real transaction history will replace them.
        exchange_prefix = service.exchange_name
        sync_asset_ids = [a.id for a in existing_assets.values()]
        if sync_asset_ids:
            from sqlalchemy import delete as sql_delete

            sync_del = await db.execute(
                sql_delete(Transaction).where(
                    Transaction.asset_id.in_(sync_asset_ids),
                    Transaction.external_id.ilike(f"{exchange_prefix}_%"),
                )
            )
            removed = sync_del.rowcount
            if removed:
                logger.info(f"Removed {removed} sync adjustment transactions before history import")
                # Also remove them from existing_trade_ids so they don't block reimport
                existing_trade_ids = {tid for tid in existing_trade_ids if not tid.startswith(f"{exchange_prefix}_")}

        imported_count = 0
        fiat_orders_count = 0
        rewards_count = 0
        conversions_count = 0
        withdrawals_imported = 0
        assets_updated = 0

        # Fetch current USD→EUR rate for USD-denominated pairs (fallback to 0.92)
        from app.services.price_service import price_service

        usd_eur_rate = 0.92
        try:
            forex_rate = await price_service.get_forex_rate("USD", "EUR")
            if forex_rate:
                usd_eur_rate = float(forex_rate)
        except Exception:
            pass

        for symbol, symbol_trades in asset_trades.items():
            if symbol in fiat_currencies:
                continue

            # Get or create asset
            if symbol in existing_assets:
                asset = existing_assets[symbol]
            else:
                # Check if an asset with same symbol already exists for another exchange
                # (avoid creating duplicates)
                existing_check = await db.execute(
                    select(Asset).where(
                        Asset.portfolio_id == portfolio.id,
                        Asset.symbol == symbol,
                        Asset.exchange == service.exchange_name,
                    )
                )
                existing_match = existing_check.scalar_one_or_none()
                if existing_match:
                    asset = existing_match
                    existing_assets[symbol] = asset
                else:
                    # Get current balance
                    balance = balance_map.get(symbol)
                    current_qty = float(balance.total) if balance else 0

                    asset = Asset(
                        portfolio_id=portfolio.id,
                        symbol=symbol,
                        name=symbol,
                        asset_type=AssetType.CRYPTO,
                        quantity=current_qty,
                        avg_buy_price=0,
                        currency="EUR",
                        exchange=service.exchange_name,
                    )
                    db.add(asset)
                    await db.flush()
                    existing_assets[symbol] = asset
                assets_updated += 1

            # Import trades as transactions
            for trade in sorted(symbol_trades, key=lambda x: x.timestamp):
                # Skip already imported trades (check both prefixed and raw forms)
                if trade.trade_id in existing_trade_ids:
                    continue
                # Cross-check: fiat_ prefixed ID may exist without prefix (from sync_exchanges)
                if trade.trade_id.startswith("fiat_") and trade.trade_id[5:] in existing_trade_ids:
                    continue

                # Determine transaction type based on trade source
                is_staking_reward = trade.trade_id.startswith("reward_staking_")
                is_airdrop = (
                    trade.trade_id.startswith("reward_airdrop_")
                    or trade.trade_id.startswith("reward_")
                    and not trade.trade_id.startswith("reward_staking_")
                )
                is_fiat_order = trade.trade_id.startswith("fiat_") or trade.trade_id.startswith("instant_")
                is_conversion = trade.trade_id.startswith("convert_")
                is_withdrawal = trade.trade_id.startswith("withdrawal_")

                # Skip withdrawals for transferred assets (e.g., BTC withdrawn from Kraken
                # to Tangem wallet). The BUYs are already on the Tangem asset, so adding
                # a TRANSFER_OUT would incorrectly subtract the quantity.
                if is_withdrawal and symbol in transferred_symbols:
                    continue

                if is_withdrawal:
                    trans_type = TransactionType.TRANSFER_OUT
                elif is_staking_reward:
                    trans_type = TransactionType.STAKING_REWARD
                elif is_airdrop:
                    trans_type = TransactionType.AIRDROP
                elif is_conversion:
                    # Use dedicated conversion types
                    if trade.trade_id.startswith("convert_sell_"):
                        trans_type = TransactionType.CONVERSION_OUT
                    else:  # convert_buy_
                        trans_type = TransactionType.CONVERSION_IN
                elif trade.side == "buy":
                    trans_type = TransactionType.BUY
                else:
                    trans_type = TransactionType.SELL

                # Calculate price in EUR
                # For USDT/USDC pairs, apply approximate USD→EUR conversion
                trade_symbol = getattr(trade, "symbol", "")
                price_eur = float(trade.price)
                if any(trade_symbol.endswith(q) for q in ["USDT", "USDC", "BUSD", "FDUSD", "USD"]):
                    price_eur = price_eur * usd_eur_rate

                # For conversions, store the conversion rate
                conversion_rate = None
                if is_conversion and trade.price:
                    conversion_rate = float(trade.price)

                # Handle fee: convert crypto fees to EUR
                fee_amount = float(trade.fee) if trade.fee else 0
                fee_currency = getattr(trade, "fee_currency", None) or "EUR"

                # If fee is in a crypto currency, convert to EUR
                if fee_currency not in ["EUR", "USD", "GBP", "CAD", "JPY"] and fee_amount > 0:
                    if fee_currency == symbol:
                        # Fee is in the same token as the trade (e.g., PEPE fee on PEPE trade)
                        if price_eur > 0:
                            fee_amount = fee_amount * price_eur
                        else:
                            fee_amount = 0
                    else:
                        # Fee is in a different token (e.g., BNB fee on PEPE trade)
                        # Look up the fee token's current price
                        fee_token_price = 0
                        try:
                            fee_price_data = await price_service.get_multiple_crypto_prices([fee_currency], "eur")
                            if fee_currency.lower() in fee_price_data:
                                fee_token_price = float(fee_price_data[fee_currency.lower()].get("price", 0))
                            elif fee_currency.upper() in fee_price_data:
                                fee_token_price = float(fee_price_data[fee_currency.upper()].get("price", 0))
                        except Exception:
                            pass
                        if fee_token_price > 0:
                            fee_amount = fee_amount * fee_token_price
                        elif price_eur > 0:
                            # Fallback: use asset price (better than nothing)
                            fee_amount = fee_amount * price_eur
                        else:
                            fee_amount = 0
                    fee_currency = "EUR"

                transaction = Transaction(
                    asset_id=asset.id,
                    transaction_type=trans_type,
                    quantity=float(trade.quantity),
                    price=price_eur,
                    fee=fee_amount,
                    fee_currency=fee_currency,
                    currency="EUR",
                    executed_at=trade.timestamp,
                    external_id=trade.trade_id,
                    exchange=service.exchange_name,
                    notes=f"trade_id:{trade.trade_id}",
                    conversion_rate=conversion_rate,
                )
                db.add(transaction)
                imported_count += 1
                if is_fiat_order:
                    fiat_orders_count += 1
                if is_staking_reward or is_airdrop:
                    rewards_count += 1
                if is_conversion:
                    conversions_count += 1
                if is_withdrawal:
                    withdrawals_imported += 1

            # Set exchange name on the asset (the exchange it was imported from)
            if not asset.exchange:
                asset.exchange = service.exchange_name

        # Flush to get transaction IDs before linking
        await db.flush()

        # Link conversion pairs together
        # Rebuild all_asset_ids to include newly created assets from the import
        refreshed_assets_result = await db.execute(select(Asset.id).where(Asset.portfolio_id == portfolio.id))
        all_asset_ids = [row[0] for row in refreshed_assets_result.fetchall()]

        # Get all newly created conversion transactions
        if conversions_count > 0 and all_asset_ids:
            conversion_trans_result = await db.execute(
                select(Transaction).where(
                    Transaction.asset_id.in_(all_asset_ids),
                    Transaction.transaction_type.in_([TransactionType.CONVERSION_OUT, TransactionType.CONVERSION_IN]),
                    Transaction.related_transaction_id.is_(None),
                    Transaction.notes.ilike("%convert_%"),
                )
            )
            conversion_transactions = conversion_trans_result.scalars().all()

            # Group by base ID (extract XXX from convert_sell_XXX or convert_buy_XXX)
            conversion_pairs = {}
            for trans in conversion_transactions:
                if trans.notes and "trade_id:" in trans.notes:
                    trade_id = trans.notes.split("trade_id:")[1]
                    # Extract base ID (remove convert_sell_ or convert_buy_ prefix)
                    if trade_id.startswith("convert_sell_"):
                        base_id = trade_id[len("convert_sell_") :]
                        if base_id not in conversion_pairs:
                            conversion_pairs[base_id] = {}
                        conversion_pairs[base_id]["sell"] = trans
                    elif trade_id.startswith("convert_buy_"):
                        base_id = trade_id[len("convert_buy_") :]
                        if base_id not in conversion_pairs:
                            conversion_pairs[base_id] = {}
                        conversion_pairs[base_id]["buy"] = trans

            # Link pairs
            linked_count = 0
            for base_id, pair in conversion_pairs.items():
                if "sell" in pair and "buy" in pair:
                    sell_trans = pair["sell"]
                    buy_trans = pair["buy"]
                    # Link sell to buy
                    sell_trans.related_transaction_id = buy_trans.id
                    buy_trans.related_transaction_id = sell_trans.id
                    linked_count += 1

            if linked_count > 0:
                logger.info(f"Linked {linked_count} conversion pairs")

        # Recalculate asset quantities and reconcile with API balances
        add_types = [
            TransactionType.BUY,
            TransactionType.TRANSFER_IN,
            TransactionType.AIRDROP,
            TransactionType.STAKING_REWARD,
            TransactionType.CONVERSION_IN,
        ]
        sub_types = [
            TransactionType.SELL,
            TransactionType.CONVERSION_OUT,
            TransactionType.TRANSFER_OUT,
        ]

        reconciled_count = 0
        for symbol, asset in existing_assets.items():
            # Skip transferred assets — user changed exchange, don't overwrite
            if symbol in transferred_symbols:
                logger.info(f"{symbol}: skipping quantity update (transferred to {asset.exchange})")
                continue

            # Calculate quantity from transactions
            calc_result = await db.execute(
                select(
                    func.coalesce(
                        func.sum(
                            case(
                                (Transaction.transaction_type.in_(add_types), Transaction.quantity),
                                (Transaction.transaction_type.in_(sub_types), -Transaction.quantity),
                                else_=0,
                            )
                        ),
                        0,
                    )
                ).where(Transaction.asset_id == asset.id)
            )
            calc_qty = max(0, float(calc_result.scalar()))

            # Get real balance from API
            balance = balance_map.get(symbol)
            api_qty = float(balance.total) if balance else 0

            # Use API balance as the source of truth
            # If there's a discrepancy, set quantity to API balance
            if abs(calc_qty - api_qty) > 0.00000001:
                asset.quantity = api_qty
                if api_qty > 0 and calc_qty > 0:
                    logger.info(
                        f"{symbol}: reconciled quantity (transactions={calc_qty:.8f}, API={api_qty:.8f}, diff={calc_qty - api_qty:.8f})"
                    )
                elif api_qty == 0 and calc_qty > 0:
                    logger.info(f"{symbol}: sold/converted (transactions show {calc_qty:.8f} but API balance is 0)")
                elif api_qty > 0 and calc_qty == 0:
                    logger.info(f"{symbol}: API balance {api_qty:.8f} but no matching transactions found")
                reconciled_count += 1
            else:
                asset.quantity = api_qty if api_qty > 0 else calc_qty

            # Recalculate avg_buy_price from BUY + CONVERSION_IN transactions with price > 0
            avg_result = await db.execute(
                select(
                    func.sum(Transaction.quantity * Transaction.price),
                    func.sum(Transaction.quantity),
                ).where(
                    Transaction.asset_id == asset.id,
                    Transaction.transaction_type.in_([TransactionType.BUY, TransactionType.CONVERSION_IN]),
                    Transaction.price > 0,
                )
            )
            row = avg_result.one()
            if row[1] and float(row[1]) > 0:
                asset.avg_buy_price = float(row[0]) / float(row[1])

        await db.flush()

        # Create STAKING transactions for Earn variants (LDUSDC → staking USDC, etc.)
        staking_created = 0
        for base_sym, staked_qty in earn_staked.items():
            if staked_qty <= 0 or base_sym not in existing_assets:
                continue
            asset = existing_assets[base_sym]
            # Check if a staking tx already exists for this asset
            existing_staking = await db.execute(
                select(Transaction)
                .where(
                    Transaction.asset_id == asset.id,
                    Transaction.transaction_type == TransactionType.STAKING,
                )
                .order_by(Transaction.executed_at.desc())
                .limit(1)
            )
            existing_staking_tx = existing_staking.scalar_one_or_none()
            if existing_staking_tx:
                # Update quantity to match current earn balance
                if abs(float(existing_staking_tx.quantity) - staked_qty) > 0.0001:
                    old_qty = float(existing_staking_tx.quantity)
                    existing_staking_tx.quantity = staked_qty
                    existing_staking_tx.executed_at = datetime.now(timezone.utc)
                    existing_staking_tx.notes = f"Auto: {staked_qty:.8f} {base_sym} in Earn/Staking"
                    staking_created += 1
                    logger.info(f"{base_sym}: updated STAKING tx {old_qty:.8f} → {staked_qty:.8f}")
                continue
            staking_tx = Transaction(
                asset_id=asset.id,
                transaction_type=TransactionType.STAKING,
                quantity=staked_qty,
                price=0,
                fee=0,
                currency="EUR",
                executed_at=datetime.now(timezone.utc),
                exchange=service.exchange_name,
                notes=f"Auto: {staked_qty:.8f} {base_sym} in Earn/Staking",
            )
            db.add(staking_tx)
            staking_created += 1
            logger.info(f"{base_sym}: created STAKING transaction ({staked_qty:.8f} in Earn)")

        if staking_created:
            await db.flush()

        # Create auto-mirror transfer_in for withdrawals (transfer_out)
        # so assets moved to cold wallets (e.g. Tangem) appear on destination.
        # This runs AFTER avg_buy_price is calculated so the cost basis propagates.
        if withdrawals_imported > 0:
            from app.services.transfer_service import create_mirror_transfer_in

            # Default destination for crypto withdrawals (cold wallet)
            cold_wallet_destination = "Tangem"

            withdrawal_asset_ids = [a.id for a in existing_assets.values()]
            if withdrawal_asset_ids:
                withdrawal_txs_result = await db.execute(
                    select(Transaction).where(
                        Transaction.asset_id.in_(withdrawal_asset_ids),
                        Transaction.transaction_type == TransactionType.TRANSFER_OUT,
                        Transaction.related_transaction_id.is_(None),
                    )
                )
                for w_tx in withdrawal_txs_result.scalars().all():
                    w_asset_result = await db.execute(select(Asset).where(Asset.id == w_tx.asset_id))
                    w_asset = w_asset_result.scalar_one_or_none()
                    if w_asset:
                        await create_mirror_transfer_in(db, w_tx, w_asset, cold_wallet_destination)
                await db.flush()

        # Create assets for API balances that have no transactions (e.g. airdrops, dust)
        fiat_currencies = {"EUR", "USD", "GBP", "TRY", "RUB", "UAH", "BRL", "AUD", "CAD", "JPY"}
        for balance in balances:
            symbol = balance.symbol
            # Skip earn variants — they're merged into base asset
            norm = _normalize_earn_variant(symbol)
            if norm != symbol:
                continue
            if symbol in fiat_currencies:
                continue
            if float(balance.total) < 0.00000001:
                continue
            if symbol in existing_assets:
                continue
            # Check if asset already exists for this exchange
            existing_check = await db.execute(
                select(Asset).where(
                    Asset.portfolio_id == portfolio.id,
                    Asset.symbol == balance.symbol,
                    Asset.exchange == service.exchange_name,
                )
            )
            if existing_check.scalar_one_or_none():
                continue
            # Create new asset from API balance
            asset = Asset(
                portfolio_id=portfolio.id,
                symbol=balance.symbol,
                name=balance.symbol,
                asset_type=AssetType.CRYPTO,
                quantity=float(balance.total),
                avg_buy_price=0,
                currency="EUR",
                exchange=service.exchange_name,
            )
            db.add(asset)
            existing_assets[balance.symbol] = asset
            assets_updated += 1
            logger.info(
                f"{balance.symbol}: created from API balance ({float(balance.total):.8f}, no transactions found)"
            )

        if reconciled_count > 0:
            logger.info(f"Reconciled {reconciled_count} assets with API balances")

        # Update last sync time
        api_key.last_sync_at = datetime.now(timezone.utc)
        api_key.mark_success()

        await db.commit()

        invalidate_dashboard_cache(str(current_user.id))

        return {
            "message": "Import de l'historique réussi",
            "imported_transactions": imported_count,
            "fiat_orders": fiat_orders_count,
            "rewards": rewards_count,
            "conversions": conversions_count,
            "withdrawals": withdrawals_imported,
            "spot_trades": max(
                0, imported_count - fiat_orders_count - rewards_count - conversions_count - withdrawals_imported
            ),
            "assets_created": assets_updated,
            "reconciled_assets": reconciled_count,
            "portfolio_id": str(portfolio.id),
            "portfolio_name": portfolio.name,
            "debug": debug_info,
        }

    except Exception as e:
        import traceback

        logger.error(f"Import error: {type(e).__name__}: {e}")
        logger.error(f"Traceback:\n{traceback.format_exc()}")

        _classify_and_mark_error(api_key, e)
        await db.commit()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de l'import des transactions. Veuillez réessayer.",
        )


@router.post("/{api_key_id}/sync", response_model=dict)
@limiter.limit("5/minute")
async def sync_exchange(
    request: Request,
    api_key_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sync balances from an exchange to portfolio assets."""
    from app.models.asset import Asset, AssetType
    from app.models.portfolio import Portfolio

    result = await db.execute(
        select(APIKey).where(
            APIKey.id == api_key_id,
            APIKey.user_id == current_user.id,
        )
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clé API non trouvée",
        )

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
            return {
                "message": "Aucun solde trouvé sur l'exchange",
                "synced_assets": 0,
            }

        # Get or create unified "Crypto" portfolio (same logic as import-history)
        portfolio_result = await db.execute(
            select(Portfolio).where(
                Portfolio.user_id == current_user.id,
                Portfolio.name == "Crypto",
            )
        )
        portfolio = portfolio_result.scalar_one_or_none()

        if not portfolio:
            # Check for legacy per-exchange portfolio
            legacy_result = await db.execute(
                select(Portfolio).where(
                    Portfolio.user_id == current_user.id,
                    Portfolio.name == f"{service.exchange_name}",
                )
            )
            portfolio = legacy_result.scalar_one_or_none()
            if portfolio:
                portfolio.name = "Crypto"
                portfolio.description = "Portefeuille crypto consolidé"

        if not portfolio:
            portfolio = Portfolio(
                user_id=current_user.id,
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
            if a.exchange == service.exchange_name or a.exchange is None or a.symbol not in existing_assets:
                existing_assets[a.symbol] = a

        synced_count = 0
        # Only skip fiat currencies, not stablecoins (users may want to track USDT, USDC, etc.)
        fiat_currencies = ["USD", "EUR", "GBP", "TRY", "RUB", "UAH", "BRL", "AUD", "CAD", "JPY"]

        for balance in balances:
            # Skip fiat currencies only
            if balance.symbol in fiat_currencies:
                continue

            if balance.symbol in existing_assets:
                # Update existing asset
                asset = existing_assets[balance.symbol]

                # Skip assets transferred to cold wallets (exchange != this exchange)
                if asset.exchange and asset.exchange != service.exchange_name:
                    continue

                old_quantity = float(asset.quantity)
                new_quantity = float(balance.total)

                if abs(new_quantity - old_quantity) > 0.00000001:
                    # Just update the quantity — real transactions come from import-history
                    asset.quantity = new_quantity
                    synced_count += 1
            else:
                # Create new asset
                asset = Asset(
                    portfolio_id=portfolio.id,
                    symbol=balance.symbol,
                    name=balance.symbol,
                    asset_type=AssetType.CRYPTO,
                    quantity=float(balance.total),
                    avg_buy_price=0,
                    currency="EUR",
                    exchange=service.exchange_name,
                )
                db.add(asset)
                await db.flush()

                # No initial transaction — real transactions come from import-history
                synced_count += 1

        # Update last sync time
        api_key.last_sync_at = datetime.now(timezone.utc)
        api_key.mark_success()

        await db.commit()

        invalidate_dashboard_cache(str(current_user.id))

        return {
            "message": "Synchronisation réussie",
            "synced_assets": synced_count,
            "portfolio_id": str(portfolio.id),
            "portfolio_name": portfolio.name,
        }

    except Exception as e:
        _classify_and_mark_error(api_key, e)
        await db.commit()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la synchronisation. Veuillez réessayer.",
        )
