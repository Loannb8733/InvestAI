"""Portfolio snapshot service for historical value tracking."""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional
import math

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.portfolio import Portfolio
from app.models.portfolio_snapshot import PortfolioSnapshot
from app.models.asset import Asset
from app.models.transaction import Transaction, TransactionType
from app.services.metrics_service import metrics_service


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
            tx_date = tx.executed_at.strftime("%Y-%m-%d")
            tx_type = tx.transaction_type
            quantity = Decimal(str(tx.quantity))
            price = Decimal(str(tx.price))
            fee = Decimal(str(tx.fee or 0))
            tx_amount = quantity * price

            # Invested: Only count money going IN (never decreases)
            if tx_type in [TransactionType.BUY]:
                cumulative += tx_amount + fee
                cumulative_net += tx_amount + fee
            elif tx_type in [TransactionType.TRANSFER_IN]:
                cumulative += tx_amount
                cumulative_net += tx_amount
            # Net capital decreases on sells
            elif tx_type in [TransactionType.SELL, TransactionType.TRANSFER_OUT]:
                cumulative_net -= tx_amount

            if cumulative_net < 0:
                cumulative_net = Decimal("0")

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
        today = datetime.utcnow()

        # Get invested timeline from transactions
        invested_timeline, net_capital_timeline = await self._get_invested_timeline(db, user_id, portfolio_id)

        if portfolio_id:
            # Get snapshots for a specific portfolio
            query = select(PortfolioSnapshot).where(
                and_(
                    PortfolioSnapshot.user_id == user_id,
                    PortfolioSnapshot.snapshot_date >= start_date,
                    PortfolioSnapshot.portfolio_id == portfolio_id,
                )
            ).order_by(PortfolioSnapshot.snapshot_date.asc())

            result = await db.execute(query)
            snapshots = result.scalars().all()
        else:
            # First try to get global snapshots (portfolio_id IS NULL)
            query = select(PortfolioSnapshot).where(
                and_(
                    PortfolioSnapshot.user_id == user_id,
                    PortfolioSnapshot.snapshot_date >= start_date,
                    PortfolioSnapshot.portfolio_id.is_(None),
                )
            ).order_by(PortfolioSnapshot.snapshot_date.asc())

            result = await db.execute(query)
            snapshots = result.scalars().all()

            # If no global snapshots, aggregate from per-portfolio snapshots
            if not snapshots:
                agg_query = select(
                    func.date(PortfolioSnapshot.snapshot_date).label("date"),
                    func.sum(PortfolioSnapshot.total_value).label("total_value"),
                    func.sum(PortfolioSnapshot.total_invested).label("total_invested"),
                    func.sum(PortfolioSnapshot.total_gain_loss).label("total_gain_loss"),
                    func.max(PortfolioSnapshot.snapshot_date).label("snapshot_date"),
                ).where(
                    and_(
                        PortfolioSnapshot.user_id == user_id,
                        PortfolioSnapshot.snapshot_date >= start_date,
                        PortfolioSnapshot.portfolio_id.isnot(None),
                    )
                ).group_by(
                    func.date(PortfolioSnapshot.snapshot_date)
                ).order_by(
                    func.date(PortfolioSnapshot.snapshot_date).asc()
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

                        formatted_data.append({
                            "date": self._format_date_for_period(row.snapshot_date, days),
                            "full_date": row.snapshot_date.isoformat(),
                            "value": value,
                            "invested": invested,
                            "net_capital": net_cap,
                            "gain_loss": value - net_cap,
                        })

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

                formatted_data.append({
                    "date": self._format_date_for_period(s.snapshot_date, days),
                    "full_date": s.snapshot_date.isoformat(),
                    "value": value,
                    "invested": invested,
                    "net_capital": net_cap,
                    "gain_loss": value - net_cap,
                })

        return formatted_data

    def _format_date_for_period(self, date: datetime, days: int) -> str:
        """Format date label based on the period length."""
        if days <= 7:
            # Short period: show day name + date (Lun 23)
            day_names = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']
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
        else:
            return 7  # Every week for year view

    async def generate_historical_from_transactions(
        self,
        db: AsyncSession,
        user_id: str,
        days: int = 30,
    ) -> List[Dict]:
        """
        Generate historical data combining:
        - Invested curve from transactions (actual buys/sells)
        - Value curve from snapshots (actual portfolio values)
        """
        # Get current metrics
        current_metrics = await metrics_service.get_user_dashboard_metrics(db, user_id)
        current_value = current_metrics["total_value"]
        current_invested = current_metrics["total_invested"]

        if current_value == 0 and current_invested == 0:
            return []

        today = datetime.utcnow()
        start_date = today - timedelta(days=days)

        # Get all user's portfolios
        portfolios_result = await db.execute(
            select(Portfolio.id).where(
                Portfolio.user_id == user_id,
            )
        )
        portfolio_ids = [str(p[0]) for p in portfolios_result.all()]

        if not portfolio_ids:
            return []

        # === 1. Build INVESTED curve from transactions ===
        transactions_query = (
            select(
                Transaction.executed_at,
                Transaction.transaction_type,
                Transaction.quantity,
                Transaction.price,
                Transaction.fee,
            )
            .join(Asset, Transaction.asset_id == Asset.id)
            .where(Asset.portfolio_id.in_(portfolio_ids))
            .order_by(Transaction.executed_at.asc())
        )

        result = await db.execute(transactions_query)
        transactions = result.all()

        # Build cumulative invested by date
        # "Invested" = total money put IN (only increases, never decreases)
        cumulative_invested = Decimal("0")
        invested_by_date: Dict[str, float] = {}

        # Net capital = money injected - money withdrawn (actual cash still in play)
        cumulative_net_capital = Decimal("0")
        net_capital_by_date: Dict[str, float] = {}

        # Also track "position value" which changes with buys AND sells
        # This represents the cost basis of currently held assets
        cumulative_position = Decimal("0")
        position_by_date: Dict[str, float] = {}

        for tx in transactions:
            tx_type = tx.transaction_type
            quantity = Decimal(str(tx.quantity))
            price = Decimal(str(tx.price))
            fee = Decimal(str(tx.fee or 0))
            tx_amount = quantity * price

            # Invested: Only count money going IN (never decreases)
            if tx_type in [TransactionType.BUY]:
                cumulative_invested += tx_amount + fee
                cumulative_net_capital += tx_amount + fee
            elif tx_type in [TransactionType.TRANSFER_IN]:
                cumulative_invested += tx_amount
                cumulative_net_capital += tx_amount

            # Net capital decreases on sells
            if tx_type in [TransactionType.SELL, TransactionType.TRANSFER_OUT]:
                cumulative_net_capital -= tx_amount

            # Position: Changes with buys AND sells (reflects actual holdings)
            if tx_type in [TransactionType.BUY, TransactionType.TRANSFER_IN]:
                cumulative_position += tx_amount
            elif tx_type in [TransactionType.SELL, TransactionType.TRANSFER_OUT]:
                cumulative_position -= tx_amount
            elif tx_type == TransactionType.CONVERSION_OUT:
                cumulative_position -= tx_amount
            elif tx_type == TransactionType.CONVERSION_IN:
                cumulative_position += tx_amount

            # Ensure position doesn't go negative
            if cumulative_position < 0:
                cumulative_position = Decimal("0")
            if cumulative_net_capital < 0:
                cumulative_net_capital = Decimal("0")

            date_str = tx.executed_at.strftime("%Y-%m-%d")
            invested_by_date[date_str] = float(cumulative_invested)
            net_capital_by_date[date_str] = float(cumulative_net_capital)
            position_by_date[date_str] = float(cumulative_position)

        # === 2. Get VALUE curve from snapshots ===
        snapshots_query = select(
            PortfolioSnapshot.snapshot_date,
            PortfolioSnapshot.total_value,
        ).where(
            and_(
                PortfolioSnapshot.user_id == user_id,
                PortfolioSnapshot.portfolio_id.is_(None),  # Global snapshots
            )
        ).order_by(PortfolioSnapshot.snapshot_date.asc())

        result = await db.execute(snapshots_query)
        snapshots = result.all()

        # Build value by date (keep last snapshot of each day)
        value_by_date: Dict[str, float] = {}
        for snap in snapshots:
            date_str = snap.snapshot_date.strftime("%Y-%m-%d")
            value_by_date[date_str] = float(snap.total_value)

        # === 3. Merge into unified timeline ===
        # Collect all dates with transactions (buys/sells) or snapshots
        all_dates = set(invested_by_date.keys()) | set(net_capital_by_date.keys()) | set(position_by_date.keys()) | set(value_by_date.keys())
        all_dates = {d for d in all_dates if d >= start_date.strftime("%Y-%m-%d")}

        if not all_dates and not transactions:
            return self._generate_flat_history(today, days, current_value, current_invested)

        # Get last known invested/net_capital before period
        last_invested = 0.0
        last_net_capital = 0.0
        for date_str in sorted(invested_by_date.keys()):
            if date_str < start_date.strftime("%Y-%m-%d"):
                last_invested = invested_by_date[date_str]
            else:
                break
        for date_str in sorted(net_capital_by_date.keys()):
            if date_str < start_date.strftime("%Y-%m-%d"):
                last_net_capital = net_capital_by_date[date_str]
            else:
                break

        # Add today's value to value_by_date for interpolation
        today_str = today.strftime("%Y-%m-%d")
        value_by_date[today_str] = current_value

        # Get sorted list of dates with known values for interpolation
        known_value_dates = sorted(value_by_date.keys())

        # Calculate performance ratio (value vs position cost basis)
        current_position = position_by_date.get(max(position_by_date.keys()), float(current_invested)) if position_by_date else float(current_invested)
        current_perf_ratio = current_value / current_position if current_position > 0 else 1.0

        # Get first known snapshot's performance ratio for backward extrapolation
        first_snapshot_ratio = current_perf_ratio
        if known_value_dates:
            first_date = known_value_dates[0]
            first_value = value_by_date[first_date]
            # Find position at that date
            first_position = 0.0
            for d in sorted(position_by_date.keys()):
                if d <= first_date:
                    first_position = position_by_date[d]
            if first_position > 0:
                first_snapshot_ratio = first_value / first_position

        def get_position_at_date(date_str: str) -> float:
            """Get position value at a given date."""
            pos = 0.0
            for d in sorted(position_by_date.keys()):
                if d <= date_str:
                    pos = position_by_date[d]
                else:
                    break
            return pos

        def interpolate_value(date_str: str, position: float) -> float:
            """Interpolate value between known snapshot points."""
            if date_str in value_by_date:
                return value_by_date[date_str]

            # Find surrounding known dates
            before_date = None
            after_date = None
            for kd in known_value_dates:
                if kd <= date_str:
                    before_date = kd
                elif after_date is None:
                    after_date = kd
                    break

            # If we have both before and after, interpolate
            if before_date and after_date:
                before_val = value_by_date[before_date]
                after_val = value_by_date[after_date]

                d1 = datetime.strptime(before_date, "%Y-%m-%d")
                d2 = datetime.strptime(after_date, "%Y-%m-%d")
                d = datetime.strptime(date_str, "%Y-%m-%d")

                total_days = (d2 - d1).days
                elapsed_days = (d - d1).days

                if total_days > 0:
                    ratio = elapsed_days / total_days
                    return before_val + (after_val - before_val) * ratio

            # If only after date known, use first snapshot's ratio with position
            if after_date and not before_date:
                return position * first_snapshot_ratio

            # If only before, use current ratio with position
            if before_date:
                return position * current_perf_ratio

            # No known values, use first snapshot ratio with position
            return position * first_snapshot_ratio

        # Build data points
        data = []

        # Get starting position
        start_position = get_position_at_date(start_date.strftime("%Y-%m-%d"))

        # Add start point
        start_value = interpolate_value(start_date.strftime("%Y-%m-%d"), start_position)
        data.append({
            "date": self._format_date_for_period(start_date, days),
            "full_date": start_date.isoformat(),
            "value": round(start_value, 2),
            "invested": round(last_invested, 2),
            "net_capital": round(last_net_capital, 2),
            "gain_loss": round(start_value - last_net_capital, 2),
        })

        # Add points for each date with data
        for date_str in sorted(all_dates):
            dt = datetime.strptime(date_str, "%Y-%m-%d")

            # Get invested (use last known if no transaction that day)
            if date_str in invested_by_date:
                last_invested = invested_by_date[date_str]
            invested = last_invested

            # Get net capital (use last known if no transaction that day)
            if date_str in net_capital_by_date:
                last_net_capital = net_capital_by_date[date_str]
            net_cap = last_net_capital

            # Get position at this date (changes with buys AND sells)
            position = get_position_at_date(date_str)

            # Interpolate value based on position
            value = interpolate_value(date_str, position)

            data.append({
                "date": self._format_date_for_period(dt, days),
                "full_date": dt.isoformat(),
                "value": round(value, 2),
                "invested": round(invested, 2),
                "net_capital": round(net_cap, 2),
                "gain_loss": round(value - net_cap, 2),
            })

        # Compute current net capital
        current_net_capital = float(current_invested)
        if net_capital_by_date:
            last_nc_date = max(net_capital_by_date.keys())
            current_net_capital = net_capital_by_date[last_nc_date]

        # Add today's point with actual current values
        data.append({
            "date": self._format_date_for_period(today, days),
            "full_date": today.isoformat(),
            "value": round(current_value, 2),
            "invested": round(float(current_invested), 2),
            "net_capital": round(current_net_capital, 2),
            "gain_loss": round(current_value - current_net_capital, 2),
        })

        # Remove duplicates based on date, keeping the last one
        seen_dates = {}
        for point in data:
            date_key = point["full_date"][:10]
            seen_dates[date_key] = point

        data = sorted(seen_dates.values(), key=lambda x: x["full_date"])

        return data

    def _generate_flat_history(
        self, today: datetime, days: int, value: float, invested: float
    ) -> List[Dict]:
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

    async def calculate_volatility(
        self, db: AsyncSession, user_id: str, days: int = 30
    ) -> float:
        """Calculate portfolio volatility based on historical returns."""
        history = await self.get_historical_values(db, user_id, days)

        if len(history) < 2:
            return 0.0

        # Calculate daily returns
        returns = []
        for i in range(1, len(history)):
            prev_value = history[i - 1]["value"]
            curr_value = history[i]["value"]
            if prev_value > 0:
                daily_return = (curr_value - prev_value) / prev_value
                returns.append(daily_return)

        if not returns:
            return 0.0

        # Calculate standard deviation of returns
        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        volatility = math.sqrt(variance) * math.sqrt(252) * 100  # Annualized

        return round(volatility, 2)

    async def calculate_sharpe_ratio(
        self,
        db: AsyncSession,
        user_id: str,
        days: int = 30,
        risk_free_rate: float = 0.02,
    ) -> float:
        """Calculate Sharpe ratio for the portfolio."""
        history = await self.get_historical_values(db, user_id, days)

        if len(history) < 2:
            return 0.0

        # Calculate returns
        returns = []
        for i in range(1, len(history)):
            prev_value = history[i - 1]["value"]
            curr_value = history[i]["value"]
            if prev_value > 0:
                daily_return = (curr_value - prev_value) / prev_value
                returns.append(daily_return)

        if not returns:
            return 0.0

        # Annualized return
        mean_return = sum(returns) / len(returns)
        annualized_return = mean_return * 252

        # Volatility
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        volatility = math.sqrt(variance) * math.sqrt(252)

        if volatility == 0:
            return 0.0

        sharpe = (annualized_return - risk_free_rate) / volatility
        return round(sharpe, 2)

    async def calculate_max_drawdown(
        self, db: AsyncSession, user_id: str, days: int = 30
    ) -> Dict:
        """
        Calculate Maximum Drawdown (MDD) - the largest peak-to-trough decline.
        Returns both the percentage and the period.
        """
        history = await self.get_historical_values(db, user_id, days)

        if len(history) < 2:
            return {"max_drawdown_percent": 0.0, "peak_date": None, "trough_date": None}

        values = [h["value"] for h in history]
        dates = [h.get("full_date", h["date"]) for h in history]

        max_drawdown = 0.0
        peak_value = values[0]
        peak_idx = 0
        trough_idx = 0
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
    ) -> Dict:
        """
        Calculate Value at Risk (VaR) using historical simulation method.
        Returns the potential loss at the given confidence level.
        """
        history = await self.get_historical_values(db, user_id, days)

        if len(history) < 5:
            return {"var_percent": 0.0, "var_amount": 0.0, "confidence_level": confidence_level}

        # Calculate daily returns
        returns = []
        for i in range(1, len(history)):
            prev_value = history[i - 1]["value"]
            curr_value = history[i]["value"]
            if prev_value > 0:
                daily_return = (curr_value - prev_value) / prev_value
                returns.append(daily_return)

        if not returns:
            return {"var_percent": 0.0, "var_amount": 0.0, "confidence_level": confidence_level}

        # Sort returns and find the percentile
        sorted_returns = sorted(returns)
        var_index = int((1 - confidence_level) * len(sorted_returns))
        var_percent = abs(sorted_returns[var_index]) * 100 if var_index < len(sorted_returns) else 0

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

        # Calculate covariance and variance
        covariance = sum(
            (p - port_mean) * (b - bench_mean)
            for p, b in zip(portfolio_returns, benchmark_returns)
        ) / len(portfolio_returns)

        bench_variance = sum(
            (b - bench_mean) ** 2 for b in benchmark_returns
        ) / len(benchmark_returns)

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
            hhi += share ** 2

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

    def calculate_stress_test(
        self, current_value: float, allocations: List[Dict], scenario_drop: float = 0.20
    ) -> Dict:
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
    ) -> Dict:
        """Get all risk metrics in one call."""
        volatility = await self.calculate_volatility(db, user_id, days)
        sharpe = await self.calculate_sharpe_ratio(db, user_id, days)
        mdd = await self.calculate_max_drawdown(db, user_id, days)
        var = await self.calculate_var(db, user_id, days, 0.95, current_value)
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
