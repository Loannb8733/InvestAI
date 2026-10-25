from typing import Any

import numpy as np
from numpy.typing import NDArray

from app.domains.planning.simulations.schemas import DCAParameters, DCAResult

FloatArray = NDArray[np.float64]

N_PATHS = 500
_START_PRICE = 100.0


def _schedule(frequency: str, duration_months: int) -> tuple[int, int]:
    if frequency == "weekly":
        return duration_months * 4, 48
    if frequency == "quarterly":
        return max(duration_months // 3, 1), 4
    return duration_months, 12


def _price_paths(params: DCAParameters, num_investments: int, periods_per_year: int) -> FloatArray:
    rng = np.random.default_rng()
    period_return = params.expected_return / 100 / periods_per_year
    period_vol = params.expected_volatility / 100 / (periods_per_year**0.5)
    returns = rng.normal(period_return, period_vol, size=(N_PATHS, num_investments))
    growth = np.clip(1.0 + returns, 0.01, None)
    prices: FloatArray = _START_PRICE * np.cumprod(growth, axis=1)
    return prices


def _median_projections(
    prices: FloatArray,
    units_per_period: FloatArray,
    cum_units: FloatArray,
    dca_values: FloatArray,
    ls_values: FloatArray,
    amount_per_investment: float,
) -> list[dict[str, Any]]:
    price_p50 = np.percentile(prices, 50, axis=0)
    units_p50 = np.percentile(units_per_period, 50, axis=0)
    cum_units_p50 = np.percentile(cum_units, 50, axis=0)
    dca_val_p10 = np.percentile(dca_values, 10, axis=0)
    dca_val_p50 = np.percentile(dca_values, 50, axis=0)
    dca_val_p90 = np.percentile(dca_values, 90, axis=0)
    ls_val_p50 = np.percentile(ls_values, 50, axis=0)
    return [
        {
            "period": i + 1,
            "price": round(float(price_p50[i]), 2),
            "amount_invested": round(amount_per_investment, 2),
            "units_bought": round(float(units_p50[i]), 4),
            "total_units": round(float(cum_units_p50[i]), 4),
            "total_invested": round(amount_per_investment * (i + 1), 2),
            "current_value": round(float(dca_val_p50[i]), 2),
            "current_value_p10": round(float(dca_val_p10[i]), 2),
            "current_value_p90": round(float(dca_val_p90[i]), 2),
            "lump_sum_value": round(float(ls_val_p50[i]), 2),
        }
        for i in range(prices.shape[1])
    ]


def simulate_dca_paths(params: DCAParameters, currency: str) -> DCAResult:
    """DCA contre Lump Sum sur ``N_PATHS`` chemins de prix communs, sans graine fixe car on rend une distribution.

    Le rendement et la volatilité annuels sont ramenés à la période d'investissement (48 semaines, 12 mois ou
    4 trimestres par an, au moins un trimestre) ; les champs historiques et ``projections`` suivent la médiane,
    avec la bande p10-p90 et la valeur Lump Sum médiane par période.
    """
    num_investments, periods_per_year = _schedule(params.frequency, params.duration_months)
    amount_per_investment = params.total_amount / num_investments
    total_invested = amount_per_investment * num_investments

    prices = _price_paths(params, num_investments, periods_per_year)
    units_per_period = amount_per_investment / prices
    cum_units = np.cumsum(units_per_period, axis=1)
    dca_values = cum_units * prices
    dca_final = dca_values[:, -1]
    ls_values = (total_invested / _START_PRICE) * prices
    ls_final = ls_values[:, -1]

    dca_p10, dca_p50, dca_p90 = (float(v) for v in np.percentile(dca_final, [10, 50, 90]))
    ls_p10, ls_p50, ls_p90 = (float(v) for v in np.percentile(ls_final, [10, 50, 90]))
    prob_dca_beats_ls = float(np.mean(dca_final > ls_final) * 100)
    projections = _median_projections(prices, units_per_period, cum_units, dca_values, ls_values, amount_per_investment)

    median_total_units = float(np.percentile(cum_units[:, -1], 50))
    average_cost = total_invested / median_total_units if median_total_units > 0 else 0.0
    return_percent = ((dca_p50 - total_invested) / total_invested * 100) if total_invested > 0 else 0.0

    return DCAResult(
        total_invested=round(total_invested, 2),
        final_value=round(dca_p50, 2),
        average_cost=round(average_cost, 2),
        total_units=round(median_total_units, 4),
        return_percent=round(return_percent, 2),
        projections=projections,
        currency=currency,
        dca_p10=round(dca_p10, 2),
        dca_p50=round(dca_p50, 2),
        dca_p90=round(dca_p90, 2),
        lumpsum_p10=round(ls_p10, 2),
        lumpsum_p50=round(ls_p50, 2),
        lumpsum_p90=round(ls_p90, 2),
        prob_dca_beats_ls=round(prob_dca_beats_ls, 1),
        n_paths=N_PATHS,
    )
