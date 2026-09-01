"""Découpage de `prediction_service.py` (ARC-05) : l'API publique doit rester intacte.

Le fichier dépassait 2 400 lignes. Les signaux alpha, la carte de stratégie et le
« what-if » en formaient le bloc le plus volumineux et le plus autonome : ils ont été
extraits dans `PredictionAlphaMixin`, en suivant la convention déjà en place
(`PredictionCyclesMixin`, `PredictionMetricsMixin`).

Un découpage par mixin ne change rien à l'usage — `PredictionService` expose les
mêmes méthodes — mais il casse silencieusement si un mixin cesse d'être hérité :
l'appel lève alors un AttributeError à l'exécution, pas à l'import. D'où ces tests.
"""

from pathlib import Path

import pytest

from app.services.prediction_service import PredictionService

_SERVICES = Path(__file__).resolve().parents[2] / "app" / "services"

# Ce que le service doit exposer, quel que soit le fichier qui l'implémente.
API_PUBLIQUE = [
    "get_price_prediction",
    "detect_anomalies",
    "get_market_sentiment",
    "get_portfolio_predictions",
    "get_top_alpha_asset",
    "get_strategy_map",
    "get_what_if",
    "get_market_events",
    "get_track_record",
    "get_portfolio_backtest",
]


class TestApiPublique:
    @pytest.mark.parametrize("methode", API_PUBLIQUE)
    def test_la_methode_reste_accessible(self, methode):
        assert hasattr(
            PredictionService(), methode
        ), f"{methode} n'est plus atteignable — un mixin a-t-il cessé d'être hérité ?"

    def test_les_trois_mixins_sont_herites(self):
        noms = {c.__name__ for c in PredictionService.__mro__}
        assert {"PredictionAlphaMixin", "PredictionCyclesMixin", "PredictionMetricsMixin"} <= noms


class TestDecoupage:
    def test_alpha_vit_dans_son_propre_module(self):
        src = (_SERVICES / "prediction_alpha.py").read_text(encoding="utf-8")
        for methode in ("get_top_alpha_asset", "get_strategy_map", "get_what_if"):
            assert f"def {methode}" in src

    def test_le_fichier_d_origine_a_bien_maigri(self):
        lignes = len((_SERVICES / "prediction_service.py").read_text(encoding="utf-8").splitlines())
        # 2 416 lignes avant extraction. Le seuil laisse de la marge, mais empêche
        # que le fichier regrossisse jusqu'à son point de départ.
        assert lignes < 2000, f"prediction_service.py fait {lignes} lignes"

    def test_aucune_methode_dupliquee_entre_les_deux(self):
        # Un copier-coller au lieu d'un déplacement passerait les tests d'API tout
        # en laissant deux implémentations à faire diverger.
        import re

        def methodes(f):
            return set(re.findall(r"^    (?:async )?def (\w+)", (_SERVICES / f).read_text(encoding="utf-8"), re.M))

        communes = methodes("prediction_service.py") & methodes("prediction_alpha.py")
        assert not communes, f"méthodes présentes des deux côtés : {communes}"
