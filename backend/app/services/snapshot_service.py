"""Portfolio snapshot service for historical value tracking."""

import logging
import math
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset
from app.models.portfolio import Portfolio
from app.models.portfolio_snapshot import PortfolioSnapshot
from app.models.transaction import Transaction, TransactionType
from app.services.metrics_service import metrics_service

logger = logging.getLogger(__name__)

# In-memory price cache: {(symbol, days): (timestamp, {date_str: price})}
_price_cache: Dict[Tuple[str, int], Tuple[float, Dict[str, float]]] = {}
_PRICE_CACHE_TTL = 1800  # 30 minutes — historical daily prices don't change
_MAX_PRICE_CACHE = 500  # max entries before eviction

# In-memory cache for full portfolio value series: {(user_id, days): (timestamp, result)}
_series_cache: Dict[Tuple[str, int], Tuple[float, List[Dict]]] = {}
_SERIES_CACHE_TTL = 120  # 2 minutes — caches the entire computed series
_MAX_SERIES_CACHE = 200  # max entries before eviction


def _cache_put(cache: dict, key, value, max_size: int) -> None:
    """Insert into a bounded cache, evicting oldest entries if full."""
    if len(cache) >= max_size:
        # Evict oldest 25% by timestamp (first element of value tuple)
        evict_count = max(1, max_size // 4)
        sorted_keys = sorted(cache, key=lambda k: cache[k][0])
        for k in sorted_keys[:evict_count]:
            del cache[k]
    cache[key] = value


class SnapshotService:
    """Service for managing portfolio value snapshots."""

    async def create_snapshot(
        self,
        db: AsyncSession,
        user_id: str,
        portfolio_id: Optional[str] = None,
        total_value: Decimal = Decimal("0"),
        total_invested: Decimal = Decimal("0"),
        currency: str = "EUR",
    ) -> PortfolioSnapshot:
        """Create a new portfolio snapshot."""
        snapshot = PortfolioSnapshot(
            user_id=user_id,
            portfolio_id=portfolio_id,
            snapshot_date=datetime.utcnow(),
            total_value=total_value,
            total_invested=total_invested,
            total_gain_loss=total_value - total_invested,
            currency=currency,
        )
        db.add(snapshot)
        await db.commit()
        await db.refresh(snapshot)
        return snapshot

    async def create_user_snapshot(
        self, db: AsyncSession, user_id: str, currency: str = "EUR"
    ) -> Optional[PortfolioSnapshot]:
        """Create a snapshot of user's total portfolio value."""
        # Get current metrics
        metrics = await metrics_service.get_user_dashboard_metrics(db, user_id, currency)

        if metrics["assets_count"] == 0:
            return None

        return await self.create_snapshot(
            db,
            user_id=user_id,
            portfolio_id=None,
            total_value=Decimal(str(metrics["total_value"])),
            total_invested=Decimal(str(metrics["total_invested"])),
            currency=currency,
        )

    async def create_user_snapshot_if_missing(
        self, db: AsyncSession, user_id: str, currency: str = "EUR"
    ) -> Optional[PortfolioSnapshot]:
        """Create today's snapshot only if one doesn't exist yet.

        Uses a single-query check to avoid TOCTOU race conditions.
        Reuses metrics already computed by the caller if available.
        """
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        existing = await db.execute(
            select(func.count())
            .select_from(PortfolioSnapshot)
            .where(
                and_(
                    PortfolioSnapshot.user_id == user_id,
                    PortfolioSnapshot.snapshot_date >= today_start,
                    PortfolioSnapshot.portfolio_id.is_(None),
                )
            )
        )
        if existing.scalar() > 0:
            return None
        return await self.create_user_snapshot(db, user_id, currency)

    async def _get_invested_timeline(
        self,
        db: AsyncSession,
        user_id: str,
        portfolio_id: Optional[str] = None,
    ) -> tuple[Dict[str, Decimal], Dict[str, Decimal]]:
        """
        Build a timeline of cumulative invested amounts from transactions.
        Returns: dict mapping date string (YYYY-MM-DD) to cumulative invested amount.
        """
        # Get relevant portfolio IDs
        if portfolio_id:
            portfolio_ids = [portfolio_id]
        else:
            portfolios_result = await db.execute(
                select(Portfolio.id).where(
                    and_(
                        Portfolio.user_id == user_id,
                    )
                )
            )
            portfolio_ids = [str(p[0]) for p in portfolios_result.all()]

        if not portfolio_ids:
            return {}, {}

        # Get all transactions ordered by date
        transactions_query = (
            select(
                Transaction.executed_at,
                Transaction.transaction_type,
                Transaction.quantity,
                Transaction.price,
                Transaction.fee,
                Transaction.created_at,
            )
            .join(Asset, Transaction.asset_id == Asset.id)
            .where(Asset.portfolio_id.in_(portfolio_ids))
            .order_by(Transaction.executed_at.asc())
        )

        result = await db.execute(transactions_query)
        transactions = result.all()

        # Build cumulative invested and net capital by date
        daily_invested: Dict[str, Decimal] = {}
        daily_net_capital: Dict[str, Decimal] = {}
        cumulative = Decimal("0")
        cumulative_net = Decimal("0")

        for tx in transactions:
            tx_exec = tx.executed_at or tx.created_at
            if tx_exec is None:
                continue
            tx_date = tx_exec.strftime("%Y-%m-%d")
            tx_type = tx.transaction_type
            quantity = Decimal(str(tx.quantity))
            price = Decimal(str(tx.price))
            _ = Decimal(str(tx.fee or 0))  # fee tracked in total_fees
            tx_amount = quantity * price

            # Invested: Only count money going IN with a real price (never decreases)
            # Fees are tracked separately in total_fees, not included in invested
            if tx_type in [TransactionType.BUY]:
                cumulative += tx_amount
                cumulative_net += tx_amount
            elif tx_type in [TransactionType.TRANSFER_IN] and price > 0:
                cumulative += tx_amount
                cumulative_net += tx_amount
            elif tx_type in [TransactionType.CONVERSION_IN] and price > 0:
                # CONVERSION_IN is a form change (crypto→crypto), not new capital
                # Only add to net_capital (asset form change), NOT to cumulative invested
                cumulative_net += tx_amount
            # Net capital decreases on sells only (not transfers to cold wallets)
            # TRANSFER_OUT = moving to cold wallet, user still owns the asset
            elif tx_type in [TransactionType.SELL]:
                cumulative_net -= tx_amount
            # Conversions are neutral: asset form changes, no capital leaves
            elif tx_type == TransactionType.CONVERSION_OUT:
                cumulative_net -= tx_amount

            # Don't clamp cumulative_net to 0: negative means user recovered
            # more than invested, which is valid and should be shown accurately

            daily_invested[tx_date] = cumulative
            daily_net_capital[tx_date] = cumulative_net

        return daily_invested, daily_net_capital

    async def get_historical_values(
        self,
        db: AsyncSession,
        user_id: str,
        days: int = 30,
        portfolio_id: Optional[str] = None,
    ) -> List[Dict]:
        """Get historical portfolio values for chart display."""
        start_date = datetime.utcnow() - timedelta(days=days)
        datetime.utcnow()

        # Get invested timeline from transactions
        invested_timeline, net_capital_timeline = await self._get_invested_timeline(db, user_id, portfolio_id)

        if portfolio_id:
            # Get snapshots for a specific portfolio
            query = (
                select(PortfolioSnapshot)
                .where(
                    and_(
                        PortfolioSnapshot.user_id == user_id,
                        PortfolioSnapshot.snapshot_date >= start_date,
                        PortfolioSnapshot.portfolio_id == portfolio_id,
                    )
                )
                .order_by(PortfolioSnapshot.snapshot_date.asc())
            )

            result = await db.execute(query)
            snapshots = result.scalars().all()
        else:
            # First try to get global snapshots (portfolio_id IS NULL)
            query = (
                select(PortfolioSnapshot)
                .where(
                    and_(
                        PortfolioSnapshot.user_id == user_id,
                        PortfolioSnapshot.snapshot_date >= start_date,
                        PortfolioSnapshot.portfolio_id.is_(None),
                    )
                )
                .order_by(PortfolioSnapshot.snapshot_date.asc())
            )

            result = await db.execute(query)
            snapshots = result.scalars().all()

            # If no global snapshots, aggregate from per-portfolio snapshots
            if not snapshots:
                agg_query = (
                    select(
                        func.date(PortfolioSnapshot.snapshot_date).label("date"),
                        func.sum(PortfolioSnapshot.total_value).label("total_value"),
                        func.sum(PortfolioSnapshot.total_invested).label("total_invested"),
                        func.sum(PortfolioSnapshot.total_gain_loss).label("total_gain_loss"),
                        func.max(PortfolioSnapshot.snapshot_date).label("snapshot_date"),
                    )
                    .where(
                        and_(
                            PortfolioSnapshot.user_id == user_id,
                            PortfolioSnapshot.snapshot_date >= start_date,
                            PortfolioSnapshot.portfolio_id.isnot(None),
                        )
                    )
                    .group_by(func.date(PortfolioSnapshot.snapshot_date))
                    .order_by(func.date(PortfolioSnapshot.snapshot_date).asc())
                )

                result = await db.execute(agg_query)
                rows = result.all()

                # Format aggregated data with transaction-based invested
                interval = self._get_data_point_interval(days)
                formatted_data = []
                last_invested = Decimal("0")
                last_net_capital = Decimal("0")

                for i, row in enumerate(rows):
                    if i % interval == 0 or i == len(rows) - 1:
                        date_str = row.snapshot_date.strftime("%Y-%m-%d")
                        # Get invested from transactions up to this date
                        for d in sorted(invested_timeline.keys()):
                            if d <= date_str:
                                last_invested = invested_timeline[d]
                        for d in sorted(net_capital_timeline.keys()):
                            if d <= date_str:
                                last_net_capital = net_capital_timeline[d]

                        invested = float(last_invested)
                        net_cap = float(last_net_capital)
                        value = float(row.total_value) if row.total_value else 0.0

                        formatted_data.append(
                            {
                                "date": self._format_date_for_period(row.snapshot_date, days),
                                "full_date": row.snapshot_date.isoformat(),
                                "value": value,
                                "invested": invested,
                                "net_capital": net_cap,
                                "gain_loss": value - invested,
                            }
                        )

                return formatted_data

        # Format dates according to period and filter by interval
        interval = self._get_data_point_interval(days)
        formatted_data = []
        last_invested = Decimal("0")
        last_net_capital = Decimal("0")

        for i, s in enumerate(snapshots):
            # Only include points at the interval (or always include last point)
            if i % interval == 0 or i == len(snapshots) - 1:
                date_str = s.snapshot_date.strftime("%Y-%m-%d")
                # Get invested from transactions up to this date
                for d in sorted(invested_timeline.keys()):
                    if d <= date_str:
                        last_invested = invested_timeline[d]
                for d in sorted(net_capital_timeline.keys()):
                    if d <= date_str:
                        last_net_capital = net_capital_timeline[d]

                invested = float(last_invested) if invested_timeline else float(s.total_invested)
                net_cap = float(last_net_capital) if net_capital_timeline else invested
                value = float(s.total_value)

                formatted_data.append(
                    {
                        "date": self._format_date_for_period(s.snapshot_date, days),
                        "full_date": s.snapshot_date.isoformat(),
                        "value": value,
                        "invested": invested,
                        "net_capital": net_cap,
                        "gain_loss": value - invested,
                    }
                )

        return formatted_data

    def _format_date_for_period(self, date: datetime, days: int) -> str:
        """Format date label based on the period length."""
        if days <= 7:
            # Short period: show day name + date (Lun 23)
            day_names = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
            return f"{day_names[date.weekday()]} {date.day}"
        elif days <= 30:
            # Medium period: show day + month (23 Jan)
            return date.strftime("%d %b")
        elif days <= 90:
            # Quarter: show day + month abbreviated (23/01)
            return date.strftime("%d/%m")
        else:
            # Year: show day + month abbreviated (23/01)
            # Using day/month to keep dates distinct
            return date.strftime("%d/%m")

    def _get_data_point_interval(self, days: int) -> int:
        """Determine the interval between data points based on period."""
        if days <= 7:
            return 1  # Every day
        elif days <= 30:
            return 1  # Every day
        elif days <= 90:
            return 3  # Every 3 days
        elif days <= 365:
            return 7  # Every week for year view
        else:
            return 14  # Every 2 weeks for multi-year view

    async def generate_historical_from_transactions(
        self,
        db: AsyncSession,
        user_id: str,
        days: int = 30,
    ) -> List[Dict]:
        """
        Generate historical data from transactions + real historical prices.

        Delegates to build_portfolio_value_series() which reconstructs daily
        portfolio value using actual market prices instead of interpolation.
        """
        return await self.build_portfolio_value_series(db, user_id, days)

    def _generate_flat_history(self, today: datetime, days: int, value: float, invested: float) -> List[Dict]:
        """Generate minimal history when no transaction data available."""
        start_date = today - timedelta(days=days)
        return [
            {
                "date": self._format_date_for_period(start_date, days),
                "full_date": start_date.isoformat(),
                "value": round(invested, 2),
                "invested": round(invested, 2),
                "net_capital": round(invested, 2),
                "gain_loss": 0.0,
            },
            {
                "date": self._format_date_for_period(today, days),
                "full_date": today.isoformat(),
                "value": round(value, 2),
                "invested": round(invested, 2),
                "net_capital": round(invested, 2),
                "gain_loss": round(value - invested, 2),
            },
        ]

    # ================================================================
    # Real-price based portfolio value reconstruction
    # ================================================================

    async def _get_user_transactions_with_assets(
        self,
        db: AsyncSession,
        user_id: str,
        portfolio_id: Optional[str] = None,
    ) -> List[Tuple]:
        """Fetch all user transactions with asset symbol and type, ordered by date."""
        if portfolio_id:
            portfolio_ids = [portfolio_id]
        else:
            portfolios_result = await db.execute(select(Portfolio.id).where(Portfolio.user_id == user_id))
            portfolio_ids = [str(p[0]) for p in portfolios_result.all()]

        if not portfolio_ids:
            return []

        query = (
            select(
                Transaction.executed_at,
                Transaction.transaction_type,
                Transaction.quantity,
                Transaction.price,
                Transaction.fee,
                Transaction.currency,
                Asset.symbol,
                Asset.asset_type,
                Transaction.created_at,
            )
            .join(Asset, Transaction.asset_id == Asset.id)
            .where(Asset.portfolio_id.in_(portfolio_ids))
            .order_by(Transaction.executed_at.asc())
        )

        result = await db.execute(query)
        return result.all()

    def _replay_transactions_to_daily_holdings(
        self,
        transactions: List[Tuple],
        start_date: datetime,
        end_date: datetime,
    ) -> Tuple[Dict[str, Dict[str, float]], Dict[str, float], Dict[str, float], Dict[str, str]]:
        """
        Replay transactions chronologically to build daily holdings map.

        Returns:
            - daily_holdings: Dict[date_str, Dict[symbol, quantity]]
            - daily_invested: Dict[date_str, cumulative_invested]
            - daily_net_capital: Dict[date_str, net_capital]
            - asset_types: Dict[symbol, asset_type_str]
        """
        holdings: Dict[str, float] = {}  # symbol -> quantity
        cumulative_invested = 0.0
        cumulative_net_capital = 0.0
        asset_types: Dict[str, str] = {}

        # Group transactions by date
        tx_by_date: Dict[str, List] = {}
        for tx in transactions:
            executed_at = tx.executed_at or tx.created_at
            if executed_at is None:
                continue
            if hasattr(executed_at, "tzinfo") and executed_at.tzinfo is not None:
                executed_at = executed_at.replace(tzinfo=None)
            date_str = executed_at.strftime("%Y-%m-%d")
            if date_str not in tx_by_date:
                tx_by_date[date_str] = []
            tx_by_date[date_str].append(tx)
            # Track asset types
            symbol = tx.symbol.upper()
            if symbol not in asset_types:
                asset_types[symbol] = tx.asset_type.value if hasattr(tx.asset_type, "value") else str(tx.asset_type)

        # Iterate day by day
        daily_holdings: Dict[str, Dict[str, float]] = {}
        daily_invested: Dict[str, float] = {}
        daily_net_capital: Dict[str, float] = {}

        current = start_date
        while current <= end_date:
            date_str = current.strftime("%Y-%m-%d")

            # Apply transactions for this day
            if date_str in tx_by_date:
                for tx in tx_by_date[date_str]:
                    symbol = tx.symbol.upper()
                    quantity = float(tx.quantity)
                    price = float(tx.price)
                    tx_type = tx.transaction_type
                    tx_amount = quantity * price

                    if tx_type in (TransactionType.BUY,):
                        holdings[symbol] = holdings.get(symbol, 0.0) + quantity
                        # Fees tracked separately — NOT included in invested/net_capital
                        # to match metrics_service.get_portfolio_history and _get_invested_timeline
                        cumulative_invested += tx_amount
                        cumulative_net_capital += tx_amount
                    elif tx_type in (
                        TransactionType.TRANSFER_IN,
                        TransactionType.AIRDROP,
                        TransactionType.STAKING_REWARD,
                    ):
                        holdings[symbol] = holdings.get(symbol, 0.0) + quantity
                        if tx_type == TransactionType.TRANSFER_IN:
                            cumulative_invested += tx_amount
                            cumulative_net_capital += tx_amount
                    elif tx_type in (TransactionType.SELL,):
                        holdings[symbol] = max(0.0, holdings.get(symbol, 0.0) - quantity)
                        cumulative_net_capital -= tx_amount
                    elif tx_type in (TransactionType.TRANSFER_OUT,):
                        holdings[symbol] = max(0.0, holdings.get(symbol, 0.0) - quantity)
                        # Don't reduce net_capital: user still owns the asset on cold wallet
                    elif tx_type == TransactionType.CONVERSION_OUT:
                        holdings[symbol] = max(0.0, holdings.get(symbol, 0.0) - quantity)
                        # Conversion = form change, reduce net_capital (symmetric with CONVERSION_IN)
                        cumulative_net_capital -= tx_amount
                    elif tx_type == TransactionType.CONVERSION_IN:
                        holdings[symbol] = holdings.get(symbol, 0.0) + quantity
                        # Conversion = form change, add to net_capital (not to invested)
                        cumulative_net_capital += tx_amount

                    # Don't clamp cumulative_net_capital to 0: negative means user
                    # recovered more than invested, which is valid and needed for TWR.

            # Record snapshot of holdings for this day (only non-zero)
            daily_holdings[date_str] = {s: q for s, q in holdings.items() if q > 1e-10}
            daily_invested[date_str] = cumulative_invested
            daily_net_capital[date_str] = cumulative_net_capital

            current += timedelta(days=1)

        return daily_holdings, daily_invested, daily_net_capital, asset_types

    async def _fetch_all_price_series(
        self,
        symbols_with_types: Dict[str, str],
        days: int,
        db: Optional["AsyncSession"] = None,
    ) -> Dict[str, Dict[str, float]]:
        """
        Fetch historical prices for all symbols.
        Returns: Dict[symbol, Dict[date_str, price_eur]]

        Priority: in-memory cache → PostgreSQL → Redis → CoinGecko/Yahoo API.
        PostgreSQL is the primary persistent source after deep backfill.
        """
        from app.core.config import settings
        from app.ml.historical_data import HistoricalDataFetcher
        from app.models.asset_price_history import AssetPriceHistory
        from app.tasks.history_cache import get_cached_history

        price_series: Dict[str, Dict[str, float]] = {}

        # Stablecoins: default price of ~1 EUR (close enough)
        STABLECOINS = {"USDT", "USDC", "DAI", "BUSD", "TUSD", "USDG"}

        now = time.time()
        symbols_to_fetch: Dict[str, str] = {}

        # 1. Check in-memory cache first (avoids DB/API entirely)
        for symbol, asset_type in symbols_with_types.items():
            symbol_upper = symbol.upper()
            cache_key = (symbol_upper, days)
            if cache_key in _price_cache:
                ts, cached_series = _price_cache[cache_key]
                if now - ts < _PRICE_CACHE_TTL:
                    price_series[symbol_upper] = cached_series
                    continue
            symbols_to_fetch[symbol_upper] = asset_type

        if not symbols_to_fetch:
            return price_series

        # 2. Check PostgreSQL first (persistent, complete after backfill)
        symbols_need_redis: Dict[str, str] = {}
        if db is not None:
            cutoff_date = (datetime.utcnow() - timedelta(days=days + 5)).date()
            for symbol_upper, asset_type in symbols_to_fetch.items():
                if symbol_upper in STABLECOINS:
                    price_series[symbol_upper] = {}
                    continue
                try:
                    result = await db.execute(
                        select(AssetPriceHistory.price_date, AssetPriceHistory.price_eur)
                        .where(
                            AssetPriceHistory.symbol == symbol_upper,
                            AssetPriceHistory.price_date >= cutoff_date,
                        )
                        .order_by(AssetPriceHistory.price_date)
                    )
                    rows = result.all()
                    if rows and len(rows) >= max(days * 0.5, 5):
                        series: Dict[str, float] = {}
                        for row in rows:
                            series[row[0].strftime("%Y-%m-%d")] = float(row[1])
                        price_series[symbol_upper] = series
                        _cache_put(_price_cache, (symbol_upper, days), (time.time(), series), _MAX_PRICE_CACHE)
                        continue
                except Exception as e:
                    logger.warning("DB price lookup failed for %s: %s", symbol_upper, e)
                symbols_need_redis[symbol_upper] = asset_type
        else:
            symbols_need_redis = {s: t for s, t in symbols_to_fetch.items() if s not in STABLECOINS}
            for s in symbols_to_fetch:
                if s in STABLECOINS:
                    price_series[s] = {}

        if not symbols_need_redis:
            return price_series

        # 3. Check Redis cache for remaining symbols
        symbols_need_api: Dict[str, str] = {}
        for symbol_upper, asset_type in symbols_need_redis.items():
            dates, prices = get_cached_history(symbol_upper, days)
            if dates and prices:
                series = {}
                for d, p in zip(dates, prices):
                    series[d.strftime("%Y-%m-%d")] = float(p)
                price_series[symbol_upper] = series
                _cache_put(_price_cache, (symbol_upper, days), (time.time(), series), _MAX_PRICE_CACHE)
            else:
                symbols_need_api[symbol_upper] = asset_type

        if not symbols_need_api:
            return price_series

        # 4. Fetch missing symbols from API with concurrency limit
        # Use a semaphore to avoid saturating CoinGecko (50 req/min free tier)
        import asyncio as _asyncio

        from app.tasks.history_cache import _persist_prices_to_db, cache_single_asset

        coingecko_key = getattr(settings, "COINGECKO_API_KEY", None) or None
        fetcher = HistoricalDataFetcher(coingecko_api_key=coingecko_key)

        # Limit to 3 concurrent API calls to respect rate limits
        _api_semaphore = _asyncio.Semaphore(3)

        async def _fetch_one(sym: str, at: str) -> Tuple[str, Optional[Tuple]]:
            async with _api_semaphore:
                try:
                    result = await fetcher.get_history(sym, at, days)
                    return (sym, result)
                except Exception as e:
                    logger.warning("Failed to fetch prices for %s: %s", sym, e)
                    return (sym, None)

        try:
            tasks = [_fetch_one(sym, at) for sym, at in symbols_need_api.items()]
            results = await _asyncio.gather(*tasks)

            symbols_failed = []
            for symbol_upper, result in results:
                if result is None:
                    symbols_failed.append(symbol_upper)
                    continue
                dates, prices = result
                if dates and prices:
                    series = {d.strftime("%Y-%m-%d"): float(p) for d, p in zip(dates, prices)}
                    price_series[symbol_upper] = series
                    _cache_put(_price_cache, (symbol_upper, days), (time.time(), series), _MAX_PRICE_CACHE)
                    # Persist to PostgreSQL for future requests
                    try:
                        await _persist_prices_to_db(symbol_upper, dates, prices)
                    except Exception:
                        pass
                else:
                    symbols_failed.append(symbol_upper)

            # Fallback for failed symbols: use stale in-memory cache if available
            for symbol_upper in symbols_failed:
                stale_key = (symbol_upper, days)
                if stale_key in _price_cache:
                    _, stale_series = _price_cache[stale_key]
                    price_series[symbol_upper] = stale_series
                    logger.info("Using stale cache for %s", symbol_upper)
                else:
                    logger.warning("No price data available for %s", symbol_upper)
                # Trigger background deep backfill for this symbol
                try:
                    asset_type = symbols_need_api.get(symbol_upper, "crypto")
                    cache_single_asset.delay(symbol_upper, asset_type)
                except Exception:
                    pass
        finally:
            await fetcher.close()

        return price_series

    async def build_portfolio_value_series(
        self,
        db: AsyncSession,
        user_id: str,
        days: int = 30,
        portfolio_id: Optional[str] = None,
    ) -> List[Dict]:
        """
        Build daily portfolio value series from transactions + real historical prices.

        This is the core method that replaces snapshot-based history.
        It replays transactions to determine daily holdings, fetches real prices,
        and computes portfolio value for each day.
        """
        # Check result-level cache first (avoids expensive DB + computation)
        cache_key = (user_id, days)
        now = time.time()
        if cache_key in _series_cache:
            ts, cached_result = _series_cache[cache_key]
            if now - ts < _SERIES_CACHE_TTL:
                return cached_result

        transactions = await self._get_user_transactions_with_assets(db, user_id, portfolio_id)

        if not transactions:
            return []

        today = datetime.utcnow()
        first_tx_date = transactions[0].executed_at or transactions[0].created_at
        if first_tx_date is None:
            first_tx_date = today

        # Normalize to naive datetimes for comparison (all dates are UTC)
        if hasattr(first_tx_date, "tzinfo") and first_tx_date.tzinfo is not None:
            first_tx_date = first_tx_date.replace(tzinfo=None)

        # Start from the later of: (first transaction, today - days)
        period_start = today - timedelta(days=days)
        # We need to replay from first transaction to get correct holdings
        replay_start = min(first_tx_date, period_start)
        replay_start = replay_start.replace(hour=0, minute=0, second=0, microsecond=0)

        # Build daily holdings
        daily_holdings, daily_invested, daily_net_capital, asset_types = self._replay_transactions_to_daily_holdings(
            transactions, replay_start, today
        )

        # Collect all symbols that were ever held
        all_symbols: Dict[str, str] = {}
        for date_holdings in daily_holdings.values():
            for symbol in date_holdings:
                if symbol not in all_symbols and symbol in asset_types:
                    all_symbols[symbol] = asset_types[symbol]

        if not all_symbols:
            return []

        # Fetch price data
        # Use max(days, days_since_first_tx) — cap at 1825 (5 years)
        days_since_first = (today - replay_start).days + 5  # extra buffer
        fetch_days = min(max(days, days_since_first, 90), 1825)
        price_series = await self._fetch_all_price_series(all_symbols, fetch_days, db=db)

        # Fetch live USD→EUR rate for stablecoin pricing (fallback to 0.92)
        try:
            from app.services.price_service import PriceService

            _ps = PriceService()
            stablecoin_eur_rate = float(await _ps.get_forex_rate("USD", "EUR") or 0.92)
        except Exception:
            stablecoin_eur_rate = 0.92

        # Fallback: if most symbols have no price data (API down), use DB snapshots
        STABLECOINS = {"USDT", "USDC", "DAI", "BUSD", "TUSD", "USDG"}
        non_stable_symbols = {s for s in all_symbols if s not in STABLECOINS}
        symbols_with_prices = {s for s in non_stable_symbols if s in price_series and price_series[s]}
        if non_stable_symbols and len(symbols_with_prices) < len(non_stable_symbols) / 2:
            logger.warning(
                "Missing price data for %d/%d symbols, falling back to DB snapshots",
                len(non_stable_symbols) - len(symbols_with_prices),
                len(non_stable_symbols),
            )
            snapshots_result = await db.execute(
                select(PortfolioSnapshot)
                .where(
                    PortfolioSnapshot.user_id == user_id,
                    PortfolioSnapshot.portfolio_id.is_(None),
                    PortfolioSnapshot.snapshot_date >= (today - timedelta(days=days + 5)),
                )
                .order_by(PortfolioSnapshot.snapshot_date.asc())
            )
            db_snapshots = snapshots_result.scalars().all()
            if db_snapshots:
                return [
                    {
                        "date": self._format_date_for_period(
                            s.snapshot_date.replace(tzinfo=None)
                            if hasattr(s.snapshot_date, "tzinfo") and s.snapshot_date.tzinfo
                            else s.snapshot_date,
                            days,
                        ),
                        "full_date": (
                            s.snapshot_date.replace(tzinfo=None)
                            if hasattr(s.snapshot_date, "tzinfo") and s.snapshot_date.tzinfo
                            else s.snapshot_date
                        ).isoformat(),
                        "value": round(float(s.total_value), 2),
                        "invested": round(float(s.total_invested), 2),
                        "net_capital": round(float(s.total_invested), 2),
                        "gain_loss": round(float(s.total_gain_loss), 2),
                    }
                    for s in db_snapshots
                ]

        # Build value series for the display period
        result: List[Dict] = []
        interval = self._get_data_point_interval(days)

        # Only output data for the requested period
        output_start = max(period_start, replay_start)
        output_start_str = output_start.strftime("%Y-%m-%d")

        # Collect all dates in the period
        period_dates = sorted(d for d in daily_holdings.keys() if d >= output_start_str)

        if not period_dates:
            return []

        # Track last known prices for LOCF (Last Observation Carried Forward)
        last_known_prices: Dict[str, float] = {}

        for i, date_str in enumerate(period_dates):
            # Only include points at the interval (or always include first/last)
            if i % interval != 0 and i != len(period_dates) - 1 and i != 0:
                # Update last known prices for ALL symbols that have exact data on skipped days
                for symbol in price_series:
                    if date_str in price_series[symbol]:
                        last_known_prices[symbol] = price_series[symbol][date_str]
                continue

            holdings = daily_holdings[date_str]
            invested = daily_invested.get(date_str, 0.0)
            net_capital = daily_net_capital.get(date_str, 0.0)

            # Compute portfolio value for this day
            daily_value = 0.0
            for symbol, qty in holdings.items():
                if qty <= 1e-10:
                    continue

                price = None
                # Try exact date
                if symbol in price_series and date_str in price_series[symbol]:
                    price = price_series[symbol][date_str]
                    last_known_prices[symbol] = price
                # LOCF: use last known price
                elif symbol in last_known_prices:
                    price = last_known_prices[symbol]
                # Stablecoin fallback (live forex rate)
                elif symbol in STABLECOINS:
                    price = stablecoin_eur_rate
                    last_known_prices[symbol] = price
                # Try to find nearest price in series
                elif symbol in price_series:
                    # Find closest earlier date
                    available_dates = sorted(price_series[symbol].keys())
                    for d in reversed(available_dates):
                        if d <= date_str:
                            price = price_series[symbol][d]
                            last_known_prices[symbol] = price
                            break
                    # If no earlier date, try first available
                    if price is None and available_dates:
                        price = price_series[symbol][available_dates[0]]
                        last_known_prices[symbol] = price

                if price is not None:
                    daily_value += qty * price

            dt = datetime.strptime(date_str, "%Y-%m-%d")
            result.append(
                {
                    "date": self._format_date_for_period(dt, days),
                    "full_date": dt.isoformat(),
                    "value": round(daily_value, 2),
                    "invested": round(invested, 2),
                    "net_capital": round(net_capital, 2),
                    "gain_loss": round(daily_value - invested, 2),
                }
            )

        # Cache the result for subsequent calls (bounded)
        _cache_put(_series_cache, cache_key, (time.time(), result), _MAX_SERIES_CACHE)
        return result

    def _estimate_interval_days(self, history: List[Dict]) -> float:
        """Estimate the average interval in days between data points.

        When data is subsampled (e.g. every 3 or 7 days), we need the actual
        interval to correctly annualize volatility and Sharpe.
        """
        if len(history) < 2:
            return 1.0

        try:
            from datetime import datetime as _dt

            dates = []
            for h in history:
                fd = h.get("full_date")
                if fd:
                    dates.append(_dt.fromisoformat(fd))
            if len(dates) >= 2:
                total_days = (dates[-1] - dates[0]).days
                intervals = len(dates) - 1
                if intervals > 0 and total_days > 0:
                    return total_days / intervals
        except Exception:
            pass

        return 1.0

    def _compute_twr_log_returns(self, history: List[Dict]) -> List[float]:
        """Compute Time-Weighted log returns that exclude capital flow effects.

        Standard log returns (log(V_t / V_{t-1})) are inflated by DCA buys
        because new money in looks like positive returns. TWR adjusts for this:
        return_t = log((V_t - capital_flow_t) / V_{t-1})
        where capital_flow_t = net_capital_t - net_capital_{t-1}.

        Returns are clipped to [-1.0, +1.0] per interval to prevent outliers
        (e.g. from missing price data) from inflating volatility/Sharpe.
        """
        # Max log-return per interval: ±1.0 ≈ ±172% gain / -63% loss
        MAX_LOG_RETURN = 1.0

        returns = []
        for i in range(1, len(history)):
            prev_value = history[i - 1]["value"]
            curr_value = history[i]["value"]
            if prev_value <= 0:
                continue
            # Exclude capital flows (buys add capital, sells remove it)
            prev_net_cap = history[i - 1].get("net_capital", 0)
            curr_net_cap = history[i].get("net_capital", 0)
            capital_flow = curr_net_cap - prev_net_cap
            adjusted_value = curr_value - capital_flow
            # Skip interval when TWR is undefined (adjusted value non-positive)
            if adjusted_value <= 0:
                continue
            log_return = math.log(adjusted_value / prev_value)
            # Clip extreme returns to prevent single outliers from dominating
            log_return = max(-MAX_LOG_RETURN, min(MAX_LOG_RETURN, log_return))
            returns.append(log_return)
        return returns

    async def calculate_volatility(
        self,
        db: AsyncSession,
        user_id: str,
        days: int = 30,
        history: Optional[List[Dict]] = None,
    ) -> float:
        """Calculate portfolio volatility based on TWR log returns.

        Uses Time-Weighted Returns (excludes capital flow effects) and
        annualization adjusted for the actual data interval.
        """
        if history is None:
            history = await self.build_portfolio_value_series(db, user_id, days)

        if len(history) < 2:
            return 0.0

        returns = self._compute_twr_log_returns(history)

        if len(returns) < 2:
            return 0.0

        # Annualized volatility: std(returns) * sqrt(periods_per_year)
        # periods_per_year = 365 / interval_days (adjusts for subsampled data)
        interval_days = self._estimate_interval_days(history)
        periods_per_year = 365.0 / interval_days

        n = len(returns)
        mean_return = sum(returns) / n
        variance = sum((r - mean_return) ** 2 for r in returns) / (n - 1)  # ddof=1
        volatility = math.sqrt(variance) * math.sqrt(periods_per_year) * 100

        return round(volatility, 2)

    async def calculate_sharpe_ratio(
        self,
        db: AsyncSession,
        user_id: str,
        days: int = 30,
        risk_free_rate: float = 0.035,
        history: Optional[List[Dict]] = None,
        roi_annualized: Optional[float] = None,
    ) -> float:
        """Calculate Sharpe ratio for the portfolio.

        Uses roi_annualized (CAGR) as the return component to ensure
        consistency: a negative CAGR always produces a negative Sharpe.
        Volatility is computed from TWR log returns.
        """
        if history is None:
            history = await self.build_portfolio_value_series(db, user_id, days)

        if len(history) < 2:
            return 0.0

        returns = self._compute_twr_log_returns(history)

        if len(returns) < 2:
            return 0.0

        # Volatility from TWR log returns (annualized)
        interval_days = self._estimate_interval_days(history)
        periods_per_year = 365.0 / interval_days

        n = len(returns)
        mean_return = sum(returns) / n
        variance = sum((r - mean_return) ** 2 for r in returns) / (n - 1)  # ddof=1
        volatility = math.sqrt(variance) * math.sqrt(periods_per_year)

        if volatility == 0:
            return 0.0

        # Use roi_annualized (CAGR) when available for return component.
        # This ensures a portfolio with negative CAGR always gets a negative Sharpe.
        if roi_annualized is not None:
            annualized_return = roi_annualized / 100.0  # convert percentage to decimal
        else:
            annualized_return = mean_return * periods_per_year

        sharpe = (annualized_return - risk_free_rate) / volatility
        return round(sharpe, 2)

    async def calculate_max_drawdown(
        self,
        db: AsyncSession,
        user_id: str,
        days: int = 30,
        history: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        Calculate Maximum Drawdown (MDD) - the largest peak-to-trough decline.
        Returns both the percentage and the period.
        """
        if history is None:
            history = await self.build_portfolio_value_series(db, user_id, days)

        if len(history) < 2:
            return {"max_drawdown_percent": 0.0, "peak_date": None, "trough_date": None}

        values = [h["value"] for h in history]
        dates = [h.get("full_date", h["date"]) for h in history]

        max_drawdown = 0.0
        peak_value = values[0]
        peak_idx = 0
        max_peak_idx = 0
        max_trough_idx = 0

        for i, value in enumerate(values):
            if value > peak_value:
                peak_value = value
                peak_idx = i

            drawdown = (peak_value - value) / peak_value if peak_value > 0 else 0

            if drawdown > max_drawdown:
                max_drawdown = drawdown
                max_peak_idx = peak_idx
                max_trough_idx = i

        return {
            "max_drawdown_percent": round(max_drawdown * 100, 2),
            "peak_date": dates[max_peak_idx] if max_drawdown > 0 else None,
            "trough_date": dates[max_trough_idx] if max_drawdown > 0 else None,
            "peak_value": values[max_peak_idx] if max_drawdown > 0 else None,
            "trough_value": values[max_trough_idx] if max_drawdown > 0 else None,
        }

    async def calculate_var(
        self,
        db: AsyncSession,
        user_id: str,
        days: int = 30,
        confidence_level: float = 0.95,
        current_value: float = 0,
        history: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        Calculate Value at Risk (VaR) using historical simulation method.
        Returns the potential loss at the given confidence level.
        """
        if history is None:
            history = await self.build_portfolio_value_series(db, user_id, days)

        if len(history) < 5:
            return {"var_percent": 0.0, "var_amount": 0.0, "confidence_level": confidence_level}

        # Use TWR log returns (consistent with Sharpe/Volatility calculations)
        # Raw simple returns are distorted by capital flows (DCA buys appear as gains)
        returns = self._compute_twr_log_returns(history)

        if not returns:
            return {"var_percent": 0.0, "var_amount": 0.0, "confidence_level": confidence_level}

        # Sort returns and find the percentile
        sorted_returns = sorted(returns)
        n = len(sorted_returns)
        # For VaR at 95%, we want the 5th percentile of returns
        # With < 20 returns, we don't have enough data for reliable VaR
        if n < 20:
            return {"var_percent": 0.0, "var_amount": 0.0, "confidence_level": confidence_level}
        # Use ceil-based index for correct empirical percentile
        var_index = max(0, math.ceil((1 - confidence_level) * n) - 1)
        var_percent = abs(sorted_returns[var_index]) * 100

        # Calculate VaR amount
        var_amount = current_value * (var_percent / 100) if current_value > 0 else 0

        return {
            "var_percent": round(var_percent, 2),
            "var_amount": round(var_amount, 2),
            "confidence_level": confidence_level,
        }

    async def calculate_beta(
        self,
        portfolio_returns: List[float],
        benchmark_returns: List[float],
    ) -> float:
        """
        Calculate Beta - measure of portfolio's volatility relative to the market.
        Beta > 1: More volatile than market
        Beta < 1: Less volatile than market
        Beta = 1: Same volatility as market
        """
        if len(portfolio_returns) < 2 or len(benchmark_returns) < 2:
            return 1.0

        # Ensure same length
        min_len = min(len(portfolio_returns), len(benchmark_returns))
        portfolio_returns = portfolio_returns[:min_len]
        benchmark_returns = benchmark_returns[:min_len]

        # Calculate means
        port_mean = sum(portfolio_returns) / len(portfolio_returns)
        bench_mean = sum(benchmark_returns) / len(benchmark_returns)

        # Calculate covariance and variance (unbiased, ddof=1, consistent with Sharpe/Volatility)
        n = len(portfolio_returns)
        covariance = sum((p - port_mean) * (b - bench_mean) for p, b in zip(portfolio_returns, benchmark_returns)) / (
            n - 1
        )

        bench_variance = sum((b - bench_mean) ** 2 for b in benchmark_returns) / (n - 1)

        if bench_variance == 0:
            return 1.0

        beta = covariance / bench_variance
        return round(beta, 2)

    async def calculate_alpha(
        self,
        portfolio_return: float,
        benchmark_return: float,
        beta: float,
        risk_free_rate: float = 0.02,
    ) -> float:
        """
        Calculate Alpha - excess return compared to benchmark.
        Alpha > 0: Outperforming the benchmark
        Alpha < 0: Underperforming the benchmark
        """
        # Jensen's Alpha = Portfolio Return - [Risk Free Rate + Beta * (Benchmark Return - Risk Free Rate)]
        expected_return = risk_free_rate + beta * (benchmark_return - risk_free_rate)
        alpha = portfolio_return - expected_return
        return round(alpha * 100, 2)  # Return as percentage

    def calculate_hhi(self, allocations: List[Dict]) -> Dict:
        """
        Calculate Herfindahl-Hirschman Index (HHI) for portfolio concentration.
        HHI ranges from 0 to 10000:
        - < 1500: Diversified
        - 1500-2500: Moderate concentration
        - > 2500: High concentration
        """
        if not allocations:
            return {
                "hhi": 0,
                "interpretation": "N/A",
                "is_concentrated": False,
                "top_concentration": None,
            }

        # Calculate HHI (sum of squared market shares)
        total_value = sum(a.get("value", 0) or a.get("current_value", 0) for a in allocations)
        if total_value == 0:
            return {
                "hhi": 0,
                "interpretation": "N/A",
                "is_concentrated": False,
                "top_concentration": None,
            }

        hhi = 0
        max_concentration = 0
        top_asset = None

        for a in allocations:
            value = a.get("value", 0) or a.get("current_value", 0)
            share = (value / total_value) * 100
            hhi += share**2

            if share > max_concentration:
                max_concentration = share
                top_asset = a.get("symbol", "Unknown")

        hhi = round(hhi, 0)

        # Interpretation
        if hhi < 1500:
            interpretation = "Bien diversifié"
            is_concentrated = False
        elif hhi < 2500:
            interpretation = "Concentration modérée"
            is_concentrated = False
        else:
            interpretation = "Forte concentration"
            is_concentrated = True

        return {
            "hhi": hhi,
            "interpretation": interpretation,
            "is_concentrated": is_concentrated,
            "top_asset": top_asset,
            "top_concentration": round(max_concentration, 1),
        }

    def calculate_stress_test(self, current_value: float, allocations: List[Dict], scenario_drop: float = 0.20) -> Dict:
        """
        Calculate portfolio value under stress scenario.
        Default scenario: 20% market drop.
        """
        if current_value == 0:
            return {
                "scenario_name": f"Correction -{int(scenario_drop * 100)}%",
                "current_value": 0,
                "stressed_value": 0,
                "potential_loss": 0,
                "potential_loss_percent": scenario_drop * 100,
            }

        # Simple stress test: apply uniform drop
        # More sophisticated: apply different drops per asset class
        stressed_value = current_value * (1 - scenario_drop)
        potential_loss = current_value - stressed_value

        return {
            "scenario_name": f"Correction -{int(scenario_drop * 100)}%",
            "current_value": round(current_value, 2),
            "stressed_value": round(stressed_value, 2),
            "potential_loss": round(potential_loss, 2),
            "potential_loss_percent": round(scenario_drop * 100, 1),
        }

    async def get_all_risk_metrics(
        self,
        db: AsyncSession,
        user_id: str,
        current_value: float,
        allocations: List[Dict],
        days: int = 30,
        history: Optional[List[Dict]] = None,
        roi_annualized: Optional[float] = None,
    ) -> Dict:
        """Get all risk metrics in one call (builds price series once)."""
        # Build portfolio value series once and share across all metric functions
        if history is None:
            history = await self.build_portfolio_value_series(db, user_id, days)
        volatility = await self.calculate_volatility(db, user_id, days, history=history)
        sharpe = await self.calculate_sharpe_ratio(db, user_id, days, history=history, roi_annualized=roi_annualized)
        mdd = await self.calculate_max_drawdown(db, user_id, days, history=history)
        var = await self.calculate_var(db, user_id, days, 0.95, current_value, history=history)
        hhi = self.calculate_hhi(allocations)
        stress_20 = self.calculate_stress_test(current_value, allocations, 0.20)
        stress_40 = self.calculate_stress_test(current_value, allocations, 0.40)

        return {
            "volatility": volatility,
            "sharpe_ratio": sharpe,
            "max_drawdown": mdd,
            "var_95": var,
            "concentration": hhi,
            "stress_test_20": stress_20,
            "stress_test_40": stress_40,
        }


# Singleton instance
snapshot_service = SnapshotService()
