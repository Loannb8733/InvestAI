"""Le mirroring incrémente la destination, il ne recalcule jamais son solde.

Pourquoi c'est une règle et pas un détail
-----------------------------------------
Recalculer ``asset.quantity`` comme la somme signée de l'historique suppose cet
historique exhaustif. Il ne l'est jamais pour un cold wallet : la sync voit les
entrées (elle les crée elle-même en miroir des retraits d'exchange) mais aucune
API ne peut remonter les sorties. Le « recalcul » y remplaçait donc un solde
correct par le total des seules entrées connues — sur des données réelles, un
actif soldé se retrouvait crédité de 109 529 unités inexistantes.

Le miroir ajoute une quantité connue : on ajoute cette quantité, point. C'est ce
que fait déjà ``create_mirror_transfer_in`` dans transfer_service.py.

Test statique car la logique est du SQL brut au sein de fonctions de démarrage :
aucun test d'exécution ne l'atteint, et une affectation de solde ne lève aucune
erreur — elle écrit juste une valeur fausse.
"""

import ast
import re
from pathlib import Path

_MAIN = (Path(__file__).resolve().parents[2] / "app" / "main.py").read_text(encoding="utf-8")


def _mirror_sections():
    """Découpe le fichier autour des fonctions de mirroring.

    Il n'en reste qu'une depuis la suppression de l'endpoint admin
    ``POST /api/v1/admin/fix-mirrors`` (SEC-04) : le mirroring de démarrage.
    """
    start = _MAIN.find("def _create_missing_transfer_mirrors")
    assert start != -1, "fonction de mirroring de démarrage introuvable"
    # jusqu'à la fin de la fonction (prochaine def au niveau module)
    end = _MAIN.find("\ndef ", start + 1)
    return [_MAIN[start : end if end != -1 else len(_MAIN)]]


def _routes_declarees():
    """Retourne [(chemin, noeud de fonction)] pour chaque route montée sur `app`.

    Analyse de l'AST et non du texte : chercher une chaîne dans le fichier ferait
    correspondre le commentaire qui documente la suppression, lequel cite
    forcément le chemin de l'endpoint et le SQL qu'il exécutait.
    """
    arbre = ast.parse(_MAIN)
    routes = []
    for noeud in arbre.body:
        if not isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in noeud.decorator_list:
            cible = deco.func if isinstance(deco, ast.Call) else deco
            if (
                isinstance(cible, ast.Attribute)
                and isinstance(cible.value, ast.Name)
                and cible.value.id == "app"
                and cible.attr in ("get", "post", "put", "delete", "patch")
            ):
                args = deco.args if isinstance(deco, ast.Call) else []
                chemin = args[0].value if args and isinstance(args[0], ast.Constant) else ""
                routes.append((chemin, noeud))
    return routes


def test_l_endpoint_admin_de_mirroring_reste_supprime():
    """Une route HTTP ne doit ni rejouer le mirroring ni migrer le schéma.

    L'endpoint supprimé exécutait un ``ALTER TABLE`` depuis une requête et
    renvoyait au client un dump des transactions ; il ne faisait rien que le
    démarrage ne fasse déjà, sous verrou et de façon idempotente. Le rétablir
    rouvrirait le chemin par lequel les fantômes Tangem sont entrés.
    """
    routes = _routes_declarees()
    admin = [c for c, _ in routes if "admin" in c]
    assert not admin, f"route admin réintroduite dans main.py : {admin}"

    for chemin, noeud in routes:
        sql = [
            n.value
            for n in ast.walk(noeud)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and "ALTER TABLE" in n.value
        ]
        assert not sql, f"la route {chemin} migre le schéma — cela relève d'Alembic : {sql}"


def test_les_soldes_destination_sont_incrementes():
    for section in _mirror_sections():
        assert (
            "UPDATE assets SET quantity = COALESCE(quantity, 0) + :add" in section
        ), "le mirroring doit incrémenter la destination du montant miroité"


def test_aucune_affectation_de_solde_dans_le_mirroring():
    # Une affectation (`SET quantity = :qty`) écraserait le solde par une valeur
    # dérivée de l'historique : c'est exactement la régression à empêcher.
    interdit = re.compile(r"UPDATE assets SET quantity = :\w+(?!\s*\+)")
    for section in _mirror_sections():
        assert not interdit.search(section), (
            "affectation directe de quantity dans une fonction de mirroring : "
            "utiliser un incrément, l'historique d'un cold wallet est incomplet"
        )


def test_le_rattrapage_global_tangem_est_bien_retire():
    # Ce rattrapage recalculait TOUS les actifs du cold wallet depuis leur
    # historique, ce qui rendait le solde faux à chaque appel de l'endpoint.
    assert "Always recalculate ALL Tangem assets" not in _MAIN


def test_aucun_recalcul_depuis_l_historique_dans_le_mirroring():
    for section in _mirror_sections():
        assert "AS net_qty" not in section, "le mirroring ne doit plus dériver le solde de la somme des transactions"
