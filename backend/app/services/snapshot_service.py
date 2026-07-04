"""Portfolio snapshot service for historical value tracking."""

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset
from app.models.portfolio import Portfolio
from app.models.portfolio_snapshot import PortfolioSnapshot
from app.models.transaction import Transaction, TransactionType
from app.services.asset_classification import STABLECOIN_PEGS, STABLECOIN_SYMBOLS
from app.services.metrics_service import metrics_service
from app.services.snapshot_risk import SnapshotRiskMixin

logger = logging.getLogger(__name__)

# Replay ordering for same-day transactions: apply IN/BUY before OUT/SELL so a
# same-timestamp OUT cannot clamp holdings to 0 before its matching IN (2b).
# Python's sort is stable, so executed_at order is preserved within each group.
_TX_REPLAY_ORDER: Dict[TransactionType, int] = {
    TransactionType.SELL: 1,
    TransactionType.TRANSFER_OUT: 1,
    TransactionType.CONVERSION_OUT: 1,
}

# In-memory price cache: {(symbol, days): (timestamp, {date_str: price})}
_price_cache: Dict[Tuple[str, int], Tuple[float, Dict[str, float]]] = {}
_PRICE_CACHE_TTL = 1800  # 30 minutes — historical daily prices don't change
_MAX_PRICE_CACHE = 500  # max entries before eviction

# In-memory cache for full portfolio value series: {(user_id, days): (timestamp, result)}
_series_cache: Dict[Tuple[str, int], Tuple[float, List[Dict]]] = {}
_SERIES_CACHE_TTL = 120  # 2 minutes — caches the entire computed series
_MAX_SERIES_CACHE = 200  # max entries before eviction

# Single-flight guard: the in-flight recompute future per (user_id, days). When
# several requests miss the series cache at once (cold start / TTL expiry), only
# the first replays the history + fetches prices; the rest await that same result
# instead of stampeding the DB and price APIs.
_series_inflight: Dict[Tuple, "asyncio.Future"] = {}


