from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_session
from app.core.errors import DomainError
from app.core.rate_limit import limiter
from app.domains.identity.dependencies import CurrentUser
from app.domains.transactions.balance_gaps import credit_gaps, find_gaps
from app.domains.transactions.csv_import import CsvImporter
from app.domains.transactions.listing import TransactionQueries, parse_types
from app.domains.transactions.repository import TransactionFilters
from app.domains.transactions.schemas import (
    BalanceGapsResponse,
    CreditResult,
    CsvImportResult,
    DeleteAllResult,
    PlatformsResponse,
    TransactionCreate,
    TransactionListPage,
    TransactionResponse,
    TransactionUpdate,
    TransactionWithAsset,
)
from app.domains.transactions.service import Requester, TransactionService
from app.services.csv_parsers import get_available_platforms

router = APIRouter()

Session = Annotated[AsyncSession, Depends(get_session)]


def _requester(request: Request, user_id: UUID) -> Requester:
    return Requester(
        user_id=user_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@router.get("", response_model=None)
async def list_transactions(
    user: CurrentUser,
    session: Session,
    asset_id: UUID | None = None,
    portfolio_id: UUID | None = None,
    transaction_type: Annotated[str | None, Query(max_length=30, description="Type, ou l'alias 'conversions'")] = None,
    exchange: Annotated[str | None, Query(max_length=50, description="Plateforme ; 'Manuel' : sans plateforme")] = None,
    asset_symbol: Annotated[str | None, Query(max_length=30)] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: Annotated[str | None, Query(max_length=100, description="Sur le symbole et les notes")] = None,
    include_total: bool = False,
    skip: int = 0,
    limit: int = 100,
) -> list[TransactionWithAsset] | TransactionListPage:
    filters = TransactionFilters(
        portfolio_id=portfolio_id,
        asset_id=asset_id,
        types=parse_types(transaction_type),
        exchange=exchange,
        asset_symbol=asset_symbol,
        date_from=date_from,
        date_to=date_to,
        search=search,
    )
    return await TransactionQueries(session).page(user.id, filters, skip=skip, limit=limit, with_total=include_total)


@router.get("/balance-gaps")
async def list_balance_gaps(user: CurrentUser, session: Session, threshold_eur: float = 5.0) -> BalanceGapsResponse:
    return await find_gaps(session, user.id, threshold_eur)


@router.post("/balance-gaps/credit-all", status_code=status.HTTP_201_CREATED)
async def credit_balance_gaps(user: CurrentUser, session: Session, threshold_eur: float = 5.0) -> CreditResult:
    return await credit_gaps(session, user.id, threshold_eur)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_transaction(
    request: Request, data: TransactionCreate, user: CurrentUser, session: Session
) -> TransactionResponse:
    return TransactionResponse.model_validate(
        await TransactionService(session).create(_requester(request, user.id), data)
    )


@router.get("/csv-platforms")
async def get_csv_platforms() -> PlatformsResponse:
    return PlatformsResponse(platforms=get_available_platforms())


@router.get("/platforms")
@limiter.limit("30/minute")
async def get_user_platforms(request: Request, user: CurrentUser, session: Session) -> PlatformsResponse:
    return PlatformsResponse(platforms=await TransactionQueries(session).platforms(user.id))


@router.get("/export-csv")
async def export_transactions_csv(
    user: CurrentUser, session: Session, portfolio_id: UUID | None = None
) -> StreamingResponse:
    content = await TransactionQueries(session).export_csv(user.id, portfolio_id)
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=transactions_export.csv"},
    )


@router.get("/{transaction_id}")
async def get_transaction(transaction_id: UUID, user: CurrentUser, session: Session) -> TransactionResponse:
    return TransactionResponse.model_validate(await TransactionService(session).get(user.id, transaction_id))


@router.patch("/{transaction_id}")
async def update_transaction(
    request: Request, transaction_id: UUID, data: TransactionUpdate, user: CurrentUser, session: Session
) -> TransactionResponse:
    service = TransactionService(session)
    return TransactionResponse.model_validate(await service.update(_requester(request, user.id), transaction_id, data))


@router.delete("/all")
async def delete_all_transactions(
    user: CurrentUser,
    session: Session,
    delete_assets: Annotated[bool, Query(description="Supprimer aussi les actifs")] = False,
    portfolio_id: Annotated[UUID | None, Query(description="Limiter à un portefeuille")] = None,
) -> DeleteAllResult:
    deleted = await TransactionService(session).delete_all(user.id, portfolio_id, delete_assets=delete_assets)
    return DeleteAllResult(deleted_count=deleted)


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(request: Request, transaction_id: UUID, user: CurrentUser, session: Session) -> None:
    await TransactionService(session).delete(_requester(request, user.id), transaction_id)


@router.post("/import-csv")
@limiter.limit("10/minute")
async def import_transactions_csv(
    request: Request,
    user: CurrentUser,
    session: Session,
    file: Annotated[UploadFile, File()],
    portfolio_id: UUID | None = None,
    platform: str | None = None,
    destination_exchange: Annotated[
        str | None, Query(description="Plateforme de destination des transferts sortants")
    ] = None,
) -> CsvImportResult:
    """Importe un export Crypto.com, Binance, Kraken ou au format InvestAI ; la plateforme est détectée si absente."""
    if not (file.filename or "").endswith(".csv"):
        raise DomainError("Le fichier doit être au format CSV")
    if portfolio_id is None:
        raise DomainError("L'identifiant du portefeuille est requis")
    try:
        content = (await file.read()).decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DomainError("Impossible de lire le fichier. Vérifiez le format du fichier.") from exc
    return await CsvImporter(session).run(user.id, portfolio_id, content, platform, destination_exchange)
