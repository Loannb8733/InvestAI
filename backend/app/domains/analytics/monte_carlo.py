import asyncio
from decimal import Decimal

import numpy as np
from numpy.typing import NDArray
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.analytics.core import AnalyticsCore
from app.domains.analytics.metrics import compute_returns
from app.domains.analytics.results import MonteCarloResult
from app.domains.analytics.simulation import simulate_monte_carlo
from app.domains.portfolio.classification import is_cash_like
from app.domains.portfolio.models import Asset

FloatArray = NDArray[np.float64]

HISTORY_DAYS = 90
MIN_RETURNS = 10


def _no_simulation(horizon_days: int) -> MonteCarloResult:
    return MonteCarloResult(
        percentiles={"p5": 0, "p25": 0, "p50": 0, "p75": 0, "p95": 0},
        expected_return=0,
        prob_positive=0,
        prob_loss_10=0,
        prob_ruin=0,
        simulations=0,
        horizon_days=horizon_days,
    )


def _split_liquidity(assets: list[Asset]) -> tuple[dict[str, Asset], Decimal]:
    seen: dict[str, Asset] = {}
    liquidity_value = Decimal("0")
    for a in assets:
        if is_cash_like(a.symbol):
            price = float(a.avg_buy_price) if a.avg_buy_price and float(a.avg_buy_price) > 0 else 1.0
            liquidity_value += Decimal(str(a.quantity)) * Decimal(str(price))
            continue
        if a.symbol not in seen:
            seen[a.symbol] = a
    return seen, liquidity_value


def _apply_contribution(
    contribution: dict[str, float], symbols: list[str], all_weights: list[float], total_value: float
) -> float:
    for sym_c, amount_eur in contribution.items():
        if sym_c in symbols:
            all_weights[symbols.index(sym_c)] += amount_eur
            total_value += amount_eur
    return total_value


def _simulation_inputs(
    all_returns: list[FloatArray], all_weights: list[float]
) -> tuple[FloatArray, FloatArray, FloatArray, int]:
    w = np.array(all_weights)
    w = w / w.sum()
    n_assets = len(all_returns)
    min_len = min(len(r) for r in all_returns)
    aligned = np.array([r[-min_len:] for r in all_returns])
    mu_vec = np.mean(aligned, axis=1)
    cov_matrix = np.cov(aligned)
    if cov_matrix.ndim == 0:
        cov_matrix = np.array([[float(cov_matrix)]])
    elif cov_matrix.ndim == 1:
        cov_matrix = cov_matrix.reshape(1, 1)
    try:
        cholesky_factor = np.linalg.cholesky(cov_matrix + np.eye(n_assets) * 1e-10)
    except np.linalg.LinAlgError:
        cholesky_factor = np.diag(np.sqrt(np.diag(cov_matrix)))
    return mu_vec, cholesky_factor, w, n_assets


class AnalyticsMonteCarlo(AnalyticsCore):
    async def _risky_returns(
        self, seen: dict[str, Asset], liquidity_value: Decimal
    ) -> tuple[list[FloatArray], list[float], Decimal]:
        all_returns: list[FloatArray] = []
        all_weights: list[float] = []
        total_value_dec = liquidity_value
        for sym, asset in seen.items():
            prices = await self._history_prices(sym, days=HISTORY_DAYS)
            price = prices[-1] if prices and prices[-1] > 0 else float(asset.avg_buy_price or 0)
            if price <= 0:
                continue
            val_dec = Decimal(str(asset.quantity)) * Decimal(str(price))
            total_value_dec += val_dec
            rets = compute_returns(prices)
            if len(rets) >= MIN_RETURNS:
                all_returns.append(rets)
                all_weights.append(float(val_dec))
        return all_returns, all_weights, total_value_dec

    async def monte_carlo(
        self,
        db: AsyncSession,
        user_id: str,
        horizon_days: int = 90,
        num_simulations: int = 5000,
        portfolio_id: str | None = None,
        annual_withdrawal_rate: float = 0.0,
        ter_percentage: float = 0.0,
        monthly_withdrawal: float = 0.0,
        contribution: dict[str, float] | None = None,
        vol_regime: str = "normal",
    ) -> MonteCarloResult:
        """Simulation corrélée (Cholesky) sur 90 jours d'historique ; liquidités et stablecoins y entrent comme un actif
        sans volatilité, et `contribution` ajoute des euros à un symbole avant normalisation des poids."""
        assets = await self._get_user_assets(db, user_id, portfolio_id=portfolio_id, exclude_stablecoins=False)
        if not assets:
            return _no_simulation(horizon_days)

        seen, liquidity_value = _split_liquidity(assets)
        all_returns, all_weights, total_value_dec = await self._risky_returns(seen, liquidity_value)
        if float(liquidity_value) > 0 and all_returns:
            all_returns.append(np.zeros(min(len(r) for r in all_returns)))
            all_weights.append(float(liquidity_value))

        total_value = float(total_value_dec)
        if not all_returns or total_value == 0:
            return _no_simulation(horizon_days)

        if contribution:
            total_value = _apply_contribution(contribution, list(seen.keys()), all_weights, total_value)

        mu_vec, cholesky_factor, w, n_assets = _simulation_inputs(all_returns, all_weights)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            simulate_monte_carlo,
            mu_vec,
            cholesky_factor,
            w,
            num_simulations,
            horizon_days,
            n_assets,
            user_id,
            annual_withdrawal_rate,
            ter_percentage,
            monthly_withdrawal,
            total_value,
            vol_regime,
        )
