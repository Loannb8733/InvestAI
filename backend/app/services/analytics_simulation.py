"""Simulation de trajectoires de patrimoine par tirages corrélés.

Extrait d'`AnalyticsService`, où ces 133 lignes de calcul vivaient au milieu de
l'orchestration. Le calcul ne touche ni la base, ni le réseau : il ne dépend que
de ses paramètres, et se vérifie donc en quelques millisecondes.

Sa graine est explicite (FIN-06) : deux appels identiques rendent la même
projection. Sans cela, l'utilisateur verrait ses percentiles changer à chaque
rafraîchissement, sans avoir rien fait.
"""

import time
from typing import Optional

import numpy as np

from app.services.analytics_types import MonteCarloResult


def _monte_carlo_compute(
    mu_vec: np.ndarray,
    L: np.ndarray,
    w: np.ndarray,
    num_simulations: int,
    horizon_days: int,
    n_assets: int,
    user_id: str,
    annual_withdrawal_rate: float = 0.0,
    ter_percentage: float = 0.0,
    monthly_withdrawal: float = 0.0,
    initial_portfolio_value: float = 0.0,
    vol_regime: str = "normal",
    seed: Optional[int] = None,
) -> "MonteCarloResult":
    """CPU-bound Monte Carlo with volatility shrinkage, withdrawals and fees.

    Volatility shrinkage: for horizons > 90 days, the Cholesky factor (L)
    is blended towards a long-term average volatility (~20% annualized)
    using a linear shrinkage schedule.  This prevents unrealistic
    extreme outcomes when short-term crypto vol (80%+) is extrapolated
    over multi-year horizons.

    vol_regime controls the long-term vol assumption:
    - "stress" (bear): 30% annualized — heavier tails, more pessimistic
    - "normal": 20% annualized — baseline
    - "low" (bull): 15% annualized — compressed vol, more optimistic

    Withdrawal modes (mutually exclusive, ``monthly_withdrawal`` takes priority):
    - ``monthly_withdrawal`` (€): absolute daily deduction = amount / 30.
      Formula: V(t) = V(t-1) * exp(r_t) * (1 - ter/365) - monthly_withdrawal/30
    - ``annual_withdrawal_rate`` (%): proportional daily deduction.

    A path is marked as "ruined" when portfolio value drops to ≤ 0.
    """
    # Cap allocation: 200 MB / 8 bytes per float64
    max_elements = 200_000_000 // 8
    capped_sims = min(num_simulations, max_elements // max(horizon_days * n_assets, 1))
    capped_sims = max(capped_sims, 100)  # At least 100 simulations

    # --- Volatility shrinkage (mean reversion) ---
    # Regime-aware long-term vol target
    _VOL_BY_REGIME = {"stress": 0.30, "normal": 0.20, "low": 0.15}
    LONG_TERM_DAILY_VOL = _VOL_BY_REGIME.get(vol_regime, 0.20) / np.sqrt(252)
    # Shrinkage ramps from 0 at 90 days to 1 at 1825 days (5 years)
    shrinkage = np.clip((horizon_days - 90) / (1825 - 90), 0.0, 1.0)

    if shrinkage > 0:
        # Build a long-term L: diagonal matrix with uniform long-term vol
        L_longterm = np.eye(n_assets) * LONG_TERM_DAILY_VOL
        L_blended = (1 - shrinkage) * L + shrinkage * L_longterm
    else:
        L_blended = L

    # Reproducibility: an explicit ``seed`` forces deterministic draws (tests,
    # or any caller that needs repeatable runs). Production leaves it None, so
    # each run gets fresh randomness from the wall clock XOR the user id.
    if seed is None:
        seed = int(time.time()) ^ (hash(user_id) % (2**31))
    rng = np.random.default_rng(seed & 0x7FFFFFFF)
    Z = rng.standard_normal(size=(capped_sims, horizon_days, n_assets))
    correlated_returns = mu_vec + np.einsum("ij,...j->...i", L_blended, Z)
    port_daily_returns = correlated_returns @ w  # (capped_sims, horizon_days)

    # --- Daily deductions from withdrawals + TER ---
    # TER: multiplicative daily factor  (1 - ter/365) applied each day.
    daily_ter_factor = 1.0
    if ter_percentage > 0:
        daily_ter_factor = 1.0 - ter_percentage / 100.0 / 365.0

    # Withdrawal: absolute daily amount (monthly_withdrawal / 30) normalised
    # to portfolio-relative units (we simulate starting at V=1.0).
    # Fallback: proportional annual_withdrawal_rate for backward compat.
    daily_abs_withdrawal = 0.0  # in normalised units (fraction of initial)
    daily_prop_withdrawal = 1.0  # multiplicative factor
    use_absolute = monthly_withdrawal > 0 and initial_portfolio_value > 0

    if use_absolute:
        daily_abs_withdrawal = (monthly_withdrawal / 30.0) / initial_portfolio_value
    elif annual_withdrawal_rate > 0:
        daily_prop_withdrawal = (1 - annual_withdrawal_rate / 100) ** (1 / 252)

    has_deductions = daily_ter_factor < 1.0 or daily_abs_withdrawal > 0 or daily_prop_withdrawal < 1.0

    if has_deductions:
        # Step-by-step simulation: V(t) starts at 1.0 (normalised)
        portfolio_values = np.ones((capped_sims, horizon_days + 1))
        for day in range(horizon_days):
            # V(t) = V(t-1) * exp(r_t) * ter_factor - abs_withdrawal
            # (or  * prop_factor  when using proportional mode)
            v_next = (
                portfolio_values[:, day] * np.exp(port_daily_returns[:, day]) * daily_ter_factor * daily_prop_withdrawal
            )
            if daily_abs_withdrawal > 0:
                v_next -= daily_abs_withdrawal
            # Floor at zero: once ruined, stay ruined
            portfolio_values[:, day + 1] = np.maximum(v_next, 0.0)

        # Ruin = portfolio touched 0 (or near-zero)
        ruin_mask = np.any(portfolio_values[:, 1:] <= 0.001, axis=1)
        prob_ruin = float(np.mean(ruin_mask) * 100)

        # Total returns from final portfolio value
        final_values = portfolio_values[:, -1]
        total_returns_pct = (final_values - 1.0) * 100
    else:
        # Original path without deductions (faster vectorized)
        cumulative_path = np.cumsum(port_daily_returns, axis=1)
        portfolio_values = np.exp(cumulative_path)  # relative to initial (1.0)
        ruin_mask = np.any(portfolio_values <= 0.01, axis=1)
        prob_ruin = float(np.mean(ruin_mask) * 100)

        cumulative = cumulative_path[:, -1]
        total_returns_pct = (np.exp(cumulative) - 1) * 100

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
