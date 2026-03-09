"""Dashboard endpoints."""

import asyncio
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.alert import Alert
from app.models.asset import Asset
from app.models.calendar_event import CalendarEvent
from app.models.portfolio import Portfolio
from app.models.portfolio_snapshot import PortfolioSnapshot
from app.models.transaction import Transaction
from app.models.user import User
from app.services.metrics_service import metrics_service
from app.services.price_service import price_service
from app.services.snapshot_service import snapshot_service

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
    period_change: float = 0.0
    period_change_percent: float = 0.0
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

    # Liquidity
    available_liquidity: float = 0.0

    # Period context
    period_days: int = 30
    period_label: str = "30j"

    # Metadata
    last_updated: str


# ============== Main Endpoint ==============


@router.get("", response_model=EnhancedDashboardResponse)
async def get_dashboard(
    days: int = Query(30, ge=0, le=3650),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EnhancedDashboardResponse:
    """Get enhanced dashboard metrics for the current user.

    days=0 means "all time" (from oldest transaction).
    """
    user_id = str(current_user.id)
    original_days = days  # Preserve for period label before resolution

    # Resolve days=0 ("all time") to actual days since first transaction
    # Cache first_tx_date for reuse in CAGR calculation below
    _first_tx_result = await db.execute(
        select(func.min(Transaction.executed_at))
        .join(Asset, Transaction.asset_id == Asset.id)
        .join(Portfolio, Asset.portfolio_id == Portfolio.id)
        .where(Portfolio.user_id == current_user.id)
    )
    _first_tx_date_cached = _first_tx_result.scalar()
    if _first_tx_date_cached and hasattr(_first_tx_date_cached, "tzinfo") and _first_tx_date_cached.tzinfo is not None:
        _first_tx_date_cached = _first_tx_date_cached.replace(tzinfo=None)

    if days == 0:
        if _first_tx_date_cached:
            days = max((datetime.utcnow() - _first_tx_date_cached).days + 1, 7)
        else:
            days = 30

    # Get basic metrics (period-aware, currency-aware)
    currency = getattr(current_user, "preferred_currency", "EUR") or "EUR"
    metrics = await metrics_service.get_user_dashboard_metrics(db, user_id, currency=currency, days=days)

    # Run historical data (heaviest call) in parallel with index comparison (HTTP only)
    historical_task = snapshot_service.build_portfolio_value_series(db, user_id, days)
    index_task = get_index_comparison(days)
    historical_data, index_comparison = await asyncio.gather(historical_task, index_task)

    # Light DB queries (fast, sequential to avoid session conflicts)
    events_window = min(days, 90) if days > 0 else 90
    recent_transactions = await get_recent_transactions_internal(db, current_user, 5, days=days)
    active_alerts = await get_active_alerts_internal(db, current_user)
    upcoming_events = await get_upcoming_events_internal(db, current_user, events_window)

    # Data quality: check actual coverage vs expected data points.
    data_interval = snapshot_service._get_data_point_interval(days)
    expected_points = max(days // data_interval, 5)
    coverage_ratio = len(historical_data) / expected_points if expected_points > 0 else 1.0
    is_data_estimated = coverage_ratio < 0.3 and days > 7
    for point in historical_data:
        point["is_estimated"] = is_data_estimated

    # Period change calculation:
    # - "Tout" (days=0): true P&L vs total_invested (unified root: Patrimoine - Investi)
    # - Other periods: keep metrics_service weighted average of market price changes
    if original_days == 0:
        total_inv = metrics["total_invested"]
        if total_inv > 0:
            metrics["period_change"] = metrics["total_value"] - total_inv
            metrics["period_change_percent"] = round(((metrics["total_value"] - total_inv) / total_inv) * 100, 2)
        else:
            metrics["period_change"] = 0.0
            metrics["period_change_percent"] = 0.0

    # Build asset-level allocation from pre-aggregated data (no extra DB/API calls)
    asset_allocation = [
        AssetAllocation(
            symbol=a["symbol"],
            name=a.get("name"),
            asset_type=a["asset_type"],
            value=a["current_value"],
            percentage=a["percentage"],
            gain_loss_percent=a["gain_loss_percent"],
            avg_buy_price=a.get("avg_buy_price"),
        )
        for a in metrics.get("aggregated_assets", [])
    ]
    asset_allocation.sort(key=lambda x: x.value, reverse=True)

    # ============== Calculate Advanced Metrics ==============

    # Calculate annualized ROI (CAGR) FIRST — needed by Sharpe ratio
    # total_return = current_value + total_sell_proceeds (all capital recovered via sells)
    cagr_base = metrics["total_invested"]
    net_cap = metrics.get("net_capital", cagr_base)
    total_sold_value = max(0, cagr_base - net_cap)
    total_return = metrics["total_value"] + total_sold_value
    if cagr_base > 0 and total_return > 0:
        if _first_tx_date_cached:
            actual_days = max((datetime.utcnow() - _first_tx_date_cached).days, 30)
        else:
            actual_days = max(days, 30)
        years = actual_days / 365.0
        roi_annualized = (pow(total_return / cagr_base, 1 / years) - 1) * 100
        roi_annualized = max(-95.0, min(roi_annualized, 1000.0))
    else:
        roi_annualized = 0.0

    # Risk metrics — pass roi_annualized so Sharpe uses the real CAGR
    risk_data = await snapshot_service.get_all_risk_metrics(
        db,
        user_id,
        metrics["total_value"],
        [{"symbol": a.symbol, "value": a.value} for a in asset_allocation],
        days,
        history=historical_data,
        roi_annualized=roi_annualized,
    )

    volatility = risk_data["volatility"]
    sharpe_ratio = risk_data["sharpe_ratio"]
    mdd_data = risk_data["max_drawdown"]
    var_data = risk_data["var_95"]

    beta = None
    alpha = None

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
    concentration_data = risk_data["concentration"]
    concentration = ConcentrationMetrics(
        hhi=concentration_data["hhi"],
        interpretation=concentration_data["interpretation"],
        is_concentrated=concentration_data["is_concentrated"],
        top_asset=concentration_data.get("top_asset"),
        top_concentration=concentration_data.get("top_concentration"),
    )

    # Stress tests
    stress_tests = [
        StressTest(**risk_data["stress_test_20"]),
        StressTest(**risk_data["stress_test_40"]),
    ]

    # P&L breakdown (realized vs unrealized) — pre-computed in metrics
    pnl_data = metrics.get("pnl_data", {})
    pnl_breakdown = PnLBreakdown(
        realized_pnl=pnl_data.get("realized_pnl", 0),
        unrealized_pnl=pnl_data.get("unrealized_pnl", 0),
        total_pnl=pnl_data.get("total_pnl", 0),
        total_fees=pnl_data.get("total_fees", 0),
        net_pnl=pnl_data.get("net_pnl", 0),
    )

    advanced_metrics = AdvancedMetrics(
        roi_annualized=round(roi_annualized, 2),
        risk_metrics=risk_metrics,
        concentration=concentration,
        stress_tests=stress_tests,
        pnl_breakdown=pnl_breakdown,
    )

    # Create snapshot for today if we have assets (max 1 per day)
    # Use already-computed metrics to avoid re-fetching prices
    if metrics["assets_count"] > 0:
        try:
            from decimal import Decimal as _Dec

            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            existing = await db.execute(
                select(func.count())
                .select_from(PortfolioSnapshot)
                .where(
                    PortfolioSnapshot.user_id == user_id,
                    PortfolioSnapshot.snapshot_date >= today_start,
                    PortfolioSnapshot.portfolio_id.is_(None),
                )
            )
            if existing.scalar() == 0:
                snap = PortfolioSnapshot(
                    user_id=user_id,
                    portfolio_id=None,
                    snapshot_date=datetime.utcnow(),
                    total_value=_Dec(str(metrics["total_value"])),
                    total_invested=_Dec(str(metrics["total_invested"])),
                    total_gain_loss=_Dec(str(metrics["total_gain_loss"])),
                    currency=currency,
                )
                db.add(snap)
                await db.commit()
        except Exception:
            pass

    from app.core.timeframe import get_period_label_fr

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
        period_change=metrics.get("period_change", 0.0),
        period_change_percent=metrics.get("period_change_percent", 0.0),
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
        available_liquidity=metrics.get("available_liquidity", 0.0),
        period_days=days,
        period_label=get_period_label_fr(original_days),
        last_updated=datetime.utcnow().isoformat(),
    )


# ============== Munitions (Deployment Capacity) ==============


class MunitionsResponse(BaseModel):
    """Munitions / deployment capacity response."""

    available_liquidity: float
    total_value: float
    liquidity_pct: float
    invested_pct: float
    next_signal_symbol: Optional[str] = None
    next_signal_action: Optional[str] = None
    next_signal_amount: float = 0.0
    can_execute: bool = True
    shortfall: float = 0.0
    message: Optional[str] = None
    profile: str = "moderate"
    deploy_to_risk: float = 0.0
    keep_in_reserve: float = 0.0


@router.get("/munitions", response_model=MunitionsResponse)
async def get_munitions(
    monthly_dca: float = Query(300.0, ge=0, description="Monthly DCA budget (€)"),
    profile: str = Query("moderate", description="Investment profile: aggressive/moderate/conservative"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get deployment capacity (munitions) for the current user."""
    from app.services.strategy_service import strategy_service

    capacity = await strategy_service.get_deployment_capacity(
        db=db,
        user_id=str(current_user.id),
        monthly_dca=monthly_dca,
        profile=profile,
    )
    return MunitionsResponse(
        available_liquidity=capacity.available_liquidity,
        total_value=capacity.total_value,
        liquidity_pct=capacity.liquidity_pct,
        invested_pct=capacity.invested_pct,
        next_signal_symbol=capacity.next_signal_symbol,
        next_signal_action=capacity.next_signal_action,
        next_signal_amount=capacity.next_signal_amount,
        can_execute=capacity.can_execute,
        shortfall=capacity.shortfall,
        message=capacity.message,
        profile=capacity.profile,
        deploy_to_risk=capacity.deploy_to_risk,
        keep_in_reserve=capacity.keep_in_reserve,
    )


# ============== Helper Functions ==============


async def get_recent_transactions_internal(
    db: AsyncSession, current_user: User, limit: int = 5, days: int = 0
) -> List[RecentTransaction]:
    """Get recent transactions for dashboard.

    Args:
        days: If > 0, only return transactions within this period.
              If 0, return the most recent transactions regardless of date.
    """
    from app.core.timeframe import get_period_start_date

    portfolio_result = await db.execute(select(Portfolio.id).where(Portfolio.user_id == current_user.id))
    portfolio_ids = [p for p in portfolio_result.scalars().all()]

    if not portfolio_ids:
        return []

    asset_result = await db.execute(select(Asset).where(Asset.portfolio_id.in_(portfolio_ids)))
    assets = asset_result.scalars().all()
    asset_map = {a.id: a for a in assets}
    asset_ids = list(asset_map.keys())

    if not asset_ids:
        return []

    query = (
        select(Transaction)
        .where(Transaction.asset_id.in_(asset_ids))
        .order_by(Transaction.executed_at.desc())
        .limit(limit)
    )
    if days > 0:
        start_date = get_period_start_date(days)
        query = query.where(Transaction.executed_at >= start_date)

    result = await db.execute(query)
    transactions = result.scalars().all()

    result_list = []
    for t in transactions:
        asset = asset_map.get(t.asset_id)
        price = float(t.price)
        # For airdrops/transfers/staking_rewards where price is 0,
        # show 0 as total — don't fake a cost with avg_buy_price
        result_list.append(
            RecentTransaction(
                id=str(t.id),
                symbol=asset.symbol if asset else "N/A",
                asset_type=asset.asset_type.value if asset else "unknown",
                transaction_type=t.transaction_type.value,
                quantity=float(t.quantity),
                price=price,
                total=float(t.quantity) * price,
                executed_at=(t.executed_at or t.created_at or datetime.utcnow()).isoformat(),
            )
        )
    return result_list


async def get_active_alerts_internal(db: AsyncSession, current_user: User) -> List[ActiveAlert]:
    """Get active alerts for dashboard."""
    result = await db.execute(
        select(Alert)
        .where(
            Alert.user_id == current_user.id,
            Alert.is_active == True,
        )
        .limit(5)
    )
    alerts = result.scalars().all()

    # Collect all asset IDs to batch-fetch
    alert_asset_ids = [alert.asset_id for alert in alerts if alert.asset_id]
    asset_map = {}
    if alert_asset_ids:
        asset_result = await db.execute(select(Asset).where(Asset.id.in_(alert_asset_ids)))
        asset_map = {a.id: a for a in asset_result.scalars().all()}

    # Batch-fetch all prices in one API call
    all_symbols = list({a.symbol for a in asset_map.values()})
    price_map = {}
    if all_symbols:
        try:
            price_data = await price_service.get_multiple_crypto_prices(all_symbols)
            price_map = {sym.upper(): d["price"] for sym, d in price_data.items()}
        except Exception:
            pass

    active_alerts = []
    for alert in alerts:
        symbol = None
        current_price = None

        if alert.asset_id and alert.asset_id in asset_map:
            asset = asset_map[alert.asset_id]
            symbol = asset.symbol
            current_price = price_map.get(symbol.upper())

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


async def get_upcoming_events_internal(db: AsyncSession, current_user: User, days: int = 30) -> List[UpcomingEvent]:
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


async def get_index_comparison(days: int = 30) -> List[IndexComparison]:
    """Get comparison with major indices/assets over the selected period."""
    index_symbols = [
        ("BTC", "Bitcoin"),
        ("ETH", "Ethereum"),
        ("SOL", "Solana"),
    ]
    indices = []

    try:
        # Fetch current prices
        all_data = await price_service.get_multiple_crypto_prices([s for s, _ in index_symbols])

        # Fetch period-specific changes
        period_changes = await metrics_service._fetch_period_changes({"crypto": [s for s, _ in index_symbols]}, days)

        for symbol, name in index_symbols:
            if symbol in all_data:
                change = period_changes.get(symbol, all_data[symbol].get("change_percent_24h", 0))
                indices.append(
                    IndexComparison(
                        name=name,
                        symbol=symbol,
                        change_percent=change,
                        price=all_data[symbol]["price"],
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
    portfolio_result = await db.execute(
        select(Portfolio).where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id,
        )
    )
    if not portfolio_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Portfolio not found")

    currency = getattr(current_user, "preferred_currency", "EUR") or "EUR"
    metrics = await metrics_service.get_portfolio_metrics(db, portfolio_id, currency=currency)
    return metrics


@router.get("/portfolio/{portfolio_id}/history")
async def get_portfolio_history(
    portfolio_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get historical investment metrics for a portfolio (including sold assets)."""
    portfolio_result = await db.execute(
        select(Portfolio).where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id,
        )
    )
    if not portfolio_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Portfolio not found")

    currency = getattr(current_user, "preferred_currency", "EUR") or "EUR"
    history = await metrics_service.get_portfolio_history(db, portfolio_id, currency=currency)
    return history


class SparklineData(BaseModel):
    """Sparkline price data for a single symbol."""

    symbol: str
    prices: List[float]
    change_pct: float


@router.get("/portfolio/{portfolio_id}/sparklines", response_model=List[SparklineData])
async def get_portfolio_sparklines(
    portfolio_id: str,
    days: int = Query(30, ge=7, le=90),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[SparklineData]:
    """Get sparkline price data for all assets in a portfolio."""
    from collections import defaultdict

    from app.models.asset_price_history import AssetPriceHistory
    from app.services.metrics_service import is_cash_like

    # Verify ownership
    portfolio_result = await db.execute(
        select(Portfolio).where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id,
        )
    )
    if not portfolio_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Portfolio not found")

    # Get unique non-stablecoin symbols
    assets_result = await db.execute(
        select(Asset.symbol).where(Asset.portfolio_id == portfolio_id, Asset.quantity > 0).distinct()
    )
    symbols = [row[0].upper() for row in assets_result.all() if not is_cash_like(row[0])]
    if not symbols:
        return []

    # Batch fetch from AssetPriceHistory
    cutoff = (datetime.utcnow() - timedelta(days=days)).date()
    result = await db.execute(
        select(
            AssetPriceHistory.symbol,
            AssetPriceHistory.price_date,
            AssetPriceHistory.price_eur,
        )
        .where(
            AssetPriceHistory.symbol.in_(symbols),
            AssetPriceHistory.price_date >= cutoff,
        )
        .order_by(AssetPriceHistory.symbol, AssetPriceHistory.price_date)
    )
    rows = result.all()

    symbol_data: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        symbol_data[row[0]].append(float(row[2]))

    sparklines = []
    for symbol in symbols:
        prices = symbol_data.get(symbol, [])
        if len(prices) < 2:
            continue
        # Normalize to [0, 1] for consistent rendering
        min_p, max_p = min(prices), max(prices)
        range_p = max_p - min_p
        normalized = [(p - min_p) / range_p if range_p > 0 else 0.5 for p in prices]
        change = ((prices[-1] - prices[0]) / prices[0] * 100) if prices[0] > 0 else 0.0

        sparklines.append(
            SparklineData(
                symbol=symbol,
                prices=normalized,
                change_pct=round(change, 2),
            )
        )

    return sparklines


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
    days: int = Query(30, ge=0, le=3650),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[HistoricalDataPoint]:
    """Get historical portfolio values. days=0 means all time."""
    user_id = str(current_user.id)

    # Resolve days=0 to all time
    if days == 0:
        first_tx = await db.execute(
            select(func.min(Transaction.executed_at))
            .join(Asset, Transaction.asset_id == Asset.id)
            .join(Portfolio, Asset.portfolio_id == Portfolio.id)
            .where(Portfolio.user_id == current_user.id)
        )
        first_date = first_tx.scalar()
        if first_date:
            if hasattr(first_date, "tzinfo") and first_date.tzinfo is not None:
                first_date = first_date.replace(tzinfo=None)
            days = max((datetime.utcnow() - first_date).days + 1, 7)
        else:
            days = 30

    # Use real price-based series (transactions + historical market prices)
    historical_data = await snapshot_service.build_portfolio_value_series(db, user_id, days)
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
    days: int = Query(default=90, ge=0, le=3650),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get normalized benchmark data (base 100) for overlay on portfolio chart.

    Returns BTC, SPY, MSCI World + portfolio performance, all normalized.
    """
    from app.core.config import settings
    from app.ml.historical_data import HistoricalDataFetcher

    user_id = current_user.id
    coingecko_key = getattr(settings, "COINGECKO_API_KEY", None) or None
    fetcher = HistoricalDataFetcher(coingecko_api_key=coingecko_key)

    benchmarks = [
        ("Bitcoin", "BTC", "crypto"),
        ("S&P 500", "SPY", "etf"),
        ("MSCI World", "IWDA.AS", "etf"),
    ]

    result = []

    try:
        for name, symbol, asset_type in benchmarks:
            try:
                dates, prices = await fetcher.get_history(symbol, asset_type, days)
                if dates and prices and len(dates) > 1:
                    base = float(prices[0]) if prices[0] != 0 else 1
                    points = []
                    for d, price in zip(dates, prices):
                        date_str = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)
                        points.append(
                            BenchmarkDataPoint(
                                date=date_str,
                                value=round(float(price) / base * 100, 2),
                            )
                        )
                    result.append(BenchmarkSeries(name=name, symbol=symbol, data=points))
            except Exception:
                pass
    finally:
        await fetcher.close()

    # Portfolio performance normalized — use real price-based series
    historical_data = await snapshot_service.build_portfolio_value_series(db, str(user_id), days)
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


# ============== Backfill Endpoints ==============


@router.post("/backfill-prices")
async def trigger_price_backfill(
    current_user: User = Depends(get_current_user),
):
    """Trigger a deep backfill of historical prices for all assets."""
    from app.tasks.history_cache import deep_backfill_prices

    task = deep_backfill_prices.delay()
    return {"status": "started", "task_id": str(task.id)}


@router.get("/backfill-status")
async def get_backfill_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check the status of historical price data coverage."""
    from app.models.asset_price_history import AssetPriceHistory

    # Count total price points in DB
    count_result = await db.execute(select(func.count()).select_from(AssetPriceHistory))
    total_points = count_result.scalar() or 0

    # Count unique symbols with data
    symbols_result = await db.execute(select(func.count(func.distinct(AssetPriceHistory.symbol))))
    symbols_covered = symbols_result.scalar() or 0

    # Count total active symbols
    active_result = await db.execute(select(func.count(func.distinct(Asset.symbol))).where(Asset.quantity > 0))
    total_active = active_result.scalar() or 0

    return {
        "total_price_points": total_points,
        "symbols_covered": symbols_covered,
        "total_active_symbols": total_active,
        "is_complete": total_points > 0 and symbols_covered >= total_active,
    }
