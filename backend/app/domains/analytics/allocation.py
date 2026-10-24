from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy import optimize as sp_optimize
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.finance_constants import annualization_days
from app.domains.analytics.metrics import compute_returns, sharpe
from app.domains.analytics.portfolio import AnalyticsPortfolio
from app.domains.analytics.results import AssetPerformance, OptimizationResult, RebalanceOrder
from app.domains.portfolio.models import Asset

FloatArray = NDArray[np.float64]

REBALANCE_THRESHOLD = 0.005
MIN_RETURNS = 10


def _optimal_weights(mu: FloatArray, cov: FloatArray, risk_free_rate: float, objective: str) -> FloatArray | None:
    def neg_sharpe(w: FloatArray) -> Any:
        ret = w @ mu
        vol = np.sqrt(w @ cov @ w)
        if vol == 0:
            return 0
        return -(ret - risk_free_rate) / vol

    def portfolio_vol(w: FloatArray) -> Any:
        return np.sqrt(w @ cov @ w)

    n = len(mu)
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]
    bounds = [(0.0, 1.0)] * n
    w0 = np.array([1.0 / n] * n)
    target = portfolio_vol if objective == "min_volatility" else neg_sharpe
    res = sp_optimize.minimize(target, w0, bounds=bounds, constraints=constraints, method="SLSQP")
    if not res.success:
        return None
    opt_w: FloatArray = res.x
    return opt_w


def _rebalance_order(asset: AssetPerformance, target_weights: dict[str, float], total_value: float) -> RebalanceOrder:
    target_w = target_weights.get(asset.symbol, asset.weight)
    target_val = total_value * target_w / 100
    diff_val = target_val - asset.current_value
    action = "hold"
    if diff_val > total_value * REBALANCE_THRESHOLD:
        action = "buy"
    elif diff_val < -total_value * REBALANCE_THRESHOLD:
        action = "sell"
    return RebalanceOrder(
        symbol=asset.symbol,
        name=asset.name,
        asset_type=asset.asset_type,
        current_weight=round(asset.weight, 2),
        target_weight=round(target_w, 2),
        diff_weight=round(target_w - asset.weight, 2),
        current_value=round(asset.current_value, 2),
        target_value=round(target_val, 2),
        diff_value=round(diff_val, 2),
        action=action,
    )


class AnalyticsAllocation(AnalyticsPortfolio):
    async def get_rebalance_orders(
        self,
        db: AsyncSession,
        user_id: str,
        target_weights: dict[str, float],
    ) -> list[RebalanceOrder]:
        """Ordres pour atteindre `target_weights` ({symbole: poids en %}) ; un actif absent garde son poids,
        et un écart sous 0,5 % de la valeur totale reste « hold »."""
        analytics = await self.get_user_analytics(db, user_id)
        if analytics.asset_count == 0:
            return []
        orders = [_rebalance_order(a, target_weights, analytics.total_value) for a in analytics.assets]
        return sorted(orders, key=lambda x: abs(x.diff_value), reverse=True)

    async def _optimizable_returns(self, seen: dict[str, Asset], days: int) -> tuple[list[str], list[FloatArray]]:
        symbols: list[str] = []
        returns_list: list[FloatArray] = []
        for sym in seen:
            rets = compute_returns(await self._history_prices(sym, days=days))
            if len(rets) >= MIN_RETURNS:
                symbols.append(sym)
                returns_list.append(rets)
        return symbols, returns_list

    async def optimize_portfolio(
        self,
        db: AsyncSession,
        user_id: str,
        objective: str = "max_sharpe",
        days: int = 90,
    ) -> OptimizationResult | None:
        """Pondérations de Markowitz sans vente à découvert, au Sharpe maximal (« max_sharpe ») ou à la volatilité
        minimale (« min_volatility ») ; None sous deux actifs exploitables ou si l'optimiseur échoue."""
        seen: dict[str, Asset] = {}
        for a in await self._get_user_assets(db, user_id):
            if a.symbol not in seen:
                seen[a.symbol] = a

        risk_free_rate = await self._fetch_risk_free_rate()
        symbols, returns_list = await self._optimizable_returns(seen, days)
        if len(symbols) < 2:
            return None

        min_len = min(len(r) for r in returns_list)
        aligned = np.array([r[-min_len:] for r in returns_list])
        opt_td = np.mean([annualization_days(seen[s].asset_type) for s in symbols])
        mu = np.mean(aligned, axis=1) * opt_td
        cov = np.cov(aligned) * opt_td

        opt_w = _optimal_weights(mu, cov, risk_free_rate, objective)
        if opt_w is None:
            return None

        opt_ret = (np.exp(float(opt_w @ mu)) - 1) * 100
        opt_vol = float(np.sqrt(opt_w @ cov @ opt_w)) * 100
        return OptimizationResult(
            weights={sym: round(float(opt_w[i]) * 100, 2) for i, sym in enumerate(symbols)},
            expected_return=round(opt_ret, 2),
            expected_volatility=round(opt_vol, 2),
            sharpe_ratio=sharpe(opt_ret, opt_vol, risk_free_rate),
        )
