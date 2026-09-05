"""Aucun test ne doit fermer la boucle d'événements partagée par la suite.

Pourquoi ce garde-fou existe
----------------------------
``pytest.ini`` déclare ``asyncio_mode = auto`` et ``conftest.py`` fournit une
fixture ``event_loop`` de portée **session** : tous les tests asynchrones du
dépôt partagent une seule boucle.

``asyncio.run()`` crée sa propre boucle et la ferme en sortant. Appelé depuis un
test, il ferme donc la boucle de session au milieu de la suite. Les tests
suivants ne sont plus exécutés mais simplement construits : ils deviennent des
coroutines jamais attendues, et pytest les compte en échec.

Le piège s'est refermé une fois : un fichier de test appelait ``asyncio.run()``
sur trois de ses cas. Lancés seuls, ses tests passaient — et les 19 tests de
``test_alert_service.py`` aussi. C'est la suite complète qui a révélé **18
échecs**, dans un fichier sans rapport, et le code de production n'y était pour
rien. Un test isolé qui passe ne prouve pas qu'il ne casse personne.

Un test asynchrone s'écrit ``async def`` et attend ses appels : le mode ``auto``
s'occupe du reste. ``asyncio.run()`` reste légitime dans un script exécutable,
qui possède son propre processus — d'où l'exemption ci-dessous.
"""

import ast
from pathlib import Path

import pytest

_TESTS = Path(__file__).resolve().parent.parent

# Scripts utilitaires : lancés seuls, en dehors de pytest, avec leur propre
# processus et donc leur propre boucle.
_SCRIPTS_EXEMPTES = {"check_total_sync.py"}


def _fichiers_de_test():
    return sorted(f for f in _TESTS.rglob("*.py") if f.name != Path(__file__).name and f.name not in _SCRIPTS_EXEMPTES)


def _appels_asyncio_run(arbre: ast.AST) -> list[int]:
    """Lignes appelant `asyncio.run(...)` — les mentions en commentaire ou en
    docstring ne comptent pas, seul le code exécuté est lu."""
    lignes = []
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.Call):
            continue
        f = noeud.func
        if isinstance(f, ast.Attribute) and f.attr == "run":
            if isinstance(f.value, ast.Name) and f.value.id == "asyncio":
                lignes.append(noeud.lineno)
    return lignes


@pytest.mark.parametrize("fichier", _fichiers_de_test(), ids=lambda f: f.name)
def test_aucun_asyncio_run_dans_les_tests(fichier):
    fautifs = _appels_asyncio_run(ast.parse(fichier.read_text(encoding="utf-8")))
    assert not fautifs, (
        f"{fichier.name} appelle asyncio.run() aux lignes {fautifs}. "
        "Cela ferme la boucle de session et fait échouer des tests sans rapport. "
        "Écrire `async def` et `await` : asyncio_mode = auto s'en charge."
    )


class TestLeGardeFouDetecteVraiment:
    """Un garde-fou qui ne détecte rien passerait au vert sans rien protéger."""

    def test_repere_un_appel_direct(self):
        assert _appels_asyncio_run(ast.parse("import asyncio\nasyncio.run(f())\n")) == [2]

    def test_repere_un_appel_imbrique(self):
        code = "import asyncio\ndef t():\n    x = asyncio.run(f())\n    return x\n"
        assert _appels_asyncio_run(ast.parse(code)) == [3]

    def test_ignore_une_mention_en_commentaire(self):
        assert _appels_asyncio_run(ast.parse("# ne jamais faire asyncio.run(f())\nx = 1\n")) == []

    def test_ignore_une_mention_en_docstring(self):
        assert _appels_asyncio_run(ast.parse('"""Ne pas utiliser asyncio.run() ici."""\nx = 1\n')) == []

    def test_ignore_un_autre_run(self):
        assert _appels_asyncio_run(ast.parse("subprocess.run(['ls'])\n")) == []
