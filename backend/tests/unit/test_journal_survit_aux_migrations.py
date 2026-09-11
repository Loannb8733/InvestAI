"""Une migration ne doit pas éteindre le journal de l'application.

`alembic/env.py` appelle `fileConfig(alembic.ini)`, qui remplace la
configuration du journal du **processus entier** — et `alembic.ini` y pose
`[logger_root] level = WARN`. Lancé seul, c'est le comportement voulu. Appelé
depuis l'application, cela coupait tous les messages INFO pour le reste de
l'exécution.

Ce que cela coûtait, mesuré le 2026-09-11 sur les journaux réels : **1 214
démarrages, zéro fois** « Alembic migrations applied successfully ». Le message
existe pourtant juste après l'appel — il était émis dans un logger qu'Alembic
venait de faire taire. Et comme `_run_alembic_upgrade` est la première opération
du démarrage, tout ce qui suivait subissait le même sort : le bilan du
rattrapage des hashs, celui des miroirs de transfert, celui des actifs
multiplateformes.

Ce silence a contribué à masquer trois mois durant un rattrapage qui échouait à
chaque démarrage (voir `test_rattrapage_des_hashs`). Un journal muet ne se
remarque pas : il ressemble à un système qui n'a rien à dire.
"""

import logging

import pytest

from app.main import _run_alembic_upgrade


@pytest.fixture
def journal_a_info():
    """Pose le niveau INFO et le rend tel qu'il était, quoi qu'il arrive."""
    racine = logging.getLogger()
    niveau, handlers = racine.level, list(racine.handlers)
    racine.setLevel(logging.INFO)
    yield racine
    racine.setLevel(niveau)
    racine.handlers = handlers


class TestNiveauDuJournal:
    def test_le_niveau_survit_a_une_migration(self, journal_a_info):
        """Le point exact du défaut.

        `WARN` après l'appel signifie que `fileConfig` a parlé : tous les INFO
        de l'application sont perdus pour le reste du processus.
        """
        _run_alembic_upgrade()

        assert journal_a_info.level <= logging.INFO, (
            "Alembic a repris la main sur le journal : les messages INFO de "
            "l'application sont perdus pour le reste de l'exécution"
        )

    def test_un_message_applicatif_passe_encore_apres_la_migration(self, journal_a_info, caplog):
        # Le niveau ne suffit pas : `fileConfig` remplace aussi les
        # gestionnaires, et un logger sans gestionnaire n'écrit nulle part.
        _run_alembic_upgrade()

        with caplog.at_level(logging.INFO, logger="app.main"):
            logging.getLogger("app.main").info("message après migration")

        assert "message après migration" in caplog.text

    def test_la_migration_annonce_son_succes(self, journal_a_info, caplog):
        """Sur 1 214 démarrages réels, ce message n'était jamais apparu.

        Il est émis juste après `command.upgrade`, donc dans le logger
        qu'Alembic venait de faire taire.
        """
        with caplog.at_level(logging.INFO, logger="app.main"):
            _run_alembic_upgrade()

        assert "Alembic migrations applied successfully" in caplog.text


class TestFormeDeLaRegle:
    def test_env_py_respecte_le_drapeau_de_l_application(self):
        """Garde-fou sur la source.

        `configure_logger` est le drapeau que la documentation d'Alembic prévoit
        pour ce cas. Le retirer d'`env.py` rétablirait le silence sans qu'aucun
        test de comportement ne s'en aperçoive dans un processus neuf.
        """
        from pathlib import Path

        env = Path(__file__).resolve().parents[2] / "alembic" / "env.py"
        source = env.read_text()

        assert "configure_logger" in source, "le drapeau a disparu d'env.py"
        assert "fileConfig(config.config_file_name)" in source, "la configuration en ligne de commande reste"

    def test_l_application_pose_le_drapeau(self):
        import inspect

        source = inspect.getsource(_run_alembic_upgrade)

        assert 'attributes["configure_logger"] = False' in source
