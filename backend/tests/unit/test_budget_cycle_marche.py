from pathlib import Path

import app.services.prediction_cycles as pc


def test_le_cycle_de_marche_borne_ses_appels_externes() -> None:
    """Fear & Greed et la dominance BTC restent bornés : l'écran ne doit pas rester figé."""
    source = Path(pc.__file__).read_text(encoding="utf-8")
    assert "wait_for" in source
    assert 0 < pc._BUDGET_APPELS_EXTERNES <= 20
