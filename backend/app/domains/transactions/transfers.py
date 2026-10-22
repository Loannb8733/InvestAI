import logging
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.portfolio.models import Asset
from app.domains.portfolio.repository import AssetRepository
from app.domains.transactions import ledger
from app.domains.transactions.models import Transaction, TransactionType
from app.domains.transactions.repository import TransactionRepository

logger = logging.getLogger(__name__)

COLD_WALLET_DESTINATION = "Tangem"
SAME_TRANSFER_TOLERANCE = Decimal("0.01")
SAME_TRANSFER_WINDOW = timedelta(days=1)


def _decimal(value: object) -> Decimal:
    """Les imports d'exchange fournissent des flottants : convertis par leur représentation décimale."""
    return Decimal(str(value)) if value is not None else Decimal("0")


def mirror_received_qty(qty: Decimal, fee: Decimal, fee_currency: str, symbol: str, *, amount_is_net: bool) -> Decimal:
    """Quantité réellement reçue à destination.

    Une saisie manuelle porte le montant brut envoyé : les frais réseau payés dans
    l'actif transféré en sont déduits. Les API de retrait (Binance, Kraken)
    donnent déjà le montant net (``amount_is_net``) : rien n'est déduit.
    """
    if not amount_is_net and fee > 0 and (not fee_currency or fee_currency == symbol):
        return qty - fee
    return qty


async def _existing_transfer_in(
    session: AsyncSession, destination: Asset, source: Transaction, quantity: Decimal
) -> Transaction | None:
    if source.executed_at is None:
        return None
    query = select(Transaction).where(
        Transaction.asset_id == destination.id,
        Transaction.transaction_type == TransactionType.TRANSFER_IN,
        Transaction.executed_at >= source.executed_at - SAME_TRANSFER_WINDOW,
        Transaction.executed_at <= source.executed_at + SAME_TRANSFER_WINDOW,
    )
    for candidate in (await session.execute(query)).scalars():
        if candidate.quantity > 0 and abs(candidate.quantity - quantity) / candidate.quantity < SAME_TRANSFER_TOLERANCE:
            return candidate
    return None


async def create_mirror_transfer_in(
    session: AsyncSession,
    source_transaction: Transaction,
    source_asset: Asset,
    destination_exchange: str,
    *,
    amount_is_net: bool = False,
) -> Transaction | None:
    """Transfert entrant miroir d'un transfert sortant, sur l'actif de la plateforme de destination.

    Un transfert entrant déjà saisi à ±1 jour et à 1 % près est relié au lieu d'être
    doublé. Le miroir porte le prix de revient de la source, qui se propage ainsi
    à la destination.
    """
    destination = await AssetRepository(session).on_platform(source_asset, destination_exchange)
    symbol = source_asset.symbol.upper()
    quantity = mirror_received_qty(
        _decimal(source_transaction.quantity),
        _decimal(source_transaction.fee),
        (source_transaction.fee_currency or "").upper(),
        symbol,
        amount_is_net=amount_is_net,
    )
    if quantity <= 0:
        logger.warning(
            "Mirror quantity <= 0 for %s transfer_out (qty=%s), skipping", symbol, source_transaction.quantity
        )
        return None
    existing = await _existing_transfer_in(session, destination, source_transaction, quantity)
    if existing is not None:
        logger.info(
            "Skip auto-mirror for %s on %s: transfer_in %s already exists", symbol, destination_exchange, existing.id
        )
        source_transaction.related_transaction_id = existing.id
        return None
    price = _decimal(source_transaction.price) or _decimal(source_asset.avg_buy_price)
    mirror = Transaction(
        asset_id=destination.id,
        transaction_type=TransactionType.TRANSFER_IN,
        quantity=quantity,
        price=price,
        fee=Decimal("0"),
        currency=source_transaction.currency,
        executed_at=source_transaction.executed_at,
        exchange=destination_exchange,
        notes=f"Auto-mirror from {source_asset.exchange or 'unknown'}",
        related_transaction_id=source_transaction.id,
    )
    mirror.compute_hash()
    session.add(mirror)
    await session.flush()
    source_transaction.related_transaction_id = mirror.id
    destination.quantity = ledger.moved(_decimal(destination.quantity), TransactionType.TRANSFER_IN, quantity)
    await session.flush()
    destination.avg_buy_price = await TransactionRepository(session).cost_basis(destination.id)
    return mirror
