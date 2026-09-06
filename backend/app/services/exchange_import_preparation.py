"""Préparation d'un import ou d'une synchronisation d'exchange.

Pourquoi ce module existe
-------------------------
Trois endpoints et une tâche Celery ouvraient leur traitement par les deux
mêmes gestes : déchiffrer les identifiants pour instancier le service
d'exchange, puis retrouver — ou créer — le portefeuille « Crypto » de
l'utilisateur.

Ces blocs étaient recopiés **à l'identique**, ligne pour ligne. Deux des trois
copies du second portaient même le commentaire « same logic as import-history »,
qui est l'aveu de la duplication plutôt que sa correction.

Le déchiffrement ne touche pas la base ; la résolution du portefeuille ne touche
pas l'exchange. Les séparer rend chacun testable seul, ce que le bloc de 1 174
lignes dont ils sont extraits n'a jamais permis.

Ce que ce module **ne** fait pas
--------------------------------
La fusion des portefeuilles hérités (« Binance », « Kraken », « Crypto.com »
consolidés dans « Crypto ») reste distincte : seul l'import d'historique la
pratiquait, et l'imposer aux deux autres appelants changerait leur
comportement. Elle est ici sous son propre nom, appelée explicitement.
"""

import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_api_key
from app.models.asset import Asset
from app.models.portfolio import Portfolio
from app.services.exchanges import get_exchange_service

logger = logging.getLogger(__name__)

NOM_PORTEFEUILLE_CRYPTO = "Crypto"
DESCRIPTION_PORTEFEUILLE_CRYPTO = "Portefeuille crypto consolidé"

# Portefeuilles d'avant la consolidation, encore présents chez les comptes
# anciens. Leurs actifs sont rapatriés dans « Crypto » au premier import.
NOMS_PORTEFEUILLES_HERITES = ["Binance", "Kraken", "Crypto.com"]


def construire_service_exchange(api_key: Any) -> Any:
    """Déchiffre les identifiants et instancie le service de l'exchange.

    Les trois secrets ne sont pas tous requis : seule la clé l'est toujours. Le
    secret et la phrase de passe restent à ``None`` quand l'exchange ne les
    utilise pas — c'est le service qui décide de ce dont il a besoin.
    """
    cle = decrypt_api_key(api_key.encrypted_api_key)
    secret = decrypt_api_key(api_key.encrypted_secret_key) if api_key.encrypted_secret_key else None
    phrase = decrypt_api_key(api_key.encrypted_passphrase) if api_key.encrypted_passphrase else None

    classe_service = get_exchange_service(api_key.exchange)
    return classe_service(cle, secret, phrase)


async def resoudre_portefeuille_crypto(
    db: AsyncSession,
    user_id: UUID,
    nom_exchange: Optional[str] = None,
) -> Portfolio:
    """Rend le portefeuille « Crypto » de l'utilisateur, en le créant au besoin.

    Trois cas, dans cet ordre :

    1. le portefeuille « Crypto » existe : il est rendu tel quel ;
    2. il n'existe pas, mais un portefeuille porte le nom de l'exchange — c'est
       un compte d'avant la consolidation : il est **renommé**, pour que son
       historique suive au lieu d'être abandonné ;
    3. aucun des deux : un portefeuille neuf est créé et poussé en base par un
       ``flush``, pour que son identifiant soit disponible immédiatement.

    Le ``flush`` ne valide rien : c'est l'appelant qui décide du ``commit``.
    """
    resultat = await db.execute(
        select(Portfolio).where(
            Portfolio.user_id == user_id,
            Portfolio.name == NOM_PORTEFEUILLE_CRYPTO,
        )
    )
    portefeuille = resultat.scalar_one_or_none()

    if not portefeuille and nom_exchange:
        resultat_herite = await db.execute(
            select(Portfolio).where(
                Portfolio.user_id == user_id,
                Portfolio.name == f"{nom_exchange}",
            )
        )
        portefeuille = resultat_herite.scalar_one_or_none()
        if portefeuille:
            portefeuille.name = NOM_PORTEFEUILLE_CRYPTO
            portefeuille.description = DESCRIPTION_PORTEFEUILLE_CRYPTO

    if not portefeuille:
        portefeuille = Portfolio(
            user_id=user_id,
            name=NOM_PORTEFEUILLE_CRYPTO,
            description=DESCRIPTION_PORTEFEUILLE_CRYPTO,
        )
        db.add(portefeuille)
        await db.flush()

    return portefeuille


async def fusionner_portefeuilles_herites(
    db: AsyncSession,
    portefeuille: Portfolio,
    user_id: UUID,
) -> int:
    """Rapatrie les portefeuilles par exchange dans le portefeuille « Crypto ».

    Déplace les actifs et les instantanés, additionne les soldes en espèces,
    puis supprime le portefeuille vidé. Rend le nombre de portefeuilles fusionnés.

    Appelée seulement par l'import d'historique : la synchronisation, elle, se
    contente du portefeuille résolu.
    """
    from app.models.portfolio_snapshot import PortfolioSnapshot

    resultat = await db.execute(
        select(Portfolio).where(
            Portfolio.user_id == user_id,
            Portfolio.id != portefeuille.id,
            Portfolio.name.in_(NOMS_PORTEFEUILLES_HERITES),
        )
    )
    autres = resultat.scalars().all()

    for autre in autres:
        actifs = await db.execute(select(Asset).where(Asset.portfolio_id == autre.id))
        for actif in actifs.scalars().all():
            actif.portfolio_id = portefeuille.id

        instantanes = await db.execute(select(PortfolioSnapshot).where(PortfolioSnapshot.portfolio_id == autre.id))
        for instantane in instantanes.scalars().all():
            instantane.portfolio_id = portefeuille.id

        if autre.cash_balances:
            if not portefeuille.cash_balances:
                portefeuille.cash_balances = {}
            for devise, montant in autre.cash_balances.items():
                portefeuille.cash_balances[devise] = portefeuille.cash_balances.get(devise, 0) + montant

        await db.delete(autre)
        logger.info("Portefeuille « %s » fusionné dans « Crypto »", autre.name)

    await db.flush()
    return len(autres)
