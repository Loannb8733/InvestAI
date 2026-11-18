"""La fiabilité affichée est mesurée sur les prévisions passées vérifiées, jamais estimée.

Avant ce changement, le badge « Fiabilité » valait ``30 + accord des modèles × 65`` et son « N tests » comptait des
modèles : un taux de réussite fictif, présenté comme significatif.
"""

import pytest

from app.domains.predictions.levels import (
    MIN_MEASURED_SAMPLES,
    measured_reliability,
    skill_from_ensemble,
)


def test_no_reliability_without_enough_checked_predictions() -> None:
    result = measured_reliability(MIN_MEASURED_SAMPLES - 1, MIN_MEASURED_SAMPLES - 1, 2.0)
    assert result["hit_rate"] is None
    assert result["reliability_score"] is None
    assert result["model_confidence"] == "insufficient_history"
    assert result["hit_rate_n_samples"] == MIN_MEASURED_SAMPLES - 1
    assert result["hit_rate_significant"] is False


def test_hit_rate_is_the_measured_share_of_correct_directions() -> None:
    result = measured_reliability(12, 9, 3.456)
    assert result["hit_rate"] == 75.0
    assert result["reliability_score"] == 75.0
    assert result["hit_rate_n_samples"] == 12
    assert result["measured_mape"] == pytest.approx(3.46)


def test_significance_needs_15_checks_and_beats_chance() -> None:
    assert measured_reliability(14, 14, None)["hit_rate_significant"] is False
    assert measured_reliability(20, 15, None)["hit_rate_significant"] is True
    assert measured_reliability(20, 12, None)["hit_rate_significant"] is False


@pytest.mark.parametrize(
    ("n", "correct", "confidence"),
    [(20, 15, "useful"), (20, 11, "uncertain"), (20, 8, "unreliable")],
)
def test_confidence_follows_the_measure(n: int, correct: int, confidence: str) -> None:
    assert measured_reliability(n, correct, None)["model_confidence"] == confidence


def test_skill_without_models_is_neutral() -> None:
    assert skill_from_ensemble([]) == 50.0
    assert skill_from_ensemble([{"mape": 5.0, "weight_pct": 100}]) == 80.0
