"""COOKIE_SECURE selon l'environnement : sûr par défaut, abaissé explicitement.

Un cookie `secure` n'est jamais renvoyé par un client parlant en http://. En CI
(APP_ENV=testing, serveur de test en clair), le cookie de session posé au login
n'était donc pas renvoyé au logout : la révocation ne recevait rien à révoquer et
le jeton restait valide. `test_access_token_revoked_after_logout` échouait — sur
un défaut d'environnement, pas sur le code de révocation, qui était correct.

Ces tests pinnent les deux moitiés de la règle : les environnements en clair sont
nommés un par un, et TOUT le reste — production incluse, et tout APP_ENV inconnu —
reste sécurisé. C'est le sens du défaut qui compte : se tromper vers `secure=True`
casse un test, se tromper vers `False` expose un cookie de session en production.
"""

import pytest

from app.core.config import INSECURE_COOKIE_ENVS, Settings


def _cookie_secure_for(app_env: str) -> bool:
    return Settings.auto_cookie_secure(None, type("I", (), {"data": {"APP_ENV": app_env}})())


class TestEnvironnementsEnClair:
    @pytest.mark.parametrize("env", ["development", "testing"])
    def test_pas_de_cookie_secure(self, env):
        assert _cookie_secure_for(env) is False

    def test_la_liste_est_explicite(self):
        assert INSECURE_COOKIE_ENVS == frozenset({"development", "testing"})


class TestResteSecurise:
    @pytest.mark.parametrize("env", ["production", "staging", "prod", "", "TESTING", "Development"])
    def test_cookie_secure_conserve(self, env):
        # Casse comprise : « TESTING » n'est pas « testing », on ne relâche rien
        # sur une variable d'environnement mal orthographiée.
        assert _cookie_secure_for(env) is True

    def test_production_jamais_relachee(self):
        assert "production" not in INSECURE_COOKIE_ENVS

    def test_defaut_sur_env_absent(self):
        # APP_ENV manquant -> "development" par défaut, cohérent avec le reste
        # de la config (un poste de dev ne sert pas en TLS).
        assert Settings.auto_cookie_secure(None, type("I", (), {"data": {}})()) is False