def _cache_put(cache: dict, key, value, max_size: int) -> None:
    """Insert into a bounded cache, evicting oldest entries if full."""
    if len(cache) >= max_size:
        # Evict oldest 25% by timestamp (first element of value tuple)
        evict_count = max(1, max_size // 4)
        sorted_keys = sorted(cache, key=lambda k: cache[k][0])
        for k in sorted_keys[:evict_count]:
            del cache[k]
    cache[key] = value


class SnapshotService(SnapshotRiskMixin):
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
            snapshot_date=datetime.now(timezone.utc),
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
        """Create today's global snapshot iff one doesn't exist yet.

        The existence check is a fast happy path; the partial UNIQUE index
        ``uq_portfolio_snapshots_user_day_global`` (migration n5i6j7k8l9m0)
        enforces the actual at-most-one-per-day invariant. The earlier
        check-then-insert was a true TOCTOU — two concurrent callers (cron +
        manual refresh) both saw 0 and both inserted. We now catch the
        IntegrityError that the constraint raises in the race window.
        """
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
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
        try:
            return await self.create_user_snapshot(db, user_id, currency)
        except IntegrityError:
            # Race against a concurrent creator — the partial UNIQUE prevented
            # the duplicate, treat it as "already exists".
            await db.rollback()
            return None

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
                Transaction.conversion_rate,
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
            # price is in the transaction currency; convert to the portfolio currency
            # via the FX rate captured at execution (defaults to 1 for same-currency
            # trades). Mirrors metrics_service so the invested/net-capital timeline
            # matches the headline metrics for non-EUR trades.
            rate = getattr(tx, "conversion_rate", None)
            fx = Decimal(str(rate)) if rate else Decimal("1")
            tx_amount = quantity * price * fx

            # Invested: Only count money going IN with a real price (never decreases)
            # Fees are tracked separately in total_fees, not included in invested
            if tx_type in [TransactionType.BUY]:
                cumulative += tx_amount
                cumulative_net += tx_amount
            elif tx_type in [TransactionType.TRANSFER_IN] and price > 0:
                cumulative += tx_amount
                cumulative_net += tx_amount
            # Net capital decreases on real sells only (cash leaves to fiat/stable).
            # TRANSFER_OUT = moving to a cold wallet (user still owns it) → unchanged.
            elif tx_type in [TransactionType.SELL]:
                cumulative_net -= tx_amount
            # CONVERSION_IN / CONVERSION_OUT are net_capital-NEUTRAL: a crypto→crypto
            # form change conserves invested capital. (Bug fix: CONVERSION_OUT used to
            # subtract the real OUT value while CONVERSION_IN added nothing — price=0
            # from the sync — so every swap wrongly drained net_capital.)

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
        start_date = datetime.now(timezone.utc) - timedelta(days=days)
        datetime.now(timezone.utc)

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

        from app.models.asset import AssetType

        query = (
            select(
                Transaction.executed_at,
                Transaction.transaction_type,
                Transaction.quantity,
                Transaction.price,
                Transaction.fee,
                Transaction.currency,
                Transaction.conversion_rate,
                Asset.symbol,
                Asset.asset_type,
                Transaction.created_at,
            )
            .join(Asset, Transaction.asset_id == Asset.id)
            .where(
                Asset.portfolio_id.in_(portfolio_ids),
                # Exclude CROWDFUNDING — managed via dedicated endpoints
                Asset.asset_type != AssetType.CROWDFUNDING,
            )
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

            # Apply transactions for this day. Process IN/BUY before OUT/SELL on the
            # same day (stable sort preserves executed_at order within each group) so
            # a same-timestamp OUT can't clamp holdings to 0 before its matching IN.
            if date_str in tx_by_date:
                day_txs = sorted(tx_by_date[date_str], key=lambda t: _TX_REPLAY_ORDER.get(t.transaction_type, 0))
                for tx in day_txs:
                    symbol = tx.symbol.upper()
                    quantity = float(tx.quantity)
                    price = float(tx.price)
                    tx_type = tx.transaction_type
                    # Convert tx-currency price to portfolio currency (EUR) via the
                    # captured FX rate (defaults to 1 for same-currency trades).
                    rate = getattr(tx, "conversion_rate", None)
                    fx = float(rate) if rate else 1.0
                    tx_amount = quantity * price * fx

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
                        # Form change: holdings move, net_capital stays NEUTRAL.
                    elif tx_type == TransactionType.CONVERSION_IN:
                        holdings[symbol] = holdings.get(symbol, 0.0) + quantity
                        # Form change: holdings move, net_capital stays NEUTRAL.
                        # (Bug fix: previously += tx_amount, but sync CONVERSION_IN
                        # has price=0 so it added nothing while CONVERSION_OUT
                        # subtracted the real value → swaps drained net_capital.)

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

        # Stablecoins carry no price history; they're valued at their peg in the
        # value series (USD-pegged -> live USD/EUR rate, EUR-pegged -> ~1 EUR).
        STABLECOINS = STABLECOIN_SYMBOLS

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

        # 2. Check PostgreSQL first (persistent, complete after backfill).
        # One batched query (WHERE symbol IN ...) instead of one SELECT per symbol.
        symbols_need_redis: Dict[str, str] = {}
        if db is not None:
            cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days + 5)).date()
            non_stable: Dict[str, str] = {}
            for symbol_upper, asset_type in symbols_to_fetch.items():
                if symbol_upper in STABLECOINS:
                    price_series[symbol_upper] = {}
                else:
                    non_stable[symbol_upper] = asset_type

            rows_by_symbol: Dict[str, Dict[str, float]] = {}
            if non_stable:
                try:
                    result = await db.execute(
                        select(
                            AssetPriceHistory.symbol,
                            AssetPriceHistory.price_date,
                            AssetPriceHistory.price_eur,
                        )
                        .where(
                            AssetPriceHistory.symbol.in_(list(non_stable)),
                            AssetPriceHistory.price_date >= cutoff_date,
                        )
                        .order_by(AssetPriceHistory.symbol, AssetPriceHistory.price_date)
                    )
                    for sym, pdate, peur in result.all():
                        rows_by_symbol.setdefault(sym, {})[pdate.strftime("%Y-%m-%d")] = float(peur)
                except Exception as e:
                    logger.warning("Batched DB price lookup failed: %s", e)

            for symbol_upper, asset_type in non_stable.items():
                series = rows_by_symbol.get(symbol_upper)
                if series:
                    price_series[symbol_upper] = series
                    _cache_put(
                        _price_cache,
                        (symbol_upper, days),
                        (time.time(), series),
                        _MAX_PRICE_CACHE,
                    )
                else:
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
                _cache_put(
                    _price_cache,
                    (symbol_upper, days),
                    (time.time(), series),
                    _MAX_PRICE_CACHE,
                )
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
                    result = await fetcher.get_history(sym, at, days, fast=True)
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
                    _cache_put(
                        _price_cache,
                        (symbol_upper, days),
                        (time.time(), series),
                        _MAX_PRICE_CACHE,
                    )
                    # Persist to PostgreSQL for future requests
                    try:
                        await _persist_prices_to_db(symbol_upper, dates, prices)
                    except Exception as exc:
                        logger.debug("Failed to persist prices to DB for %s: %s", symbol_upper, exc)
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
                except Exception as exc:
                    logger.debug("Failed to schedule deep backfill for %s: %s", symbol_upper, exc)
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
        """Cached, single-flight daily portfolio value series.

        The 2-minute series cache is fronted by a per-key single-flight guard so
        concurrent cache misses share one recompute instead of each replaying the
        full transaction history and re-fetching historical prices.
        """
        cache_key = (user_id, days)
        now = time.time()
        if cache_key in _series_cache:
            ts, cached_result = _series_cache[cache_key]
            if now - ts < _SERIES_CACHE_TTL:
                return cached_result

        inflight = _series_inflight.get(cache_key)
        if inflight is not None:
            return await inflight

        fut: "asyncio.Future" = asyncio.get_event_loop().create_future()
        _series_inflight[cache_key] = fut
        try:
            result = await self._compute_portfolio_value_series(db, user_id, days, portfolio_id)
            _cache_put(_series_cache, cache_key, (time.time(), result), _MAX_SERIES_CACHE)
            if not fut.done():
                fut.set_result(result)
            return result
        except BaseException as exc:
            if not fut.done():
                fut.set_exception(exc)
            raise
        finally:
            _series_inflight.pop(cache_key, None)

    async def _compute_portfolio_value_series(
        self,
        db: AsyncSession,
        user_id: str,
        days: int = 30,
        portfolio_id: Optional[str] = None,
    ) -> List[Dict]:
        """Full (uncached) value-series computation. Fronted by build_portfolio_value_series."""
        transactions = await self._get_user_transactions_with_assets(db, user_id, portfolio_id)

        if not transactions:
            return []

        today = datetime.now(timezone.utc)
        today_naive = today.replace(tzinfo=None)  # naive UTC for all Python-side date comparisons
        first_tx_date = transactions[0].executed_at or transactions[0].created_at
        if first_tx_date is None:
            first_tx_date = today_naive

        # Normalize to naive datetimes for comparison (all dates are UTC)
        if hasattr(first_tx_date, "tzinfo") and first_tx_date.tzinfo is not None:
            first_tx_date = first_tx_date.replace(tzinfo=None)

        # Start from the later of: (first transaction, today - days)
        period_start = today_naive - timedelta(days=days)
        # We need to replay from first transaction to get correct holdings
        replay_start = min(first_tx_date, period_start)
        replay_start = replay_start.replace(hour=0, minute=0, second=0, microsecond=0)

        # Build daily holdings
        (
            daily_holdings,
            daily_invested,
            daily_net_capital,
            asset_types,
        ) = self._replay_transactions_to_daily_holdings(transactions, replay_start, today_naive)

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
        days_since_first = (today_naive - replay_start).days + 5  # extra buffer
        fetch_days = min(max(days, days_since_first, 90), 1825)
        price_series = await self._fetch_all_price_series(all_symbols, fetch_days, db=db)

        # Fetch live USD→EUR rate for stablecoin pricing (cold-start fallback).
        try:
            from app.core.finance_constants import COLD_START_USD_EUR
            from app.services.price_service import PriceService

            _ps = PriceService()
            stablecoin_eur_rate = float(await _ps.get_forex_rate("USD", "EUR") or COLD_START_USD_EUR)
        except Exception:
            stablecoin_eur_rate = float(COLD_START_USD_EUR)

        # Fallback: if most symbols have no price data (API down), use DB snapshots
        STABLECOINS = STABLECOIN_SYMBOLS
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
                            (
                                s.snapshot_date.replace(tzinfo=None)
                                if hasattr(s.snapshot_date, "tzinfo") and s.snapshot_date.tzinfo
                                else s.snapshot_date
                            ),
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
                # Stablecoin fallback: EUR-pegged coins are worth ~1 EUR, USD-pegged
                # coins are worth the live USD->EUR rate.
                elif symbol in STABLECOINS:
                    price = 1.0 if STABLECOIN_PEGS.get(symbol) == "EUR" else stablecoin_eur_rate
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

        return result


snapshot_service = SnapshotService()
