"""Tests unitaires du moteur FIRE probabiliste (fonction pure, seed fixé).

Valide :
1. Volatilité quasi nulle → l'année FIRE médiane colle au croisement
   déterministe (tolérance ±1 an) et la proba bascule ~0 → ~1 autour.
2. Valeur de départ >= nombre FIRE → prob_by_year[0] == 1.0 (état absorbant).
3. Contribution énorme → prob_at_horizon ≈ 1 ; contribution nulle + valeur
   faible + horizon court → ≈ 0.
4. index_contributions=False ⇒ proba <= celle avec True (mêmes chemins).
5. survival_prob_30y dans le bon ordre de grandeur Trinity pour 4 %/7 %/15 %.
"""

import math

from app.api.v1.endpoints.simulations import simulate_fire_probabilistic

START_YEAR = 2026
SEED = 42

BASE_PARAMS = {
    "current_value": 100_000.0,
    "monthly_contribution": 1_000.0,
    "annual_expenses": 36_000.0,
    "withdrawal_rate": 0.04,
    "annual_return_mean": 0.07,
    "annual_volatility": 0.15,
    "inflation": 0.02,
    "index_contributions": True,
    "years_horizon": 30,
    "n_paths": 1000,
    "seed": SEED,
    "start_year": START_YEAR,
}


def run(**overrides):
    params = {**BASE_PARAMS, **overrides}
    return simulate_fire_probabilistic(**params)


def deterministic_fire_year(
    current_value: float,
    monthly_contribution: float,
    annual_expenses: float,
    withdrawal_rate: float,
    annual_return: float,
    inflation: float,
    index_contributions: bool,
    years_horizon: int,
) -> int | None:
    """Croisement déterministe (croissance mensuelle certaine, mêmes conventions)."""
    fire_number_0 = annual_expenses / withdrawal_rate
    if current_value >= fire_number_0:
        return 0
    growth = (1.0 + annual_return) ** (1.0 / 12.0)
    infl_m = (1.0 + inflation) ** (1.0 / 12.0)
    value = current_value
    for t in range(years_horizon * 12):
        contribution = monthly_contribution * (infl_m**t) if index_contributions else monthly_contribution
        value = value * growth + contribution
        if value >= fire_number_0 * (infl_m ** (t + 1)):
            return math.ceil((t + 1) / 12)
    return None


class TestFireProbabilistic:
    def test_near_zero_vol_matches_deterministic_crossing(self):
        """Vol 0.01 + rendement 7 % : année médiane ≈ croisement déterministe ±1 an."""
        result = run(annual_volatility=0.01)
        det_years = deterministic_fire_year(
            current_value=BASE_PARAMS["current_value"],
            monthly_contribution=BASE_PARAMS["monthly_contribution"],
            annual_expenses=BASE_PARAMS["annual_expenses"],
            withdrawal_rate=BASE_PARAMS["withdrawal_rate"],
            annual_return=BASE_PARAMS["annual_return_mean"],
            inflation=BASE_PARAMS["inflation"],
            index_contributions=True,
            years_horizon=BASE_PARAMS["years_horizon"],
        )
        assert det_years is not None, "le scénario de base doit croiser dans l'horizon"
        assert result["fire_year_p50"] is not None
        median_offset = result["fire_year_p50"] - START_YEAR
        assert abs(median_offset - det_years) <= 1, f"médiane {median_offset} ans vs déterministe {det_years} ans"

        # La proba cumulée bascule de ~0 à ~1 autour du croisement déterministe.
        probs = {e["year"] - START_YEAR: e["prob"] for e in result["prob_by_year"]}
        assert probs[max(det_years - 3, 0)] <= 0.2
        assert probs[min(det_years + 3, BASE_PARAMS["years_horizon"])] >= 0.8

    def test_already_fire_probability_is_one_at_year_zero(self):
        """current_value >= nombre FIRE (900 k) → prob_by_year[0].prob == 1.0."""
        result = run(current_value=1_000_000.0)
        assert result["fire_number_today"] == 900_000.0
        assert result["prob_by_year"][0]["prob"] == 1.0
        assert result["prob_at_horizon"] == 1.0
        assert result["fire_year_p10"] == START_YEAR
        assert result["fire_year_p50"] == START_YEAR
        assert result["fire_year_p90"] == START_YEAR

    def test_huge_contribution_reaches_fire_almost_surely(self):
        """Contribution de 20 k€/mois → quasi-certitude d'être FIRE à l'horizon."""
        result = run(monthly_contribution=20_000.0)
        assert result["prob_at_horizon"] >= 0.99

    def test_no_contribution_low_value_short_horizon_never_fire(self):
        """1 k€ de départ, 0 contribution, 5 ans → proba ≈ 0."""
        result = run(current_value=1_000.0, monthly_contribution=0.0, years_horizon=5)
        assert result["prob_at_horizon"] <= 0.01
        assert result["fire_year_p50"] is None
        assert result["fire_year_p90"] is None

    def test_unindexed_contributions_never_beat_indexed(self):
        """index_contributions=False ⇒ prob_at_horizon <= version indexée (même seed)."""
        indexed = run(index_contributions=True)
        flat = run(index_contributions=False)
        assert flat["prob_at_horizon"] <= indexed["prob_at_horizon"]

    def test_survival_prob_matches_trinity_order_of_magnitude(self):
        """Retrait 4 %, rendement 7 %, vol 15 % → survie 30 ans dans [0.7, 1.0]."""
        result = run()
        assert 0.7 <= result["survival_prob_30y"] <= 1.0

    def test_percentile_years_are_ordered_and_final_values_monotonic(self):
        """Cohérence interne : p10 (optimiste) <= p50 <= p90 ; percentiles finaux croissants."""
        result = run()
        years = [result["fire_year_p10"], result["fire_year_p50"], result["fire_year_p90"]]
        present = [y for y in years if y is not None]
        assert present == sorted(present)
        # p10 atteint avant p50 avant p90 (quantiles d'une distribution cumulée)
        if result["fire_year_p10"] is not None and result["fire_year_p50"] is not None:
            assert result["fire_year_p10"] <= result["fire_year_p50"]
        assert result["final_value_p10"] <= result["final_value_p50"] <= result["final_value_p90"]
        # Les probas cumulées sont non décroissantes (état absorbant)
        probs = [e["prob"] for e in result["prob_by_year"]]
        assert all(a <= b for a, b in zip(probs, probs[1:], strict=False))

    def test_seed_reproducibility(self):
        """Même seed → résultats strictement identiques."""
        a = run()
        b = run()
        assert a == b
