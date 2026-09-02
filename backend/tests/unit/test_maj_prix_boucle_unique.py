"""`update_all_prices` doit tenir dans une seule boucle, et appeler des méthodes qui existent.

Deux défauts empilés, l'un masquant l'autre
--------------------------------------------
La tâche appelait en direct `update_crypto_prices()`, `update_stock_prices()` et
`update_exchange_rates()`. Chacune fait son propre `run_async`, donc sa propre
boucle — alors que l'engine SQLAlchemy async garde ses connexions attachées à la
première. La deuxième échouait sur « Task attached to a different loop ».

Le défaut était **latent** : seules les tâches crypto et actions sont
planifiées, séparément, donc chacune a bien sa boucle en production. Il ne
piégeait que celui qui déclenchait `update_all_prices` à la main.

Une fois la boucle unifiée, un second bug est apparu derrière :
`price_service.get_exchange_rate(...)` n'a jamais existé — la méthode s'appelle
`get_forex_rate`. L'`AttributeError` était rattrapée par le `except` voisin, si
bien que la tâche rapportait « 0 mis à jour » sans jamais rien tenter. Après
correction : **6 taux mis à jour** au lieu de 0.
"""

import ast
import inspect
from pathlib import Path

from app.services.price_service import PriceService
from app.tasks import price_updates


class TestBoucleUnique:
    def test_la_tache_globale_n_appelle_plus_les_taches_celery(self):
        source = inspect.getsource(price_updates.update_all_prices)
        for tache in ("update_crypto_prices()", "update_stock_prices()", "update_exchange_rates()"):
            assert tache not in source, (
                f"`{tache}` appelée en direct : chaque tâche ouvre sa propre boucle "
                "et la seconde casse sur « Task attached to a different loop »"
            )

    def test_elle_enchaine_les_coroutines_dans_une_seule_boucle(self):
        source = inspect.getsource(price_updates.update_all_prices)
        assert source.count("run_async(") == 1, "une seule boucle doit être ouverte"
        for coro in ("_maj_crypto", "_maj_actions", "_maj_taux_change"):
            assert coro in source, f"{coro} n'est plus enchaînée par la tâche globale"

    def test_les_coroutines_sont_accessibles_au_niveau_module(self):
        """Imbriquées, elles ne pouvaient pas être enchaînées par un appelant."""
        for nom in ("_maj_crypto", "_maj_actions", "_maj_taux_change"):
            assert inspect.iscoroutinefunction(
                getattr(price_updates, nom, None)
            ), f"{nom} n'est pas une coroutine de module : la tâche globale ne peut pas l'appeler"

    def test_chaque_tache_garde_sa_propre_boucle(self):
        """Lancées séparément par le planificateur, elles doivent rester autonomes."""
        for tache in ("update_crypto_prices", "update_stock_prices", "update_exchange_rates"):
            source = inspect.getsource(getattr(price_updates, tache))
            assert "run_async(" in source, f"{tache} n'ouvre plus de boucle : elle échouerait hors contexte async"


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
