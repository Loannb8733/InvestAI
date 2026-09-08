"""Certains constructeurs SQLAlchemy ne se prennent pas sur `func`.

`func.<nom>(...)` fabrique toujours un appel de **fonction SQL** nommée
`<nom>`. Pour une vraie fonction — `func.count`, `func.sum`, `func.distinct` —
c'est exactement ce qu'on veut. Pour une **expression** du langage — `case`,
`and_`, `exists` — c'est un piège : l'objet se construit sans broncher, puis
échoue soit à l'appel (un mot-clé comme `else_` qu'un appel de fonction refuse,
et l'on obtient un `TypeError`), soit à la compilation, avec un SQL qui n'a
aucun sens.

Ce garde-fou existe parce que le cas s'est produit : `_validate_portfolio_consistency`
construisait sa somme conditionnelle avec `func.case(..., else_=0)`. La tâche
tournait **tous les jours à 4 h UTC** et levait `TypeError` avant même
d'atteindre la base — donc n'avait jamais rien vérifié. Le module était couvert
à 0 % : personne ne l'avait jamais exécutée hors production, où l'échec se
perdait dans les journaux Celery (NEW-42).
"""

import ast
from pathlib import Path

import pytest

import app

# Constructeurs du module `sqlalchemy` qui ne sont **pas** des fonctions SQL.
# `distinct`, `count`, `sum`, `coalesce`, `min`, `max` en sont, et restent
# parfaitement valides sur `func`.
INTERDITS_SUR_FUNC = {
    "case",
    "and_",
    "or_",
    "not_",
    "select",
    "exists",
    "between",
    "union",
    "tuple_",
    "literal",
    "bindparam",
}

RACINE = Path(app.__file__).parent


def _fautes() -> list[str]:
    trouvees = []
    for chemin in RACINE.rglob("*.py"):
        try:
            arbre = ast.parse(chemin.read_text())
        except (SyntaxError, UnicodeDecodeError):
            continue
        for n in ast.walk(arbre):
            if (
                isinstance(n, ast.Attribute)
                and isinstance(n.value, ast.Name)
                and n.value.id == "func"
                and n.attr in INTERDITS_SUR_FUNC
            ):
                relatif = chemin.relative_to(RACINE.parent)
                trouvees.append(f"{relatif}:{n.lineno} — func.{n.attr}")
    return trouvees


def test_aucun_constructeur_sql_pris_sur_func():
    fautes = _fautes()

    assert (
        fautes == []
    ), "Ces expressions doivent être importées du module `sqlalchemy`, non " "prises sur `func` :\n  " + "\n  ".join(
        fautes
    )


@pytest.mark.parametrize("nom", sorted(INTERDITS_SUR_FUNC))
def test_le_constructeur_existe_bien_dans_le_module(nom):
    """La liste ne doit pas interdire des noms qui n'existent pas.

    Un nom mal orthographié rendrait la garde inopérante sans que rien ne le
    signale — le défaut même qu'elle surveille.
    """
    import sqlalchemy

    assert hasattr(sqlalchemy, nom)
