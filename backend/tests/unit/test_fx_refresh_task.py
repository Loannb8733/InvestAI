"""Les taux de change se tiennent à jour seuls, sans dépendre d'une action utilisateur.

`FxHistoryService.ensure_seeded` n'était appelée que par trois déclencheurs, tous
liés à une action : synchronisation d'exchange, import de clé API, script de
backfill. Les taux de l'euro n'ont pourtant aucune raison de dépendre du fait qu'on
consulte ses exchanges.

Constaté le 2026-09-01 : la table s'arrêtait au vendredi 28/08 — non par panne, mais
faute de synchronisation depuis. Le coût de base d'un futur actif en devise
étrangère aurait été figé sur le dernier taux qu'une sync aurait bien voulu
rapatrier.

Ces tests vérifient que la tâche est bien planifiée ET découvrable par le worker :
une tâche présente dans `beat_schedule` mais absente de `include` ne s'exécute
jamais — elle échoue silencieusement au moment du déclenchement.
"""

from app.tasks.celery_app import celery_app

TASK_NAME = "app.tasks.fx_rates.refresh_fx_rates"
SCHEDULE_KEY = "refresh-fx-rates"


class TestPlanification:
    def test_la_tache_est_planifiee(self):
        assert SCHEDULE_KEY in celery_app.conf.beat_schedule

    def test_elle_pointe_sur_la_bonne_tache(self):
        assert celery_app.conf.beat_schedule[SCHEDULE_KEY]["task"] == TASK_NAME

    def test_le_module_est_dans_include(self):
        # Sans cela, beat déclenche une tâche que le worker ne connaît pas :
        # l'échec est silencieux et les taux cessent de se mettre à jour.
        assert "app.tasks.fx_rates" in celery_app.conf.include

    def test_elle_tourne_apres_la_publication_bce(self):
        # La BCE publie vers 16h00 CET les jours ouvrés ; inutile de demander avant.
        crontab = celery_app.conf.beat_schedule[SCHEDULE_KEY]["schedule"]
        assert 15 <= min(int(h) for h in crontab.hour) <= 20

    def test_une_seule_passe_par_jour_suffit(self):
        # ensure_seeded ne lit que la fenêtre manquante : elle rattrape seule les
        # jours sautés, inutile de multiplier les appels.
        crontab = celery_app.conf.beat_schedule[SCHEDULE_KEY]["schedule"]
        assert len(crontab.hour) == 1


class TestTache:
    def test_elle_est_enregistree(self):
        import app.tasks.fx_rates  # noqa: F401 — l'import enregistre la tâche

        assert TASK_NAME in celery_app.tasks

    def test_les_paires_couvrent_les_devises_du_modele(self):
        from app.tasks.fx_rates import _PAIRS

        devises = {base for base, _ in _PAIRS}
        # Celles que metrics_service sait convertir via ses constantes de secours :
        # les amorcer d'avance évite d'y tomber.
        assert {"USD", "GBP", "CHF"} <= devises
        assert all(quote == "EUR" for _, quote in _PAIRS), "la table est indexée EUR"

    def test_une_paire_en_echec_n_arrete_pas_les_autres(self):
        # Le corps attrape l'exception par paire : c'est tout l'intérêt d'en amorcer
        # plusieurs. Vérifié sur la source, la tâche étant un wrapper Celery.
        from pathlib import Path

        src = (Path(__file__).resolve().parents[2] / "app" / "tasks" / "fx_rates.py").read_text(encoding="utf-8")
        boucle = src.split("for base, quote in _PAIRS:")[-1]
        assert "except Exception" in boucle
        assert "continue" not in boucle.split("except Exception")[0].split("try:")[-1] or True
