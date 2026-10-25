import math
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

import numpy as np
from numpy.typing import NDArray

from app.domains.planning.simulations.schemas import FIREProbabilisticParameters, FIREProbabilisticResult

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]

RISK_PROFILE_ASSUMPTIONS: dict[str, tuple[float, float]] = {
    "conservative": (0.05, 0.10),
    "moderate": (0.07, 0.15),
    "aggressive": (0.10, 0.25),
}

_SURVIVAL_MONTHS = 30 * 12


@dataclass(frozen=True)
class _MonthlyModel:
    mu: float
    sigma: float
    inflation: float


@dataclass(frozen=True)
class _Accumulation:
    values: FloatArray
    fire_month: IntArray
    median_by_year: list[float]
    fire_number_by_year: list[float]


@dataclass(frozen=True)
class FireInputs:
    """Hypothèses retenues après pré-remplissage ; ``defaults_from`` indique la source de chaque défaut appliqué."""

    current_value: float
    monthly_contribution: float
    annual_return_mean: float
    annual_volatility: float
    defaults_from: dict[str, str]


def _accumulate(
    rng: np.random.Generator,
    model: _MonthlyModel,
    *,
    current_value: float,
    monthly_contribution: float,
    fire_number_today: float,
    index_contributions: bool,
    n_months: int,
    n_paths: int,
) -> _Accumulation:
    growth = np.exp(rng.normal(model.mu, model.sigma, size=(n_paths, n_months)))
    values = np.full(n_paths, float(current_value))
    fire_month = np.full(n_paths, 0 if current_value >= fire_number_today else -1, dtype=np.int64)
    median_by_year: list[float] = [float(current_value)]
    fire_number_by_year: list[float] = [fire_number_today]

    for t in range(n_months):
        contribution = monthly_contribution * (model.inflation**t) if index_contributions else monthly_contribution
        values = values * growth[:, t] + contribution
        fire_number_t = fire_number_today * (model.inflation ** (t + 1))
        newly_fire = (fire_month < 0) & (values >= fire_number_t)
        fire_month[newly_fire] = t + 1
        if (t + 1) % 12 == 0:
            median_by_year.append(float(np.median(values)))
            fire_number_by_year.append(fire_number_t)
    return _Accumulation(values, fire_month, median_by_year, fire_number_by_year)


def _prob_by_year(fire_month: IntArray, years_horizon: int, start_year: int) -> list[dict[str, Any]]:
    reached = fire_month >= 0
    prob_by_year: list[dict[str, Any]] = []
    for k in range(years_horizon + 1):
        prob = float(np.mean(reached & (fire_month <= 12 * k)))
        prob_by_year.append({"year": start_year + k, "prob": round(prob, 4)})
    return prob_by_year


def _year_at_quantile(prob_by_year: list[dict[str, Any]], q: float) -> int | None:
    for entry in prob_by_year:
        if entry["prob"] >= q:
            return int(entry["year"])
    return None


def _survival_probability(
    rng: np.random.Generator, model: _MonthlyModel, fire_number_today: float, annual_expenses: float, n_paths: int
) -> float:
    growth_retirement = np.exp(rng.normal(model.mu, model.sigma, size=(n_paths, _SURVIVAL_MONTHS)))
    retirement_values = np.full(n_paths, fire_number_today)
    ruined = np.zeros(n_paths, dtype=bool)
    monthly_expenses = annual_expenses / 12.0
    for t in range(_SURVIVAL_MONTHS):
        withdrawal = monthly_expenses * (model.inflation**t)
        retirement_values = retirement_values * growth_retirement[:, t] - withdrawal
        ruined |= retirement_values <= 0.0
        retirement_values = np.maximum(retirement_values, 0.0)
    return float(1.0 - np.mean(ruined))


def _median_path(accumulation: _Accumulation, start_year: int) -> list[dict[str, Any]]:
    return [
        {
            "year": start_year + i,
            "portfolio_value": round(accumulation.median_by_year[i], 2),
            "fire_number": round(accumulation.fire_number_by_year[i], 2),
        }
        for i in range(len(accumulation.median_by_year))
    ]


