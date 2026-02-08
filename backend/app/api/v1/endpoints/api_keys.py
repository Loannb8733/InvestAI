"""API Keys endpoints for exchange connections."""

from datetime import datetime, timedelta
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import decrypt_api_key, encrypt_api_key
from app.models.api_key import APIKey
from app.models.user import User
from app.schemas.api_key import (
    APIKeyCreate,
    APIKeyResponse,
    APIKeyTestResult,
    APIKeyUpdate,
    ExchangeInfo,
)
from app.services.exchanges import SUPPORTED_EXCHANGES, get_exchange_service

router = APIRouter()


@router.get("/exchanges", response_model=List[ExchangeInfo])
async def list_supported_exchanges() -> List[ExchangeInfo]:
    """List all supported exchanges."""
    return [ExchangeInfo(**exchange) for exchange in SUPPORTED_EXCHANGES]


@router.get("/", response_model=List[APIKeyResponse])
async def list_api_keys(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[APIKeyResponse]:
    """List all API keys for the current user."""
    result = await db.execute(
        select(APIKey).where(APIKey.user_id == current_user.id)
    )
    api_keys = result.scalars().all()
    return api_keys


@router.post("/", response_model=APIKeyResponse, status_code=status.HTTP_201_CREATED)
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

    # Check if API key already exists for this exchange
    existing = await db.execute(
        select(APIKey).where(
            APIKey.user_id == current_user.id,
            APIKey.exchange == exchange_lower,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous avez déjà une clé API pour cet exchange.",
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
async def test_api_key(
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
            api_key.last_sync_at = datetime.utcnow().isoformat()
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
            message=f"Erreur: {str(e)}",
        )


@router.post("/{api_key_id}/import-history")
async def import_trade_history(
    api_key_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import full trade history from exchange with actual prices."""
    from app.models.asset import Asset, AssetType
    from app.models.portfolio import Portfolio
    from app.models.transaction import Transaction, TransactionType
    from decimal import Decimal
    from collections import defaultdict

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

        # Get or create portfolio for this exchange
        portfolio_result = await db.execute(
            select(Portfolio).where(
                Portfolio.user_id == current_user.id,
                Portfolio.name == f"{service.exchange_name}",
                Portfolio.user_id == current_user.id,
            )
        )
        portfolio = portfolio_result.scalar_one_or_none()

        if not portfolio:
            portfolio = Portfolio(
                user_id=current_user.id,
                name=f"{service.exchange_name}",
                description=f"Portefeuille importé depuis {service.exchange_name}",
            )
            db.add(portfolio)
            await db.flush()

        # Get current balances first
        balances = await service.get_balances()
        balance_map = {b.symbol: b for b in balances}

        # Get all trades
        trades = await service.get_trades(limit=1000)

        # Get Instant Buy transactions from Kraken ledgers
        instant_buys = []
        if hasattr(service, 'get_instant_buys'):
            print("Querying Kraken Instant Buy history from ledgers...")
            instant_buys = await service.get_instant_buys(limit=500)
            print(f"Instant Buy orders found: {len(instant_buys)}")
            # Add instant buys to trades list
            trades.extend(instant_buys)

        # Get staking rewards from Kraken ledgers
        rewards = []
        if hasattr(service, 'get_rewards'):
            print("Querying Kraken rewards/staking history from ledgers...")
            rewards = await service.get_rewards(limit=500)
            print(f"Rewards found: {len(rewards)}")

            # Fetch historical prices for rewards
            if rewards:
                from app.services.price_service import price_service
                import asyncio
                print("Fetching historical prices for rewards (this may take a moment)...")

                # Group rewards by symbol and date to minimize API calls
                price_cache = {}
                for reward in rewards:
                    # Extract symbol from pair (e.g., BTCEUR -> BTC)
                    symbol = reward.symbol.replace("EUR", "").replace("USD", "")
                    date_key = f"{symbol}_{reward.timestamp.strftime('%Y-%m-%d')}"

                    if date_key not in price_cache:
                        try:
                            price = await price_service.get_historical_crypto_price(
                                symbol, reward.timestamp, "eur"
                            )
                            price_cache[date_key] = price
                            if price:
                                print(f"  {symbol} @ {reward.timestamp.date()}: {float(price):.2f} EUR")
                            # Delay to avoid CoinGecko rate limiting (50 req/min)
                            await asyncio.sleep(1.5)
                        except Exception as e:
                            print(f"  Error getting price for {symbol}: {e}")
                            price_cache[date_key] = None

                    # Update reward price
                    if price_cache.get(date_key):
                        reward.price = price_cache[date_key]

            # Add rewards to trades list
            trades.extend(rewards)

        # Get crypto-to-crypto conversions (Kraken, Crypto.com)
        conversions = []
        if hasattr(service, 'get_crypto_conversions'):
            print(f"Querying {service.exchange_name} crypto-to-crypto conversions...")
            conversions = await service.get_crypto_conversions(limit=500)
            print(f"Crypto conversions found: {len(conversions)}")

            # Fetch historical prices for conversions if needed
            if conversions:
                from app.services.price_service import price_service
                import asyncio
                print("Fetching historical prices for conversions...")

                price_cache = {}
                for conversion in conversions:
                    # Extract base symbol from pair (e.g., ETHBTC -> ETH, BTC_ETH -> BTC)
                    symbol = conversion.symbol
                    # Handle different pair formats
                    for sep in ["_", "/"]:
                        if sep in symbol:
                            parts = symbol.split(sep)
                            symbol = parts[0]
                            break
                    else:
                        # No separator, try to extract base from common patterns
                        for quote in ["EUR", "USD", "USDT", "BTC", "ETH"]:
                            if symbol.endswith(quote) and len(symbol) > len(quote):
                                symbol = symbol[:-len(quote)]
                                break

                    date_key = f"{symbol}_{conversion.timestamp.strftime('%Y-%m-%d')}"

                    if date_key not in price_cache:
                        try:
                            price = await price_service.get_historical_crypto_price(
                                symbol, conversion.timestamp, "eur"
                            )
                            price_cache[date_key] = price
                            if price:
                                print(f"  {symbol} @ {conversion.timestamp.date()}: {float(price):.2f} EUR")
                            # Delay to avoid rate limiting
                            await asyncio.sleep(1.5)
                        except Exception as e:
                            print(f"  Error getting price for {symbol}: {e}")
                            price_cache[date_key] = None

                    # Update conversion price if we have historical data
                    if price_cache.get(date_key) and conversion.price == Decimal("0"):
                        conversion.price = price_cache[date_key]

            # Add conversions to trades list
            trades.extend(conversions)

        # Get fiat orders (direct EUR/USD purchases via card/bank)
        # Query full history (from 2017 when Binance started)
        fiat_orders = await service.get_fiat_orders(limit=500)
        print(f"Fiat orders found: {len(fiat_orders)}")

        # Get convert history (EUR -> BTC conversions)
        # Query in 30-day chunks from 2017 to now (API requires time ranges)
        convert_orders = []
        if hasattr(service, 'get_convert_history'):
            # Start from 2017 (Binance launch) to now
            target_start = datetime(2017, 7, 1, 0, 0, 0)  # Binance launched July 2017
            target_end = datetime.now()

            print(f"Querying FULL convert history from {target_start} to {target_end}")

            # Query in 30-day chunks going backwards
            chunk_end = target_end

            while chunk_end > target_start:
                chunk_start = max(chunk_end - timedelta(days=30), target_start)

                try:
                    chunk = await service.get_convert_history(
                        start_time=chunk_start,
                        end_time=chunk_end,
                        limit=1000
                    )

                    if chunk:
                        convert_orders.extend(chunk)
                        print(f"Found {len(chunk)} conversions from {chunk_start.date()} to {chunk_end.date()}")
                except Exception as e:
                    print(f"Error querying convert history {chunk_start.date()} to {chunk_end.date()}: {e}")

                chunk_end = chunk_start - timedelta(seconds=1)

            print(f"Total convert orders found: {len(convert_orders)}")

        # Get Auto-Invest (DCA) history
        auto_invest_orders = []
        if hasattr(service, 'get_auto_invest_history'):
            print("Querying Auto-Invest history...")
            # Query in 90-day chunks
            chunk_end = datetime.now()
            target_start = datetime(2020, 1, 1)  # Auto-invest launched around 2020

            while chunk_end > target_start:
                chunk_start = max(chunk_end - timedelta(days=90), target_start)
                try:
                    chunk = await service.get_auto_invest_history(
                        start_time=chunk_start,
                        end_time=chunk_end,
                        limit=100
                    )
                    if chunk:
                        auto_invest_orders.extend(chunk)
                        print(f"Found {len(chunk)} auto-invest orders from {chunk_start.date()} to {chunk_end.date()}")
                except Exception as e:
                    print(f"Error querying auto-invest: {e}")
                chunk_end = chunk_start - timedelta(seconds=1)

            print(f"Total auto-invest orders found: {len(auto_invest_orders)}")

        # Combine all orders
        all_fiat_orders = fiat_orders + convert_orders + auto_invest_orders

        # Debug info
        debug_info = {
            "balances_count": len(balances),
            "spot_trades_count": len(trades) - len(instant_buys) - len(rewards) - len(conversions),
            "instant_buys_count": len(instant_buys),
            "rewards_count": len(rewards),
            "conversions_count": len(conversions),
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
            for quote in ["USDT", "BUSD", "EUR", "USD", "BTC", "ETH", "BNB"]:
                if symbol.endswith(quote):
                    base_asset = symbol[:-len(quote)]
                    asset_trades[base_asset].append(trade)
                    break

        # Add fiat orders to asset_trades (convert to trade-like objects)
        fiat_order_ids = set()
        for fiat_order in all_fiat_orders:
            symbol = fiat_order.crypto_symbol
            if symbol:
                # Create a trade-like object from fiat order
                class FiatTrade:
                    def __init__(self, order):
                        self.trade_id = f"fiat_{order.order_id}"
                        self.symbol = f"{order.crypto_symbol}{order.fiat_currency}"
                        self.side = order.side
                        self.quantity = order.crypto_amount
                        self.price = order.price
                        self.fee = order.fee
                        self.fee_currency = order.fiat_currency
                        self.timestamp = order.timestamp

                asset_trades[symbol].append(FiatTrade(fiat_order))
                fiat_order_ids.add(f"fiat_{fiat_order.order_id}")

        # Get existing assets
        assets_result = await db.execute(
            select(Asset).where(
                Asset.portfolio_id == portfolio.id,
            )
        )
        existing_assets = {a.symbol: a for a in assets_result.scalars().all()}

        # Get existing transaction IDs to avoid duplicates
        existing_trade_ids = set()
        if existing_assets:
            asset_ids = [a.id for a in existing_assets.values()]
            # Get both regular trade IDs and fiat order IDs
            trans_result = await db.execute(
                select(Transaction.notes).where(
                    Transaction.asset_id.in_(asset_ids),
                    Transaction.notes.isnot(None),
                )
            )
            for note in trans_result.scalars().all():
                if note and "trade_id:" in note:
                    existing_trade_ids.add(note.split("trade_id:")[1])

        imported_count = 0
        fiat_orders_count = 0
        rewards_count = 0
        conversions_count = 0
        assets_updated = 0
        # Only skip fiat currencies, not stablecoins (users may want to track USDT, USDC, etc.)
        fiat_currencies = ["USD", "EUR", "GBP", "TRY", "RUB", "UAH", "BRL", "AUD", "CAD", "JPY"]

        for symbol, symbol_trades in asset_trades.items():
            if symbol in fiat_currencies:
                continue

            # Get or create asset
            if symbol in existing_assets:
                asset = existing_assets[symbol]
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
                )
                db.add(asset)
                await db.flush()
                existing_assets[symbol] = asset
                assets_updated += 1

            # Calculate average buy price from trades
            total_bought_qty = Decimal("0")
            total_bought_cost = Decimal("0")
            total_sold_qty = Decimal("0")
            total_sold_value = Decimal("0")

            # Import trades as transactions
            for trade in sorted(symbol_trades, key=lambda x: x.timestamp):
                # Skip already imported trades
                if trade.trade_id in existing_trade_ids:
                    continue

                # Determine transaction type based on trade source
                is_staking_reward = trade.trade_id.startswith("reward_staking_")
                is_airdrop = trade.trade_id.startswith("reward_airdrop_") or trade.trade_id.startswith("reward_") and not trade.trade_id.startswith("reward_staking_")
                is_fiat_order = trade.trade_id.startswith("fiat_") or trade.trade_id.startswith("instant_")
                is_conversion = trade.trade_id.startswith("convert_")

                if is_staking_reward:
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

                # Calculate price in EUR (approximate if in USDT)
                price_eur = float(trade.price)  # Assume 1:1 for USDT for now

                # For conversions, store the conversion rate
                conversion_rate = None
                if is_conversion and trade.price:
                    conversion_rate = float(trade.price)

                transaction = Transaction(
                    asset_id=asset.id,
                    transaction_type=trans_type,
                    quantity=float(trade.quantity),
                    price=price_eur,
                    fee=float(trade.fee) if trade.fee else 0,
                    currency="EUR",
                    executed_at=trade.timestamp,
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

                # Track for average calculation (exclude rewards - they're free)
                if trade.side == "buy" and not (is_staking_reward or is_airdrop):
                    total_bought_qty += trade.quantity
                    total_bought_cost += trade.quantity * trade.price
                elif trade.side == "sell":
                    total_sold_qty += trade.quantity
                    total_sold_value += trade.quantity * trade.price

            # Update average buy price
            if total_bought_qty > 0:
                avg_price = float(total_bought_cost / total_bought_qty)
                # If we have existing buys, calculate weighted average
                if asset.avg_buy_price and asset.avg_buy_price > 0:
                    # Combine with existing
                    existing_cost = float(asset.quantity) * float(asset.avg_buy_price)
                    new_total_cost = existing_cost + float(total_bought_cost)
                    new_total_qty = float(asset.quantity) + float(total_bought_qty)
                    if new_total_qty > 0:
                        asset.avg_buy_price = new_total_cost / new_total_qty
                else:
                    asset.avg_buy_price = avg_price

            # Update quantity from current balance
            balance = balance_map.get(symbol)
            if balance:
                asset.quantity = float(balance.total)

        # Flush to get transaction IDs before linking
        await db.flush()

        # Link conversion pairs together
        # Get all newly created conversion transactions
        if conversions_count > 0:
            conversion_trans_result = await db.execute(
                select(Transaction).where(
                    Transaction.transaction_type.in_([
                        TransactionType.CONVERSION_OUT,
                        TransactionType.CONVERSION_IN
                    ]),
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
                        base_id = trade_id[len("convert_sell_"):]
                        if base_id not in conversion_pairs:
                            conversion_pairs[base_id] = {}
                        conversion_pairs[base_id]["sell"] = trans
                    elif trade_id.startswith("convert_buy_"):
                        base_id = trade_id[len("convert_buy_"):]
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
                print(f"Linked {linked_count} conversion pairs")

        # Update last sync time
        api_key.last_sync_at = datetime.utcnow().isoformat()
        api_key.last_error = None

        await db.commit()

        return {
            "message": "Import de l'historique réussi",
            "imported_transactions": imported_count,
            "fiat_orders": fiat_orders_count,
            "rewards": rewards_count,
            "conversions": conversions_count,
            "spot_trades": imported_count - fiat_orders_count - rewards_count - conversions_count,
            "assets_created": assets_updated,
            "portfolio_id": str(portfolio.id),
            "portfolio_name": portfolio.name,
            "debug": debug_info,
        }

    except Exception as e:
        import traceback
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Import error: {type(e).__name__}: {e}")
        logger.error(f"Traceback:\n{traceback.format_exc()}")

        api_key.last_error = str(e)[:500]
        await db.commit()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de l'import: {str(e)}",
        )


@router.post("/{api_key_id}/sync")
async def sync_exchange(
    api_key_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sync balances from an exchange to portfolio assets."""
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

        # Get balances
        balances = await service.get_balances()

        if not balances:
            return {
                "message": "Aucun solde trouvé sur l'exchange",
                "synced_assets": 0,
            }

        # Get or create portfolio for this exchange
        portfolio_result = await db.execute(
            select(Portfolio).where(
                Portfolio.user_id == current_user.id,
                Portfolio.name == f"{service.exchange_name}",
                Portfolio.user_id == current_user.id,
            )
        )
        portfolio = portfolio_result.scalar_one_or_none()

        if not portfolio:
            portfolio = Portfolio(
                user_id=current_user.id,
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
                old_quantity = float(asset.quantity)
                new_quantity = float(balance.total)

                if abs(new_quantity - old_quantity) > 0.00000001:
                    # Create adjustment transaction
                    diff = new_quantity - old_quantity
                    trans_type = (
                        TransactionType.TRANSFER_IN
                        if diff > 0
                        else TransactionType.TRANSFER_OUT
                    )

                    transaction = Transaction(
                        asset_id=asset.id,
                        transaction_type=trans_type,
                        quantity=abs(diff),
                        price=0,
                        fee=0,
                        currency="EUR",
                        notes=f"Sync auto depuis {service.exchange_name}",
                    )
                    db.add(transaction)

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
                )
                db.add(asset)
                await db.flush()

                # Create initial transfer transaction
                if float(balance.total) > 0:
                    transaction = Transaction(
                        asset_id=asset.id,
                        transaction_type=TransactionType.TRANSFER_IN,
                        quantity=float(balance.total),
                        price=0,
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

        return {
            "message": f"Synchronisation réussie",
            "synced_assets": synced_count,
            "portfolio_id": str(portfolio.id),
            "portfolio_name": portfolio.name,
        }

    except Exception as e:
        api_key.last_error = str(e)[:500]
        await db.commit()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la synchronisation: {str(e)}",
        )
