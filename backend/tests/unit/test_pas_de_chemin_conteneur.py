"""Aucun test ne doit dépendre d'un chemin qui n'existe que dans le conteneur.

Pourquoi ce garde-fou existe
----------------------------
Le répertoire ``/app`` est le point de montage du code dans l'image Docker. Il
n'existe ni sur un poste de développement, ni dans l'intégration continue, qui
travaille sur une copie du dépôt.

Le piège s'est déjà refermé deux fois :

1. les scripts destructeurs faisaient ``sys.path.insert(0, "/app")`` avant leur
   garde-fou, si bien qu'en CI l'import échouait avant que le refus soit
   prononcé — six exécutions rouges d'affilée (NEW-12) ;
2. un test écrit deux jours plus tard, en pleine connaissance de cette leçon,
   lisait ``Path("/app", "app/tasks/sync_exchanges.py")``. Même cause, même
   effet : `FileNotFoundError` en CI, tests verts en local.

Un chemin de fichier se dérive du module importé (``Path(module.__file__)``) ou
de l'emplacement du test (``Path(__file__).resolve().parents[n]``). Jamais d'une
racine absolue supposée.
"""

import ast
from pathlib import Path

import pytest

_TESTS = Path(__file__).resolve().parent.parent


def _fichiers_de_test():
    return sorted(f for f in _TESTS.rglob("*.py") if f.name != Path(__file__).name)


@pytest.mark.parametrize("fichier", _fichiers_de_test(), ids=lambda f: f.name)
def test_aucun_chemin_conteneur_dans_le_code(fichier):
    """Les commentaires peuvent citer « /app » ; le code exécuté, non."""
    arbre = ast.parse(fichier.read_text(encoding="utf-8"))

    fautifs = [
        n.value
        for n in ast.walk(arbre)
        if isinstance(n, ast.Constant)
        and isinstance(n.value, str)
        and (n.value == "/app" or n.value.startswith("/app/"))
    ]

    assert not fautifs, (
        f"{fichier.name} contient un chemin de conteneur : {fautifs}. "
        "Il n'existe pas en CI — dériver le chemin du module importé "
        "(Path(module.__file__)) ou du fichier de test."
    )
