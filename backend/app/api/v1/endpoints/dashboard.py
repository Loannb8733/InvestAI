"""Dashboard endpoints."""

from datetime import datetime, timedelta
from typing import List, Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.models.asset import Asset
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction
from app.models.alert import Alert
from app.models.calendar_event import CalendarEvent
from app.services.metrics_service import metrics_service
from app.services.snapshot_service import snapshot_service
from app.services.price_service import price_service

router = APIRouter()


# ============== Pydantic Models ==============

class HistoricalDataPoint(BaseModel):
    """Historical data point for charts."""
    date: str
    full_date: Optional[str] = None
    value: float
    invested: Optional[float] = None
    net_capital: Optional[float] = None
    gain_loss: Optional[float] = None
    is_estimated: bool = False


class RecentTransaction(BaseModel):
    """Recent transaction for dashboard."""
    id: str
    symbol: str
    asset_type: str
    transaction_type: str
    quantity: float
    price: float
    total: float
    executed_at: str


class ActiveAlert(BaseModel):
    """Active alert summary."""
    id: str
    name: str
    symbol: Optional[str]
    condition: str
    threshold: float
    current_price: Optional[float] = None


class UpcomingEvent(BaseModel):
    """Upcoming calendar event."""
    id: str
    title: str
    event_type: str
    event_date: str
    amount: Optional[float] = None


class AssetAllocation(BaseModel):
    """Individual asset allocation."""
    symbol: str
    name: Optional[str]
    asset_type: str
    value: float
    percentage: float
    gain_loss_percent: float
    avg_buy_price: Optional[float] = None


class IndexComparison(BaseModel):
    """Index comparison data."""
    name: str
    symbol: str
    change_percent: float
    price: float


class MaxDrawdown(BaseModel):
    """Maximum drawdown metrics."""
    max_drawdown_percent: float
    peak_date: Optional[str] = None
    trough_date: Optional[str] = None
    peak_value: Optional[float] = None
    trough_value: Optional[float] = None


class ValueAtRisk(BaseModel):
    """Value at Risk metrics."""
    var_percent: float
    var_amount: float
    confidence_level: float


class ConcentrationMetrics(BaseModel):
    """Portfolio concentration metrics (HHI)."""
    hhi: float
    interpretation: str
    is_concentrated: bool
    top_asset: Optional[str] = None
    top_concentration: Optional[float] = None


class StressTest(BaseModel):
    """Stress test scenario."""
    scenario_name: str
    current_value: float
    stressed_value: float
    potential_loss: float
    potential_loss_percent: float


class PnLBreakdown(BaseModel):
    """P&L breakdown between realized and unrealized."""
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    total_fees: float
    net_pnl: float


class RiskMetrics(BaseModel):
    """All risk-related metrics."""
    volatility: float
    sharpe_ratio: float
    max_drawdown: MaxDrawdown
    var_95: ValueAtRisk
    beta: Optional[float] = None
    alpha: Optional[float] = None


class AdvancedMetrics(BaseModel):
    """Advanced portfolio metrics."""
    roi_annualized: float
    risk_metrics: RiskMetrics
    concentration: ConcentrationMetrics
    stress_tests: List[StressTest]
    pnl_breakdown: PnLBreakdown


class EnhancedDashboardResponse(BaseModel):
    """Enhanced dashboard response with all features."""
    # Basic metrics
    total_value: float
    total_invested: float
    net_capital: float  # total_invested - total_sold (actual cash still in play)
    total_gain_loss: float
    total_gain_loss_percent: float
    net_gain_loss: float  # total_value - net_capital
    net_gain_loss_percent: float
    daily_change: float
    daily_change_percent: float
    portfolios_count: int
    assets_count: int

    # Allocation
    allocation: List[dict]
    asset_allocation: List[AssetAllocation]

    # Performers
    top_performers: List[dict]
    worst_performers: List[dict]

    # Historical data
    historical_data: List[HistoricalDataPoint]
    is_data_estimated: bool

    # Recent transactions
    recent_transactions: List[RecentTransaction]

    # Alerts
    active_alerts: List[ActiveAlert]

    # Calendar
    upcoming_events: List[UpcomingEvent]

    # Index comparison
    index_comparison: List[IndexComparison]

    # Advanced metrics (includes risk, concentration, stress tests, P&L breakdown)
    advanced_metrics: AdvancedMetrics

    # Metadata
    last_updated: str


