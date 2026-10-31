from dataclasses import replace
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.finance_constants import RISK_FREE_RATE
from app.domains.analytics.core import AnalyticsCore, AssetData
from app.domains.analytics.metrics import calmar, sharpe, sortino
from app.domains.analytics.portfolio_risk import portfolio_risk
from app.domains.analytics.results import AssetPerformance, PortfolioAnalytics
from app.domains.analytics.scoring import build_interpretations, diversification_score, hhi
from app.domains.dashboard.metrics.service import metrics_service
from app.domains.portfolio.models import Asset, Portfolio


def _aggregate_by_symbol(asset_data: list[AssetData]) -> list[AssetData]:
    aggregated: dict[str, AssetData] = {}
    for data in asset_data:
        sym = data["asset"].symbol
        if sym in aggregated:
            aggregated[sym]["current_value"] += data["current_value"]
            aggregated[sym]["total_invested"] += data["total_invested"]
        else:
            aggregated[sym] = dict(data)
    for d in aggregated.values():
        d["gain_loss"] = d["current_value"] - d["total_invested"]
        d["gain_loss_percent"] = (d["gain_loss"] / d["total_invested"] * 100) if d["total_invested"] > 0 else 0
    return list(aggregated.values())


def _allocations(real_assets: list[AssetData], total_value: float) -> tuple[dict[str, float], dict[str, float]]:
    allocation_by_type: dict[str, float] = {}
    allocation_by_asset: dict[str, float] = {}
    for d in real_assets:
        a = d["asset"]
        w = (d["current_value"] / total_value * 100) if total_value > 0 else 0
        d["weight"] = w
        at = a.asset_type.value
        allocation_by_type[at] = allocation_by_type.get(at, 0) + w
        allocation_by_asset[a.symbol] = w
    return allocation_by_type, allocation_by_asset


def _performance(d: AssetData, risk_free_rate: float) -> AssetPerformance:
    a = d["asset"]
    v = d["volatility"]
    ann_r = d.get("annualized_return", 0.0)
    return AssetPerformance(
        symbol=a.symbol,
        name=a.name or a.symbol,
        asset_type=a.asset_type.value,
        current_value=d["current_value"],
        total_invested=d["total_invested"],
        gain_loss=d["gain_loss"],
        gain_loss_percent=d["gain_loss_percent"],
        weight=d["weight"],
        daily_return=round(d["daily_return"], 2),
        volatility_30d=round(v, 1),
        sharpe_ratio=sharpe(ann_r, v, risk_free_rate),
        sortino_ratio=sortino(ann_r, d["downside_dev"], risk_free_rate),
        max_drawdown=round(d["max_drawdown"], 2),
    )


def _assemble_analytics(asset_data: list[AssetData], risk_free_rate: float = RISK_FREE_RATE) -> PortfolioAnalytics:
    real_assets = [d for d in asset_data if not d.get("is_stablecoin", False)]

    total_value_dec = sum((Decimal(str(d["current_value"])) for d in real_assets), Decimal("0"))
    total_invested_dec = sum((Decimal(str(d["total_invested"])) for d in real_assets), Decimal("0"))
    total_gl_dec = total_value_dec - total_invested_dec
    total_value = float(total_value_dec)

    allocation_by_type, allocation_by_asset = _allocations(real_assets, total_value)
    pm = portfolio_risk(real_assets, total_value)
    vol = pm["volatility"]
    ann_ret = pm["annualized_return"]
    max_dd = pm["max_drawdown"]
    var95_pct = pm["var_95_pct"]
    sharpe_ratio = sharpe(ann_ret, vol, risk_free_rate)
    sortino_ratio = sortino(ann_ret, pm["downside_dev"], risk_free_rate)
    calmar_ratio = calmar(ann_ret, max_dd)

    var_95_eur = round(total_value * var95_pct / 100, 2)
    concentration = hhi(allocation_by_asset)
    perfs = [_performance(d, risk_free_rate) for d in real_assets]
    sorted_p = sorted(perfs, key=lambda x: x.gain_loss_percent, reverse=True)

    return PortfolioAnalytics(
        total_value=total_value,
        total_invested=float(total_invested_dec),
        total_gain_loss=float(total_gl_dec),
        total_gain_loss_percent=float(total_gl_dec / total_invested_dec * 100) if total_invested_dec > 0 else 0,
        portfolio_volatility=vol,
        sharpe_ratio=sharpe_ratio,
        sortino_ratio=sortino_ratio,
        calmar_ratio=calmar_ratio,
        max_drawdown=max_dd,
        var_95=var_95_eur,
        cvar_95=round(total_value * pm["cvar_95_pct"] / 100, 2),
        var_95_description=(
            (f"Perte journalière maximale attendue (95%): {var_95_eur:.2f} EUR ({var95_pct:.2f}% du portefeuille)")
            if var95_pct > 0
            else ""
        ),
        diversification_score=diversification_score(len(real_assets), len(allocation_by_type), concentration),
        concentration_risk=concentration,
        asset_count=len(real_assets),
        allocation_by_type=allocation_by_type,
        allocation_by_asset=allocation_by_asset,
        assets=perfs,
        best_performer=sorted_p[0].symbol if sorted_p else None,
        worst_performer=sorted_p[-1].symbol if len(sorted_p) > 1 else None,
        interpretations=build_interpretations(
            sharpe=sharpe_ratio,
            sortino=sortino_ratio,
            calmar=calmar_ratio,
            volatility=vol,
            max_dd=max_dd,
            asset_data=real_assets,
        ),
    )


