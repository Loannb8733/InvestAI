"""Mise en euros des prix et des frais d'un mouvement importé.

Pourquoi ce module existe
-------------------------
Un exchange cote ses paires dans sa propre devise et prélève ses frais dans le
jeton qui l'arrange. Avant d'écrire une transaction, l'import ramène les deux en
euros — sans quoi le coût de revient, et la fiscalité qui en découle, seraient
faux.

Cette conversion tenait en une trentaine de lignes au milieu d'une boucle
d'écriture, avec trois cas et deux replis en cascade, et n'avait aucun test.
L'appel réseau qui donne le cours d'un jeton tiers reste chez l'appelant : ce
qui est ici se calcule et se vérifie sans rien contacter.
"""

import logging

logger = logging.getLogger(__name__)

# Devises de cotation qui valent un dollar : une paire qui s'y termine est cotée
# en USD, et son prix demande une conversion.
SUFFIXES_COTATION_USD = ("USDT", "USDC", "BUSD", "FDUSD", "USD")

# Devises dans lesquelles des frais sont déjà exploitables tels quels. Les
# autres sont des jetons, dont il faut trouver la contre-valeur.
DEVISES_FRAIS_SANS_CONVERSION = frozenset({"EUR", "USD", "GBP", "CAD", "JPY"})


def est_cote_en_usd(symbole_paire: str) -> bool:
    """Dit si le prix d'une paire est libellé en dollars.

    « BTCUSDT » l'est, « BTCEUR » non. Le test porte sur le suffixe : c'est la
    devise de cotation qui compte, pas l'actif acheté.
    """
    if not symbole_paire:
        return False
    return symbole_paire.endswith(SUFFIXES_COTATION_USD)


def frais_a_convertir(devise_frais: str, montant: float) -> bool:
    """Dit si des frais demandent une mise en euros.

    Des frais nuls n'ont rien à convertir, et une devise déjà exploitable non
    plus. Ne restent que les frais prélevés en jeton.
    """
    return montant > 0 and devise_frais not in DEVISES_FRAIS_SANS_CONVERSION


def convertir_frais_en_eur(
    montant: float,
    devise_frais: str,
    symbole_actif: str,
    prix_actif_eur: float,
    prix_jeton_eur: float = 0.0,
) -> float:
    """Ramène en euros des frais prélevés en jeton.

    Deux situations, et un repli.

    Quand les frais sont dans le jeton même qui a été échangé — des frais en
    PEPE sur un achat de PEPE — le prix de l'actif fait l'affaire.

    Quand ils sont dans un autre jeton — des frais en BNB sur un achat de
    PEPE — il faut le cours de ce jeton-là, que l'appelant fournit.

    **Le repli est approximatif, et c'est le comportement d'origine :** faute de
    cours pour le jeton des frais, le prix de l'actif échangé est employé à sa
    place. Cela revient à valoriser du BNB au cours du PEPE. Le montant obtenu
    n'a pas de sens en soi ; il vaut mieux qu'un zéro, qui minorerait le coût de
    revient et gonflerait la plus-value imposable. Faute des deux, les frais
    sont abandonnés.
    """
    if montant <= 0:
        return 0.0

    if devise_frais == symbole_actif:
        return montant * prix_actif_eur if prix_actif_eur > 0 else 0.0

    if prix_jeton_eur > 0:
        return montant * prix_jeton_eur

    if prix_actif_eur > 0:
        logger.debug(
            "Frais en %s valorisés au cours de %s, faute de cours propre",
            devise_frais,
            symbole_actif,
        )
        return montant * prix_actif_eur

    return 0.0


def lire_prix_jeton(reponse_prix: dict, devise: str) -> float:
    """Extrait le cours d'un jeton d'une réponse de `get_multiple_crypto_prices`.

    La clé peut arriver en minuscules ou en majuscules selon la source ; les
    deux sont essayées avant d'abandonner.
    """
    if not reponse_prix:
        return 0.0
    for cle in (devise.lower(), devise.upper()):
        if cle in reponse_prix:
            try:
                return float(reponse_prix[cle].get("price", 0))
            except (AttributeError, TypeError, ValueError):
                return 0.0
    return 0.0
