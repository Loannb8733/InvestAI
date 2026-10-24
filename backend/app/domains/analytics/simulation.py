import numpy as np
from numpy.typing import NDArray

from app.domains.analytics.results import MonteCarloResult

DEFAULT_SEED = 20260911

_MAX_ELEMENTS = 200_000_000 // 8
_MIN_SIMULATIONS = 100
_LONG_TERM_VOL_BY_REGIME = {"stress": 0.30, "normal": 0.20, "low": 0.15}
_SHRINKAGE_START_DAYS = 90
_SHRINKAGE_FULL_DAYS = 1825

FloatArray = NDArray[np.float64]


def _capped_simulations(num_simulations: int, horizon_days: int, n_assets: int) -> int:
    capped_sims = min(num_simulations, _MAX_ELEMENTS // max(horizon_days * n_assets, 1))
    return max(capped_sims, _MIN_SIMULATIONS)


def _blended_cholesky(cholesky: FloatArray, horizon_days: int, n_assets: int, vol_regime: str) -> FloatArray:
    long_term_daily_vol = _LONG_TERM_VOL_BY_REGIME.get(vol_regime, 0.20) / np.sqrt(252)
    shrinkage = np.clip(
        (horizon_days - _SHRINKAGE_START_DAYS) / (_SHRINKAGE_FULL_DAYS - _SHRINKAGE_START_DAYS), 0.0, 1.0
    )
    if shrinkage > 0:
        long_term = np.eye(n_assets) * long_term_daily_vol
        blended: FloatArray = (1 - shrinkage) * cholesky + shrinkage * long_term
        return blended
    return cholesky


def _portfolio_daily_returns(
    mu_vec: FloatArray,
    cholesky: FloatArray,
    w: FloatArray,
    shape: tuple[int, int, int],
    seed: int,
) -> FloatArray:
    rng = np.random.default_rng(seed & 0x7FFFFFFF)
    shocks = rng.standard_normal(size=shape)
    correlated_returns = mu_vec + np.einsum("ij,...j->...i", cholesky, shocks)
    daily: FloatArray = correlated_returns @ w
    return daily


def _daily_deductions(
    annual_withdrawal_rate: float,
    ter_percentage: float,
    monthly_withdrawal: float,
    initial_portfolio_value: float,
) -> tuple[float, float, float]:
    daily_ter_factor = 1.0
    if ter_percentage > 0:
        daily_ter_factor = 1.0 - ter_percentage / 100.0 / 365.0
    daily_abs_withdrawal = 0.0
    daily_prop_withdrawal = 1.0
    if monthly_withdrawal > 0 and initial_portfolio_value > 0:
        daily_abs_withdrawal = (monthly_withdrawal / 30.0) / initial_portfolio_value
    elif annual_withdrawal_rate > 0:
        daily_prop_withdrawal = (1 - annual_withdrawal_rate / 100) ** (1 / 252)
    return daily_ter_factor, daily_abs_withdrawal, daily_prop_withdrawal


def _paths_with_deductions(
    port_daily_returns: FloatArray,
    daily_ter_factor: float,
    daily_abs_withdrawal: float,
    daily_prop_withdrawal: float,
) -> tuple[float, FloatArray]:
    capped_sims, horizon_days = port_daily_returns.shape
    portfolio_values = np.ones((capped_sims, horizon_days + 1))
    for day in range(horizon_days):
        v_next = (
            portfolio_values[:, day] * np.exp(port_daily_returns[:, day]) * daily_ter_factor * daily_prop_withdrawal
        )
        if daily_abs_withdrawal > 0:
            v_next -= daily_abs_withdrawal
        portfolio_values[:, day + 1] = np.maximum(v_next, 0.0)
    ruin_mask = np.any(portfolio_values[:, 1:] <= 0.001, axis=1)
    prob_ruin = float(np.mean(ruin_mask) * 100)
    final_values = portfolio_values[:, -1]
    return prob_ruin, (final_values - 1.0) * 100


def _paths_without_deductions(port_daily_returns: FloatArray) -> tuple[float, FloatArray]:
    cumulative_path = np.cumsum(port_daily_returns, axis=1)
    portfolio_values = np.exp(cumulative_path)
    ruin_mask = np.any(portfolio_values <= 0.01, axis=1)
    prob_ruin = float(np.mean(ruin_mask) * 100)
    cumulative = cumulative_path[:, -1]
    return prob_ruin, (np.exp(cumulative) - 1) * 100


def _summary(total_returns_pct: FloatArray, prob_ruin: float, capped_sims: int, horizon_days: int) -> MonteCarloResult:
    return MonteCarloResult(
        percentiles={
            "p5": round(float(np.percentile(total_returns_pct, 5)), 2),
            "p25": round(float(np.percentile(total_returns_pct, 25)), 2),
            "p50": round(float(np.percentile(total_returns_pct, 50)), 2),
            "p75": round(float(np.percentile(total_returns_pct, 75)), 2),
            "p95": round(float(np.percentile(total_returns_pct, 95)), 2),
        },
        expected_return=round(float(np.mean(total_returns_pct)), 2),
        prob_positive=round(float(np.mean(total_returns_pct > 0) * 100), 1),
        prob_loss_10=round(float(np.mean(total_returns_pct < -10) * 100), 1),
        prob_ruin=round(prob_ruin, 1),
        simulations=capped_sims,
        horizon_days=horizon_days,
    )


def simulate_monte_carlo(
    mu_vec: FloatArray,
    cholesky: FloatArray,
    w: FloatArray,
    num_simulations: int,
    horizon_days: int,
    n_assets: int,
    user_id: str,
    annual_withdrawal_rate: float = 0.0,
    ter_percentage: float = 0.0,
    monthly_withdrawal: float = 0.0,
    initial_portfolio_value: float = 0.0,
    vol_regime: str = "normal",
    seed: int | None = None,
) -> MonteCarloResult:
    """Rendement total simulé par chocs corrélés, en valeur normalisée à 1.

    Graine constante par défaut, ni horloge ni utilisateur : deux scénarios comparés subissent les mêmes chocs.
    Au-delà de 90 jours, la volatilité converge linéairement jusqu'à 5 ans vers 30 % (stress), 20 % (normal)
    ou 15 % (low) annualisés. Retrait mensuel absolu (montant / 30 par jour), prioritaire sur le taux annuel
    proportionnel ; les frais TER s'appliquent chaque jour ; une trajectoire tombée à zéro est ruinée.
    """
    capped_sims = _capped_simulations(num_simulations, horizon_days, n_assets)
    blended = _blended_cholesky(cholesky, horizon_days, n_assets, vol_regime)
    if seed is None:
        seed = DEFAULT_SEED
    port_daily_returns = _portfolio_daily_returns(mu_vec, blended, w, (capped_sims, horizon_days, n_assets), seed)
    ter_factor, abs_withdrawal, prop_withdrawal = _daily_deductions(
        annual_withdrawal_rate, ter_percentage, monthly_withdrawal, initial_portfolio_value
    )
    if ter_factor < 1.0 or abs_withdrawal > 0 or prop_withdrawal < 1.0:
        prob_ruin, total_returns_pct = _paths_with_deductions(
            port_daily_returns, ter_factor, abs_withdrawal, prop_withdrawal
        )
    else:
        prob_ruin, total_returns_pct = _paths_without_deductions(port_daily_returns)
    return _summary(total_returns_pct, prob_ruin, capped_sims, horizon_days)
