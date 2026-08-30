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

import re
from pathlib import Path

_MAIN = (Path(__file__).resolve().parents[2] / "app" / "main.py").read_text(encoding="utf-8")

# Les deux chemins qui créent des miroirs : au démarrage, et via l'endpoint admin.
_MIRROR_FUNCS = ("_create_missing_transfer_mirrors", "fix-mirrors")


def _mirror_sections():
    """Découpe le fichier autour des fonctions de mirroring."""
    sections = []
    start = _MAIN.find("def _create_missing_transfer_mirrors")
    assert start != -1, "fonction de mirroring de démarrage introuvable"
    # jusqu'à la fin de la fonction (prochaine def au niveau module)
    end = _MAIN.find("\ndef ", start + 1)
    sections.append(_MAIN[start : end if end != -1 else len(_MAIN)])

    admin = _MAIN.find('@app.post("/api/v1/admin/fix-mirrors")')
    assert admin != -1, "endpoint admin fix-mirrors introuvable"
    # borne : la route suivante, sinon la fin du fichier
    nxt = _MAIN.find("\n@app.", admin + 1)
    sections.append(_MAIN[admin : nxt if nxt != -1 else len(_MAIN)])
    return sections


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
