from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from app.domains.transactions.transfers import COLD_WALLET_DESTINATION

NOISE = Decimal("1e-8")
DUST_SHARE = Decimal("1e-6")
SAME_MOVE_SHARE = Decimal("1e-6")
CREDITED = frozenset({"success", "credited", "completed", "complete", "done", "ok", "settled"})
SENT = frozenset({"success", "completed", "complete", "done", "ok", "sent", "processed"})

Gap = Literal["none", "dust", "transfer"]


def balance_gap(ours: Decimal, theirs: Decimal) -> Gap:
    """Nature d'un écart de solde : bruit, poussière d'arrondi à aligner, ou mouvement à enregistrer."""
    gap = abs(theirs - ours)
    if gap <= NOISE:
        return "none"
    return "dust" if gap <= max(NOISE, abs(theirs) * DUST_SHARE) else "transfer"


def undoes_recent_move(gap: Decimal, recent: Iterable[Decimal | None]) -> bool:
    """L'ajustement aurait-il la taille exacte d'un mouvement récent que le solde local n'a pas encore vu ?"""
    if gap == 0:
        return False
    for quantity in recent:
        if quantity is None or quantity <= 0:
            continue
        if abs(abs(gap) - quantity) <= max(NOISE, quantity * SAME_MOVE_SHARE):
            return True
    return False


def has_status(status: str | None, accepted: frozenset[str]) -> bool:
    return (status or "").strip().lower() in accepted


def cold_wallet_for(address: str | None, wallets: dict[str, str]) -> str:
    """Wallet froid nommé pour cette adresse de retrait, sinon le wallet par défaut."""
    if address:
        label = wallets.get(address.strip().lower())
        if label:
            return label
    return COLD_WALLET_DESTINATION


def as_utc(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)
