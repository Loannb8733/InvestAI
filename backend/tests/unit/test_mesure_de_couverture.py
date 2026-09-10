"""Le réglage sans lequel la couverture des routes est mesurée à côté.

Ce qui s'est passé
------------------
Dix-neuf tests parcouraient `update_transaction` et `delete_transaction` de bout
en bout — création, modification, suppression, miroirs de transfert, tous verts
— et coverage rapportait **12 %** sur le fichier. Le chiffre n'était pas faux
par excès de prudence : il ne voyait tout simplement pas ce qui s'exécutait.

SQLAlchemy 2.0 en mode asyncio fait passer chaque requête par un **greenlet**.
Coverage ne suit pas les greenlets sans qu'on le lui demande : il voit l'appel
entrer dans la route, puis perd la trace au premier `await db.execute(...)` —
c'est-à-dire à la deuxième ligne de la plupart des routes. Tout ce qui suit est
compté comme non exécuté.

L'écart mesuré, la ligne ajoutée puis retirée :

    endpoints/transactions.py    12 %  ->  31 %
    total du projet              47 %  ->  50 %   (561 lignes)

Pourquoi c'est un garde-fou et pas un détail de configuration
--------------------------------------------------------------
La méthode de ce projet est de **mesurer avant d'engager du travail** : la
couverture décide où l'effort va. Un instrument qui sous-estime de trois points
en moyenne, et de vingt points sur les routes proches de la base, envoie
écrire des tests là où il y en a déjà et laisse dans l'ombre ce qui n'en a pas.
Perdre cette ligne ne casserait aucun test — cela fausserait le choix de tous
les suivants.
"""

import configparser
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]


def _configuration() -> configparser.ConfigParser:
    fichier = RACINE / ".coveragerc"
    assert fichier.exists(), (
        f"{fichier} a disparu : la couverture des routes retomberait à un tiers " "de sa valeur réelle"
    )
    config = configparser.ConfigParser()
    config.read(fichier)
    return config


def test_les_greenlets_sont_traces():
    """Sans quoi tout ce qui suit un accès à la base cesse d'être compté."""
    concurrency = _configuration().get("run", "concurrency", fallback="")

    assert "greenlet" in concurrency, (
        "`concurrency = greenlet` a disparu de .coveragerc : la couverture des "
        "routes et des services touchant la base serait à nouveau sous-estimée "
        "d'environ vingt points, et les prochaines cibles choisies sur ce chiffre"
    )


def test_les_threads_sont_traces():
    """Starlette exécute les dépendances synchrones dans son pool de threads."""
    assert "thread" in _configuration().get("run", "concurrency", fallback="")
