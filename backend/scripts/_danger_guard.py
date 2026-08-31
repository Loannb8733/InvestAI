"""Garde-fou pour les scripts de maintenance destructifs.

Certains scripts de ce répertoire réécrivent des colonnes financières à partir
d'hypothèses qui ne tiennent plus. Ils se lancent en une commande, commitent sans
confirmation, et leur nom ne dit rien de leur dangerosité — `recalculate_quantities`
sonne comme une remise en ordre inoffensive.

Ce module leur impose un consentement explicite : le script refuse de s'exécuter
tant que l'opérateur n'a pas passé le drapeau, après avoir lu ce qu'il risque.

Volontairement sans dépendance (ni SQLAlchemy ni app.*) pour rester importable et
testable seul.
"""

from __future__ import annotations

import sys
from typing import Sequence

CONSENT_FLAG = "--i-know-what-im-doing"


def consent_granted(argv: Sequence[str]) -> bool:
    """Le drapeau de consentement est-il présent ? Fonction pure."""
    return CONSENT_FLAG in list(argv)


def require_consent(script_name: str, danger: str, alternative: str, argv: Sequence[str] | None = None) -> None:
    """Interrompt le script si le consentement explicite n'a pas été donné.

    ``danger`` décrit ce que le script casse, en clair. ``alternative`` indique quoi
    faire à la place : un refus sans porte de sortie pousse à contourner le garde-fou.
    """
    if consent_granted(sys.argv if argv is None else argv):
        return

    print(f"\n  ⚠  {script_name} — EXÉCUTION BLOQUÉE\n")
    print(f"  {danger}\n")
    print(f"  À faire à la place : {alternative}\n")
    print(f"  Si vous savez ce que vous faites : python scripts/{script_name} {CONSENT_FLAG}\n")
    raise SystemExit(1)
