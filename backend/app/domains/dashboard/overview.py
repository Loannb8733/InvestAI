"""Assemblage de l'écran du tableau de bord."""

import asyncio
import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeframe import get_period_label_fr
from app.domains.dashboard import repository
from app.domains.dashboard.analysis import annualized_roi, build_advanced_metrics, compute_period_twr
from app.domains.dashboard.earn import build_earn_summary
from app.domains.dashboard.feed import active_alerts, get_index_comparison, recent_transactions, upcoming_events
from app.domains.dashboard.metrics.service import metrics_service
from app.domains.dashboard.schemas import (
    AssetAllocation,
    CurrencyExposure,
    EnhancedDashboardResponse,
    HistoricalDataPoint,
    IndexComparison,
)
from app.domains.dashboard.snapshots.periods import data_point_interval
from app.domains.dashboard.snapshots.service import snapshot_service
from app.domains.identity.models import User
from app.domains.portfolio.classification import STABLECOIN_PEGS, is_safe_haven
from app.domains.transactions.cost_basis.context import aware

logger = logging.getLogger(__name__)

_MIN_ALL_TIME_DAYS = 7
_EVENT_DAYS = 90
_SHORT_PERIOD_DAYS = 7
_MIN_COVERAGE = 0.3


def resolve_period_days(days: int, first_transaction: datetime | None) -> int:
    """`days=0` signifie « Tout » : du premier jour de l'historique à aujourd'hui ; sans historique, aucune période."""
    if days != 0:
        return days
    if not first_transaction:
        return 0
    return max((datetime.now(UTC) - first_transaction).days + 1, _MIN_ALL_TIME_DAYS)


async def _charts(db: AsyncSession, user_id: str, days: int) -> tuple[list[dict[str, Any]], list[IndexComparison]]:
    history, indices = await asyncio.gather(
        snapshot_service.build_portfolio_value_series(db, user_id, days),
        get_index_comparison(days),
        return_exceptions=True,
    )
    if isinstance(history, BaseException):
        logger.error("Série de valeur indisponible (user=%s, days=%s)", user_id, days, exc_info=history)
        history = []
    if isinstance(indices, BaseException):
        logger.error("Comparaison d'indices indisponible (days=%s)", days, exc_info=indices)
        indices = []
    return history, indices


def _flag_estimated(history: list[dict[str, Any]], days: int) -> bool:
    expected = max(days // data_point_interval(days), 5)
    estimated = len(history) / expected < _MIN_COVERAGE and days > _SHORT_PERIOD_DAYS
    for point in history:
        point["is_estimated"] = estimated
    return estimated


def _apply_all_time_change(metrics: dict[str, Any]) -> None:
    metrics["period_change"] = metrics["total_gain_loss"]
    metrics["period_change_percent"] = round(metrics["total_gain_loss_percent"], 2)


def _asset_allocation(metrics: dict[str, Any], staked: dict[str, float]) -> list[AssetAllocation]:
    allocation = [
        AssetAllocation(
            symbol=asset["symbol"],
            name=asset.get("name"),
            asset_type=asset["asset_type"],
            value=asset["current_value"],
            percentage=asset["percentage"],
            gain_loss_percent=asset["gain_loss_percent"],
            avg_buy_price=asset.get("avg_buy_price"),
            staked_quantity=staked.get(asset["symbol"].upper()),
        )
        for asset in metrics.get("aggregated_assets", [])
    ]
    allocation.sort(key=lambda entry: entry.value, reverse=True)
    return allocation


async def _record_daily_snapshot(db: AsyncSession, user_id: str, metrics: dict[str, Any], currency: str) -> None:
    if metrics["assets_count"] <= 0:
        return
    try:
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        if not await repository.has_global_snapshot_since(db, user_id, today):
            await repository.insert_global_snapshot(
                db,
                user_id,
                datetime.now(UTC),
                Decimal(str(metrics["total_value"])),
                Decimal(str(metrics["total_invested"])),
                Decimal(str(metrics["total_gain_loss"])),
                currency,
            )
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.warning("Daily portfolio snapshot creation failed for user %s: %s", user_id, exc)


def _exposure_currency(asset: dict[str, Any], currencies: dict[str, str]) -> str:
    symbol = (asset.get("symbol") or "").upper()
    if asset.get("asset_type", "") != "crypto":
        return currencies.get(asset.get("id", ""), "EUR")
    return "OR" if is_safe_haven(symbol) else STABLECOIN_PEGS.get(symbol, "USD")


async def _currency_exposure(db: AsyncSession, user_id: UUID, metrics: dict[str, Any]) -> list[CurrencyExposure]:
    currencies = await repository.asset_currencies(db, user_id)
    totals: dict[str, float] = {}
    for asset in metrics.get("assets", []):
        value = asset.get("current_value", 0.0)
        if value > 0:
            currency = _exposure_currency(asset, currencies)
            totals[currency] = totals.get(currency, 0.0) + value
    total = sum(totals.values()) or 1.0
    return [
        CurrencyExposure(currency=currency, value=round(value, 2), percentage=round(value / total * 100, 1))
        for currency, value in sorted(totals.items(), key=lambda item: item[1], reverse=True)
    ]


async def build_overview(days: int, current_user: User, db: AsyncSession) -> EnhancedDashboardResponse:
    """Calcule l'écran complet ; graphiques et risque peuvent manquer, le patrimoine non."""
    account_id = current_user.id
    user_id = str(account_id)
    currency = current_user.preferred_currency or "EUR"
    first_transaction = aware(await repository.first_transaction_date(db, account_id))
    period = resolve_period_days(days, first_transaction)
    metrics = await metrics_service.get_user_dashboard_metrics(db, user_id, currency=currency, days=period)
    history, indices = await _charts(db, user_id, period)
    transactions = await recent_transactions(db, account_id, days=period)
    alerts = await active_alerts(db, account_id)
    events = await upcoming_events(db, account_id, _EVENT_DAYS)
    estimated = _flag_estimated(history, period)
    if days == 0:
        _apply_all_time_change(metrics)
    earn, staked = await build_earn_summary(db, account_id, metrics)
    allocation = _asset_allocation(metrics, staked)
    roi = annualized_roi(metrics, first_transaction, period)
    advanced = await build_advanced_metrics(db, user_id, metrics, allocation, period, history, roi)
    await _record_daily_snapshot(db, user_id, metrics, currency)
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
        period_twr_percent=compute_period_twr(history),
        portfolios_count=metrics["portfolios_count"],
        assets_count=metrics["assets_count"],
        allocation=metrics["allocation"],
        asset_allocation=allocation,
        top_performers=metrics["top_performers"],
        worst_performers=metrics["worst_performers"],
        historical_data=[HistoricalDataPoint(**point) for point in history],
        is_data_estimated=estimated,
        recent_transactions=transactions,
        active_alerts=alerts,
        upcoming_events=events,
        index_comparison=indices,
        advanced_metrics=advanced,
        available_liquidity=metrics.get("available_liquidity", 0.0),
        earn_summary=earn,
        currency_exposure=await _currency_exposure(db, account_id, metrics),
        total_dividend_income=metrics.get("total_dividend_income", 0.0),
        total_return=metrics.get("total_return", 0.0),
        period_days=period,
        period_label=get_period_label_fr(days),
        forex_stale=metrics.get("forex_stale", False),
        unpriced_symbols=metrics.get("unpriced_symbols", []),
        last_updated=datetime.now(UTC).isoformat(),
    )
