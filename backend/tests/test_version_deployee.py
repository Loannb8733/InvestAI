"""Marqueur de version exposé par la sonde de vivacité.

Vérifier qu'un déploiement a pris demandait de sonder une route supprimée et
d'espérer un 404 : la méthode ne sert qu'une fois, puis le marqueur est
consommé. Les autres changements d'une release vivent derrière
l'authentification, donc invérifiables de l'extérieur.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

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


class TestVersionDeSchema:
    """Le schéma a-t-il suivi le code ?

    Le conteneur lance `alembic upgrade head || echo "ALEMBIC MIGRATION
    FAILED"` : un échec de migration **ne bloque pas** le démarrage. C'est un
    choix assumé — un déploiement automatique ne doit pas couper le service —
    mais il laissait une question sans réponse depuis l'extérieur : le code
    tourne, et le schéma ?

    Le marqueur de commit répond pour l'un. Ces deux clés répondent pour
    l'autre : `/health` annonce la révision attendue, `/health/ready` la
    compare à celle que la base porte réellement.
    """

    async def test_la_sonde_de_vivacite_annonce_la_revision_attendue(self, client):
        reponse = await client.get("/health")

        assert reponse.status_code == 200
        assert reponse.json()["schema_attendu"] != "inconnue"

    async def test_la_revision_attendue_est_celle_qu_alembic_designe(self):
        """Elle est lue par Alembic, non déduite des fichiers.

        Un premier essai cherchait la révision que nul ne cite en
        `down_revision` : il en trouvait **trois** là où Alembic n'en voit
        qu'une. Le graphe se lit avec l'outil qui le construit.
        """
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from app.main import _REVISION_ATTENDUE

        script = ScriptDirectory.from_config(Config("alembic.ini"))

        assert script.get_heads() == [_REVISION_ATTENDUE]

    async def test_la_sonde_annonce_toujours_la_revision_attendue(self, client):
        """Même quand la base ne peut rien confirmer.

        La base de test est bâtie par `create_all`, non par Alembic : elle n'a
        donc pas de table `alembic_version` et la lecture échoue. C'est le cas
        où l'information a le plus de valeur — et c'est celui où elle manquait,
        la branche d'erreur oubliant de poser la clé. Constaté en CI, invisible
        en local, où la base de test traînait la table d'une migration passée.
        """
        reponse = await client.get("/health/ready")
        corps = reponse.json()

        assert corps["schema_attendu"]
        assert corps["schema_applique"]

    async def test_la_revision_attendue_survit_a_une_base_illisible(self, client):
        """Le défaut exact, et la raison pour laquelle il a échappé au local.

        `/health/ready` interroge le moteur de l'application, non la base de
        test : en local il tombe sur la base de développement, migrée, qui
        porte `alembic_version`. En intégration continue cette table n'existe
        pas, la lecture lève, et la branche d'erreur oubliait de poser
        `schema_attendu` — la seule information encore disponible à ce
        moment-là, puisqu'elle est connue au démarrage sans la base.

        Le test force l'échec de lecture au lieu de dépendre de ce que la base
        locale contient ce jour-là.
        """
        with patch("app.main.engine") as moteur:
            moteur.connect.side_effect = RuntimeError("base injoignable")
            reponse = await client.get("/health/ready")

        corps = reponse.json()
        assert corps["schema_applique"] == "illisible"
        assert corps["schema_attendu"], "l'information la plus utile disparaissait au pire moment"

    async def test_un_schema_lisible_et_concordant_rend_le_service_pret(self, client, monkeypatch):
        from app import main

        with patch.object(main, "_REVISION_ATTENDUE", "abc123"):
            with patch("app.main.engine") as moteur:
                connexion = AsyncMock()
                connexion.execute = AsyncMock(return_value=MagicMock(scalar=lambda: "abc123"))
                moteur.connect.return_value.__aenter__ = AsyncMock(return_value=connexion)
                moteur.connect.return_value.__aexit__ = AsyncMock(return_value=False)
                reponse = await client.get("/health/ready")

        assert reponse.json()["schema_applique"] == reponse.json()["schema_attendu"]

    async def test_un_schema_en_retard_rend_le_service_degrade(self, client, monkeypatch):
        """C'est le cas que tout ceci sert à voir.

        Les deux versions coïncident toujours en test : sans cette simulation,
        retirer la comparaison ne ferait tomber aucun test — le canari l'a
        montré. Une révision attendue différente de celle que porte la base doit
        faire répondre **503**, pour qu'un déploiement dont la migration a
        échoué se voie de l'extérieur.
        """
        from app import main

        monkeypatch.setattr(main, "_REVISION_ATTENDUE", "revision_qui_n_existe_pas")

        reponse = await client.get("/health/ready")

        assert reponse.status_code == 503
        assert reponse.json()["status"] == "degraded"
