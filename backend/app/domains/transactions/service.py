from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError, NotFoundError
from app.domains.portfolio.models import Asset
from app.domains.portfolio.repository import AssetRepository
from app.domains.system.audit import log_audit
from app.domains.transactions import ledger
from app.domains.transactions.models import Transaction, TransactionType
from app.domains.transactions.repository import TransactionRepository
from app.domains.transactions.schemas import TransactionCreate, TransactionUpdate
from app.domains.transactions.transfers import COLD_WALLET_DESTINATION, create_mirror_transfer_in

TRANSACTION_NOT_FOUND = "Transaction non trouvée"
ASSET_NOT_FOUND = "Actif non trouvé"
DUPLICATE = "Une transaction identique existe déjà (même actif, type, quantité, prix et date)."
LINKED_TYPE_CHANGE = "Le type d'un transfert relié ne se modifie pas : supprimez-le puis recréez-le."


class DuplicateTransactionError(DomainError):
    status_code = 409


@dataclass(frozen=True)
class Requester:
    user_id: UUID
    ip_address: str | None
    user_agent: str | None


def _audit_value(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, Decimal | float | int):
        return float(value)
    return str(value)


class TransactionService:
    """Écritures du journal : chacune ajuste quantité et prix de revient de son actif, et laisse une trace d'audit."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._transactions = TransactionRepository(session)
        self._assets = AssetRepository(session)

    async def _audit(self, requester: Requester, action: str, resource_id: UUID, details: dict[str, Any]) -> None:
        await log_audit(
            self._session,
            action=action,
            user_id=requester.user_id,
            resource_type="transaction",
            resource_id=str(resource_id),
            details=details,
            ip_address=requester.ip_address,
            user_agent=requester.user_agent,
        )

    async def _owned(self, user_id: UUID, transaction_id: UUID) -> Transaction:
        transaction = await self._transactions.owned_one(user_id, transaction_id)
        if transaction is None:
            raise NotFoundError(TRANSACTION_NOT_FOUND)
        return transaction

    async def _rehash(self, transaction: Transaction) -> None:
        transaction.compute_hash()
        if transaction.internal_hash and await self._transactions.hash_taken(
            transaction.internal_hash, other_than=transaction.id
        ):
            raise DuplicateTransactionError(DUPLICATE)

    async def _refresh_cost_basis(self, *assets: Asset) -> None:
        await self._transactions.flush()
        for asset in assets:
            asset.avg_buy_price = await self._transactions.cost_basis(asset.id)

    async def _platform_asset(self, asset: Asset, exchange: str | None) -> Asset:
        wanted = (exchange or "").strip()
        if wanted and wanted.lower() != (asset.exchange or "").strip().lower():
            return await self._assets.on_platform(asset, wanted)
        return asset

    async def get(self, user_id: UUID, transaction_id: UUID) -> Transaction:
        return await self._owned(user_id, transaction_id)

    async def create(self, requester: Requester, data: TransactionCreate) -> Transaction:
        """Une plateforme différente de celle de l'actif range la transaction sur l'actif de cette plateforme."""
        chosen = await self._assets.owned_one(requester.user_id, data.asset_id)
        if chosen is None:
            raise NotFoundError(ASSET_NOT_FOUND)
        asset = await self._platform_asset(chosen, data.exchange)
        quantity = ledger.capped(data.quantity, ledger.MAX_TRANSACTION_QUANTITY, "quantity")
        transaction = Transaction(
            asset_id=asset.id,
            transaction_type=data.transaction_type,
            quantity=quantity,
            price=ledger.capped(data.price, ledger.MAX_PRICE, "price"),
            fee=ledger.capped(data.fee, ledger.MAX_PRICE, "fee"),
            fee_currency=data.fee_currency,
            currency=data.currency,
            executed_at=data.executed_at,
            exchange=data.exchange,
            external_id=data.external_id,
            notes=data.notes,
        )
        await self._rehash(transaction)
        self._transactions.add(transaction)
        asset.quantity = ledger.moved(asset.quantity, transaction.transaction_type, quantity)
        await self._refresh_cost_basis(asset)
        if data.transaction_type == TransactionType.TRANSFER_OUT:
            destination = (data.destination_exchange or "").strip() or COLD_WALLET_DESTINATION
            await create_mirror_transfer_in(self._session, transaction, asset, destination)
        await self._audit(
            requester,
            "transaction.create",
            transaction.id,
            {
                "asset_id": str(asset.id),
                "symbol": asset.symbol,
                "type": data.transaction_type.value,
                "quantity": float(data.quantity),
                "price": float(data.price),
                "fee": float(data.fee),
            },
        )
        return transaction

    async def update(self, requester: Requester, transaction_id: UUID, data: TransactionUpdate) -> Transaction:
        """Annule l'effet de l'ancienne version, applique la nouvelle, recalcule l'empreinte.

        Une nouvelle plateforme déplace la transaction vers l'actif correspondant ;
        la quantité d'un transfert relié met à jour son miroir.
        """
        transaction = await self._owned(requester.user_id, transaction_id)
        changes = data.model_dump(exclude_unset=True)
        if (
            "transaction_type" in changes
            and transaction.related_transaction_id
            and changes["transaction_type"] != transaction.transaction_type
        ):
            raise DomainError(LINKED_TYPE_CHANGE)
        before = {field: _audit_value(getattr(transaction, field)) for field in changes}
        source = await self._assets.by_id(transaction.asset_id)
        source.quantity = ledger.moved(source.quantity, transaction.transaction_type, transaction.quantity, undo=True)
        for field, value in changes.items():
            setattr(transaction, field, value)
        target = await self._platform_asset(source, transaction.exchange) if "exchange" in changes else source
        transaction.asset_id = target.id
        target.quantity = ledger.moved(target.quantity, transaction.transaction_type, transaction.quantity)
        await self._rehash(transaction)
        if "quantity" in changes and transaction.related_transaction_id:
            await self._resize_mirror(transaction)
        if changes.get("transaction_type") == TransactionType.TRANSFER_OUT and not transaction.related_transaction_id:
            await self._transactions.flush()
            await create_mirror_transfer_in(self._session, transaction, target, COLD_WALLET_DESTINATION)
        await self._refresh_cost_basis(*{source.id: source, target.id: target}.values())
        await self._audit(
            requester,
            "transaction.update",
            transaction.id,
            {"old": before, "new": {field: _audit_value(getattr(transaction, field)) for field in changes}},
        )
        return transaction

    async def _resize_mirror(self, transaction: Transaction) -> None:
        mirror = (
            await self._transactions.get(transaction.related_transaction_id)
            if transaction.related_transaction_id
            else None
        )
        if mirror is None:
            return
        asset = await self._assets.by_id(mirror.asset_id)
        asset.quantity = ledger.moved(asset.quantity, mirror.transaction_type, mirror.quantity, undo=True)
        mirror.quantity = transaction.quantity
        asset.quantity = ledger.moved(asset.quantity, mirror.transaction_type, mirror.quantity)
        await self._rehash(mirror)
        await self._refresh_cost_basis(asset)

    async def delete(self, requester: Requester, transaction_id: UUID) -> None:
        """Supprime la transaction et son miroir éventuel, en annulant leurs effets sur les actifs."""
        transaction = await self._owned(requester.user_id, transaction_id)
        details = {
            "asset_id": str(transaction.asset_id),
            "type": transaction.transaction_type.value,
            "quantity": float(transaction.quantity),
            "price": float(transaction.price),
            "fee": float(transaction.fee),
            "executed_at": str(transaction.executed_at),
            "exchange": transaction.exchange,
        }
        touched: dict[UUID, Asset] = {}
        mirror = (
            await self._transactions.get(transaction.related_transaction_id)
            if transaction.related_transaction_id
            else None
        )
        for removed in [transaction] + ([mirror] if mirror is not None else []):
            asset = await self._assets.by_id(removed.asset_id)
            asset.quantity = ledger.moved(asset.quantity, removed.transaction_type, removed.quantity, undo=True)
            touched[asset.id] = asset
        transaction.related_transaction_id = None
        if mirror is not None:
            mirror.related_transaction_id = None
            await self._transactions.flush()
            await self._transactions.delete(mirror)
        await self._transactions.delete(transaction)
        await self._refresh_cost_basis(*touched.values())
        await self._audit(requester, "transaction.delete", transaction_id, details)

    async def delete_all(self, user_id: UUID, portfolio_id: UUID | None, *, delete_assets: bool) -> int:
        """Vide le journal (d'un portefeuille ou de tous) ; les actifs sont remis à zéro, ou supprimés."""
        assets = await self._assets.listed_all(user_id, portfolio_id)
        if not assets:
            return 0
        deleted = await self._transactions.delete_for_assets([a.id for a in assets])
        for asset in assets:
            if delete_assets:
                await self._session.delete(asset)
            else:
                asset.quantity = ledger.ZERO
                asset.avg_buy_price = ledger.ZERO
        await self._session.flush()
        return deleted
