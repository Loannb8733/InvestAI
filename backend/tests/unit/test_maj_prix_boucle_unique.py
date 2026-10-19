"""Les tâches de prix n'appellent que des méthodes qui existent sur la façade de prix."""

import ast
from pathlib import Path

from app.domains.market_data.prices.service import PriceService
from app.tasks import price_updates


class TestMethodesExistantes:
    def test_aucun_appel_a_une_methode_absente_de_la_facade(self) -> None:
        """Le `except` voisin transformait l'AttributeError en « 0 mis à jour »."""
        arbre = ast.parse(Path(price_updates.__file__).read_text(encoding="utf-8"))
        appelees = {
            noeud.func.attr
            for noeud in ast.walk(arbre)
            if isinstance(noeud, ast.Call)
            and isinstance(noeud.func, ast.Attribute)
            and isinstance(noeud.func.value, ast.Name)
            and noeud.func.value.id == "price_feed"
        }
        assert appelees, "aucun appel à price_feed détecté : le test ne protège plus rien"
        assert not [m for m in appelees if not hasattr(PriceService, m)]
