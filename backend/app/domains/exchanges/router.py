from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_session
from app.core.errors import NotFoundError
from app.core.rate_limit import limiter
from app.domains.exchanges import background
from app.domains.exchanges.connectors.registry import SUPPORTED_EXCHANGES
from app.domains.exchanges.schemas import (
    APIKeyCreate,
    APIKeyResponse,
    APIKeyUpdate,
    BalanceSyncResult,
    ColdWalletCreate,
    ColdWalletResponse,
    ConnectionTestResult,
    ExchangeInfo,
    TaskDispatched,
    TaskStatus,
)
from app.domains.exchanges.service import ExchangeAccounts
from app.domains.identity.dependencies import CurrentUser

keys_router = APIRouter()
wallets_router = APIRouter()


def get_accounts(session: Annotated[AsyncSession, Depends(get_session)]) -> ExchangeAccounts:
    return ExchangeAccounts(session)


Accounts = Annotated[ExchangeAccounts, Depends(get_accounts)]


@keys_router.get("/exchanges")
async def list_supported_exchanges() -> list[ExchangeInfo]:
    return [ExchangeInfo.model_validate(exchange) for exchange in SUPPORTED_EXCHANGES]


@keys_router.get("")
async def list_api_keys(user: CurrentUser, accounts: Accounts) -> list[APIKeyResponse]:
    return [APIKeyResponse.model_validate(key) for key in await accounts.keys(user.id)]


@keys_router.post("", status_code=status.HTTP_201_CREATED)
async def create_api_key(data: APIKeyCreate, user: CurrentUser, accounts: Accounts) -> APIKeyResponse:
    return APIKeyResponse.model_validate(await accounts.add_key(user.id, data))


@keys_router.get("/import-status/{task_id}")
async def get_import_status(task_id: str, user: CurrentUser) -> TaskStatus:
    """État d'un import en arrière-plan ; une tâche d'autrui répond comme une tâche inconnue."""
    found = background.status_of(user.id, task_id)
    if found is None:
        raise NotFoundError("Tâche non trouvée")
    return found


@keys_router.get("/{api_key_id}")
async def get_api_key(api_key_id: UUID, user: CurrentUser, accounts: Accounts) -> APIKeyResponse:
    return APIKeyResponse.model_validate(await accounts.key(user.id, api_key_id))


@keys_router.patch("/{api_key_id}")
async def update_api_key(api_key_id: UUID, data: APIKeyUpdate, user: CurrentUser, accounts: Accounts) -> APIKeyResponse:
    return APIKeyResponse.model_validate(await accounts.update_key(user.id, api_key_id, data))


@keys_router.delete("/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(api_key_id: UUID, user: CurrentUser, accounts: Accounts) -> None:
    await accounts.remove_key(user.id, api_key_id)


@keys_router.post("/{api_key_id}/test")
@limiter.limit("5/minute")
async def test_api_key(
    request: Request, api_key_id: UUID, user: CurrentUser, accounts: Accounts
) -> ConnectionTestResult:
    return await accounts.test_key(user.id, api_key_id)


@keys_router.post("/{api_key_id}/sync")
@limiter.limit("5/minute")
async def sync_exchange(request: Request, api_key_id: UUID, user: CurrentUser, accounts: Accounts) -> BalanceSyncResult:
    return await accounts.sync_balances(user.id, api_key_id)


@keys_router.post("/{api_key_id}/import-async")
@limiter.limit("3/minute")
async def import_history_async(
    request: Request, api_key_id: UUID, user: CurrentUser, accounts: Accounts
) -> TaskDispatched:
    """Lance la synchronisation de l'historique en arrière-plan ; l'état se lit sur /import-status/{task_id}."""
    await accounts.key(user.id, api_key_id)
    task_id = background.start(user.id, api_key_id, "import")
    return TaskDispatched(task_id=task_id, message="Import lancé en arrière-plan")


@keys_router.post("/{api_key_id}/refresh-fx")
@limiter.limit("3/minute")
async def refresh_exchange_fx(
    request: Request, api_key_id: UUID, user: CurrentUser, accounts: Accounts
) -> TaskDispatched:
    """Recalcule en arrière-plan les taux USD→EUR des transactions déjà importées, sans en créer."""
    await accounts.key(user.id, api_key_id)
    task_id = background.start(user.id, api_key_id, "fx_refresh")
    return TaskDispatched(task_id=task_id, message="Recalcul des taux FX lancé en arrière-plan")


@wallets_router.get("")
async def list_cold_wallets(user: CurrentUser, accounts: Accounts) -> list[ColdWalletResponse]:
    return [ColdWalletResponse.model_validate(w) for w in await accounts.wallets(user.id)]


@wallets_router.post("", status_code=status.HTTP_201_CREATED)
async def upsert_cold_wallet(data: ColdWalletCreate, user: CurrentUser, accounts: Accounts) -> ColdWalletResponse:
    return ColdWalletResponse.model_validate(await accounts.name_wallet(user.id, data))


@wallets_router.delete("/{wallet_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cold_wallet(wallet_id: UUID, user: CurrentUser, accounts: Accounts) -> None:
    await accounts.remove_wallet(user.id, wallet_id)
