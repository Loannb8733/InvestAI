"""Les tâches de prix n'appellent que des méthodes qui existent sur PriceService."""

import ast
from pathlib import Path

from app.services.price_service import PriceService
from app.tasks import price_updates


class TestMethodesExistantes:
    def test_aucun_appel_a_une_methode_absente_de_price_service(self):
        """Le `except` voisin transformait l'AttributeError en « 0 mis à jour »."""
        source = Path(price_updates.__file__).read_text(encoding="utf-8")
        arbre = ast.parse(source)

        appelees = set()
        for noeud in ast.walk(arbre):
            if (
                isinstance(noeud, ast.Call)
                and isinstance(noeud.func, ast.Attribute)
                and isinstance(noeud.func.value, ast.Name)
                and noeud.func.value.id == "price_service"
            ):
                appelees.add(noeud.func.attr)

        assert appelees, "aucun appel à price_service détecté : le test ne protège plus rien"
        manquantes = [m for m in appelees if not hasattr(PriceService, m)]
        assert not manquantes, (
            f"méthode(s) inexistante(s) sur PriceService : {manquantes} — "
            "l'AttributeError serait avalée et la tâche rapporterait un succès vide"
        )
