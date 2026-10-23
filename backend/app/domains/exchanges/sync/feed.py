import logging
from collections.abc import Awaitable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from app.domains.exchanges.connectors.base import (
    BaseExchangeService,
    ExchangeDeposit,
    ExchangeFiatOrder,
    ExchangeTrade,
    ExchangeWithdrawal,
)

logger = logging.getLogger(__name__)

PAGE = 500
RECENT_LEDGER_ENTRIES = 1000
ALL_LEDGER_ENTRIES = 10000


@runtime_checkable
class LedgerSource(Protocol):
    async def get_ledgers(self, *, limit: int = ...) -> list[dict[str, Any]]: ...

    async def get_instant_buys(
        self, limit: int = ..., ledgers: list[dict[str, Any]] | None = ...
    ) -> tuple[list[ExchangeTrade], set[str]]: ...

    async def get_crypto_conversions(
        self, limit: int = ..., exclude_refids: set[str] | None = ..., ledgers: list[dict[str, Any]] | None = ...
    ) -> list[ExchangeTrade]: ...

    async def get_rewards(
        self, limit: int = ..., ledgers: list[dict[str, Any]] | None = ...
    ) -> list[ExchangeTrade]: ...


@runtime_checkable
class InstantBuySource(Protocol):
    async def get_instant_buys(self, limit: int = ...) -> tuple[list[ExchangeTrade], set[str]]: ...


@runtime_checkable
class ConversionSource(Protocol):
    async def get_crypto_conversions(self, limit: int = ...) -> list[ExchangeTrade]: ...


@runtime_checkable
class RewardSource(Protocol):
    async def get_rewards(self, limit: int = ...) -> list[ExchangeTrade]: ...


@runtime_checkable
class AutoInvestSource(Protocol):
    async def get_auto_invest_history(self) -> list[ExchangeFiatOrder]: ...


@runtime_checkable
class ConvertSource(Protocol):
    async def get_convert_history(self, start_time: datetime | None = ...) -> list[ExchangeFiatOrder]: ...


@dataclass
class Feed:
    """Historique rendu par un exchange, par nature d'opération."""

    trades: list[ExchangeTrade] = field(default_factory=list)
    instant_buys: list[ExchangeTrade] = field(default_factory=list)
    fiat_orders: list[ExchangeFiatOrder] = field(default_factory=list)
    conversions: list[ExchangeTrade] = field(default_factory=list)
    rewards: list[ExchangeTrade] = field(default_factory=list)
    deposits: list[ExchangeDeposit] = field(default_factory=list)
    withdrawals: list[ExchangeWithdrawal] = field(default_factory=list)


async def _safely[T](label: str, call: Awaitable[list[T]]) -> list[T]:
    try:
        return await call
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s indisponible : %s", label, exc)
        return []


async def _pair(
    label: str, call: Awaitable[tuple[list[ExchangeTrade], set[str]]]
) -> tuple[list[ExchangeTrade], set[str]]:
    try:
        return await call
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s indisponible : %s", label, exc)
        return [], set()


def _fingerprints(orders: Iterable[ExchangeFiatOrder]) -> set[tuple[str, str, int]]:
    prints = set()
    for order in orders:
        minute = int(order.timestamp.timestamp()) // 60
        for shift in (-1, 0, 1):
            prints.add((order.crypto_symbol, str(order.crypto_amount.normalize()), minute + shift))
    return prints


def unseen_converts(
    converts: Iterable[ExchangeFiatOrder], fiat_orders: Iterable[ExchangeFiatOrder]
) -> list[ExchangeFiatOrder]:
    """Conversions fiat absentes des ordres fiat : même actif, même quantité, à une minute près."""
    seen = _fingerprints(fiat_orders)
    return [
        c
        for c in converts
        if (c.crypto_symbol, str(c.crypto_amount.normalize()), int(c.timestamp.timestamp()) // 60) not in seen
    ]


async def _ledger_feed(client: LedgerSource, feed: Feed, full: bool) -> None:
    limit = ALL_LEDGER_ENTRIES if full else RECENT_LEDGER_ENTRIES
    ledgers = await _safely("Ledgers", client.get_ledgers(limit=limit))
    feed.instant_buys, refids = await _pair("Achats instantanés", client.get_instant_buys(ledgers=ledgers))
    feed.conversions = await _safely(
        "Conversions", client.get_crypto_conversions(exclude_refids=refids, ledgers=ledgers)
    )
    feed.rewards = await _safely("Récompenses", client.get_rewards(ledgers=ledgers))


async def collect(client: BaseExchangeService, *, convert_since: datetime | None, full: bool) -> Feed:
    """Rassemble l'historique de l'exchange ; une source qui échoue est journalisée et laissée vide."""
    feed = Feed(
        trades=await _safely("Trades", client.get_trades(limit=PAGE)),
        fiat_orders=await _safely("Ordres fiat", client.get_fiat_orders()),
        deposits=await _safely("Dépôts", client.get_deposits(limit=PAGE)),
        withdrawals=await _safely("Retraits", client.get_withdrawals(limit=PAGE)),
    )
    if isinstance(client, LedgerSource):
        await _ledger_feed(client, feed, full)
    else:
        if isinstance(client, InstantBuySource):
            feed.instant_buys, _ = await _pair("Achats instantanés", client.get_instant_buys(limit=PAGE))
        if isinstance(client, ConversionSource):
            feed.conversions = await _safely("Conversions", client.get_crypto_conversions(limit=PAGE))
        if isinstance(client, RewardSource):
            feed.rewards = await _safely("Récompenses", client.get_rewards(limit=PAGE))
    if isinstance(client, ConvertSource):
        converts = await _safely("Conversions fiat", client.get_convert_history(start_time=convert_since))
        feed.fiat_orders += unseen_converts(converts, feed.fiat_orders)
    if isinstance(client, AutoInvestSource):
        feed.fiat_orders += await _safely("Auto-invest", client.get_auto_invest_history())
    return feed
