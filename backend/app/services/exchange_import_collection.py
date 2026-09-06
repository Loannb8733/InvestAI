"""Transformations pures de la collecte d'un import d'exchange.

Pourquoi ce module existe
-------------------------
La collecte d'`import_trade_history` mêle treize appels réseau et deux
transformations qui, elles, ne dépendent de rien : normaliser les soldes
« Earn », et écarter les ordres de conversion que l'API des ordres fiat a déjà
rendus.

Ces deux-là portent la logique la plus subtile de la collecte — une fusion de
soldes et un appariement approximatif — et étaient enfouies au milieu d'un bloc
de 1 121 lignes, donc intestables. Sorties du réseau, elles se vérifient
directement.

Le reste de la collecte n'est pas ici : les appels au service, leurs fenêtres
de trente jours et leurs temporisations restent dans l'endpoint tant qu'ils
n'ont pas leur propre filet.
"""

import logging
from typing import Any, Iterable

from app.services.exchanges.base import ExchangeBalance

logger = logging.getLogger(__name__)

# Tolérance d'appariement entre un ordre fiat et un ordre de conversion : la
# minute, plus ses deux voisines. Les deux API datent le même achat à quelques
# secondes d'écart, ce qui suffit à le faire basculer d'une minute à l'autre.
_MINUTES_VOISINES = (0, 1, -1)


def normaliser_balances_earn(balances: Iterable[Any]) -> tuple[dict, dict]:
    """Fusionne les soldes « Earn » dans leur symbole de base.

    Binance expose les positions d'épargne sous un symbole dérivé — ``LDUSDC``
    pour de l'USDC placé. Sans fusion, le rapprochement voit deux actifs là où
    l'utilisateur n'en détient qu'un, et croit le solde de base insuffisant.

    Rend deux dictionnaires :

    - les soldes par symbole, variantes fondues dans leur base ;
    - les quantités placées par symbole de base, qui servent à afficher la part
      immobilisée.

    Un solde de base absent n'empêche rien : la variante devient alors le solde,
    sous le nom de base. C'est le cas d'un actif entièrement placé.
    """
    from app.tasks.sync_exchanges import _normalize_earn_variant

    balances = list(balances)
    soldes_bruts = {b.symbol: b for b in balances}
    place_par_symbole: dict = {}
    soldes: dict = {}

    for solde in balances:
        base = _normalize_earn_variant(solde.symbol)

        if base == solde.symbol:
            # Symbole ordinaire : conservé tel quel, sans écraser une fusion
            # déjà constituée par une variante rencontrée plus tôt.
            if solde.symbol not in soldes:
                soldes[solde.symbol] = solde
            continue

        place_par_symbole[base] = place_par_symbole.get(base, 0) + float(solde.total)
        logger.info(
            "Variante Earn : %s (%s) → placé sur %s",
            solde.symbol,
            float(solde.total),
            base,
        )

        # Trois cas d'addition : sur une fusion en cours, sur le solde de base
        # s'il existe, ou seule.
        socle = soldes.get(base) or soldes_bruts.get(base)
        if socle is not None:
            soldes[base] = ExchangeBalance(
                symbol=base,
                free=socle.free + solde.free,
                locked=socle.locked + solde.locked,
                total=socle.total + solde.total,
            )
        else:
            soldes[base] = ExchangeBalance(symbol=base, free=solde.free, locked=solde.locked, total=solde.total)

    return soldes, place_par_symbole


def _empreintes_ordres_fiat(ordres_fiat: Iterable[Any]) -> set:
    """Clés d'appariement d'un ordre fiat : (symbole, quantité, minute)."""
    empreintes = set()
    for ordre in ordres_fiat:
        minute = int(ordre.timestamp.timestamp()) // 60
        quantite = (
            str(ordre.crypto_amount.normalize())
            if hasattr(ordre.crypto_amount, "normalize")
            else str(ordre.crypto_amount)
        )
        for decalage in _MINUTES_VOISINES:
            empreintes.add((ordre.crypto_symbol, quantite, minute + decalage))
    return empreintes


def dedupliquer_convert_contre_fiat(
    ordres_convert: Iterable[Any],
    ordres_fiat: Iterable[Any],
) -> list:
    """Écarte les ordres de conversion déjà rendus par l'API des ordres fiat.

    Les deux points d'entrée de Binance — ``fiat/payments`` et
    ``convert/tradeFlow`` — décrivent le même achat en euros avec des
    identifiants différents. Sans ce tri, chaque achat par carte compterait
    double.

    L'appariement est approximatif par nécessité : les deux API datent le même
    achat à quelques secondes d'écart. La comparaison porte sur le symbole, la
    quantité normalisée et la minute, à une minute près de part et d'autre.
    """
    ordres_convert = list(ordres_convert)
    empreintes = _empreintes_ordres_fiat(ordres_fiat)

    conserves = []
    for ordre in ordres_convert:
        minute = int(ordre.timestamp.timestamp()) // 60
        quantite = (
            str(ordre.crypto_amount.normalize())
            if hasattr(ordre.crypto_amount, "normalize")
            else str(ordre.crypto_amount)
        )
        if (ordre.crypto_symbol, quantite, minute) in empreintes:
            logger.debug(
                "Ordre de conversion ignoré, déjà vu côté fiat : %s %s à %s",
                ordre.crypto_symbol,
                ordre.crypto_amount,
                ordre.timestamp,
            )
            continue
        conserves.append(ordre)

    ecartes = len(ordres_convert) - len(conserves)
    if ecartes:
        logger.info("%d ordre(s) de conversion écarté(s), déjà présents côté fiat", ecartes)

    return conserves
