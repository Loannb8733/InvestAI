"""Marqueur de version exposé par la sonde de vivacité.

Vérifier qu'un déploiement a pris demandait de sonder une route supprimée et
d'espérer un 404 : la méthode ne sert qu'une fois, puis le marqueur est
consommé. Les autres changements d'une release vivent derrière
l'authentification, donc invérifiables de l'extérieur.
"""

from datetime import datetime

from app.main import health_check, resoudre_commit


class TestResolutionDuCommit:
    def test_lit_la_variable_de_render(self):
        assert resoudre_commit({"RENDER_GIT_COMMIT": "429d948f0e1c2b3a4d5e6f7"}) == "429d948"

    def test_repli_sur_git_commit(self):
        """Pour les autres hébergeurs et Docker local."""
        assert resoudre_commit({"GIT_COMMIT": "abcdef1234567"}) == "abcdef1"

    def test_render_prime_sur_le_repli(self):
        env = {"RENDER_GIT_COMMIT": "1111111aaaa", "GIT_COMMIT": "2222222bbbb"}
        assert resoudre_commit(env) == "1111111"

    def test_sans_variable_le_marqueur_est_explicite(self):
        """« inconnu » plutôt qu'une chaîne vide : l'absence doit se lire."""
        assert resoudre_commit({}) == "inconnu"

    def test_variable_vide_traitee_comme_absente(self):
        assert resoudre_commit({"RENDER_GIT_COMMIT": "   "}) == "inconnu"

    def test_sha_tronque_a_sept_caracteres(self):
        """Assez pour identifier une version, pas plus que ce que dit `git log`."""
        assert len(resoudre_commit({"GIT_COMMIT": "0123456789abcdef"})) == 7

    def test_sha_deja_court_conserve(self):
        assert resoudre_commit({"GIT_COMMIT": "abc12"}) == "abc12"


class TestSondeDeVivacite:
    """`asyncio_mode = auto` : ces tests s'exécutent sur la boucle de session.

    Ne jamais y appeler `asyncio.run()` — il ferme la boucle partagée par toute
    la suite, et les tests suivants deviennent des coroutines jamais attendues.
    """

    async def test_expose_le_commit_et_l_heure_de_demarrage(self):
        reponse = await health_check()
        assert reponse["status"] == "alive"
        assert "commit" in reponse
        assert "demarre_a" in reponse

    async def test_l_heure_de_demarrage_est_datable(self):
        reponse = await health_check()
        # Lève si le format n'est pas ISO 8601.
        datetime.fromisoformat(reponse["demarre_a"])

    async def test_l_heure_ne_bouge_pas_entre_deux_appels(self):
        """C'est le démarrage du processus, pas l'heure courante — un
        redémarrage se lit donc à ce champ."""
        assert (await health_check())["demarre_a"] == (await health_check())["demarre_a"]
