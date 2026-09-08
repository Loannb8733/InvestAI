"""Aucun repli du cœur financier ne doit être muet.

Deux défauts de cette famille ont été corrigés — les alertes qui retombaient sur
le prix de revient (NEW-35) et l'échec d'analyse devenu « Bonne diversification »
(NEW-36). Les gestionnaires restants ont été examinés un par un : leurs valeurs
de secours sont **défendables** (mettre zéro à la place afficherait souvent un
faux zéro rassurant, exactement le motif qu'on vient de corriger).

Ce qui ne l'était pas, c'est leur silence. Une panne durable du fournisseur de
prix, du cache d'historique ou de la détection de régime ne laissait aucune
trace : rien à lire dans les journaux pour comprendre pourquoi les chiffres
paraissent figés.

Ce test tient la règle sur les fichiers du cœur financier. Il est statique — le
comportement à verrouiller est déclaratif, et monter chaque chemin d'échec
coûterait bien plus qu'il ne rapporte.
"""

import ast
from pathlib import Path

import pytest

# Fichiers où un échec silencieux fausse un chiffre affiché à l'utilisateur.
MODULES_SENSIBLES = [
    "app.services.alert_service",
    "app.services.metrics_service",
    "app.services.smart_insights_service",
    "app.services.snapshot_service",
]

_JOURNALISATION = {"error", "warning", "exception", "info", "debug"}


def _gestionnaires_muets(chemin_module: str) -> list[int]:
    import importlib

    module = importlib.import_module(chemin_module)
    arbre = ast.parse(Path(module.__file__).read_text())

    muets = []
    for n in ast.walk(arbre):
        if not isinstance(n, ast.ExceptHandler):
            continue
        large = n.type is None or (isinstance(n.type, ast.Name) and n.type.id == "Exception")
        if not large:
            continue
        # Un gestionnaire qui relève, ou qui remonte l'erreur à l'appelant
        # d'une autre manière (liste d'erreurs collectées), n'est pas muet.
        if any(isinstance(c, ast.Raise) for c in ast.walk(n)):
            continue
        journalise = any(
            isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr in _JOURNALISATION
            for c in ast.walk(n)
        )
        collecte = any(
            isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr == "append"
            for c in ast.walk(n)
        )
        if not journalise and not collecte:
            muets.append(n.lineno)
    return muets


@pytest.mark.parametrize("module", MODULES_SENSIBLES)
def test_aucun_gestionnaire_muet_dans_le_coeur_financier(module):
    muets = _gestionnaires_muets(module)

    assert muets == [], (
        f"{module} : gestionnaire(s) `except Exception` sans trace, ligne(s) {muets}. "
        "Un repli silencieux rend une panne durable indétectable — journaliser, "
        "relever, ou collecter l'erreur pour l'appelant."
    )
