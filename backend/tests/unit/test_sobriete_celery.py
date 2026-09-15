"""Le worker Celery ne doit pas épuiser le quota Upstash à vide.

Mesuré au repos avant réglage : 94 commandes Redis par minute (BRPOP toutes les
secondes, battement publié toutes les 2 s), soit ~4 millions par mois pour un
quota de 500 000 — épuisé le 2026-09-15. Après réglage : 6 par minute.
"""

from pathlib import Path

import pytest

from app.tasks.celery_app import celery_app

_RACINE = Path(__file__).resolve().parents[3]


def test_la_file_n_est_pas_interrogee_chaque_seconde():
    options = celery_app.conf.broker_transport_options

    assert options.get("polling_interval", 1) >= 10
    assert options.get("health_check_interval", 25) >= 60


def test_les_resultats_de_taches_ne_sont_pas_ecrits():
    """Aucun code ne les lit ; chaque exécution coûtait cinq commandes ou plus."""
    assert celery_app.conf.task_ignore_result is True
    assert celery_app.conf.task_track_started is False


def test_le_worker_de_production_ne_publie_pas_de_battement():
    chemin = _RACINE / "render.yaml"
    if not chemin.exists():
        # Le conteneur de développement ne monte que backend/ ; la CI, elle,
        # exécute les tests depuis le dépôt complet.
        pytest.skip("render.yaml hors du conteneur")
    render = chemin.read_text(encoding="utf-8")
    commandes = [ligne for ligne in render.splitlines() if "celery_app worker" in ligne]

    assert commandes, "commande du worker introuvable dans render.yaml"
    for commande in commandes:
        for option in ("--without-heartbeat", "--without-gossip", "--without-mingle"):
            assert option in commande, f"{option} manquant : {commande.strip()}"
