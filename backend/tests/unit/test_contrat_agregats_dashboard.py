"""Les contrats de `get_user_dashboard_metrics` : ce que ses lecteurs attendent.

`metrics_service.get_user_dashboard_metrics` publie une liste `aggregated_assets`
que cinq consommateurs relisent. Chacun y prend les clés dont il a besoin — et
rien ne vérifiait qu'elles existent.

Deux défauts sont nés de ce silence, tous deux invisibles aux tests unitaires
des fonctions concernées, qui étaient nourries à la main par des dictionnaires
conformes que personne ne produisait :

- `current_price` manquait, et l'estimation fiscale du rebalancement annonçait
  **0 EUR d'impôt** quelle que soit la plus-value (corrigé, NEW-32) ;
- `quantity` manquait, et le résumé Earn du tableau de bord valorisait à **0 EUR**
  toute crypto stakée non-stablecoin (corrigé, NEW-33) ;
- au niveau du dictionnaire racine, `assets`, `total_dividend_income` et
  `total_return` manquaient aussi : l'exposition par devise restait vide — la
  carte n'était donc **jamais affichée** — et les deux autres valeurs
  retombaient sur leur défaut de 0 (corrigé, NEW-34).

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


def cles_racine() -> set[str]:
    """Clés du dictionnaire que `get_user_dashboard_metrics` retourne."""
    lignes = Path(module_metrics.__file__).read_text().split("\n")
    i = next(i for i, l in enumerate(lignes) if '"aggregated_assets": [' in l)
    debut = max(j for j in range(i) if lignes[j].strip().startswith("return {"))
    fin = next(j for j in range(i, len(lignes)) if lignes[j].rstrip() == "        }")
    return set(re.findall(r'^\s+"(\w+)":', "\n".join(lignes[debut : fin + 1]), re.M))


# Clés du dictionnaire racine lues par ses sept consommateurs.
CONTRAT_RACINE = {
    "total_value": "rebalancement, simulations, stratégie, alertes, emails, dashboard",
    "aggregated_assets": "rebalancement, alertes, dashboard, rapports",
    "assets": "dashboard — exposition par devise (NEW-34)",
    "total_dividend_income": "dashboard — bandeau de synthèse (NEW-34)",
    "total_return": "dashboard — bandeau de synthèse (NEW-34)",
    "available_liquidity": "dashboard",
    "period_changes": "dashboard",
}


@pytest.mark.parametrize("cle", sorted(CONTRAT_RACINE))
def test_chaque_cle_racine_attendue_est_projetee(cle):
    assert cle in cles_racine(), f"`{cle}` a disparu du dictionnaire du dashboard — lue par {CONTRAT_RACINE[cle]}."


def test_l_exposition_par_devise_a_de_quoi_travailler():
    """`currency_exposure` regroupe les actifs par devise de cotation.

    Elle a besoin des entrées **individuelles** — `aggregated_assets`, agrégé
    par symbole, ne porte ni `id` ni la granularité par plateforme. Sans la clé
    `assets`, les deux boucles de l'endpoint tournaient à vide et le client
    recevait une liste vide, qu'il traduit par une carte masquée.
    """
    assert "assets" in cles_racine()