def _with_gain(analytics: PortfolioAnalytics, figures: dict[str, Any]) -> PortfolioAnalytics:
    return replace(
        analytics,
        total_gain_loss=figures["total_gain_loss"],
        total_gain_loss_percent=figures["total_gain_loss_percent"],
    )


class AnalyticsPortfolio(AnalyticsCore):
    async def get_portfolio_analytics(
        self,
        db: AsyncSession,
        portfolio_id: str,
        currency: str = "EUR",
        days: int = 60,
    ) -> PortfolioAnalytics:
        """Analyse d'un portefeuille ; `currency` ne vaut que pour le gain, le reste suit les cours en base."""
        gain = await metrics_service.get_portfolio_performance(db, portfolio_id, currency)
        result = await db.execute(select(Asset).where(Asset.portfolio_id == portfolio_id, Asset.quantity > 0))
        assets = result.scalars().all()
        if not assets:
            return _with_gain(self._empty_analytics(), gain)

        risk_free_rate = await self._fetch_risk_free_rate()
        asset_data = await self._build_asset_data(assets, days=days)
        return _with_gain(_assemble_analytics(asset_data, risk_free_rate=risk_free_rate), gain)

    async def get_user_analytics(
        self,
        db: AsyncSession,
        user_id: str,
        currency: str = "EUR",
        days: int = 60,
    ) -> PortfolioAnalytics:
        """Analyse de tous les portefeuilles de l'utilisateur, positions regroupées par symbole."""
        portfolios = (await db.execute(select(Portfolio).where(Portfolio.user_id == user_id))).scalars().all()
        if not portfolios:
            return self._empty_analytics()

        gain = await metrics_service.get_user_dashboard_metrics(db, user_id, currency, days)
        portfolio_ids = [p.id for p in portfolios]
        result = await db.execute(select(Asset).where(Asset.portfolio_id.in_(portfolio_ids), Asset.quantity > 0))
        assets = result.scalars().all()
        if not assets:
            return _with_gain(self._empty_analytics(), gain)

        risk_free_rate = await self._fetch_risk_free_rate()
        asset_data = await self._build_asset_data(assets, days=days)
        return _with_gain(_assemble_analytics(_aggregate_by_symbol(asset_data), risk_free_rate=risk_free_rate), gain)

    def _empty_analytics(self) -> PortfolioAnalytics:
        return PortfolioAnalytics(
            total_value=0,
            total_invested=0,
            total_gain_loss=0,
            total_gain_loss_percent=0,
            portfolio_volatility=0,
            sharpe_ratio=0,
            sortino_ratio=0,
            calmar_ratio=0,
            max_drawdown=0,
            var_95=0,
            cvar_95=0,
            diversification_score=0,
            concentration_risk=0,
            asset_count=0,
            allocation_by_type={},
            allocation_by_asset={},
            assets=[],
            best_performer=None,
            worst_performer=None,
        )
