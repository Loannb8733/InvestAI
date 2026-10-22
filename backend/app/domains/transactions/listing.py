import csv
import io
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError, NotFoundError
from app.domains.portfolio.models import Asset
from app.domains.portfolio.repository import AssetRepository, PortfolioRepository
from app.domains.transactions.models import Transaction, TransactionType
from app.domains.transactions.repository import TransactionFilters, TransactionRepository
from app.domains.transactions.schemas import TransactionListPage, TransactionWithAsset

CONVERSIONS_ALIAS = "conversions"
EXPORT_HEADER = ["symbol", "type", "quantity", "price", "fee", "date", "exchange", "notes"]


def parse_types(raw: str | None) -> tuple[TransactionType, ...]:
    """Type demandé, ou les deux sens de conversion pour l'alias ``conversions`` ; vide sans filtre."""
    if not raw:
        return ()
    value = raw.strip().lower()
    if value == CONVERSIONS_ALIAS:
        return (TransactionType.CONVERSION_IN, TransactionType.CONVERSION_OUT)
    try:
        return (TransactionType(value),)
    except ValueError as exc:
        raise InvalidTypeError("Type de transaction invalide") from exc


class InvalidTypeError(DomainError):
    status_code = 422


def _with_asset(transaction: Transaction, asset: Asset) -> TransactionWithAsset:
    response = TransactionWithAsset.model_validate(
        {
            **{
                field: getattr(transaction, field)
                for field in TransactionWithAsset.model_fields
                if hasattr(transaction, field)
            },
            "exchange": transaction.exchange or asset.exchange,
            "asset_symbol": asset.symbol,
            "asset_name": asset.name,
            "asset_type": asset.asset_type.value,
        }
    )
    return response


def _plain(value: Decimal) -> str:
    return format(value.normalize(), "f") if value else "0"


class TransactionQueries:
    def __init__(self, session: AsyncSession) -> None:
        self._transactions = TransactionRepository(session)
        self._assets = AssetRepository(session)
        self._portfolios = PortfolioRepository(session)

    async def _check_scope(self, user_id: UUID, filters: TransactionFilters) -> None:
        if filters.portfolio_id is not None and await self._portfolios.owned_one(user_id, filters.portfolio_id) is None:
            raise NotFoundError("Portefeuille non trouvé")
        if filters.asset_id is not None and await self._assets.owned_one(user_id, filters.asset_id) is None:
            raise NotFoundError("Actif non trouvé")

    async def page(
        self, user_id: UUID, filters: TransactionFilters, *, skip: int, limit: int, with_total: bool
    ) -> list[TransactionWithAsset] | TransactionListPage:
        """Page filtrée en SQL, donc sur tout l'historique ; ``with_total`` ajoute le nombre total filtré."""
        await self._check_scope(user_id, filters)
        items = [_with_asset(t, a) for t, a in await self._transactions.page(user_id, filters, skip=skip, limit=limit)]
        if not with_total:
            return items
        return TransactionListPage(items=items, total=await self._transactions.count(user_id, filters))

    async def platforms(self, user_id: UUID) -> list[str]:
        return await self._transactions.platforms(user_id)

    async def export_csv(self, user_id: UUID, portfolio_id: UUID | None) -> str:
        """Journal au format CSV (séparateur « ; »), les plus récentes d'abord."""
        portfolios = await self._portfolios.owned(user_id)
        if not portfolios or (portfolio_id is not None and portfolio_id not in {p.id for p in portfolios}):
            raise NotFoundError("Aucun portefeuille trouvé")
        output = io.StringIO()
        writer = csv.writer(output, delimiter=";")
        writer.writerow(EXPORT_HEADER)
        for transaction, asset in await self._transactions.all_with_assets(user_id, portfolio_id):
            writer.writerow(
                [
                    asset.symbol,
                    transaction.transaction_type.value,
                    _plain(transaction.quantity),
                    _plain(transaction.price),
                    _plain(transaction.fee),
                    transaction.executed_at.strftime("%Y-%m-%d %H:%M:%S") if transaction.executed_at else "",
                    transaction.exchange or asset.exchange or "",
                    transaction.notes or "",
                ]
            )
        return output.getvalue()
