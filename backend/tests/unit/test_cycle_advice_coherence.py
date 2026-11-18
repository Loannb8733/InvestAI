"""Les repères de cycle restent de l'information générale.

Contrat vérifié :
1. Chaque phase produit des repères descriptifs (CONTEXTE, RISQUE, HISTORIQUE), jamais une consigne.
2. Aucun texte ne contient de montant en euros, quel que soit le portefeuille.
3. Une concentration de risque au-delà de 60 % produit un constat CONCENTRATION de priorité critique.
"""

import re

import pytest

from app.domains.predictions.cycle_advice import CONCENTRATION, CONTEXT, HISTORY, RISK, cycle_advice

THEMES = {CONCENTRATION, CONTEXT, HISTORY, RISK}
IMPERATIVES = re.compile(
    r"\b(achetez|vendez|prenez|placez|accumulez|renforcez|réduisez|évitez|investissez|n'achetez|attendez|"
    r"préparez|remontez|identifiez|privilégiez|sécurisez)\b",
    re.IGNORECASE,
)

PHASES = [
    ("bottom", 25),
    ("bearish", 30),
    ("bearish", 10),
    ("top", 60),
    ("bullish", 90),
    ("bullish", 60),
    ("unknown", 50),
]


@pytest.mark.parametrize(("regime", "fear_greed"), PHASES)
@pytest.mark.parametrize("portfolio_value", [0.0, 863.90, 100_000.0])
def test_advice_is_descriptive_without_amounts(regime: str, fear_greed: int, portfolio_value: float) -> None:
    advice = cycle_advice(regime=regime, cycle_pos=50, fear_greed=fear_greed, portfolio_value=portfolio_value)
    assert advice
    for item in advice:
        assert item["action"] in THEMES, item
        text = f"{item['title']} {item['description']}"
        assert "€" not in text, f"montant dans : {text}"
        assert not IMPERATIVES.search(text), f"consigne dans : {text}"


def test_high_concentration_is_reported_as_critical() -> None:
    advice = cycle_advice(regime="bottom", cycle_pos=10, fear_greed=15, portfolio_value=863.90, max_risk_weight=75.0)
    concentration = [a for a in advice if a["action"] == CONCENTRATION]
    assert concentration and concentration[0]["priority"] == "critical"
    assert "75 %" in concentration[0]["description"]


def test_no_concentration_warning_when_balanced() -> None:
    advice = cycle_advice(regime="bottom", cycle_pos=10, fear_greed=15, portfolio_value=863.90, max_risk_weight=30.0)
    assert all(a["action"] != CONCENTRATION for a in advice)


def test_extreme_fear_and_greed_pick_the_matching_phase() -> None:
    fear = cycle_advice(regime="bullish", cycle_pos=50, fear_greed=10)
    greed = cycle_advice(regime="bearish", cycle_pos=50, fear_greed=90)
    assert fear[0]["title"] == "Phase de creux potentiel"
    assert greed[0]["title"] == "Marché baissier"
