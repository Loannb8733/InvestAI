"""Metrics calculation service for portfolio analysis."""

import asyncio
import logging
from decimal import Decimal
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset, AssetType
from app.models.transaction import Transaction, TransactionType
from app.models.portfolio import Portfolio
from app.ml.historical_data import HistoricalDataFetcher
from app.services.price_service import price_service

logger = logging.getLogger(__name__)

# Fiat currencies -> counted as cash
FIAT_SYMBOLS = {"EUR", "USD", "GBP", "CHF", "CAD", "AUD", "JPY"}

# Stablecoins -> separate card, excluded from investment metrics
STABLECOIN_SYMBOLS = {
    "USDT", "USDC", "BUSD", "DAI", "TUSD", "USDP", "GUSD", "FRAX", "LUSD",
    "USDG", "PYUSD", "FDUSD", "EURC", "EURT",
}


def is_fiat(symbol: str) -> bool:
    return symbol.upper() in FIAT_SYMBOLS


def is_stablecoin(symbol: str) -> bool:
    return symbol.upper() in STABLECOIN_SYMBOLS


def is_cash_like(symbol: str) -> bool:
    return is_fiat(symbol) or is_stablecoin(symbol)


class MetricsService:
    """Service for calculating portfolio metrics."""

    async def get_asset_metrics(
        self, asset: Asset, current_price: Optional[Decimal] = None
    ) -> Dict:
        """Calculate metrics for a single asset."""
        quantity = Decimal(str(asset.quantity))
        avg_buy_price = Decimal(str(asset.avg_buy_price))

        # Total invested
        total_invested = quantity * avg_buy_price

        # Current value
        if current_price is None:
            current_value = total_invested
            gain_loss = Decimal("0")
            gain_loss_percent = 0.0
        else:
            current_price = Decimal(str(current_price))
            current_value = quantity * current_price
            gain_loss = current_value - total_invested
            gain_loss_percent = (
                float(gain_loss / total_invested * 100) if total_invested > 0 else 0.0
            )

        return {
            "quantity": float(quantity),
            "avg_buy_price": float(avg_buy_price),
            "total_invested": float(total_invested),
            "current_price": float(current_price) if current_price else None,
            "current_value": float(current_value),
            "gain_loss": float(gain_loss),
            "gain_loss_percent": gain_loss_percent,
        }

    async def get_portfolio_metrics(
        self, db: AsyncSession, portfolio_id: str, currency: str = "EUR",
        include_zero_quantity: bool = False,
        min_value_eur: float = 0.10  # Filter out dust positions worth less than this
    ) -> Dict:
        """Calculate metrics for an entire portfolio."""
        # Get all assets in portfolio
        query = select(Asset).where(
            Asset.portfolio_id == portfolio_id,
        )
        if not include_zero_quantity:
            query = query.where(Asset.quantity > 0)

        result = await db.execute(query)
        all_assets = result.scalars().all()

        # Filter out dust positions (worth less than min_value_eur)
        assets = []
        for asset in all_assets:
            # Estimate value: quantity * avg_buy_price (as approximation)
            est_value = float(asset.quantity) * float(asset.avg_buy_price) if asset.avg_buy_price else 0
            if est_value >= min_value_eur or include_zero_quantity:
                assets.append(asset)

        if not assets:
            return {
                "total_value": 0.0,
                "total_invested": 0.0,
                "total_gain_loss": 0.0,
                "total_gain_loss_percent": 0.0,
                "assets_count": 0,
                "assets": [],
                "cash_from_stablecoins": 0.0,
                "stablecoins": [],
                "cash_from_fiat": 0.0,
                "fiat_assets": [],
            }

        # Separate into: investments, stablecoins, fiat cash
        investment_assets = [a for a in assets if not is_cash_like(a.symbol)]
        stablecoin_assets = [a for a in assets if is_stablecoin(a.symbol)]
        fiat_assets = [a for a in assets if is_fiat(a.symbol)]

        # Group assets by type for batch price fetching
        crypto_symbols = [a.symbol for a in investment_assets if a.asset_type == AssetType.CRYPTO]
        stock_symbols = [
            a.symbol for a in investment_assets if a.asset_type in [AssetType.STOCK, AssetType.ETF]
        ]

        # Fetch prices (with 24h change data)
        prices = {}
        price_changes = {}
        if crypto_symbols:
            crypto_prices = await price_service.get_multiple_crypto_prices(
                crypto_symbols, currency.lower()
            )
            for symbol, data in crypto_prices.items():
                prices[symbol] = data["price"]
                price_changes[symbol] = float(data.get("change_percent_24h", 0) or 0)

        for symbol in stock_symbols:
            stock_data = await price_service.get_stock_price(symbol)
            if stock_data:
                prices[symbol] = stock_data["price"]
                price_changes[symbol] = float(stock_data.get("change_percent_24h", 0) or 0)

        # Calculate metrics for each investment asset
        total_value = Decimal("0")
        total_invested = Decimal("0")
        asset_metrics = []

        for asset in investment_assets:
            current_price = prices.get(asset.symbol.upper())
            metrics = await self.get_asset_metrics(asset, current_price)

            total_value += Decimal(str(metrics["current_value"]))
            total_invested += Decimal(str(metrics["total_invested"]))

            asset_metrics.append({
                "id": str(asset.id),
                "symbol": asset.symbol,
                "name": asset.name,
                "asset_type": asset.asset_type.value,
                "change_percent_24h": price_changes.get(asset.symbol.upper(), 0.0),
                **metrics,
            })

        # Calculate stablecoin cash value
        cash_from_stablecoins = Decimal("0")
        stablecoin_list = []
        for asset in stablecoin_assets:
            value = float(asset.quantity) * float(asset.avg_buy_price) if float(asset.avg_buy_price) > 0 else float(asset.quantity)
            cash_from_stablecoins += Decimal(str(value))
            stablecoin_list.append({
                "id": str(asset.id),
                "symbol": asset.symbol,
                "quantity": float(asset.quantity),
                "value": value,
            })

        # Calculate fiat cash value
        cash_from_fiat = Decimal("0")
        fiat_list = []
        for asset in fiat_assets:
            value = float(asset.quantity)  # 1 EUR = 1 EUR
            cash_from_fiat += Decimal(str(value))
            fiat_list.append({
                "id": str(asset.id),
                "symbol": asset.symbol,
                "quantity": float(asset.quantity),
                "value": value,
            })

        # Sort by value descending
        asset_metrics.sort(key=lambda x: x["current_value"], reverse=True)

        total_gain_loss = total_value - total_invested
        total_gain_loss_percent = (
            float(total_gain_loss / total_invested * 100) if total_invested > 0 else 0.0
        )

        return {
            "total_value": float(total_value),
            "total_invested": float(total_invested),
            "total_gain_loss": float(total_gain_loss),
            "total_gain_loss_percent": total_gain_loss_percent,
            "assets_count": len(investment_assets),
            "assets": asset_metrics,
            "cash_from_stablecoins": float(cash_from_stablecoins),
            "stablecoins": stablecoin_list,
            "cash_from_fiat": float(cash_from_fiat),
            "fiat_assets": fiat_list,
        }

    async def _fetch_period_changes(
        self, symbols_by_type: Dict[str, List[str]], days: int
    ) -> Dict[str, float]:
        """Fetch price change percentage over a period for each symbol.

        Returns {SYMBOL: change_percent} using CoinGecko /coins/markets
        (single batch call) for crypto and Yahoo Finance for stocks.
        """
        import httpx

        changes: Dict[str, float] = {}

        # Map days to CoinGecko price_change_percentage param
        # Available: 1h, 24h, 7d, 14d, 30d, 200d, 1y
        if days <= 7:
            cg_period = "7d"
            cg_key = "price_change_percentage_7d_in_currency"
        elif days <= 14:
            cg_period = "14d"
            cg_key = "price_change_percentage_14d_in_currency"
        elif days <= 30:
            cg_period = "30d"
            cg_key = "price_change_percentage_30d_in_currency"
        elif days <= 200:
            cg_period = "200d"
            cg_key = "price_change_percentage_200d_in_currency"
        else:
            cg_period = "1y"
            cg_key = "price_change_percentage_1y_in_currency"

        # Crypto: batch call via /coins/markets
        crypto_symbols = symbols_by_type.get("crypto", [])
        if crypto_symbols:
            try:
                # Build coin IDs
                from app.ml.historical_data import HistoricalDataFetcher as HDF
                coin_ids = [
                    HDF.SYMBOL_MAP.get(s.upper(), s.lower())
                    for s in crypto_symbols
                ]

                headers = {
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "application/json",
                }
                coingecko_key = getattr(price_service, 'coingecko_api_key', None)
                if coingecko_key:
                    headers["x-cg-demo-api-key"] = coingecko_key

                async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
                    response = await client.get(
                        "https://api.coingecko.com/api/v3/coins/markets",
                        params={
                            "vs_currency": "eur",
                            "ids": ",".join(coin_ids),
                            "price_change_percentage": cg_period,
                            "per_page": 250,
                        },
                    )
                    response.raise_for_status()
                    data = response.json()

                    # Reverse map coin_id -> symbol
                    id_to_symbol = {v: k for k, v in HDF.SYMBOL_MAP.items()}

                    for coin in data:
                        coin_id = coin.get("id", "")
                        symbol = id_to_symbol.get(coin_id, coin.get("symbol", "").upper())
                        pct = coin.get(cg_key, {})
                        if isinstance(pct, dict):
                            pct = pct.get("eur", 0) or 0
                        changes[symbol.upper()] = float(pct or 0)

            except Exception as e:
                logger.warning("Failed to fetch crypto period changes: %s", e)

        # Stocks/ETFs: use Yahoo Finance chart for each symbol
        stock_symbols = symbols_by_type.get("stock", []) + symbols_by_type.get("etf", [])
        if stock_symbols:
            fetcher = HistoricalDataFetcher()
            try:
                for symbol in stock_symbols:
                    try:
                        _, prices = await fetcher.get_stock_history(symbol, days=days)
                        if prices and len(prices) >= 2:
                            change = (prices[-1] - prices[0]) / prices[0] * 100
                            changes[symbol.upper()] = change
                    except Exception:
                        pass
            finally:
                await fetcher.close()

        return changes

    async def get_user_dashboard_metrics(
        self, db: AsyncSession, user_id: str, currency: str = "EUR",
        days: int = 30,
    ) -> Dict:
        """Calculate dashboard metrics for a user's entire portfolio."""
        # Get all user portfolios
        result = await db.execute(
            select(Portfolio).where(
                Portfolio.user_id == user_id,
            )
        )
        portfolios = result.scalars().all()

        if not portfolios:
            return {
                "total_value": 0.0,
                "total_invested": 0.0,
                "net_capital": 0.0,
                "total_gain_loss": 0.0,
                "total_gain_loss_percent": 0.0,
                "net_gain_loss": 0.0,
                "net_gain_loss_percent": 0.0,
                "daily_change": 0.0,
                "daily_change_percent": 0.0,
                "portfolios_count": 0,
                "assets_count": 0,
                "allocation": [],
                "top_performers": [],
                "worst_performers": [],
            }

        # Calculate metrics for each portfolio
        total_value = Decimal("0")
        total_invested = Decimal("0")
        total_sold = Decimal("0")
        all_assets = []

        for portfolio in portfolios:
            portfolio_metrics = await self.get_portfolio_metrics(
                db, str(portfolio.id), currency
            )
            # Get historical total invested (sum of all buy transactions)
            portfolio_history = await self.get_portfolio_history(
                db, str(portfolio.id), currency
            )
            total_value += Decimal(str(portfolio_metrics["total_value"]))
            total_invested += Decimal(str(portfolio_history["total_invested_all_time"]))
            total_sold += Decimal(str(portfolio_history.get("total_sold", 0)))
            all_assets.extend(portfolio_metrics["assets"])

        total_gain_loss = total_value - total_invested
        total_gain_loss_percent = (
            float(total_gain_loss / total_invested * 100) if total_invested > 0 else 0.0
        )

        # Calculate allocation by asset type
        allocation = {}
        for asset in all_assets:
            asset_type = asset["asset_type"]
            if asset_type not in allocation:
                allocation[asset_type] = 0.0
            allocation[asset_type] += asset["current_value"]

        allocation_list = [
            {
                "type": asset_type,
                "value": value,
                "percentage": (value / float(total_value) * 100) if total_value > 0 else 0,
            }
            for asset_type, value in allocation.items()
        ]
        allocation_list.sort(key=lambda x: x["value"], reverse=True)

        # Aggregate assets by symbol (merge duplicates across portfolios)
        symbol_agg: Dict[str, Dict] = {}
        for a in all_assets:
            sym = a["symbol"]
            if sym not in symbol_agg:
                symbol_agg[sym] = {
                    "symbol": sym,
                    "name": a["name"],
                    "asset_type": a["asset_type"],
                    "current_price": a.get("current_price"),
                    "total_invested": 0.0,
                    "current_value": 0.0,
                }
            symbol_agg[sym]["total_invested"] += a["total_invested"]
            symbol_agg[sym]["current_value"] += a["current_value"]

        # Fetch period change percentages (batch API call)
        symbols_by_type: Dict[str, List[str]] = {}
        for data in symbol_agg.values():
            at = data["asset_type"]
            symbols_by_type.setdefault(at, []).append(data["symbol"])

        period_changes = await self._fetch_period_changes(symbols_by_type, days)

        # Assign period change for each symbol
        for data in symbol_agg.values():
            sym = data["symbol"].upper()
            if sym in period_changes:
                data["period_change_percent"] = period_changes[sym]
            else:
                # Fallback to gain/loss vs avg buy price
                inv = data["total_invested"]
                data["period_change_percent"] = (
                    (data["current_value"] - inv) / inv * 100 if inv > 0 else 0.0
                )

        aggregated = list(symbol_agg.values())

        # Top and worst performers (by price change over selected period)
        top_performers = [
            a for a in aggregated if a["period_change_percent"] > 0
        ]
        top_performers.sort(key=lambda x: x["period_change_percent"], reverse=True)
        top_performers = top_performers[:5]

        worst_performers = [
            a for a in aggregated if a["period_change_percent"] < 0
        ]
        worst_performers.sort(key=lambda x: x["period_change_percent"])
        worst_performers = worst_performers[:5]

        # Period change (portfolio-level)
        period_change = 0.0
        period_change_percent = 0.0

        # Net capital = money injected - money withdrawn (actual cash still in play)
        net_capital = total_invested - total_sold
        net_gain_loss = total_value - net_capital
        net_gain_loss_percent = (
            float(net_gain_loss / net_capital * 100) if net_capital > 0 else 0.0
        )

        return {
            "total_value": float(total_value),
            "total_invested": float(total_invested),
            "net_capital": float(net_capital),
            "total_gain_loss": float(total_gain_loss),
            "total_gain_loss_percent": total_gain_loss_percent,
            "net_gain_loss": float(net_gain_loss),
            "net_gain_loss_percent": net_gain_loss_percent,
            "daily_change": period_change,
            "daily_change_percent": period_change_percent,
            "portfolios_count": len(portfolios),
            "assets_count": len(all_assets),
            "allocation": allocation_list,
            "top_performers": [
                {
                    "symbol": a["symbol"],
                    "name": a["name"],
                    "asset_type": a["asset_type"],
                    "gain_loss_percent": round(a["period_change_percent"], 2),
                    "current_value": a["current_value"],
                }
                for a in top_performers
            ],
            "worst_performers": [
                {
                    "symbol": a["symbol"],
                    "name": a["name"],
                    "asset_type": a["asset_type"],
                    "gain_loss_percent": round(a["period_change_percent"], 2),
                    "current_value": a["current_value"],
                }
                for a in worst_performers
            ],
        }

    async def get_portfolio_history(
        self, db: AsyncSession, portfolio_id: str, currency: str = "EUR"
    ) -> Dict:
        """
        Calculate historical investment metrics for a portfolio.
        Includes all assets (even those with 0 quantity) and calculates
        total invested from all buy transactions.
        """
        # Get ALL assets in portfolio (including zero quantity)
        result = await db.execute(
            select(Asset).where(
                Asset.portfolio_id == portfolio_id,
                )
        )
        all_assets = result.scalars().all()
        asset_ids = [a.id for a in all_assets]

        if not asset_ids:
            return {
                "total_invested_all_time": 0.0,
                "total_sold": 0.0,
                "realized_gains": 0.0,
                "current_holdings_count": 0,
                "sold_assets_count": 0,
                "historical_assets": [],
            }

        # Get all transactions for these assets
        result = await db.execute(
            select(Transaction).where(
                Transaction.asset_id.in_(asset_ids),
            ).order_by(Transaction.executed_at.desc())
        )
        transactions = result.scalars().all()

        # Calculate totals per asset
        asset_history = {}
        for asset in all_assets:
            asset_history[str(asset.id)] = {
                "id": str(asset.id),
                "symbol": asset.symbol,
                "name": asset.name,
                "asset_type": asset.asset_type.value,
                "current_quantity": float(asset.quantity),
                "total_bought": Decimal("0"),
                "total_bought_value": Decimal("0"),
                "total_sold": Decimal("0"),
                "total_sold_value": Decimal("0"),
                "total_fees": Decimal("0"),
                "first_transaction": None,
                "last_transaction": None,
            }

        # Process transactions
        for tx in transactions:
            asset_id = str(tx.asset_id)
            if asset_id not in asset_history:
                continue

            ah = asset_history[asset_id]
            tx_type = tx.transaction_type.value.upper()

            # Track dates
            tx_date = tx.executed_at
            if ah["last_transaction"] is None or tx_date > ah["last_transaction"]:
                ah["last_transaction"] = tx_date
            if ah["first_transaction"] is None or tx_date < ah["first_transaction"]:
                ah["first_transaction"] = tx_date

            # Track fees
            ah["total_fees"] += Decimal(str(tx.fee or 0))

            # Track buys
            if tx_type in ["BUY", "TRANSFER_IN", "AIRDROP", "STAKING_REWARD", "CONVERSION_IN"]:
                ah["total_bought"] += Decimal(str(tx.quantity))
                ah["total_bought_value"] += Decimal(str(tx.quantity)) * Decimal(str(tx.price))

            # Track sells
            elif tx_type in ["SELL", "TRANSFER_OUT", "CONVERSION_OUT"]:
                ah["total_sold"] += Decimal(str(tx.quantity))
                ah["total_sold_value"] += Decimal(str(tx.quantity)) * Decimal(str(tx.price))

        # Calculate summary metrics
        total_invested_all_time = Decimal("0")
        total_sold_value = Decimal("0")
        total_fees = Decimal("0")
        current_holdings = []
        sold_assets = []

        for asset_id, ah in asset_history.items():
            # Exclude stablecoins/fiat from investment totals
            if is_cash_like(ah["symbol"]):
                continue
            total_invested_all_time += ah["total_bought_value"]
            total_sold_value += ah["total_sold_value"]
            total_fees += ah["total_fees"]

            # Format for output
            asset_data = {
                "id": ah["id"],
                "symbol": ah["symbol"],
                "name": ah["name"],
                "asset_type": ah["asset_type"],
                "current_quantity": ah["current_quantity"],
                "total_bought": float(ah["total_bought"]),
                "total_bought_value": float(ah["total_bought_value"]),
                "total_sold": float(ah["total_sold"]),
                "total_sold_value": float(ah["total_sold_value"]),
                "total_fees": float(ah["total_fees"]),
                "realized_gain": float(ah["total_sold_value"] - (ah["total_bought_value"] * ah["total_sold"] / ah["total_bought"])) if ah["total_bought"] > 0 and ah["total_sold"] > 0 else 0.0,
                "first_transaction": ah["first_transaction"].isoformat() if ah["first_transaction"] else None,
                "last_transaction": ah["last_transaction"].isoformat() if ah["last_transaction"] else None,
            }

            # Consider as "sold" if quantity is 0 or value is less than 0.10€
            est_value = float(ah["current_quantity"]) * float(ah["total_bought_value"] / ah["total_bought"]) if ah["total_bought"] > 0 else 0
            if ah["current_quantity"] > 0 and est_value >= 0.10:
                current_holdings.append(asset_data)
            else:
                sold_assets.append(asset_data)

        # Sort by total invested
        sold_assets.sort(key=lambda x: x["total_bought_value"], reverse=True)

        # Sum realized gains from individual assets (already computed per-asset)
        total_realized_gains = sum(
            Decimal(str(a["realized_gain"])) for a in current_holdings + sold_assets
        )

        return {
            "total_invested_all_time": float(total_invested_all_time),
            "total_sold": float(total_sold_value),
            "total_fees": float(total_fees),
            "realized_gains": float(total_realized_gains),
            "current_holdings_count": len(current_holdings),
            "sold_assets_count": len(sold_assets),
            "sold_assets": sold_assets,
        }

    async def calculate_roi(
        self, total_invested: Decimal, current_value: Decimal
    ) -> float:
        """Calculate Return on Investment."""
        if total_invested <= 0:
            return 0.0
        return float((current_value - total_invested) / total_invested * 100)

    async def calculate_cagr(
        self,
        initial_value: Decimal,
        final_value: Decimal,
        years: float,
    ) -> float:
        """Calculate Compound Annual Growth Rate."""
        if initial_value <= 0 or years <= 0:
            return 0.0
        return float((pow(float(final_value / initial_value), 1 / years) - 1) * 100)

    async def calculate_realized_unrealized_pnl(
        self, db: AsyncSession, user_id: str, currency: str = "EUR"
    ) -> Dict:
        """
        Calculate realized and unrealized P&L separately.
        Realized: Profits/losses from assets that have been sold
        Unrealized (Latent): Profits/losses from current holdings
        """
        # Get all user portfolios
        result = await db.execute(
            select(Portfolio).where(
                Portfolio.user_id == user_id,
            )
        )
        portfolios = result.scalars().all()

        total_realized = Decimal("0")
        total_unrealized = Decimal("0")
        total_fees = Decimal("0")

        for portfolio in portfolios:
            history = await self.get_portfolio_history(db, str(portfolio.id), currency)
            metrics = await self.get_portfolio_metrics(db, str(portfolio.id), currency)

            # Realized gains from sold assets
            total_fees += Decimal(str(history.get("total_fees", 0)))

            # Calculate realized P&L from sold assets
            for sold_asset in history.get("sold_assets", []):
                realized_gain = Decimal(str(sold_asset.get("realized_gain", 0)))
                total_realized += realized_gain

            # Unrealized P&L from current holdings
            total_unrealized += Decimal(str(metrics.get("total_gain_loss", 0)))

        return {
            "realized_pnl": float(total_realized),
            "unrealized_pnl": float(total_unrealized),
            "total_pnl": float(total_realized + total_unrealized),
            "total_fees": float(total_fees),
            "net_pnl": float(total_realized + total_unrealized - total_fees),
        }


# Singleton instance
metrics_service = MetricsService()
