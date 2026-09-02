"""Le classifieur d'erreurs d'exchange ne doit exister qu'une fois.

Pourquoi c'est une règle et pas un détail
-----------------------------------------
La même fonction vivait en double : dans la tâche de synchronisation et dans les
endpoints de clés API. Les deux copies **avaient déjà commencé à diverger** —
celle des endpoints avait perdu son `logger.error` final, si bien qu'une erreur
générique n'y laissait aucune trace là où la tâche la journalisait.

C'est le défaut habituel de la duplication : invisible tant que les copies se
ressemblent, et quand elles divergent, rien ne dit laquelle a raison. Ici,
l'écart portait précisément sur la capacité à diagnostiquer un incident.
"""

import ast
from pathlib import Path

import pytest

import app.api.v1.endpoints.api_keys as endpoints_cles
import app.tasks.sync_exchanges as tache_sync
from app.services.exchange_error_classifier import classify_and_mark_error


class CleFactice:
    """Enregistre l'appel reçu, sans dépendre du modèle SQLAlchemy."""

    def __init__(self):
        self.id = "cle-test"
        self.appels = []

    def mark_auth_failure(self, message):
        self.appels.append(("auth", message))

    def mark_rate_limited(self, message):
        self.appels.append(("debit", message))

    def mark_error(self, message):
        self.appels.append(("generique", message))


class TestUneSeuleImplementation:
    def test_les_deux_modules_pointent_la_meme_fonction(self):
        assert tache_sync._classify_and_mark_error is classify_and_mark_error
        assert endpoints_cles._classify_and_mark_error is classify_and_mark_error

    @pytest.mark.parametrize(
        "chemin",
        ["app/tasks/sync_exchanges.py", "app/api/v1/endpoints/api_keys.py"],
    )
    def test_aucune_copie_locale_ne_reapparait(self, chemin):
        source = Path("/app", chemin).read_text(encoding="utf-8")
        definitions = [
            n.name
            for n in ast.walk(ast.parse(source))
            if isinstance(n, ast.FunctionDef) and "classify_and_mark_error" in n.name
        ]
        assert not definitions, (
            f"{chemin} redéfinit le classifieur : les copies divergent en silence, "
            "et rien n'indique laquelle fait autorité"
        )


class TestComportement:
    """Les trois issues doivent rester distinctes : elles n'ont pas les mêmes suites."""

    def test_401_desactive_la_cle(self):
        import httpx

        cle = CleFactice()
        reponse = httpx.Response(401, request=httpx.Request("GET", "https://exchange.test"))
        classify_and_mark_error(cle, httpx.HTTPStatusError("nope", request=reponse.request, response=reponse))
        assert cle.appels == [("auth", "nope")]

    def test_429_ne_desactive_pas_la_cle(self):
        """Une limite de débit est passagère : désactiver la clé serait excessif."""
        import httpx

        cle = CleFactice()
        reponse = httpx.Response(429, request=httpx.Request("GET", "https://exchange.test"))
        classify_and_mark_error(cle, httpx.HTTPStatusError("trop", request=reponse.request, response=reponse))
        assert cle.appels == [("debit", "trop")]

    def test_kraken_signale_son_refus_dans_le_corps(self):
        """Kraken répond 200 avec l'erreur en JSON : sans ce cas, la clé resterait active."""
        cle = CleFactice()
        classify_and_mark_error(cle, Exception("EAPI:Invalid key"))
        assert cle.appels == [("auth", "EAPI:Invalid key")]

    def test_une_erreur_quelconque_reste_generique(self):
        cle = CleFactice()
        classify_and_mark_error(cle, Exception("timeout réseau"))
        assert cle.appels == [("generique", "timeout réseau")]

    def test_l_erreur_generique_est_journalisee(self, caplog):
        """C'est la ligne que la copie des endpoints avait perdue."""
        import logging

        cle = CleFactice()
        with caplog.at_level(logging.ERROR):
            classify_and_mark_error(cle, Exception("panne"))
        assert any(
            "sync error" in m for m in caplog.messages
        ), "une erreur générique sans trace laisse un incident indiagnosticable"
