import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.dashboard.metrics.service import metrics_service
from app.domains.dashboard.snapshots.service import snapshot_service
from app.domains.portfolio.classification import is_safe_haven
from app.domains.portfolio.models import Asset, Portfolio
from app.domains.transactions.models import Transaction

logger = logging.getLogger(__name__)


@dataclass
class PortfolioSummary:
    name: str
    total_value: float
    total_invested: float
    gain_loss: float
    gain_loss_percent: float
    asset_count: int


@dataclass
class AssetReport:
    symbol: str
    name: str
    asset_type: str
    quantity: float
    avg_buy_price: float
    current_price: float
    total_invested: float
    current_value: float
    gain_loss: float
    gain_loss_percent: float
    breakeven_price: float | None = None
    risk_weight: float | None = None
    total_fees: float = 0.0
    exchange: str | None = None


@dataclass
class TaxTransaction:
    date: datetime | None
    symbol: str
    transaction_type: str
    quantity: float
    price: float
    total: float
    fee: float
    gain_loss: float | None


def _empty_report(year: int | None) -> dict[str, Any]:
    return {
        "portfolios": [],
        "assets": [],
        "transactions": [],
        "summary": {
            "total_value": 0.0,
            "total_invested": 0.0,
            "gain_loss": 0.0,
            "gain_loss_percent": 0.0,
        },
        "pnl_data": {},
        "risk_metrics": {},
        "platform_analysis": [],
        "generated_at": datetime.now(UTC),
        "year": year,
    }


def _portfolio_summary(portfolio: Portfolio, pm: dict[str, Any]) -> PortfolioSummary:
    p_value = pm["total_value"]
    p_invested = pm["total_invested"]
    p_gain = p_value - p_invested
    p_gain_pct = (p_gain / p_invested * 100) if p_invested > 0 else 0
    return PortfolioSummary(
        name=portfolio.name,
        total_value=p_value,
        total_invested=p_invested,
        gain_loss=p_gain,
        gain_loss_percent=p_gain_pct,
        asset_count=pm.get("assets_count", len(pm.get("assets", []))),
    )


def _asset_report(a: dict[str, Any]) -> AssetReport:
    return AssetReport(
        symbol=a["symbol"],
        name=a.get("name") or a["symbol"],
        asset_type=a["asset_type"],
        quantity=a["quantity"],
        avg_buy_price=a["avg_buy_price"],
        current_price=a.get("current_price") or a["avg_buy_price"],
        total_invested=a["total_invested"],
        current_value=a["current_value"],
        gain_loss=a["gain_loss"],
        gain_loss_percent=a["gain_loss_percent"],
        breakeven_price=a.get("breakeven_price"),
        risk_weight=a.get("risk_weight"),
        total_fees=a.get("total_fees", 0.0),
        exchange=a.get("exchange"),
    )


async def _collect_portfolios(
    db: AsyncSession, portfolios: Sequence[Portfolio], currency: str
) -> tuple[list[PortfolioSummary], list[AssetReport], list[str]]:
    summaries: list[PortfolioSummary] = []
    asset_reports: list[AssetReport] = []
    asset_ids: list[str] = []
    for portfolio in portfolios:
        pm = await metrics_service.get_portfolio_metrics(db, str(portfolio.id), currency=currency)
        summaries.append(_portfolio_summary(portfolio, pm))
        for a in pm.get("assets", []):
            asset_ids.append(a["id"])
            asset_reports.append(_asset_report(a))
    return summaries, asset_reports, asset_ids


async def _load_transactions(db: AsyncSession, asset_ids: list[str], year: int | None) -> list[TaxTransaction]:
    if not asset_ids:
        return []
    trans_query = select(Transaction).where(Transaction.asset_id.in_(asset_ids))
    if year:
        trans_query = trans_query.where(
            Transaction.executed_at >= datetime(year, 1, 1),
            Transaction.executed_at <= datetime(year, 12, 31, 23, 59, 59),
        )
    trans_query = trans_query.order_by(func.coalesce(Transaction.executed_at, Transaction.created_at).desc())
    trans_result = await db.execute(trans_query)
    transactions = trans_result.scalars().all()

    asset_id_result = await db.execute(select(Asset.id, Asset.symbol).where(Asset.id.in_(asset_ids)))
    id_to_symbol = {str(row[0]): row[1] for row in asset_id_result.all()}

    tax_transactions: list[TaxTransaction] = []
    for trans in transactions:
        symbol = id_to_symbol.get(str(trans.asset_id), "")
        if symbol:
            tax_transactions.append(
                TaxTransaction(
                    date=trans.executed_at,
                    symbol=symbol,
                    transaction_type=trans.transaction_type.value,
                    quantity=float(trans.quantity),
                    price=float(trans.price),
                    total=float(trans.quantity) * float(trans.price),
                    fee=float(trans.fee) if trans.fee else 0,
                    gain_loss=None,
                )
            )
    return tax_transactions


