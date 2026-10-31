"""État partagé par les étapes d'un rejeu FIFO."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.domains.transactions.cost_basis.config import ReplayConfig, ReplayEvent, ReplayResult
from app.domains.transactions.cost_basis.layers import FifoKey, Layer

logger = logging.getLogger(__name__)

ONE = Decimal("1")


@dataclass
class ReplayContext:
    """Réglages, résultat en construction et données d'appui d'un rejeu."""

    config: ReplayConfig
    result: ReplayResult
    aid_to_symbol: dict[str, str]
    aid_to_avg_price: dict[str, Decimal]
    sym_avg_price: dict[str, Decimal]
    usd_to_portfolio: Decimal | float | None
    conversion_ins: list[Any]
    on_event: Callable[[ReplayEvent], None] | None

    @property
    def portfolio_currency(self) -> str:
        """Devise du portefeuille, en majuscules."""
        return self.config.portfolio_currency.upper()

    def emit(self, event: ReplayEvent) -> None:
        """Enregistre un événement et le transmet à l'appelant."""
        self.result.events.append(event)
        if self.on_event is not None:
            self.on_event(event)

    def warn(self, message: str, *args: object) -> None:
        """Journalise une anomalie et la garde dans le résultat."""
        logger.warning(message, *args)
        self.result.warnings.append(message % args if args else message)

    def add_layer(self, key: FifoKey, layer: Layer) -> None:
        """Ajoute une couche à la fin du lot d'une clé."""
        self.result.fifo.setdefault(key, []).append(layer)


@dataclass(frozen=True)
class ReplayRow:
    """Une transaction du rejeu, normalisée."""

    tx: Any
    symbol: str
    exchange: str
    key: FifoKey
    quantity: Decimal
    executed_at: datetime | None


def aware(moment: datetime | None) -> datetime | None:
    """Date en UTC quand elle est sans fuseau."""
    if moment is not None and moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment


def fx_rate(tx: Any) -> Decimal:
    """Taux de change saisi à l'exécution, 1 par défaut."""
    return Decimal(str(tx.conversion_rate)) if tx.conversion_rate else ONE


def transaction_currency(tx: Any) -> str:
    """Devise de la transaction, EUR par défaut."""
    return (tx.currency or "EUR").upper()
