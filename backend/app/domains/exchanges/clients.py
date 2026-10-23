from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_api_key
from app.domains.exchanges.models import APIKey
from app.domains.portfolio.models import Portfolio
from app.services.exchanges.base import BaseExchangeService
from app.services.exchanges.registry import get_exchange_service

CRYPTO_PORTFOLIO = "Crypto"
CRYPTO_DESCRIPTION = "Portefeuille crypto consolidé"


def open_client(key: APIKey) -> BaseExchangeService:
    """Client de l'exchange avec les secrets déchiffrés de la clé."""
    secret = decrypt_api_key(key.encrypted_secret_key) if key.encrypted_secret_key else None
    passphrase = decrypt_api_key(key.encrypted_passphrase) if key.encrypted_passphrase else None
    return get_exchange_service(key.exchange)(decrypt_api_key(key.encrypted_api_key), secret, passphrase)


async def crypto_portfolio(session: AsyncSession, user_id: UUID, exchange: str) -> Portfolio:
    """Portefeuille « Crypto » de l'utilisateur, sinon celui au nom de l'exchange renommé, sinon un nouveau."""
    for name in (CRYPTO_PORTFOLIO, exchange):
        query = select(Portfolio).where(Portfolio.user_id == user_id, Portfolio.name == name)
        portfolio = (await session.execute(query)).scalar_one_or_none()
        if portfolio is not None:
            if portfolio.name != CRYPTO_PORTFOLIO:
                portfolio.name, portfolio.description = CRYPTO_PORTFOLIO, CRYPTO_DESCRIPTION
            return portfolio
    portfolio = Portfolio(user_id=user_id, name=CRYPTO_PORTFOLIO, description=CRYPTO_DESCRIPTION)
    session.add(portfolio)
    await session.flush()
    return portfolio
