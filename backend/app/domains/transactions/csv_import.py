import asyncio
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError, NotFoundError
from app.domains.market_data.history.tasks import schedule_refresh
from app.domains.portfolio.classification import is_fiat
from app.domains.portfolio.models import Asset, AssetType, Portfolio
from app.domains.transactions import ledger
from app.domains.transactions.models import Transaction, TransactionType
from app.domains.transactions.repository import TransactionRepository
from app.domains.transactions.schemas import CsvImportResult
from app.domains.transactions.transfers import COLD_WALLET_DESTINATION, create_mirror_transfer_in
from app.services.csv_parsers import detect_csv_format, get_parser_by_name

logger = logging.getLogger(__name__)

MIN_QUANTITY = Decimal("1e-8")
MAX_REPORTED_ERRORS = 50
IMPORTABLE = {t.value: t for t in ledger.INFLOWS | ledger.OUTFLOWS}
UNKNOWN_FORMAT = "Format CSV non reconnu. Veuillez spécifier la plateforme."

DedupKey = tuple[str, str, str, str, int]


@dataclass
class _Batch:
    portfolio: Portfolio
    exchange: str
    destination: str | None
    by_platform: dict[tuple[str, str], Asset]
    seen: set[DedupKey]
    errors: list[str]
    created: list[UUID] = field(default_factory=list)
    skipped: int = 0
    touched: dict[UUID, Asset] = field(default_factory=dict)


def _bounded(value: Any, cap: Decimal, name: str) -> Decimal:
    return max(ledger.ZERO, ledger.capped(Decimal(str(value)), cap, name))


def _dedup_key(symbol: str, kind: str, quantity: Any, price: Any, moment: Any) -> DedupKey:
    return (symbol, kind, f"{float(quantity):.8f}", f"{float(price):.8f}", int(moment.timestamp()))


class CsvImporter:
    """Import d'un export de plateforme dans un portefeuille.

    Chaque ligne ajuste la quantité de son actif comme une saisie manuelle ; le prix
    de revient des actifs touchés est recalculé à la fin. Une ligne déjà présente
    (même symbole, type, quantité, prix et seconde, ou même empreinte) est comptée
    à part.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._transactions = TransactionRepository(session)

    async def run(
        self, user_id: UUID, portfolio_id: UUID, content: str, platform: str | None, destination_exchange: str | None
    ) -> CsvImportResult:
        query = select(Portfolio).where(Portfolio.id == portfolio_id, Portfolio.user_id == user_id)
        portfolio = (await self._session.execute(query)).scalar_one_or_none()
        if portfolio is None:
            raise NotFoundError("Portefeuille non trouvé")
        parser = get_parser_by_name(platform) if platform else detect_csv_format(content)
        if parser is None:
            raise DomainError(f"Unknown platform: {platform}" if platform else UNKNOWN_FORMAT)
        try:
            rows, errors = await asyncio.to_thread(parser.parse_csv, content)
        except Exception as exc:
            logger.error("Error parsing CSV: %s", exc)
            raise DomainError("Erreur lors de la lecture du fichier CSV. Vérifiez le format et le contenu.") from exc
        assets = list((await self._session.execute(select(Asset).where(Asset.portfolio_id == portfolio.id))).scalars())
        batch = _Batch(
            portfolio=portfolio,
            exchange=parser.name,
            destination=destination_exchange.strip() if destination_exchange else None,
            by_platform={(a.symbol.upper(), a.exchange or ""): a for a in assets},
            seen=await self._existing_keys([a.id for a in assets]),
            errors=list(errors),
        )
        for row in sorted(rows, key=lambda r: r.timestamp):
            await self._import_row(row, batch)
        for asset in batch.touched.values():
            asset.avg_buy_price = await self._transactions.cost_basis(asset.id)
            schedule_refresh(asset.symbol, asset.asset_type.value)
        await self._session.flush()
        return CsvImportResult(
            success_count=len(batch.created),
            error_count=len(batch.errors),
            skipped_count=batch.skipped,
            errors=batch.errors[:MAX_REPORTED_ERRORS],
            created_transactions=batch.created,
        )

    async def _import_row(self, row: Any, batch: "_Batch") -> None:
        symbol = row.symbol.upper()
        if is_fiat(symbol):
            return
        asset = await self._asset(batch.portfolio, symbol, batch.exchange, row.currency, batch.by_platform)
        kind = IMPORTABLE.get(row.transaction_type)
        if kind is None:
            batch.errors.append(f"Unknown transaction type: {row.transaction_type}")
            return
        key = _dedup_key(symbol, kind.value, row.quantity, row.price, row.timestamp)
        if key in batch.seen:
            batch.skipped += 1
            return
        batch.seen.add(key)
        quantity = _bounded(row.quantity, ledger.MAX_TRANSACTION_QUANTITY, "quantity")
        if quantity < MIN_QUANTITY:
            return
        fee = _bounded(row.fee, ledger.MAX_PRICE, "fee")
        transaction = Transaction(
            asset_id=asset.id,
            transaction_type=kind,
            quantity=quantity,
            price=_bounded(row.price, ledger.MAX_PRICE, "price"),
            fee=fee,
            fee_currency=symbol if fee > 0 else None,
            currency=row.currency or "EUR",
            executed_at=row.timestamp,
            notes=row.notes,
            exchange=batch.exchange,
        )
        transaction.compute_hash()
        if transaction.internal_hash and await self._transactions.hash_taken(transaction.internal_hash):
            batch.skipped += 1
            return
        self._transactions.add(transaction)
        asset.quantity = ledger.moved(asset.quantity, kind, quantity)
        batch.touched[asset.id] = asset
        if kind == TransactionType.TRANSFER_OUT:
            await self._transactions.flush()
            await create_mirror_transfer_in(
                self._session, transaction, asset, batch.destination or COLD_WALLET_DESTINATION
            )
        await self._transactions.flush()
        batch.created.append(transaction.id)

    async def _existing_keys(self, asset_ids: list[UUID]) -> set[DedupKey]:
        if not asset_ids:
            return set()
        query = (
            select(
                Asset.symbol,
                Transaction.transaction_type,
                Transaction.quantity,
                Transaction.price,
                Transaction.executed_at,
            )
            .join(Asset, Transaction.asset_id == Asset.id)
            .where(Transaction.asset_id.in_(asset_ids), Transaction.executed_at.is_not(None))
        )
        return {
            _dedup_key(symbol.upper(), kind.value, quantity, price, moment)
            for symbol, kind, quantity, price, moment in (await self._session.execute(query)).all()
        }

    async def _asset(
        self,
        portfolio: Portfolio,
        symbol: str,
        exchange: str,
        currency: str | None,
        by_platform: dict[tuple[str, str], Asset],
    ) -> Asset:
        """Actif du symbole sur la plateforme du fichier ; un actif sans plateforme la reçoit, sinon il est créé."""
        asset = by_platform.get((symbol, exchange))
        if asset is None and (unassigned := by_platform.pop((symbol, ""), None)) is not None:
            unassigned.exchange = exchange
            asset = unassigned
        if asset is None:
            asset = Asset(
                portfolio_id=portfolio.id,
                symbol=symbol,
                name=symbol,
                asset_type=AssetType.CRYPTO,
                quantity=ledger.ZERO,
                avg_buy_price=ledger.ZERO,
                currency=currency or "EUR",
                exchange=exchange,
            )
            self._session.add(asset)
            await self._session.flush()
        by_platform[(symbol, exchange)] = asset
        return asset
