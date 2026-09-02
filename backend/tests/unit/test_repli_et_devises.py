"""Deux défauts trouvés en profilant le dashboard : un filet muet, des appels perdus.

Le repli PostgreSQL ne fonctionnait dans aucun chemin web
---------------------------------------------------------
`history_cache.get_cached_history` est synchrone et faisait
`run_async(_load_prices_from_db(...))` pour son dernier recours. Or elle est
appelée par `snapshot_service`, `metrics_service` et `analytics_service` — tous
dans une boucle d'événements. On ne peut pas démarrer une boucle dans une
boucle : l'exception était avalée par le `except` voisin, la coroutine jamais
attendue, et le repli rendait `[], []` en silence.

Mesuré avant correction : **91 prix depuis un script, 0 depuis un endpoint**.
Un filet de sécurité qui ne se déclenche que là où on n'en a pas besoin.

`fee_currency` n'est pas toujours une monnaie
----------------------------------------------
Payer ses frais en PAXG ou en OM est courant sur un exchange, et la base en
contient 65. Chacune déclenchait un appel à
`exchangerate-api.com/v4/latest/PAXG` — 404 systématique, requête perdue à
chaque calcul de métriques.
"""

import ast
import inspect
from pathlib import Path

import pytest

from app.services.price_service import PriceService
from app.tasks import history_cache


class TestRepliPostgres:
    def test_le_repli_n_utilise_plus_run_async(self):
        source = inspect.getsource(history_cache.get_cached_history)
        assert "run_async" not in source, (
            "`run_async` dans une fonction synchrone appelée depuis des services web : "
            "impossible de démarrer une boucle dans une boucle, le repli reste muet"
        )

    def test_le_repli_lit_bien_postgres(self):
        source = inspect.getsource(history_cache.get_cached_history)
        assert "_charger_prix_depuis_db_sync" in source, (
            "le dernier recours PostgreSQL a disparu : un Redis vide rendrait "
            "une série vide alors que la base a l'historique"
        )

    def test_la_lecture_synchrone_ne_cree_aucune_boucle(self):
        arbre = ast.parse(inspect.getsource(history_cache._charger_prix_depuis_db_sync))
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Await):
                pytest.fail("un `await` ici exigerait une boucle — c'est précisément le bug corrigé")
        # Docstring retirée avant l'inspection : celle de la fonction cite
        # `run_async` pour expliquer le bug qu'elle corrige, et la lire ferait
        # échouer le test qu'elle documente. Cinquième occurrence du motif dans
        # cette session — un contrôle statique doit porter sur le code exécuté.
        corps = arbre.body[0]
        if corps.body and isinstance(corps.body[0], ast.Expr) and isinstance(corps.body[0].value, ast.Constant):
            corps.body = corps.body[1:]

        source = ast.unparse(arbre)
        for interdit in ("asyncio", "run_async", "AsyncSessionLocal"):
            assert interdit not in source, f"`{interdit}` réintroduit une dépendance à une boucle"

    def test_les_taches_celery_gardent_run_async(self):
        """Les autres appels sont légitimes : une tâche Celery n'a pas de boucle."""
        source = Path(history_cache.__file__).read_text(encoding="utf-8")
        assert source.count("run_async(") >= 3, (
            "les tâches Celery doivent continuer d'utiliser run_async : elles "
            "s'exécutent hors boucle, c'est le cas prévu"
        )


class TestDevisesReelles:
    @pytest.mark.parametrize("code", ["PAXG", "OM", "BTC", "USDC", "PEPE", "SOL03"])
    @pytest.mark.asyncio
    async def test_un_symbole_crypto_ne_declenche_aucun_appel(self, code):
        # `SOL03` figure aussi en base : une valeur manifestement corrompue, que
        # la liste blanche écarte au même titre.
        assert await PriceService().get_forex_rate(code, "EUR") is None

    @pytest.mark.parametrize("code", ["EUR", "USD", "GBP", "CHF"])
    def test_les_monnaies_de_l_application_restent_acceptees(self, code):
        assert code in PriceService.DEVISES_FIAT, (
            f"{code} est proposée dans les préférences utilisateur : la retirer "
            "de la liste blanche couperait la conversion pour ces comptes"
        )

    def test_la_liste_est_blanche_et_non_noire(self):
        """Une liste noire laisserait passer tout symbole crypto non prévu."""
        source = inspect.getsource(PriceService.get_forex_rate)
        assert "DEVISES_FIAT" in source and "not in" in source, (
            "la garde doit vérifier l'appartenance à la liste des monnaies, " "pas l'absence d'une liste de cryptos"
        )
