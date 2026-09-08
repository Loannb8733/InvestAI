"""Le contrat d'`aggregated_assets` : ce que la projection doit fournir.

`metrics_service.get_user_dashboard_metrics` publie une liste `aggregated_assets`
que cinq consommateurs relisent. Chacun y prend les clés dont il a besoin — et
rien ne vérifiait qu'elles existent.

Deux défauts sont nés de ce silence, tous deux invisibles aux tests unitaires
des fonctions concernées, qui étaient nourries à la main par des dictionnaires
conformes que personne ne produisait :

- `current_price` manquait, et l'estimation fiscale du rebalancement annonçait
  **0 EUR d'impôt** quelle que soit la plus-value (corrigé, NEW-32) ;
- `quantity` manquait, et le résumé Earn du tableau de bord valorisait à **0 EUR**
  toute crypto stakée non-stablecoin (corrigé ici).

Ce test tient la liste. Il est volontairement statique — monter le dashboard
complet demanderait toute la chaîne, alors que la régression à verrouiller est
déclarative : une clé disparaît de la projection sans que son lecteur bronche.
"""

import re
from pathlib import Path

import pytest

import app.services.metrics_service as module_metrics


def cles_projetees() -> set[str]:
    source = Path(module_metrics.__file__).read_text()
    debut = source.index('"aggregated_assets": [')
    # Borne : la clause `for` de la compréhension. Un `],` naïf tomberait sur
    # le premier `a["symbol"]` venu.
    bloc = source[debut : source.index("for a in aggregated", debut)]
    return set(re.findall(r'"(\w+)":', bloc)) - {"aggregated_assets"}


# Clés lues par les consommateurs, relevées à la main dans le code appelant.
# La colonne de droite dit qui les lit — un lecteur qui disparaît peut retirer
# sa clé, un nouveau doit l'ajouter ici.
CONTRAT = {
    "symbol": "les cinq consommateurs",
    "name": "dashboard.py — allocation par actif",
    "asset_type": "report_rebalancing — filtre crypto ; dashboard — allocation",
    "current_value": "les cinq consommateurs",
    "current_price": "report_rebalancing — estimation fiscale (NEW-32)",
    "quantity": "dashboard.py — prix unitaire du résumé Earn",
    "avg_buy_price": "dashboard.py — allocation par actif",
    "gain_loss_percent": "dashboard.py — allocation par actif",
    "percentage": "dashboard.py — allocation par actif",
}


@pytest.mark.parametrize("cle", sorted(CONTRAT))
def test_chaque_cle_attendue_est_projetee(cle):
    assert cle in cles_projetees(), (
        f"`{cle}` a disparu des agrégats du dashboard — lue par {CONTRAT[cle]}. "
        "Une clé absente ne lève pas : le lecteur reçoit 0 ou None et se tait."
    )


def test_le_prix_unitaire_du_resume_earn_est_calculable():
    """Le résumé Earn divise `current_value` par `quantity`.

    Les deux clés doivent être présentes ensemble : sans `quantity`, la carte
    des prix reste vide et chaque position stakée non-stablecoin est valorisée
    à zéro — y compris dans le calcul de l'APR, qui s'appuie sur elle.
    """
    projetees = cles_projetees()

    assert {"current_value", "quantity"} <= projetees
