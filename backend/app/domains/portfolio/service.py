import logging
from collections.abc import Sequence
from uuid import UUID

from app.core.errors import DomainError, NotFoundError
from app.domains.market_data.history.tasks import schedule_refresh
from app.domains.portfolio.models import Asset, Portfolio
from app.domains.portfolio.repository import AssetRepository, PortfolioRepository
from app.domains.portfolio.schemas import AssetCreate, AssetUpdate, CashBalanceUpdate, PortfolioCreate, PortfolioUpdate

logger = logging.getLogger(__name__)

PORTFOLIO_NOT_FOUND = "Portefeuille non trouvé"
ASSET_NOT_FOUND = "Actif non trouvé"
DUPLICATE_ASSET = "Un actif avec ce symbole existe déjà sur cette plateforme"


class PortfolioService:
    """Portefeuilles d'un utilisateur et leurs soldes de trésorerie par plateforme."""

    def __init__(self, portfolios: PortfolioRepository) -> None:
        self._portfolios = portfolios

    async def list(self, user_id: UUID) -> Sequence[Portfolio]:
        return await self._portfolios.owned(user_id)

    async def get(self, user_id: UUID, portfolio_id: UUID) -> Portfolio:
        portfolio = await self._portfolios.owned_one(user_id, portfolio_id)
        if portfolio is None:
            raise NotFoundError(PORTFOLIO_NOT_FOUND)
        return portfolio

    async def create(self, user_id: UUID, data: PortfolioCreate) -> Portfolio:
        return await self._portfolios.add(Portfolio(user_id=user_id, name=data.name, description=data.description))

    async def update(self, user_id: UUID, portfolio_id: UUID, data: PortfolioUpdate) -> Portfolio:
        portfolio = await self.get(user_id, portfolio_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(portfolio, field, value)
        return await self._portfolios.save(portfolio)

    async def delete(self, user_id: UUID, portfolio_id: UUID) -> None:
        """Supprime le portefeuille avec ses actifs et leurs transactions."""
        await self._portfolios.delete(await self.get(user_id, portfolio_id))

    async def set_cash(self, user_id: UUID, portfolio_id: UUID, data: CashBalanceUpdate) -> Portfolio:
        """Pose le solde d'une plateforme ; un montant nul le retire."""
        portfolio = await self.get(user_id, portfolio_id)
        balances = dict(portfolio.cash_balances or {})
        if data.amount > 0:
            balances[data.exchange] = data.amount
        else:
            balances.pop(data.exchange, None)
        portfolio.cash_balances = balances
        return await self._portfolios.save(portfolio)

    async def remove_cash(self, user_id: UUID, portfolio_id: UUID, exchange: str) -> Portfolio:
        portfolio = await self.get(user_id, portfolio_id)
        portfolio.cash_balances = {k: v for k, v in (portfolio.cash_balances or {}).items() if k != exchange}
        return await self._portfolios.save(portfolio)


class AssetService:
    """Actifs des portefeuilles d'un utilisateur ; le symbole est unique par portefeuille et par plateforme."""

    def __init__(self, assets: AssetRepository, portfolios: PortfolioRepository) -> None:
        self._assets = assets
        self._portfolios = portfolios

    async def list(self, user_id: UUID, portfolio_id: UUID | None) -> Sequence[Asset]:
        if portfolio_id is not None and await self._portfolios.owned_one(user_id, portfolio_id) is None:
            raise NotFoundError(PORTFOLIO_NOT_FOUND)
        return await self._assets.listed(user_id, portfolio_id)

    async def get(self, user_id: UUID, asset_id: UUID) -> Asset:
        asset = await self._assets.owned_one(user_id, asset_id)
        if asset is None:
            raise NotFoundError(ASSET_NOT_FOUND)
        return asset

    async def create(self, user_id: UUID, data: AssetCreate) -> Asset:
        """Crée l'actif puis programme le chargement de son historique de cours."""
        if await self._portfolios.owned_one(user_id, data.portfolio_id) is None:
            raise NotFoundError(PORTFOLIO_NOT_FOUND)
        symbol, exchange = data.symbol.upper(), data.exchange or ""
        if await self._assets.exists(data.portfolio_id, symbol, exchange):
            raise DomainError(DUPLICATE_ASSET)
        asset = await self._assets.add(
            Asset(
                portfolio_id=data.portfolio_id,
                symbol=symbol,
                name=data.name,
                asset_type=data.asset_type,
                quantity=data.quantity,
                avg_buy_price=data.avg_buy_price,
                currency=data.currency,
                exchange=exchange,
                interest_rate=data.interest_rate,
                maturity_date=data.maturity_date,
                project_status=data.project_status,
                invested_amount=data.invested_amount,
            )
        )
        schedule_refresh(asset.symbol, asset.asset_type.value)
        return asset

    async def update(self, user_id: UUID, asset_id: UUID, data: AssetUpdate) -> Asset:
        asset = await self.get(user_id, asset_id)
        changes = data.model_dump(exclude_unset=True)
        if "exchange" in changes and changes["exchange"] is None:
            changes["exchange"] = ""
        for field, value in changes.items():
            setattr(asset, field, value)
        return await self._assets.save(asset)

    async def delete(self, user_id: UUID, asset_id: UUID) -> None:
        """Supprime l'actif et ses transactions ; les transferts d'autres actifs qui y renvoyaient sont détachés."""
        await self._assets.delete(await self.get(user_id, asset_id))
