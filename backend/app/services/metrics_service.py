"""Metrics calculation service for portfolio analysis."""

import asyncio
import logging
import math
import time
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ml.historical_data import HistoricalDataFetcher
from app.models.asset import Asset, AssetType
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction
from app.services.price_service import price_service

logger = logging.getLogger(__name__)

# In-memory cache for dashboard metrics: {(user_id, days): (timestamp, result)}
_dashboard_cache: Dict[Tuple[str, int], Tuple[float, Dict]] = {}
_DASHBOARD_CACHE_TTL = 120  # 2 minutes
_MAX_DASHBOARD_CACHE = 200  # max entries before eviction


def _cache_put_dashboard(key: Tuple, value: Tuple) -> None:
    """Insert into bounded dashboard cache, evicting oldest entries if full."""
    if len(_dashboard_cache) >= _MAX_DASHBOARD_CACHE:
        evict_count = max(1, _MAX_DASHBOARD_CACHE // 4)
        sorted_keys = sorted(_dashboard_cache, key=lambda k: _dashboard_cache[k][0])
        for k in sorted_keys[:evict_count]:
            del _dashboard_cache[k]
    _dashboard_cache[key] = value


def invalidate_dashboard_cache(user_id: str) -> None:
    """Evict all cached dashboard entries for a given user.

    Call after any mutation (create/update/delete transaction) so the next
    dashboard or report request picks up fresh data immediately.
    """
    keys_to_delete = [k for k in _dashboard_cache if k[0] == user_id]
    for k in keys_to_delete:
        del _dashboard_cache[k]


# Fiat currencies -> counted as cash
FIAT_SYMBOLS = {"EUR", "USD", "GBP", "CHF", "CAD", "AUD", "JPY"}

# Stablecoins -> separate card, excluded from investment metrics
STABLECOIN_SYMBOLS = {
    "USDT",
    "USDC",
    "BUSD",
    "DAI",
    "TUSD",
    "USDP",
    "GUSD",
    "FRAX",
    "LUSD",
    "USDG",
    "PYUSD",
    "FDUSD",
    "EURC",
    "EURT",
}


def is_fiat(symbol: str) -> bool:
    return symbol.upper() in FIAT_SYMBOLS


def is_stablecoin(symbol: str) -> bool:
    return symbol.upper() in STABLECOIN_SYMBOLS


def is_cash_like(symbol: str) -> bool:
    return is_fiat(symbol) or is_stablecoin(symbol)


# Canonical alias — use this across the codebase
is_liquidity = is_cash_like


# Gold / safe-haven asset detection
_GOLD_SYMBOLS = {"PAXG", "XAUT", "GLD", "IAU", "SGOL", "GOLD"}


def is_safe_haven(symbol: str) -> bool:
    """Return True for gold-backed tokens and ETFs."""
    return symbol.upper() in _GOLD_SYMBOLS


class MetricsService:
    """Service for calculating portfolio metrics."""

    async def get_asset_metrics(self, asset: Asset, current_price: Optional[Decimal] = None) -> Dict:
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
            gain_loss_percent = float(gain_loss / total_invested * 100) if total_invested > 0 else 0.0

        return {
            "quantity": float(quantity),
            "avg_buy_price": float(avg_buy_price),
            "total_invested": float(total_invested),
            "current_price": float(current_price) if current_price else None,
            "current_value": float(current_value),
            "gain_loss": float(gain_loss),
            "gain_loss_percent": gain_loss_percent,
        }

    async def _compute_risk_weights(
        self,
        db: AsyncSession,
        symbols: List[str],
        symbol_values: Dict[str, float],
        total_value: float,
        days: int = 90,
    ) -> Dict[str, float]:
        """Compute risk weight per symbol based on historical volatility contribution."""
        if not symbols or total_value <= 0:
            return {}

        from app.models.asset_price_history import AssetPriceHistory

        cutoff = (datetime.utcnow() - timedelta(days=days)).date()

        result = await db.execute(
            select(
                AssetPriceHistory.symbol,
                AssetPriceHistory.price_date,
                AssetPriceHistory.price_eur,
            )
            .where(
                AssetPriceHistory.symbol.in_([s.upper() for s in symbols]),
                AssetPriceHistory.price_date >= cutoff,
            )
            .order_by(AssetPriceHistory.symbol, AssetPriceHistory.price_date)
        )
        rows = result.all()

        # Group prices by symbol
        symbol_prices: Dict[str, List[float]] = defaultdict(list)
        for row in rows:
            symbol_prices[row[0]].append(float(row[2]))

        # Compute annualized volatility per symbol
        volatilities: Dict[str, float] = {}
        for symbol, prices in symbol_prices.items():
            if len(prices) < 10:
                volatilities[symbol] = 0.0
                continue
            daily_returns = [
                (prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices)) if prices[i - 1] > 0
            ]
            if not daily_returns:
                volatilities[symbol] = 0.0
                continue
            mean_ret = sum(daily_returns) / len(daily_returns)
            variance = sum((r - mean_ret) ** 2 for r in daily_returns) / len(daily_returns)
            volatilities[symbol] = math.sqrt(variance) * math.sqrt(252)

        # Weighted risk contributions
        total_weighted = 0.0
        weighted_vols: Dict[str, float] = {}
        for symbol in symbols:
            s = symbol.upper()
            weight = symbol_values.get(s, 0) / total_value if total_value > 0 else 0
            wv = weight * volatilities.get(s, 0)
            weighted_vols[s] = wv
            total_weighted += wv

        # Normalize to percentages
        risk_weights: Dict[str, float] = {}
        for symbol, wv in weighted_vols.items():
            risk_weights[symbol] = round((wv / total_weighted * 100) if total_weighted > 0 else 0, 2)

        return risk_weights

    async def get_portfolio_metrics(
        self,
        db: AsyncSession,
        portfolio_id: str,
        currency: str = "EUR",
        include_zero_quantity: bool = False,
        min_value_eur: float = 0.10,  # Filter out dust positions worth less than this
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

        # Pre-filter: remove assets with zero quantity (actual dust filtering
        # happens later after live prices are fetched, so we keep all qty > 0 here)
        assets = []
        for asset in all_assets:
            if not include_zero_quantity:
                qty = float(asset.quantity)
                avg_price = float(asset.avg_buy_price) if asset.avg_buy_price else 0.0
                current_price = float(asset.current_price) if asset.current_price else 0.0
                best_price = avg_price or current_price
                if best_price > 0:
                    est_value = qty * best_price
                    if est_value < min_value_eur:
                        continue
                # No price info yet — keep the asset; real value will be
                # determined after live prices are fetched below.
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
        # Exclude CROWDFUNDING — managed via dedicated /crowdfunding endpoints
        investment_assets = [a for a in assets if not is_cash_like(a.symbol) and a.asset_type != AssetType.CROWDFUNDING]
        stablecoin_assets = [a for a in assets if is_stablecoin(a.symbol)]
        fiat_assets = [a for a in assets if is_fiat(a.symbol)]

        # Batch-fetch total fees per asset from transactions
        inv_asset_ids = [a.id for a in investment_assets]
        fees_map: Dict[str, float] = {}
        if inv_asset_ids:
            from app.models.transaction import TransactionType as TxType

            fee_result = await db.execute(
                select(
                    Transaction.asset_id,
                    func.sum(
                        case(
                            (
                                Transaction.transaction_type == TxType.FEE,
                                Transaction.quantity * Transaction.price,
                            ),
                            else_=func.coalesce(Transaction.fee, 0),
                        )
                    ).label("total_fees"),
                )
                .where(Transaction.asset_id.in_(inv_asset_ids))
                .group_by(Transaction.asset_id)
            )
            fees_map = {str(r[0]): float(r[1] or 0) for r in fee_result.all()}

        # Group assets by type for batch price fetching
        crypto_symbols = [a.symbol for a in investment_assets if a.asset_type == AssetType.CRYPTO]
        stock_symbols = [a.symbol for a in investment_assets if a.asset_type in [AssetType.STOCK, AssetType.ETF]]

        # Fetch prices (with 24h change data) — fallback to DB current_price on timeout
        prices = {}
        price_changes = {}

        # Pre-populate fallback prices from DB (current_price stored on asset)
        db_fallback_prices = {
            a.symbol.upper(): float(a.current_price)
            for a in investment_assets
            if a.current_price and float(a.current_price) > 0
        }

        if crypto_symbols:
            try:
                crypto_prices = await asyncio.wait_for(
                    price_service.get_multiple_crypto_prices(crypto_symbols, currency.lower()),
                    timeout=5.0,
                )
                for symbol, data in crypto_prices.items():
                    prices[symbol.upper()] = data["price"]
                    price_changes[symbol.upper()] = float(data.get("change_percent_24h", 0) or 0)
            except (asyncio.TimeoutError, Exception) as e:
                logger.warning("Crypto price fetch failed (%s), using DB fallback", type(e).__name__)

        if stock_symbols:

            async def _fetch_stock(sym):
                data = await price_service.get_stock_price(sym)
                return sym, data

            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*[_fetch_stock(s) for s in stock_symbols], return_exceptions=True),
                    timeout=5.0,
                )
                for res in results:
                    if isinstance(res, Exception):
                        continue
                    symbol, stock_data = res
                    if stock_data:
                        stock_price = stock_data["price"]
                        quote_ccy = stock_data.get("quote_currency", "USD")
                        target = currency.upper()
                        if quote_ccy != target:
                            try:
                                rate = await price_service.get_forex_rate(quote_ccy, target)
                                if rate:
                                    stock_price = stock_price * rate
                            except Exception:
                                logger.warning("Forex %s→%s unavailable for stock %s", quote_ccy, target, symbol)
                        prices[symbol.upper()] = stock_price
                        price_changes[symbol.upper()] = float(stock_data.get("change_percent_24h", 0) or 0)
            except (asyncio.TimeoutError, Exception) as e:
                logger.warning("Stock price fetch failed (%s), using DB fallback", type(e).__name__)

        # Fill missing prices from DB fallback
        for sym, fallback_price in db_fallback_prices.items():
            if sym not in prices:
                prices[sym] = fallback_price
                price_changes.setdefault(sym, 0.0)

        # Calculate metrics for each investment asset
        total_value = Decimal("0")
        total_invested = Decimal("0")
        asset_metrics = []
        crowdfunding_active = 0
        crowdfunding_completed = 0
        crowdfunding_total_invested = Decimal("0")
        crowdfunding_projected_interest = Decimal("0")
        crowdfunding_next_maturity = None

        for asset in investment_assets:
            # Crowdfunding / real estate with invested_amount: no live price
            is_crowdfunding = asset.asset_type == AssetType.CROWDFUNDING or (
                asset.asset_type == AssetType.REAL_ESTATE and asset.invested_amount is not None
            )

            if is_crowdfunding:
                inv_amount = Decimal(str(asset.invested_amount))
                status = asset.project_status or "active"

                if status == "completed":
                    current_value = Decimal("0")
                    crowdfunding_completed += 1
                else:
                    current_value = inv_amount
                    crowdfunding_active += 1

                crowdfunding_total_invested += inv_amount

                # Projected annual interest
                rate = Decimal(str(asset.interest_rate)) if asset.interest_rate else Decimal("0")
                if status == "active" and rate > 0:
                    crowdfunding_projected_interest += inv_amount * rate / 100

                # Track next maturity
                if status == "active" and asset.maturity_date:
                    if crowdfunding_next_maturity is None or asset.maturity_date < crowdfunding_next_maturity:
                        crowdfunding_next_maturity = asset.maturity_date

                metrics = {
                    "quantity": float(asset.quantity),
                    "avg_buy_price": float(inv_amount),
                    "total_invested": float(inv_amount),
                    "current_price": float(inv_amount) if status != "completed" else 0.0,
                    "current_value": float(current_value),
                    "gain_loss": 0.0,
                    "gain_loss_percent": 0.0,
                }
            else:
                current_price = prices.get(asset.symbol.upper())
                metrics = await self.get_asset_metrics(asset, current_price)

                # Post-filter: skip dust positions based on actual current value
                if (
                    not include_zero_quantity
                    and metrics["current_value"] < min_value_eur
                    and metrics["total_invested"] < min_value_eur
                ):
                    continue

            total_value += Decimal(str(metrics["current_value"]))
            total_invested += Decimal(str(metrics["total_invested"]))

            # Per-asset fees and break-even price
            asset_fees = fees_map.get(str(asset.id), 0.0)
            qty = metrics["quantity"]
            breakeven_price = (metrics["total_invested"] + asset_fees) / qty if qty > 0 else None

            asset_entry = {
                "id": str(asset.id),
                "symbol": asset.symbol,
                "name": asset.name,
                "asset_type": asset.asset_type.value,
                "exchange": asset.exchange,
                "change_percent_24h": price_changes.get(asset.symbol.upper(), 0.0),
                "total_fees": asset_fees,
                "breakeven_price": round(breakeven_price, 2) if breakeven_price is not None else None,
                **metrics,
            }
            # Include crowdfunding fields if present
            if is_crowdfunding:
                asset_entry["interest_rate"] = float(asset.interest_rate) if asset.interest_rate else None
                asset_entry["maturity_date"] = asset.maturity_date.isoformat() if asset.maturity_date else None
                asset_entry["project_status"] = asset.project_status
                asset_entry["invested_amount"] = float(asset.invested_amount) if asset.invested_amount else None

            asset_metrics.append(asset_entry)

        # Fetch forex rates for stablecoin/fiat valuation in target currency
        # USD stablecoins → target currency, EUR fiat → target currency
        target = currency.upper()
        usd_to_target = 1.0  # fallback if target is USD
        eur_to_target = 1.0  # fallback if target is EUR
        _FALLBACK_RATES = {
            "EUR": {"USD": 1.09, "CHF": 0.94, "GBP": 0.86},
            "USD": {"EUR": 0.92, "CHF": 0.86, "GBP": 0.79},
        }
        try:
            if target != "USD":
                rate = await price_service.get_forex_rate("USD", target)
                usd_to_target = float(rate) if rate else _FALLBACK_RATES.get("USD", {}).get(target, 1.0)
            if target != "EUR":
                rate = await price_service.get_forex_rate("EUR", target)
                eur_to_target = float(rate) if rate else _FALLBACK_RATES.get("EUR", {}).get(target, 1.0)
        except Exception:
            usd_to_target = _FALLBACK_RATES.get("USD", {}).get(target, 1.0) if target != "USD" else 1.0
            eur_to_target = _FALLBACK_RATES.get("EUR", {}).get(target, 1.0) if target != "EUR" else 1.0

        # Calculate stablecoin cash value (filter out dust)
        cash_from_stablecoins = Decimal("0")
        stablecoin_list = []
        usd_stablecoins = {"USDT", "USDC", "BUSD", "DAI", "FDUSD", "TUSD"}
        for asset in stablecoin_assets:
            # Stablecoins are valued at ~1:1 with their denomination
            if asset.symbol.upper() in usd_stablecoins:
                unit_price = usd_to_target
            else:
                unit_price = eur_to_target  # EUR-denominated stablecoins
            value = float(asset.quantity) * unit_price
            if value < min_value_eur:
                continue
            cash_from_stablecoins += Decimal(str(value))
            stablecoin_list.append(
                {
                    "id": str(asset.id),
                    "symbol": asset.symbol,
                    "quantity": float(asset.quantity),
                    "value": value,
                }
            )

        # Calculate fiat cash value
        cash_from_fiat = Decimal("0")
        fiat_list = []
        _fiat_rates = {"EUR": eur_to_target, "USD": usd_to_target, "GBP": 1.0, "CHF": 1.0}
        # Fetch additional rates for non-target fiat if needed
        for sym in {"GBP", "CHF"} - {target}:
            try:
                rate = await price_service.get_forex_rate(sym, target)
                if rate:
                    _fiat_rates[sym] = float(rate)
            except Exception:
                pass
        _fiat_rates[target] = 1.0  # target currency = 1:1
        for asset in fiat_assets:
            rate = _fiat_rates.get(asset.symbol.upper(), eur_to_target)
            value = float(asset.quantity) * rate
            cash_from_fiat += Decimal(str(value))
            fiat_list.append(
                {
                    "id": str(asset.id),
                    "symbol": asset.symbol,
                    "quantity": float(asset.quantity),
                    "value": value,
                }
            )

        # Sort by value descending
        asset_metrics.sort(key=lambda x: x["current_value"], reverse=True)

        # Compute risk weights (volatility contribution per symbol)
        symbol_values: Dict[str, float] = {}
        for am in asset_metrics:
            s = am["symbol"].upper()
            symbol_values[s] = symbol_values.get(s, 0) + am["current_value"]
        risk_weights = await self._compute_risk_weights(
            db, list(symbol_values.keys()), symbol_values, float(total_value)
        )
        for am in asset_metrics:
            am["risk_weight"] = risk_weights.get(am["symbol"].upper(), 0.0)

        total_gain_loss = total_value - total_invested
        total_gain_loss_percent = float(total_gain_loss / total_invested * 100) if total_invested > 0 else 0.0

        # Available liquidity = stablecoins + fiat assets + portfolio cash_balances
        available_liquidity = float(cash_from_stablecoins + cash_from_fiat)

        result = {
            "total_value": float(total_value),
            "total_invested": float(total_invested),
            "total_gain_loss": float(total_gain_loss),
            "total_gain_loss_percent": total_gain_loss_percent,
            "assets_count": len(asset_metrics),
            "assets": asset_metrics,
            "cash_from_stablecoins": float(cash_from_stablecoins),
            "stablecoins": stablecoin_list,
            "cash_from_fiat": float(cash_from_fiat),
            "fiat_assets": fiat_list,
            "available_liquidity": available_liquidity,
        }

        # Include crowdfunding summary if relevant
        if crowdfunding_active > 0 or crowdfunding_completed > 0:
            result["crowdfunding_summary"] = {
                "total_invested": float(crowdfunding_total_invested),
                "active_projects": crowdfunding_active,
                "completed_projects": crowdfunding_completed,
                "projected_annual_interest": float(crowdfunding_projected_interest),
                "next_maturity": crowdfunding_next_maturity.isoformat() if crowdfunding_next_maturity else None,
            }

        return result

    async def _fetch_period_changes(self, symbols_by_type: Dict[str, List[str]], days: int) -> Dict[str, float]:
        """Fetch price change percentage over a period for each symbol.

        Strategy (prioritized):
        1. Cached historical data (Redis/PostgreSQL) — fast, no API calls
        2. CoinGecko batch API for crypto — single call, pre-computed periods
        3. Live historical fetch — last resort, one API call per symbol

        Returns {SYMBOL: change_percent}.
        """
        from app.tasks.history_cache import get_cached_history

        changes: Dict[str, float] = {}
        uncached_crypto: list[str] = []
        uncached_stocks: list[str] = []

        # ── Step 1: Try cached historical data first (no API calls) ──
        all_symbols = []
        for syms in symbols_by_type.values():
            all_symbols.extend(syms)

        for symbol in all_symbols:
            try:
                _dates, prices = get_cached_history(symbol.upper(), days=max(days, 2))
            except Exception:
                prices = []
            if prices and len(prices) >= 2 and prices[0] != 0:
                change = (prices[-1] - prices[0]) / prices[0] * 100
                changes[symbol.upper()] = change
            else:
                # Track uncached symbols by type for live fallback
                sym_upper = symbol.upper()
                if sym_upper in [s.upper() for s in symbols_by_type.get("crypto", [])]:
                    uncached_crypto.append(symbol)
                else:
                    uncached_stocks.append(symbol)

        # If all symbols resolved from cache, return early
        if not uncached_crypto and not uncached_stocks:
            return changes

        # ── Step 2: CoinGecko batch API for uncached crypto ──
        if uncached_crypto:
            import httpx

            from app.core.timeframe import get_coingecko_period

            cg_period, cg_key = get_coingecko_period(days)
            if cg_period is not None:
                try:
                    from app.ml.historical_data import HistoricalDataFetcher as HDF

                    coin_ids = [HDF.SYMBOL_MAP.get(s.upper(), s.lower()) for s in uncached_crypto]
                    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
                    coingecko_key = getattr(price_service, "coingecko_api_key", None)
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
                        id_to_symbol = {v: k for k, v in HDF.SYMBOL_MAP.items()}
                        for coin in data:
                            coin_id = coin.get("id", "")
                            symbol = id_to_symbol.get(coin_id, coin.get("symbol", "").upper())
                            pct = coin.get(cg_key)
                            if pct is None:
                                continue
                            if isinstance(pct, dict):
                                pct = pct.get("eur")
                                if pct is None:
                                    continue
                            changes[symbol.upper()] = float(pct)
                            # Remove from uncached since we got data
                            uncached_crypto = [s for s in uncached_crypto if s.upper() != symbol.upper()]
                except Exception as e:
                    logger.warning("Failed to fetch crypto period changes (batch): %s", e)

        # ── Step 2b: Try PostgreSQL asset_price_history for remaining ──
        remaining = uncached_crypto + uncached_stocks
        if remaining:
            try:
                from app.core.database import AsyncSessionLocal
                from app.models.asset_price_history import AssetPriceHistory

                cutoff = (datetime.utcnow() - timedelta(days=days + 5)).date()
                async with AsyncSessionLocal() as _db:
                    for symbol in list(remaining):
                        sym_upper = symbol.upper()
                        result = await _db.execute(
                            select(AssetPriceHistory.price_eur)
                            .where(
                                AssetPriceHistory.symbol == sym_upper,
                                AssetPriceHistory.price_date >= cutoff,
                            )
                            .order_by(AssetPriceHistory.price_date)
                        )
                        prices = [float(r[0]) for r in result.all()]
                        if prices and len(prices) >= 2 and prices[0] != 0:
                            change = (prices[-1] - prices[0]) / prices[0] * 100
                            changes[sym_upper] = change
                            remaining = [s for s in remaining if s.upper() != sym_upper]
            except Exception as e:
                logger.warning("DB period change lookup failed: %s", e)

        # ── Step 3: Live historical fetch for remaining uncached symbols (fast mode) ──
        if remaining:
            fetcher = HistoricalDataFetcher()
            try:
                for symbol in remaining:
                    try:
                        sym_upper = symbol.upper()
                        if sym_upper in [s.upper() for s in symbols_by_type.get("crypto", [])]:
                            _, prices = await fetcher.get_crypto_history(symbol, days=days, fast=True)
                        else:
                            _, prices = await fetcher.get_stock_history(symbol, days=days)
                        if prices and len(prices) >= 2 and prices[0] != 0:
                            change = (prices[-1] - prices[0]) / prices[0] * 100
                            changes[sym_upper] = change
                    except Exception:
                        pass
            finally:
                await fetcher.close()

        return changes

    async def get_user_dashboard_metrics(
        self,
        db: AsyncSession,
        user_id: str,
        currency: str = "EUR",
        days: int = 30,
    ) -> Dict:
        """Calculate dashboard metrics for a user's entire portfolio."""
        # Check in-memory cache
        cache_key = (user_id, days, currency)
        now = time.time()
        if cache_key in _dashboard_cache:
            ts, cached = _dashboard_cache[cache_key]
            if now - ts < _DASHBOARD_CACHE_TTL:
                return cached

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
        total_realized = Decimal("0")
        total_unrealized = Decimal("0")
        total_pnl_fees = Decimal("0")
        total_liquidity = Decimal("0")
        all_assets = []

        for portfolio in portfolios:
            portfolio_metrics = await self.get_portfolio_metrics(db, str(portfolio.id), currency)
            # Get historical total invested (sum of all buy transactions)
            portfolio_history = await self.get_portfolio_history(db, str(portfolio.id), currency)
            total_value += Decimal(str(portfolio_metrics["total_value"]))
            total_invested += Decimal(str(portfolio_history["total_invested_all_time"]))
            total_sold += Decimal(str(portfolio_history.get("total_sold", 0)))
            total_realized += Decimal(str(portfolio_history.get("realized_gains", 0)))
            # Unrealized P&L from portfolio_metrics: correctly uses cost basis
            # of CURRENT holdings only (qty * avg_buy_price), not all-time invested
            total_unrealized += Decimal(str(portfolio_metrics["total_gain_loss"]))
            total_pnl_fees += Decimal(str(portfolio_history.get("total_fees", 0)))
            total_liquidity += Decimal(str(portfolio_metrics.get("available_liquidity", 0)))
            # Add portfolio cash_balances (fiat held on exchanges)
            for _ccy, amount in (portfolio.cash_balances or {}).items():
                total_liquidity += Decimal(str(amount))
            all_assets.extend(portfolio_metrics["assets"])

        # total_gain_loss: gain/loss relative to total ever invested (includes sold positions)
        # This is used for the "brut" view; net_gain_loss below is the primary P&L metric
        total_gain_loss = total_value - total_invested
        if total_invested > 0:
            total_gain_loss_percent = float(total_gain_loss / total_invested * 100)
        else:
            total_gain_loss_percent = 0.0

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
                    "total_quantity": 0.0,
                }
            symbol_agg[sym]["total_invested"] += a["total_invested"]
            symbol_agg[sym]["current_value"] += a["current_value"]
            symbol_agg[sym]["total_quantity"] += a.get("quantity", 0)

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
                data["period_change_percent"] = (data["current_value"] - inv) / inv * 100 if inv > 0 else 0.0

        aggregated = list(symbol_agg.values())

        # Top and worst performers (by price change over selected period)
        top_performers = [a for a in aggregated if a["period_change_percent"] > 0]
        top_performers.sort(key=lambda x: x["period_change_percent"], reverse=True)
        top_performers = top_performers[:5]

        worst_performers = [a for a in aggregated if a["period_change_percent"] < 0]
        worst_performers.sort(key=lambda x: x["period_change_percent"])
        worst_performers = worst_performers[:5]

        # Period change (portfolio-level) — weighted average of asset period changes
        period_change_percent = 0.0
        if float(total_value) > 0 and aggregated:
            for a in aggregated:
                weight = a["current_value"] / float(total_value) if float(total_value) > 0 else 0
                period_change_percent += a.get("period_change_percent", 0) * weight
        period_change = float(total_value) * period_change_percent / 100 if period_change_percent else 0.0

        # Net capital = money injected - money withdrawn (informational only)
        net_capital = total_invested - total_sold

        # Unified P&L: ALL indicators use the same root formula:
        #   net_gain_loss = total_value - total_invested
        # This is the single source of truth. No "Richesse vs Comptable" split.
        net_gain_loss = total_value - total_invested
        if total_invested > 0:
            net_gain_loss_percent = float(net_gain_loss / total_invested * 100)
        else:
            net_gain_loss_percent = 0.0

        result = {
            "total_value": float(total_value),
            "total_invested": float(total_invested),
            "net_capital": float(net_capital),
            "total_gain_loss": float(total_gain_loss),
            "total_gain_loss_percent": total_gain_loss_percent,
            "net_gain_loss": float(net_gain_loss),
            "net_gain_loss_percent": net_gain_loss_percent,
            "daily_change": sum(a["current_value"] * a.get("change_percent_24h", 0) / 100 for a in all_assets),
            "daily_change_percent": sum(
                (a["current_value"] / float(total_value)) * a.get("change_percent_24h", 0) for a in all_assets
            )
            if float(total_value) > 0
            else 0.0,
            "period_change": period_change,
            "period_change_percent": period_change_percent,
            "portfolios_count": len(portfolios),
            "assets_count": len({a["symbol"] for a in all_assets}),
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
            "available_liquidity": float(total_liquidity),
            "period_changes": period_changes,
            # Pre-built asset allocation (avoids N+1 re-fetch in dashboard endpoint)
            "aggregated_assets": [
                {
                    "symbol": a["symbol"],
                    "name": a["name"],
                    "asset_type": a["asset_type"],
                    "current_value": a["current_value"],
                    "total_invested": a["total_invested"],
                    "avg_buy_price": (a["total_invested"] / a["total_quantity"] if a["total_quantity"] > 0 else 0.0),
                    "gain_loss_percent": round(a.get("period_change_percent", 0), 2),
                    "percentage": round(
                        (a["current_value"] / float(total_value) * 100) if float(total_value) > 0 else 0, 2
                    ),
                }
                for a in aggregated
                if a["current_value"] > 0
            ],
            # P&L breakdown: always all-time, unified on the same root as net_gain_loss.
            # total_pnl = total_value - total_invested (single source of truth)
            # unrealized = total_pnl - realized (residual, ensures perfect reconciliation)
            # Guarantee: realized + unrealized = total_pnl (by construction)
            # net_pnl = total_pnl - fees (fees deducted exactly once)
            "pnl_data": {
                "realized_pnl": float(total_realized),
                "unrealized_pnl": float((total_value - total_invested) - total_realized),
                "total_pnl": float(total_value - total_invested),
                "total_fees": float(total_pnl_fees),
                "net_pnl": float(total_value - total_invested - total_pnl_fees),
                "is_all_time": True,  # P&L breakdown is always cumulative
            },
        }

        # Cache the result (bounded)
        _cache_put_dashboard(cache_key, (time.time(), result))
        return result

    async def get_portfolio_history(self, db: AsyncSession, portfolio_id: str, currency: str = "EUR") -> Dict:
        """
        Calculate historical investment metrics for a portfolio.
        Includes all assets (even those with 0 quantity) and calculates
        total invested from all buy transactions.
        """
        # Get ALL assets in portfolio (including zero quantity), excluding CROWDFUNDING
        result = await db.execute(
            select(Asset).where(
                Asset.portfolio_id == portfolio_id,
                Asset.asset_type != AssetType.CROWDFUNDING,
            )
        )
        all_assets = result.scalars().all()
        asset_ids = [a.id for a in all_assets]

        if not asset_ids:
            return {
                "total_invested_all_time": 0.0,
                "total_sold": 0.0,
                "total_fees": 0.0,
                "realized_gains": 0.0,
                "current_holdings_count": 0,
                "sold_assets_count": 0,
                "sold_assets": [],
            }

        # Get all transactions for these assets
        result = await db.execute(
            select(Transaction)
            .where(
                Transaction.asset_id.in_(asset_ids),
            )
            .order_by(Transaction.executed_at.desc())
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
                "exchange": asset.exchange,
                "current_quantity": float(asset.quantity),
                "total_bought": Decimal("0"),
                "total_bought_value": Decimal("0"),
                "total_bought_with_cost": Decimal("0"),  # Only transactions with price > 0
                "total_bought_cost_value": Decimal("0"),  # Only transactions with price > 0
                "total_bought_fiat_value": Decimal("0"),  # Only BUY+TRANSFER_IN (real money in, not conversions)
                "total_sold": Decimal("0"),
                "total_sold_value": Decimal("0"),
                "total_fees": Decimal("0"),
                "first_transaction": None,
                "last_transaction": None,
            }

        # Build historical price lookup for transactions with price=0
        # Collect (symbol, date) pairs that need pricing
        from app.models.asset_price_history import AssetPriceHistory

        asset_id_to_symbol = {str(a.id): a.symbol.upper() for a in all_assets}
        price_lookup_needed: set = set()
        for tx in transactions:
            if Decimal(str(tx.price)) == 0 and tx.executed_at is not None:
                sym = asset_id_to_symbol.get(str(tx.asset_id))
                if sym:
                    price_lookup_needed.add((sym, tx.executed_at.date()))

        # Batch fetch from AssetPriceHistory
        historical_prices: dict = {}  # (symbol, date) → price_eur
        if price_lookup_needed:
            symbols_needed = list({s for s, _ in price_lookup_needed})
            dates_needed = list({d for _, d in price_lookup_needed})
            price_result = await db.execute(
                select(
                    AssetPriceHistory.symbol,
                    AssetPriceHistory.price_date,
                    AssetPriceHistory.price_eur,
                ).where(
                    AssetPriceHistory.symbol.in_(symbols_needed),
                    AssetPriceHistory.price_date.in_(dates_needed),
                )
            )
            for row in price_result.all():
                historical_prices[(row[0], row[1])] = Decimal(str(row[2]))

        def _resolve_price(tx, symbol: str) -> Decimal:
            """Get transaction price, falling back to historical price if 0."""
            p = Decimal(str(tx.price))
            if p > 0:
                return p
            if tx.executed_at is not None:
                hist_p = historical_prices.get((symbol, tx.executed_at.date()))
                if hist_p:
                    return hist_p
            return Decimal("0")

        # Process transactions
        for tx in transactions:
            asset_id = str(tx.asset_id)
            if asset_id not in asset_history:
                continue

            ah = asset_history[asset_id]
            tx_type = tx.transaction_type.value.upper()
            symbol = asset_id_to_symbol.get(asset_id, "")

            # Track dates (skip if executed_at is None)
            tx_date = tx.executed_at
            if tx_date is not None:
                if ah["last_transaction"] is None or tx_date > ah["last_transaction"]:
                    ah["last_transaction"] = tx_date
                if ah["first_transaction"] is None or tx_date < ah["first_transaction"]:
                    ah["first_transaction"] = tx_date

            # Track fees — FEE-type transactions use quantity*price as the fee amount,
            # so we do NOT also add tx.fee for them (would double-count)
            if tx_type == "FEE":
                ah["total_fees"] += Decimal(str(tx.quantity)) * Decimal(str(tx.price))
            else:
                ah["total_fees"] += Decimal(str(tx.fee or 0))

            # Track buys (including dividend/interest which add quantity)
            if tx_type in ["BUY", "TRANSFER_IN", "AIRDROP", "STAKING_REWARD", "CONVERSION_IN", "DIVIDEND", "INTEREST"]:
                # Use original price for buy-side — do NOT resolve historical prices
                # Airdrops/rewards are free (price=0 is correct, not "invested")
                tx_price = Decimal(str(tx.price))
                tx_qty = Decimal(str(tx.quantity))
                ah["total_bought"] += tx_qty
                ah["total_bought_value"] += tx_qty * tx_price
                # Track cost basis separately: only include transactions with a real price
                # so that free tokens (airdrops, transfers at price=0) don't deflate avg cost
                if tx_price > 0:
                    ah["total_bought_with_cost"] += tx_qty
                    ah["total_bought_cost_value"] += tx_qty * tx_price
                # Track real money in (BUY + TRANSFER_IN with price) for total_invested
                # CONVERSION_IN is excluded: it's a form change (crypto→crypto), not new capital
                if tx_type in ["BUY", "TRANSFER_IN"] and tx_price > 0:
                    ah["total_bought_fiat_value"] += tx_qty * tx_price

            # Track sells (real capital out)
            # TRANSFER_OUT excluded: user still owns the asset on cold wallet
            # CONVERSION_OUT included: user disposed of the asset (even if swapped to another crypto),
            #   so it should appear in history as quantity sold
            elif tx_type in ["SELL", "CONVERSION_OUT"]:
                tx_price = _resolve_price(tx, symbol)
                ah["total_sold"] += Decimal(str(tx.quantity))
                ah["total_sold_value"] += Decimal(str(tx.quantity)) * tx_price

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
            # total_invested: only count BUY transactions (real money in)
            # CONVERSION_IN is a form change (crypto→crypto), not new capital
            total_invested_all_time += ah["total_bought_fiat_value"]
            total_sold_value += ah["total_sold_value"]
            total_fees += ah["total_fees"]

            # Format for output
            asset_data = {
                "id": ah["id"],
                "symbol": ah["symbol"],
                "name": ah["name"],
                "asset_type": ah["asset_type"],
                "exchange": ah["exchange"],
                "current_quantity": ah["current_quantity"],
                "total_bought": float(ah["total_bought"]),
                "total_bought_value": float(ah["total_bought_value"]),
                "total_sold": float(ah["total_sold"]),
                "total_sold_value": float(ah["total_sold_value"]),
                "total_fees": float(ah["total_fees"]),
                "realized_gain": float(
                    ah["total_sold_value"]
                    - (ah["total_bought_cost_value"] * ah["total_sold"] / ah["total_bought_with_cost"])
                )
                if ah["total_bought_with_cost"] > 0 and ah["total_sold"] > 0
                else (
                    # No cost basis (free tokens: airdrops, rewards) → sold value is pure profit
                    float(ah["total_sold_value"])
                    if ah["total_sold"] > 0
                    else 0.0
                ),
                "first_transaction": ah["first_transaction"].isoformat() if ah["first_transaction"] else None,
                "last_transaction": ah["last_transaction"].isoformat() if ah["last_transaction"] else None,
            }

            # Consider as "sold" only if quantity is ~0 AND has actual sells/conversions
            # Assets only transferred out (no sells) stay in current_holdings
            if ah["current_quantity"] <= 0 and ah["total_sold"] > 0:
                sold_assets.append(asset_data)
            elif ah["current_quantity"] <= 0:
                # Zero quantity but no sells (transferred out only) — skip from history
                continue
            elif ah["total_sold"] > 0:
                # Partially sold: estimate remaining value
                est_value = (
                    float(ah["current_quantity"]) * float(ah["total_bought_value"] / ah["total_bought"])
                    if ah["total_bought"] > 0 and ah["total_bought_value"] > 0
                    else float(ah["current_quantity"])
                )
                if est_value < 0.10:
                    sold_assets.append(asset_data)
                else:
                    current_holdings.append(asset_data)
            else:
                current_holdings.append(asset_data)

        # Sort by total invested
        sold_assets.sort(key=lambda x: x["total_bought_value"], reverse=True)

        # Sum realized gains from individual assets (already computed per-asset)
        total_realized_gains = sum(Decimal(str(a["realized_gain"])) for a in current_holdings + sold_assets)

        return {
            "total_invested_all_time": float(total_invested_all_time),
            "total_sold": float(total_sold_value),
            "total_fees": float(total_fees),
            "realized_gains": float(total_realized_gains),
            "current_holdings_count": len(current_holdings),
            "sold_assets_count": len(sold_assets),
            "sold_assets": sold_assets,
        }

    async def calculate_roi(self, total_invested: Decimal, current_value: Decimal) -> float:
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

    async def calculate_realized_unrealized_pnl(self, db: AsyncSession, user_id: str, currency: str = "EUR") -> Dict:
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

            total_fees += Decimal(str(history.get("total_fees", 0)))

            # Realized P&L: from sold_assets AND current_holdings with partial sells
            total_realized += Decimal(str(history.get("realized_gains", 0)))

            # Unrealized P&L from current holdings (total_gain_loss = current_value - total_invested)
            portfolio_gain_loss = Decimal(str(metrics.get("total_gain_loss", 0)))
            total_unrealized += portfolio_gain_loss

        return {
            "realized_pnl": float(total_realized),
            "unrealized_pnl": float(total_unrealized),
            "total_pnl": float(total_realized + total_unrealized),
            "total_fees": float(total_fees),
            "net_pnl": float(total_realized + total_unrealized - total_fees),
        }


# Singleton instance
metrics_service = MetricsService()
