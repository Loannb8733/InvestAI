"""Un gestionnaire d'erreur ne valide pas le travail qu'il vient d'interrompre.

Pourquoi ce garde-fou existe
----------------------------
Trois blocs `except` appelaient `db.commit()` pour garder la trace d'un échec
sur la clé API. Mais `commit()` valide **toute la session**, pas seulement ce
marquage — et ces blocs enveloppent des imports qui écrivent au fil de l'eau.

Mesuré avant correction : `import_trade_history` comptait 7 `db.add()` et 8
`db.flush()` dans un `try` de 1 147 lignes, pour un seul `commit()` normal tout
à la fin. Une erreur survenant dans les 1 065 lignes précédentes faisait donc
valider les écritures en attente : un import interrompu laissait en base une
moitié de transactions, sans que rien ne le signale.

La règle : dès qu'un `try` contient des écritures, son `except` ne peut pas
committer sans avoir d'abord annulé. `rollback_puis_marquer` fait les deux dans
le bon ordre.
"""

import ast
import re
from pathlib import Path

import pytest

_APP = Path(__file__).resolve().parents[2] / "app"


def _fichiers_applicatifs():
    return sorted(p for p in _APP.rglob("*.py") if "__pycache__" not in p.parts)


def commits_sans_rollback(source: str) -> list[tuple[int, int]]:
    """(ligne du handler, nombre d'écritures dans le try) pour chaque cas fautif."""
    lignes = source.splitlines()
    fautifs = []

    for noeud in ast.walk(ast.parse(source)):
        if not isinstance(noeud, ast.Try):
            continue
        corps = "\n".join(lignes[noeud.lineno - 1 : noeud.end_lineno])
        ecritures = len(re.findall(r"\bdb\.add(?:_all)?\(", corps)) + len(re.findall(r"await db\.flush\(\)", corps))
        if not ecritures:
            continue
        for handler in noeud.handlers:
            bloc = "\n".join(lignes[handler.lineno - 1 : handler.end_lineno])
            if "await db.commit()" in bloc and "await db.rollback()" not in bloc:
                fautifs.append((handler.lineno, ecritures))
    return fautifs


@pytest.mark.parametrize("fichier", _fichiers_applicatifs(), ids=lambda p: p.name)
def test_aucun_commit_sans_rollback_dans_un_handler(fichier):
    fautifs = commits_sans_rollback(fichier.read_text(encoding="utf-8"))
    assert not fautifs, (
        f"{fichier.name} : `db.commit()` dans un `except` aux lignes "
        f"{[ligne for ligne, _ in fautifs]}, alors que le `try` contient des écritures. "
        "Le commit validerait le travail partiel. Utiliser `rollback_puis_marquer`, "
        "ou annuler explicitement avant de committer."
    )


class TestLeGardeFouDetecteVraiment:
    """Un garde-fou qui ne détecte rien passerait au vert sans rien protéger."""

    def test_repere_le_motif_fautif(self):
        code = (
            "async def f(db):\n"
            "    try:\n"
            "        db.add(x)\n"
            "        await g()\n"
            "    except Exception:\n"
            "        await db.commit()\n"
        )
        assert commits_sans_rollback(code) == [(5, 1)]

    def test_accepte_un_rollback_prealable(self):
        code = (
            "async def f(db):\n"
            "    try:\n"
            "        db.add(x)\n"
            "    except Exception:\n"
            "        await db.rollback()\n"
            "        await db.commit()\n"
        )
        assert commits_sans_rollback(code) == []

    def test_ignore_un_try_sans_ecriture(self):
        """Un commit qui ne valide que ce que le handler vient de faire est sain."""
        code = (
            "async def f(db):\n"
            "    try:\n"
            "        await lire()\n"
            "    except Exception:\n"
            "        await db.commit()\n"
        )
        assert commits_sans_rollback(code) == []

    def test_compte_aussi_les_flush(self):
        code = (
            "async def f(db):\n"
            "    try:\n"
            "        await db.flush()\n"
            "    except Exception:\n"
            "        await db.commit()\n"
        )
        assert commits_sans_rollback(code) == [(4, 1)]