async def _risk_metrics(
    db: AsyncSession, user_id: str, dashboard: dict[str, Any], asset_ids: list[str]
) -> dict[str, Any]:
    try:
        allocations = [
            {"symbol": a["symbol"], "value": a["current_value"]} for a in dashboard.get("aggregated_assets", [])
        ]
        first_tx_result = await db.execute(
            select(func.min(Transaction.executed_at)).where(Transaction.asset_id.in_(asset_ids))
        )
        first_tx_date = first_tx_result.scalar()
        if first_tx_date:
            if first_tx_date.tzinfo is None:
                first_tx_date = first_tx_date.replace(tzinfo=UTC)
            risk_days = max((datetime.now(UTC) - first_tx_date).days + 1, 7)
        else:
            risk_days = 30

        return await snapshot_service.get_all_risk_metrics(
            db,
            user_id,
            current_value=dashboard["total_value"],
            allocations=allocations,
            days=risk_days,
        )
    except Exception:
        logger.warning("Failed to compute risk metrics for report", exc_info=True)
        return {}


def _platform_analysis(asset_reports: list[AssetReport]) -> list[dict[str, Any]]:
    platform_map: dict[str, dict[str, Any]] = {}
    for ar in asset_reports:
        ex = ar.exchange or "Autre"
        if ex not in platform_map:
            platform_map[ex] = {
                "exchange": ex,
                "total_value": 0.0,
                "total_invested": 0.0,
                "total_fees": 0.0,
                "count": 0,
            }
        platform_map[ex]["total_value"] += ar.current_value
        platform_map[ex]["total_invested"] += ar.total_invested
        platform_map[ex]["total_fees"] += ar.total_fees
        platform_map[ex]["count"] += 1

    platform_analysis = []
    for p in platform_map.values():
        invested = p["total_invested"]
        p["roi_percent"] = ((p["total_value"] - invested) / invested * 100) if invested > 0 else 0
        p["net_pnl"] = p["total_value"] - invested
        platform_analysis.append(p)
    platform_analysis.sort(key=lambda x: x["total_value"], reverse=True)
    return platform_analysis


def _attribution(asset_reports: list[AssetReport], liquidity: float) -> dict[str, float]:
    attribution = {
        "alpha": 0.0,
        "beta": 0.0,
        "protection": 0.0,
        "fixed_income": 0.0,
        "munitions": liquidity,
    }
    for ar in asset_reports:
        sym = ar.symbol.upper()
        if ar.asset_type == "crowdfunding":
            attribution["fixed_income"] += ar.current_value
        elif sym == "BTC":
            attribution["beta"] += ar.current_value
        elif is_safe_haven(sym):
            attribution["protection"] += ar.current_value
        else:
            attribution["alpha"] += ar.current_value
    return attribution


def _cash_flows(transactions: list[TaxTransaction]) -> dict[str, float]:
    cash_flows = {"total_deposits": 0.0, "total_withdrawals": 0.0}
    for tx in transactions:
        tt = tx.transaction_type
        if tt == "buy":
            cash_flows["total_deposits"] += tx.total
        elif tt == "sell":
            cash_flows["total_withdrawals"] += tx.total
    cash_flows["net_flows"] = cash_flows["total_deposits"] - cash_flows["total_withdrawals"]
    return cash_flows


class ReportDataMixin:
    async def get_report_data(
        self,
        db: AsyncSession,
        user_id: str,
        year: int | None = None,
        currency: str = "EUR",
    ) -> dict[str, Any]:
        """Remet en forme les chiffres de metrics_service et snapshot_service sans rien recalculer.

        Les frais d'achat étant inclus dans le montant investi, le P&L net par plateforme ne les retranche pas une
        seconde fois ; seuls les achats et ventes comptent comme flux de trésorerie, pas les transferts.
        """
        dashboard = await metrics_service.get_user_dashboard_metrics(db, user_id, currency=currency)

        result = await db.execute(select(Portfolio).where(Portfolio.user_id == user_id))
        portfolios = result.scalars().all()
        if not portfolios:
            return _empty_report(year)

        portfolio_summaries, asset_reports, asset_ids = await _collect_portfolios(db, portfolios, currency)
        tax_transactions = await _load_transactions(db, asset_ids, year)
        risk_metrics = await _risk_metrics(db, user_id, dashboard, asset_ids)

        return {
            "portfolios": portfolio_summaries,
            "assets": asset_reports,
            "transactions": tax_transactions,
            "summary": {
                "total_value": dashboard["total_value"],
                "total_invested": dashboard["total_invested"],
                "gain_loss": dashboard.get("net_gain_loss", 0),
                "gain_loss_percent": dashboard.get("net_gain_loss_percent", 0),
            },
            "pnl_data": dashboard.get("pnl_data", {}),
            "risk_metrics": risk_metrics,
            "platform_analysis": _platform_analysis(asset_reports),
            "attribution": _attribution(asset_reports, dashboard.get("available_liquidity", 0.0)),
            "cash_flows": _cash_flows(tax_transactions),
            "generated_at": datetime.now(UTC),
            "year": year,
        }