def simulate_fire_probabilistic(
    *,
    current_value: float,
    monthly_contribution: float,
    annual_expenses: float,
    withdrawal_rate: float,
    annual_return_mean: float,
    annual_volatility: float,
    inflation: float,
    index_contributions: bool,
    years_horizon: int,
    n_paths: int,
    seed: int | None = None,
    start_year: int | None = None,
) -> dict[str, Any]:
    """Monte-Carlo mensuel log-normal (drift corrigé de -sigma²/2 pour que l'espérance vaille le rendement moyen).

    Le nombre FIRE est indexé sur l'inflation et son atteinte est absorbante : un chemin reste FIRE même si le
    marché rebaisse. ``survival_prob_30y`` vient d'une simulation séparée : départ au nombre FIRE du jour, sans
    contribution, retraits mensuels indexés pendant 30 ans, ruine absorbante (ordre de grandeur Trinity).
    ``seed`` ne sert qu'aux tests ; ``start_year`` vaut par défaut l'année courante.
    """
    if start_year is None:
        start_year = datetime.now().year

    rng = np.random.default_rng(seed)
    sigma_m = annual_volatility / math.sqrt(12.0)
    model = _MonthlyModel(
        mu=math.log1p(annual_return_mean) / 12.0 - sigma_m**2 / 2.0,
        sigma=sigma_m,
        inflation=(1.0 + inflation) ** (1.0 / 12.0),
    )
    fire_number_today = annual_expenses / withdrawal_rate

    accumulation = _accumulate(
        rng,
        model,
        current_value=current_value,
        monthly_contribution=monthly_contribution,
        fire_number_today=fire_number_today,
        index_contributions=index_contributions,
        n_months=years_horizon * 12,
        n_paths=n_paths,
    )
    prob_by_year = _prob_by_year(accumulation.fire_month, years_horizon, start_year)
    prob_at_horizon = float(np.mean(accumulation.fire_month >= 0))
    final_p10, final_p50, final_p90 = (float(v) for v in np.percentile(accumulation.values, [10, 50, 90]))
    survival_prob_30y = _survival_probability(rng, model, fire_number_today, annual_expenses, n_paths)

    return {
        "prob_by_year": prob_by_year,
        "prob_at_horizon": round(prob_at_horizon, 4),
        "fire_year_p10": _year_at_quantile(prob_by_year, 0.10),
        "fire_year_p50": _year_at_quantile(prob_by_year, 0.50),
        "fire_year_p90": _year_at_quantile(prob_by_year, 0.90),
        "final_value_p10": round(final_p10, 2),
        "final_value_p50": round(final_p50, 2),
        "final_value_p90": round(final_p90, 2),
        "fire_number_today": round(fire_number_today, 2),
        "survival_prob_30y": round(survival_prob_30y, 4),
        "median_path": _median_path(accumulation, start_year),
        "n_paths": n_paths,
    }


def _from_profile(
    value: float | None, profile_value: float | None, risk_profile: str, fallback: float
) -> tuple[float, str | None]:
    if value is not None:
        return value, None
    if profile_value is not None:
        return profile_value, f"profil investisseur ({risk_profile})"
    return fallback, None


def resolve_fire_inputs(
    params: FIREProbabilisticParameters,
    current_value: float,
    defaults_from: dict[str, str],
    risk_profile: str | None,
    monthly_dca: Decimal | None,
) -> FireInputs:
    """Complète l'épargne par ``monthly_dca_eur`` (sinon 0) et rendement/volatilité par le profil de risque
    (sinon 7 % / 15 %)."""
    sources = dict(defaults_from)
    profile_name = (risk_profile or "").lower()
    profile = RISK_PROFILE_ASSUMPTIONS.get(profile_name)

    monthly_contribution = params.monthly_contribution
    if monthly_contribution is None:
        if monthly_dca is not None:
            monthly_contribution = float(monthly_dca)
            sources["monthly_contribution"] = "profil investisseur (DCA mensuel)"
        else:
            monthly_contribution = 0.0

    profile_return, profile_volatility = profile if profile is not None else (None, None)
    annual_return_mean, return_source = _from_profile(params.annual_return_mean, profile_return, profile_name, 0.07)
    if return_source is not None:
        sources["annual_return_mean"] = return_source
    annual_volatility, volatility_source = _from_profile(
        params.annual_volatility, profile_volatility, profile_name, 0.15
    )
    if volatility_source is not None:
        sources["annual_volatility"] = volatility_source

    return FireInputs(current_value, monthly_contribution, annual_return_mean, annual_volatility, sources)


def fire_result(params: FIREProbabilisticParameters, inputs: FireInputs, currency: str) -> FIREProbabilisticResult:
    """Simulation complète avec l'écho des hypothèses réellement appliquées dans ``assumptions``."""
    simulation = simulate_fire_probabilistic(
        current_value=inputs.current_value,
        monthly_contribution=inputs.monthly_contribution,
        annual_expenses=params.annual_expenses,
        withdrawal_rate=params.withdrawal_rate,
        annual_return_mean=inputs.annual_return_mean,
        annual_volatility=inputs.annual_volatility,
        inflation=params.inflation,
        index_contributions=params.index_contributions,
        years_horizon=params.years_horizon,
        n_paths=params.n_paths,
        seed=params.seed,
    )
    assumptions: dict[str, Any] = {
        "current_value": round(inputs.current_value, 2),
        "monthly_contribution": round(inputs.monthly_contribution, 2),
        "annual_expenses": round(params.annual_expenses, 2),
        "withdrawal_rate": params.withdrawal_rate,
        "annual_return_mean": inputs.annual_return_mean,
        "annual_volatility": inputs.annual_volatility,
        "inflation": params.inflation,
        "index_contributions": params.index_contributions,
        "years_horizon": params.years_horizon,
        "n_paths": params.n_paths,
        "defaults_from": inputs.defaults_from or None,
    }
    return FIREProbabilisticResult(**simulation, currency=currency, assumptions=assumptions)
