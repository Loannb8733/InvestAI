import logging
from decimal import Decimal

from app.domains.transactions.models import TransactionType

logger = logging.getLogger(__name__)

INFLOWS = frozenset(
    {
        TransactionType.BUY,
        TransactionType.TRANSFER_IN,
        TransactionType.CONVERSION_IN,
        TransactionType.AIRDROP,
        TransactionType.STAKING_REWARD,
        TransactionType.INTEREST,
    }
)
OUTFLOWS = frozenset(
    {TransactionType.SELL, TransactionType.TRANSFER_OUT, TransactionType.CONVERSION_OUT, TransactionType.FEE}
)
COST_BASIS_TYPES = (TransactionType.BUY, TransactionType.CONVERSION_IN, TransactionType.TRANSFER_IN)
LINKED_TYPES = frozenset({TransactionType.TRANSFER_IN, TransactionType.TRANSFER_OUT})

MAX_TRANSACTION_QUANTITY = Decimal("9.9999e17")
MAX_PRICE = Decimal("9.9999e11")
MAX_ASSET_QUANTITY = Decimal("9.9999e15")
ZERO = Decimal("0")


def signed(kind: TransactionType, quantity: Decimal) -> Decimal:
    """Effet d'une transaction sur la quantité détenue ; nul pour le staking, dont le principal sort du journal."""
    if kind in INFLOWS:
        return quantity
    if kind in OUTFLOWS:
        return -quantity
    return ZERO


def capped(value: Decimal, cap: Decimal, field: str) -> Decimal:
    """Plafond de la colonne, bien au-delà de tout montant réaliste ; un dépassement est journalisé."""
    if value > cap:
        logger.warning("%s=%s exceeds column capacity; clamping to %s", field, value, cap)
        return cap
    return value


def moved(position: Decimal, kind: TransactionType, quantity: Decimal, *, undo: bool = False) -> Decimal:
    """Quantité d'un actif après application (ou annulation) d'une transaction, jamais négative."""
    delta = signed(kind, quantity)
    result = position - delta if undo else position + delta
    if result < ZERO:
        logger.warning("Quantity would go negative (%s), clamped to 0", result)
        return ZERO
    return capped(result, MAX_ASSET_QUANTITY, "asset.quantity")
