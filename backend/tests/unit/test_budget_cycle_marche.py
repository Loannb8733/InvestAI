from pathlib import Path

import app.domains.predictions.cycles as pc


def test_le_cycle_de_marche_borne_ses_appels_externes() -> None:
    """Fear & Greed et la dominance BTC restent bornés : l'écran ne doit pas rester figé."""
    source = Path(pc.__file__).read_text(encoding="utf-8")
    assert "wait_for" in source
    assert 0 < pc.EXTERNAL_CALL_BUDGET <= 20
