"""Réglages du rejeu FIFO : un réglage par divergence légitime entre l'affichage et la fiscalité."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from app.domains.transactions.cost_basis.layers import ZERO, FifoKey, Layer


class RewardBasis(StrEnum):
    """Coût des airdrops et récompenses : cours du jour (affichage) ou zéro (2086, sans acquisition à titre onéreux)."""

    MARKET_PRICE = "market_price"
    ZERO = "zero"


class ConversionDestBasis(StrEnum):
    """Coût de la destination d'une conversion : prix enregistré (affichage) ou coût source reporté (2086, sursis)."""

    RECORDED_PRICE = "recorded_price"
    CARRY_COST = "carry_cost"


class UnmatchedTransferInPolicy(StrEnum):
    """Transfert entrant sans sortie associée : coût récupéré (affichage) ou zéro (2086, coût non prouvé)."""

    RECOVER = "recover"
    ZERO = "zero"


class UnmatchedConversionOutPolicy(StrEnum):
    """Conversion sortante sans destination : couches conservées, ou consommées comme une cession (2086 historique)."""

    PRESERVE = "preserve"
    CONSUME = "consume"


class FeeHandling(StrEnum):
    """Frais : selon `fee_currency`, reportés si besoin de change (affichage), ou en devise de transaction (2086)."""

    FEE_CURRENCY_AWARE = "fee_currency_aware"
    TX_CURRENCY = "tx_currency"


@dataclass(frozen=True)
class ReplayConfig:
    """Réglages d'un rejeu ; les valeurs par défaut sont celles de l'affichage."""

    portfolio_currency: str = "EUR"
    reward_basis: RewardBasis = RewardBasis.MARKET_PRICE
    conversion_dest_basis: ConversionDestBasis = ConversionDestBasis.RECORDED_PRICE
    unmatched_transfer_in: UnmatchedTransferInPolicy = UnmatchedTransferInPolicy.RECOVER
    unmatched_conversion_out: UnmatchedConversionOutPolicy = UnmatchedConversionOutPolicy.PRESERVE
    fee_handling: FeeHandling = FeeHandling.FEE_CURRENCY_AWARE
    trim_transfer_network_fee: bool = True
    seed_stablecoin_layers: bool = False
    conversion_external_id_fallback: bool = True
    skip_null_executed_at: bool = False


@dataclass
class ReplayEvent:
    """Émis dans l'ordre du rejeu pour qu'un appelant applique sa propre formule de gain."""

    kind: str
    tx: Any
    tx_dt: datetime | None
    symbol: str
    quantity: Decimal
    price: Decimal = ZERO
    fee: Decimal = ZERO
    total_cost: Decimal = ZERO
    cost_removed: Decimal = ZERO
    oldest_acquired_at: datetime | None = None
    matched: bool = False
    dest_symbol: str | None = None
    dest_qty: Decimal = ZERO
    dest_cost: Decimal = ZERO
    dest_layer_cost: Decimal = ZERO


@dataclass
class ReplayResult:
    """Couches restantes, transferts sans arrivée, événements et montants à convertir après le rejeu."""

    fifo: dict[FifoKey, list[Layer]] = field(default_factory=dict)
    orphan_transit: dict[FifoKey, list[Layer]] = field(default_factory=dict)
    events: list[ReplayEvent] = field(default_factory=list)
    pending_fee_conversions: list[tuple[Any, Decimal, str]] = field(default_factory=list)
    dividend_income: dict[FifoKey, Decimal] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
