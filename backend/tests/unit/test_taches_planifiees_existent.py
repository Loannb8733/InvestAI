"""Chaque tâche du planificateur doit exister et être importable.

`beat_schedule` désigne ses tâches par leur nom complet
(`app.tasks.cleanup.run_weekly_cleanup`). Rien ne relie ce texte au code : une
fonction renommée, un module déplacé, et Celery échoue **à l'exécution** — dans
ses journaux, où l'on ne regarde pas. C'est ainsi que le `TypeError` quotidien
de NEW-42 a pu passer des mois inaperçu.

Exécuter les tâches elles-mêmes n'est pas possible ici : elles passent par
`run_async`, qui installe une boucle d'événements neuve puis la ferme. Depuis
la suite, cela retirerait sa boucle à l'appelant — le module `async_runner`
garde la trace des 103 tests tombés le jour où ce comportement a été tenté.

Ce test vérifie donc ce qui l'est sans les lancer : que chaque nom désigne une
tâche réelle, et que le nom déclaré sur la tâche correspond à celui que le
planificateur appelle.
"""

import importlib

import pytest

from app.tasks.celery_app import celery_app

PLANIFIEES = sorted({cfg["task"] for cfg in celery_app.conf.beat_schedule.values()})


def test_le_planificateur_n_est_pas_vide():
    assert len(PLANIFIEES) >= 20, "le planificateur a maigri — changement volontaire ?"


@pytest.mark.parametrize("nom_complet", PLANIFIEES)
def test_chaque_tache_planifiee_existe(nom_complet):
    chemin_module, nom_fonction = nom_complet.rsplit(".", 1)

    module = importlib.import_module(chemin_module)
    tache = getattr(module, nom_fonction, None)

    assert tache is not None, (
        f"{chemin_module} n'expose pas `{nom_fonction}` — le planificateur "
        "l'appellera et Celery échouera dans ses journaux."
    )


@pytest.mark.parametrize("nom_complet", PLANIFIEES)
def test_le_nom_declare_correspond_a_celui_du_planificateur(nom_complet):
    """`@celery_app.task(name=...)` doit dire la même chose que `beat_schedule`.

    Les deux se recopient à la main : un module renommé d'un côté et pas de
    l'autre passe la vérification d'existence mais échoue au routage.
    """
    chemin_module, nom_fonction = nom_complet.rsplit(".", 1)
    tache = getattr(importlib.import_module(chemin_module), nom_fonction)

    assert getattr(tache, "name", None) == nom_complet
