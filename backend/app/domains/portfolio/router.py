from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_session
from app.core.rate_limit import RATE_LIMITS, limiter
from app.domains.identity.dependencies import CurrentUser
from app.domains.portfolio.repository import AssetRepository, PortfolioRepository
from app.domains.portfolio.schemas import (
    AssetCreate,
    AssetResponse,
    AssetUpdate,
    CashBalanceUpdate,
    PortfolioCreate,
    PortfolioResponse,
    PortfolioUpdate,
)
from app.domains.portfolio.service import AssetService, PortfolioService

portfolios_router = APIRouter()
assets_router = APIRouter()


def get_portfolio_service(session: Annotated[AsyncSession, Depends(get_session)]) -> PortfolioService:
    return PortfolioService(PortfolioRepository(session))


def get_asset_service(session: Annotated[AsyncSession, Depends(get_session)]) -> AssetService:
    return AssetService(AssetRepository(session), PortfolioRepository(session))


Portfolios = Annotated[PortfolioService, Depends(get_portfolio_service)]
Assets = Annotated[AssetService, Depends(get_asset_service)]


@portfolios_router.get("")
@limiter.limit(RATE_LIMITS["api_read"])
async def list_portfolios(request: Request, user: CurrentUser, service: Portfolios) -> list[PortfolioResponse]:
    return [PortfolioResponse.model_validate(p) for p in await service.list(user.id)]


@portfolios_router.post("", status_code=status.HTTP_201_CREATED)
async def create_portfolio(data: PortfolioCreate, user: CurrentUser, service: Portfolios) -> PortfolioResponse:
    return PortfolioResponse.model_validate(await service.create(user.id, data))


@portfolios_router.get("/{portfolio_id}")
@limiter.limit(RATE_LIMITS["api_read"])
async def get_portfolio(
    request: Request, portfolio_id: UUID, user: CurrentUser, service: Portfolios
) -> PortfolioResponse:
    return PortfolioResponse.model_validate(await service.get(user.id, portfolio_id))


@portfolios_router.patch("/{portfolio_id}")
async def update_portfolio(
    portfolio_id: UUID, data: PortfolioUpdate, user: CurrentUser, service: Portfolios
) -> PortfolioResponse:
    return PortfolioResponse.model_validate(await service.update(user.id, portfolio_id, data))


@portfolios_router.delete("/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_portfolio(portfolio_id: UUID, user: CurrentUser, service: Portfolios) -> None:
    await service.delete(user.id, portfolio_id)


@portfolios_router.put("/{portfolio_id}/cash-balance")
async def update_cash_balance(
    portfolio_id: UUID, data: CashBalanceUpdate, user: CurrentUser, service: Portfolios
) -> PortfolioResponse:
    return PortfolioResponse.model_validate(await service.set_cash(user.id, portfolio_id, data))


@portfolios_router.delete("/{portfolio_id}/cash-balance/{exchange}")
async def delete_cash_balance(
    portfolio_id: UUID, exchange: str, user: CurrentUser, service: Portfolios
) -> PortfolioResponse:
    return PortfolioResponse.model_validate(await service.remove_cash(user.id, portfolio_id, exchange))


@assets_router.get("")
@limiter.limit(RATE_LIMITS["api_read"])
async def list_assets(
    request: Request, user: CurrentUser, service: Assets, portfolio_id: UUID | None = None
) -> list[AssetResponse]:
    return [AssetResponse.model_validate(a) for a in await service.list(user.id, portfolio_id)]


@assets_router.post("", status_code=status.HTTP_201_CREATED)
async def create_asset(data: AssetCreate, user: CurrentUser, service: Assets) -> AssetResponse:
    return AssetResponse.model_validate(await service.create(user.id, data))


@assets_router.get("/{asset_id}")
@limiter.limit(RATE_LIMITS["api_read"])
async def get_asset(request: Request, asset_id: UUID, user: CurrentUser, service: Assets) -> AssetResponse:
    return AssetResponse.model_validate(await service.get(user.id, asset_id))


@assets_router.patch("/{asset_id}")
async def update_asset(asset_id: UUID, data: AssetUpdate, user: CurrentUser, service: Assets) -> AssetResponse:
    return AssetResponse.model_validate(await service.update(user.id, asset_id, data))


@assets_router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(asset_id: UUID, user: CurrentUser, service: Assets) -> None:
    await service.delete(user.id, asset_id)