# ============== Main Endpoint ==============

@router.get("/")
async def get_dashboard(
    days: int = Query(30, ge=7, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EnhancedDashboardResponse:
    """Get enhanced dashboard metrics for the current user."""
    user_id = str(current_user.id)

    # Get basic metrics (period-aware)
    metrics = await metrics_service.get_user_dashboard_metrics(
        db, user_id, days=days
    )

    # Get historical data
    is_data_estimated = False
    historical_data = await snapshot_service.get_historical_values(db, user_id, days)
    if not historical_data:
        # Generate from transactions if no snapshots exist
        historical_data = await snapshot_service.generate_historical_from_transactions(
            db, user_id, days
        )
        is_data_estimated = True

    # Mark data points as estimated
    for point in historical_data:
        point["is_estimated"] = is_data_estimated

    # Calculate period change from historical data
    if historical_data and len(historical_data) >= 2:
        start_value = historical_data[0].get("value", 0)
        end_value = metrics["total_value"]
        if start_value > 0:
            period_change = end_value - start_value
            period_change_percent = (period_change / start_value) * 100
            metrics["daily_change"] = period_change
            metrics["daily_change_percent"] = round(period_change_percent, 2)

    # Get asset-level allocation with avg buy price
    asset_allocation = []
    all_assets_data = []
    if metrics["assets_count"] > 0:
        result = await db.execute(
            select(Portfolio).where(
                Portfolio.user_id == current_user.id,
            )
        )
        portfolios = result.scalars().all()

        for portfolio in portfolios:
            portfolio_metrics = await metrics_service.get_portfolio_metrics(
                db, str(portfolio.id)
            )
            for asset in portfolio_metrics.get("assets", []):
                all_assets_data.append(asset)
                if asset["current_value"] > 0:
                    percentage = (
                        (asset["current_value"] / metrics["total_value"] * 100)
                        if metrics["total_value"] > 0
                        else 0
                    )
                    asset_allocation.append(
                        AssetAllocation(
                            symbol=asset["symbol"],
                            name=asset.get("name"),
                            asset_type=asset["asset_type"],
                            value=asset["current_value"],
                            percentage=round(percentage, 2),
                            gain_loss_percent=asset.get("gain_loss_percent", 0),
                            avg_buy_price=asset.get("avg_buy_price"),
                        )
                    )

        asset_allocation.sort(key=lambda x: x.value, reverse=True)

    # Get recent transactions (last 5)
    recent_transactions = await get_recent_transactions_internal(db, current_user, 5)

    # Get active alerts
    active_alerts = await get_active_alerts_internal(db, current_user)

    # Get upcoming events (next 30 days)
    upcoming_events = await get_upcoming_events_internal(db, current_user, 30)

    # Get index comparison (BTC, ETH, SOL)
    index_comparison = await get_index_comparison()

    # ============== Calculate Advanced Metrics ==============

    # Risk metrics
    volatility = await snapshot_service.calculate_volatility(db, user_id, days)
    sharpe_ratio = await snapshot_service.calculate_sharpe_ratio(db, user_id, days)
    mdd_data = await snapshot_service.calculate_max_drawdown(db, user_id, days)
    var_data = await snapshot_service.calculate_var(
        db, user_id, days, 0.95, metrics["total_value"]
    )

    # Beta and Alpha calculation (vs BTC as benchmark for crypto-heavy portfolios)
    beta = None
    alpha = None
    if historical_data and len(historical_data) > 5:
        # Get BTC historical prices for beta calculation
        # For now, use a default beta of 1.0 - in production would fetch actual BTC prices
        beta = 1.0
        alpha = 0.0

    max_drawdown = MaxDrawdown(
        max_drawdown_percent=mdd_data["max_drawdown_percent"],
        peak_date=mdd_data.get("peak_date"),
        trough_date=mdd_data.get("trough_date"),
        peak_value=mdd_data.get("peak_value"),
        trough_value=mdd_data.get("trough_value"),
    )

    var_95 = ValueAtRisk(
        var_percent=var_data["var_percent"],
        var_amount=var_data["var_amount"],
        confidence_level=var_data["confidence_level"],
    )

    risk_metrics = RiskMetrics(
        volatility=volatility,
        sharpe_ratio=sharpe_ratio,
        max_drawdown=max_drawdown,
        var_95=var_95,
        beta=beta,
        alpha=alpha,
    )

    # Concentration metrics (HHI)
    concentration_data = snapshot_service.calculate_hhi(
        [{"symbol": a.symbol, "value": a.value} for a in asset_allocation]
    )
    concentration = ConcentrationMetrics(
        hhi=concentration_data["hhi"],
        interpretation=concentration_data["interpretation"],
        is_concentrated=concentration_data["is_concentrated"],
        top_asset=concentration_data.get("top_asset"),
        top_concentration=concentration_data.get("top_concentration"),
    )

    # Stress tests
    stress_test_20 = snapshot_service.calculate_stress_test(
        metrics["total_value"], all_assets_data, 0.20
    )
    stress_test_40 = snapshot_service.calculate_stress_test(
        metrics["total_value"], all_assets_data, 0.40
    )
    stress_tests = [
        StressTest(**stress_test_20),
        StressTest(**stress_test_40),
    ]

    # P&L breakdown (realized vs unrealized)
    pnl_data = await metrics_service.calculate_realized_unrealized_pnl(db, user_id)
    pnl_breakdown = PnLBreakdown(
        realized_pnl=pnl_data["realized_pnl"],
        unrealized_pnl=pnl_data["unrealized_pnl"],
        total_pnl=pnl_data["total_pnl"],
        total_fees=pnl_data["total_fees"],
        net_pnl=pnl_data["net_pnl"],
    )

    # Calculate annualized ROI using CAGR formula
    if metrics["total_invested"] > 0 and metrics["total_value"] > 0:
        years = max(days, 30) / 365.0
        roi_annualized = (pow(metrics["total_value"] / metrics["total_invested"], 1 / years) - 1) * 100
    else:
        roi_annualized = 0.0

    advanced_metrics = AdvancedMetrics(
        roi_annualized=round(roi_annualized, 2),
        risk_metrics=risk_metrics,
        concentration=concentration,
        stress_tests=stress_tests,
        pnl_breakdown=pnl_breakdown,
    )

    # Create snapshot for today if we have assets
    if metrics["assets_count"] > 0:
        await snapshot_service.create_user_snapshot(db, user_id)

    return EnhancedDashboardResponse(
        total_value=metrics["total_value"],
        total_invested=metrics["total_invested"],
        net_capital=metrics.get("net_capital", metrics["total_invested"]),
        total_gain_loss=metrics["total_gain_loss"],
        total_gain_loss_percent=metrics["total_gain_loss_percent"],
        net_gain_loss=metrics.get("net_gain_loss", metrics["total_gain_loss"]),
        net_gain_loss_percent=metrics.get("net_gain_loss_percent", metrics["total_gain_loss_percent"]),
        daily_change=metrics["daily_change"],
        daily_change_percent=metrics["daily_change_percent"],
        portfolios_count=metrics["portfolios_count"],
        assets_count=metrics["assets_count"],
        allocation=metrics["allocation"],
        asset_allocation=asset_allocation,
        top_performers=metrics["top_performers"],
        worst_performers=metrics["worst_performers"],
        historical_data=[HistoricalDataPoint(**d) for d in historical_data],
        is_data_estimated=is_data_estimated,
        recent_transactions=recent_transactions,
        active_alerts=active_alerts,
        upcoming_events=upcoming_events,
        index_comparison=index_comparison,
        advanced_metrics=advanced_metrics,
        last_updated=datetime.utcnow().isoformat(),
    )


# ============== Helper Functions ==============

async def get_recent_transactions_internal(
    db: AsyncSession, current_user: User, limit: int = 5
) -> List[RecentTransaction]:
    """Get recent transactions for dashboard."""
    portfolio_result = await db.execute(
        select(Portfolio.id).where(
            Portfolio.user_id == current_user.id
        )
    )
    portfolio_ids = [p for p in portfolio_result.scalars().all()]

    if not portfolio_ids:
        return []

    asset_result = await db.execute(
        select(Asset).where(
            Asset.portfolio_id.in_(portfolio_ids)
        )
    )
    assets = asset_result.scalars().all()
    asset_map = {a.id: a for a in assets}
    asset_ids = list(asset_map.keys())

    if not asset_ids:
        return []

    result = await db.execute(
        select(Transaction)
        .where(Transaction.asset_id.in_(asset_ids))
        .order_by(Transaction.executed_at.desc())
        .limit(limit)
    )
    transactions = result.scalars().all()

    result_list = []
    for t in transactions:
        asset = asset_map.get(t.asset_id)
        price = float(t.price)
        # Fallback to avg_buy_price for transfers/airdrops where price is 0
        if price == 0 and asset:
            price = float(asset.avg_buy_price)
        result_list.append(
            RecentTransaction(
                id=str(t.id),
                symbol=asset.symbol if asset else "N/A",
                asset_type=asset.asset_type.value if asset else "unknown",
                transaction_type=t.transaction_type.value,
                quantity=float(t.quantity),
                price=price,
                total=float(t.quantity) * price,
                executed_at=t.executed_at.isoformat(),
            )
        )
    return result_list


async def get_active_alerts_internal(
    db: AsyncSession, current_user: User
) -> List[ActiveAlert]:
    """Get active alerts for dashboard."""
    result = await db.execute(
        select(Alert).where(
            Alert.user_id == current_user.id,
            Alert.is_active == True,
        ).limit(5)
    )
    alerts = result.scalars().all()

    active_alerts = []
    for alert in alerts:
        symbol = None
        current_price = None

        if alert.asset_id:
            asset_result = await db.execute(
                select(Asset).where(Asset.id == alert.asset_id)
            )
            asset = asset_result.scalar_one_or_none()
            if asset:
                symbol = asset.symbol
                try:
                    prices = await price_service.get_multiple_crypto_prices([symbol])
                    if symbol.upper() in prices:
                        current_price = prices[symbol.upper()]["price"]
                except Exception:
                    pass

        active_alerts.append(
            ActiveAlert(
                id=str(alert.id),
                name=alert.name,
                symbol=symbol,
                condition=alert.condition.value,
                threshold=float(alert.threshold),
                current_price=current_price,
            )
        )

    return active_alerts


async def get_upcoming_events_internal(
    db: AsyncSession, current_user: User, days: int = 30
) -> List[UpcomingEvent]:
    """Get upcoming calendar events for dashboard."""
    now = datetime.utcnow()
    end_date = now + timedelta(days=days)

    result = await db.execute(
        select(CalendarEvent)
        .where(
            CalendarEvent.user_id == current_user.id,
            CalendarEvent.event_date >= now,
            CalendarEvent.event_date <= end_date,
            CalendarEvent.is_completed == False,
        )
        .order_by(CalendarEvent.event_date.asc())
        .limit(5)
    )
    events = result.scalars().all()

    return [
        UpcomingEvent(
            id=str(e.id),
            title=e.title,
            event_type=e.event_type.value,
            event_date=e.event_date.isoformat(),
            amount=float(e.amount) if e.amount else None,
        )
        for e in events
    ]


async def get_index_comparison() -> List[IndexComparison]:
    """Get comparison with major indices/assets."""
    indices = []

    try:
        # Get BTC price and 24h change
        btc_data = await price_service.get_multiple_crypto_prices(["BTC"])
        if "BTC" in btc_data:
            indices.append(
                IndexComparison(
                    name="Bitcoin",
                    symbol="BTC",
                    change_percent=btc_data["BTC"].get("change_24h", 0),
                    price=btc_data["BTC"]["price"],
                )
            )

        # Get ETH price and 24h change
        eth_data = await price_service.get_multiple_crypto_prices(["ETH"])
        if "ETH" in eth_data:
            indices.append(
                IndexComparison(
                    name="Ethereum",
                    symbol="ETH",
                    change_percent=eth_data["ETH"].get("change_24h", 0),
                    price=eth_data["ETH"]["price"],
                )
            )

        # Get SOL price
        sol_data = await price_service.get_multiple_crypto_prices(["SOL"])
        if "SOL" in sol_data:
            indices.append(
                IndexComparison(
                    name="Solana",
                    symbol="SOL",
                    change_percent=sol_data["SOL"].get("change_24h", 0),
                    price=sol_data["SOL"]["price"],
                )
            )

    except Exception:
        pass

    return indices


# ============== Additional Endpoints ==============

@router.get("/portfolio/{portfolio_id}")
async def get_portfolio_dashboard(
    portfolio_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get dashboard metrics for a specific portfolio."""
    metrics = await metrics_service.get_portfolio_metrics(db, portfolio_id)
    return metrics


@router.get("/portfolio/{portfolio_id}/history")
async def get_portfolio_history(
    portfolio_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get historical investment metrics for a portfolio (including sold assets)."""
    history = await metrics_service.get_portfolio_history(db, portfolio_id)
    return history


@router.get("/recent-transactions", response_model=List[RecentTransaction])
async def get_recent_transactions(
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[RecentTransaction]:
    """Get recent transactions."""
    return await get_recent_transactions_internal(db, current_user, limit)


@router.get("/active-alerts", response_model=List[ActiveAlert])
async def get_active_alerts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[ActiveAlert]:
    """Get active alerts."""
    return await get_active_alerts_internal(db, current_user)


@router.get("/upcoming-events", response_model=List[UpcomingEvent])
async def get_upcoming_events(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[UpcomingEvent]:
    """Get upcoming calendar events."""
    return await get_upcoming_events_internal(db, current_user, days)


@router.get("/historical-data", response_model=List[HistoricalDataPoint])
async def get_historical_data(
    days: int = Query(30, ge=7, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[HistoricalDataPoint]:
    """Get historical portfolio values."""
    user_id = str(current_user.id)

    # Always use transaction-based generation for better investment progression visualization
    # This shows actual investment growth over time rather than flat snapshot values
    historical_data = await snapshot_service.generate_historical_from_transactions(
        db, user_id, days
    )
    is_estimated = True

    # If no transaction data, try snapshots as fallback
    if not historical_data:
        historical_data = await snapshot_service.get_historical_values(db, user_id, days)
        is_estimated = False

    for point in historical_data:
        point["is_estimated"] = is_estimated
    return [HistoricalDataPoint(**d) for d in historical_data]


class BenchmarkDataPoint(BaseModel):
    """Benchmark data point (normalized to base 100)."""
    date: str
    value: float


class BenchmarkSeries(BaseModel):
    """A single benchmark series."""
    name: str
    symbol: str
    data: List[BenchmarkDataPoint]


@router.get("/benchmarks", response_model=List[BenchmarkSeries])
async def get_benchmark_data(
    days: int = Query(default=90, ge=7, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get normalized benchmark data (base 100) for overlay on portfolio chart.

    Returns BTC, SPY, MSCI World + portfolio performance, all normalized.
    """
    from app.ml.historical_data import HistoricalDataManager

    user_id = current_user.id
    hist_manager = HistoricalDataManager()

    benchmarks = [
        ("Bitcoin", "BTC", "crypto"),
        ("S&P 500", "SPY", "etf"),
        ("MSCI World", "IWDA.AS", "etf"),
    ]

    result = []

    for name, symbol, asset_type in benchmarks:
        try:
            df = await hist_manager.get_history(symbol, asset_type, days)
            if df is not None and len(df) > 1:
                prices = df["close"].values if "close" in df.columns else df.iloc[:, 0].values
                dates = df.index if hasattr(df.index, 'strftime') else range(len(prices))
                base = float(prices[0]) if prices[0] != 0 else 1
                points = []
                for i, price in enumerate(prices):
                    d = dates[i]
                    date_str = d.strftime("%Y-%m-%d") if hasattr(d, 'strftime') else str(d)
                    points.append(BenchmarkDataPoint(
                        date=date_str,
                        value=round(float(price) / base * 100, 2),
                    ))
                result.append(BenchmarkSeries(name=name, symbol=symbol, data=points))
        except Exception:
            pass

    # Portfolio performance normalized
    historical_data = await snapshot_service.get_historical_values(db, user_id, days)
    if not historical_data:
        historical_data = await snapshot_service.generate_historical_from_transactions(
            db, user_id, days
        )
    if historical_data and len(historical_data) > 1:
        base = historical_data[0].get("value", 1) or 1
        points = [
            BenchmarkDataPoint(
                date=p["date"],
                value=round(p["value"] / base * 100, 2),
            )
            for p in historical_data
        ]
        result.append(BenchmarkSeries(name="Mon portefeuille", symbol="PORTFOLIO", data=points))

    return result
