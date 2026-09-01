"""`/auth/register` ne doit pas révéler si une adresse est déjà enregistrée.

Pourquoi c'est une règle et pas un détail
-----------------------------------------
Une route d'inscription qui répond « Un compte avec cet email existe déjà » est
un oracle : elle permet de tester une liste d'adresses et d'apprendre lesquelles
sont clientes du service. Le reste du module s'en protège déjà — `forgot-password`
et `resend-verification` portent chacune un commentaire explicite disant qu'elles
répondent toujours la même chose. Seul `register` avait été oublié.

Deux fuites sont couvertes ici :

1. **La réponse** — même statut, même corps dans les deux cas.
2. **Le temps de réponse** — ne hacher le mot de passe que pour une adresse libre
   rendrait la réponse mesurablement plus lente dans ce cas (bcrypt à 12 rounds
   coûte ~250 ms). L'oracle survivrait au chronomètre.

Test statique : la route dépend d'une session de base et d'un service d'email ;
l'exécuter demanderait un socle d'intégration alors que la propriété à vérifier
est structurelle.
"""

import ast
from pathlib import Path

_AUTH = (Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "endpoints" / "auth.py").read_text(
    encoding="utf-8"
)


def _fonction_register() -> ast.AsyncFunctionDef:
    arbre = ast.parse(_AUTH)
    for noeud in ast.walk(arbre):
        if isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)) and noeud.name == "register":
            return noeud
    raise AssertionError("fonction register introuvable dans auth.py")


def _chaines(noeud) -> list:
    """Chaînes du code exécutable, docstrings exclues.

    La docstring de `register` explique justement quel message est proscrit, et
    la prose déclencherait le test qu'elle documente.
    """
    docstrings = {
        n.body[0].value
        for n in ast.walk(noeud)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module))
        and n.body
        and isinstance(n.body[0], ast.Expr)
        and isinstance(n.body[0].value, ast.Constant)
    }
    return [
        n.value
        for n in ast.walk(noeud)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and n not in docstrings
    ]


def test_register_ne_leve_aucune_erreur_sur_email_existant():
    """Un `raise HTTPException` dans register distingue les deux cas."""
    reg = _fonction_register()
    raises = [n for n in ast.walk(reg) if isinstance(n, ast.Raise)]
    assert not raises, (
        "register lève une exception : la réponse diffère donc selon que "
        "l'adresse existe ou non, ce qui rétablit l'oracle d'énumération"
    )


def test_register_ne_dit_pas_que_le_compte_existe_deja():
    reg = _fonction_register()
    for texte in _chaines(reg):
        bas = texte.lower()
        assert "existe déjà" not in bas, f"message révélant l'existence du compte : {texte!r}"
        assert "already exists" not in bas, f"message révélant l'existence du compte : {texte!r}"


def test_le_hachage_precede_la_branche_sur_l_existence():
    """Sinon le temps de réponse trahit ce que le corps ne dit plus.

    `hash_password` doit être appelé au niveau du corps de la fonction, avant le
    `if existing_user`, et non à l'intérieur d'une seule des deux branches.
    """
    reg = _fonction_register()

    index_if = None
    index_hash = None
    for i, instr in enumerate(reg.body):
        if index_hash is None and any(
            isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "hash_password"
            for n in ast.walk(instr)
        ):
            index_hash = i
        if index_if is None and isinstance(instr, ast.If):
            index_if = i

    assert index_hash is not None, "hash_password n'est plus appelé au niveau du corps de register"
    assert index_if is not None, "structure de register inattendue : aucun branchement trouvé"
    assert index_hash < index_if, (
        "le mot de passe n'est haché que dans une branche : la réponse est alors "
        "plus rapide pour une adresse déjà prise, ce qui trahit son existence"
    )
