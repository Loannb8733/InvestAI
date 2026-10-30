from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import session_factory
from app.domains.exchanges.clients import crypto_portfolio, open_client
from app.domains.exchanges.failures import rollback_and_mark
from app.domains.exchanges.models import APIKey, ColdWalletAddress
from app.domains.exchanges.sync.balances import reconcile
from app.domains.exchanges.sync.book import Book, now
from app.domains.exchanges.sync.feed import collect
from app.domains.exchanges.sync.movements import (
    import_conversions,
    import_deposits,
    import_rewards,
    import_withdrawals,
)
from app.domains.exchanges.sync.orders import import_orders, orders, repair_orders
from app.domains.exchanges.sync.pricing import TradeFx
from app.domains.exchanges.sync.rules import as_utc
from app.domains.exchanges.sync.symbols import holdings
from app.services.metrics_service import invalidate_dashboard_cache

CONVERT_OVERLAP = timedelta(days=30)
WITHDRAWAL_OVERLAP = timedelta(days=7)
UNKNOWN_KEY = "API key not found or inactive"
FAILED = "sync_failed"


@dataclass(frozen=True)
class SyncOutcome:
    success: bool
    synced: int = 0
    healed: int = 0
    error: str | None = None


@dataclass(frozen=True)
class SyncSummary:
    total: int
    success: int
    failed: int


async def _wallets(session: AsyncSession, user_id: UUID) -> dict[str, str]:
    query = select(ColdWalletAddress.address, ColdWalletAddress.label).where(ColdWalletAddress.user_id == user_id)
    return {address.strip().lower(): label for address, label in (await session.execute(query)).tuples()}


async def _run(session: AsyncSession, key: APIKey, heal_fx: bool) -> SyncOutcome:
    client = open_client(key)
    balances = await client.get_balances()
    if not balances:
        return SyncOutcome(success=True)
    last_sync = as_utc(key.last_sync_at)
    convert_since = None if heal_fx or last_sync is None else last_sync - CONVERT_OVERLAP
    feed = await collect(client, convert_since=convert_since, full=convert_since is None)
    portfolio = await crypto_portfolio(session, key.user_id, client.exchange_name)
    book = await Book.open(session, portfolio, client.exchange_name)
    fx = await TradeFx.seeded(session)
    if heal_fx:
        healed = await repair_orders(book, fx, orders(book, feed))
        return SyncOutcome(success=True, synced=healed, healed=healed)
    book.adopt()
    await import_orders(book, fx, orders(book, feed))
    await import_conversions(book, feed.conversions)
    await import_rewards(book, feed.rewards)
    await import_deposits(book, feed.deposits)
    wallets = await _wallets(session, key.user_id)
    after = last_sync - WITHDRAWAL_OVERLAP if last_sync else now()
    await import_withdrawals(book, feed.withdrawals, after=after, wallets=wallets)
    await reconcile(book, holdings(balances))
    await book.close()
    return SyncOutcome(success=True, synced=book.written)


async def sync_account(api_key_id: UUID | str, *, heal_fx: bool = False) -> SyncOutcome:
    """Importe l'historique d'un compte d'exchange et aligne ses actifs sur ses soldes, en une seule transaction.

    En recalcul FX, seuls la devise et le taux des ordres déjà importés sont repris.
    Un échec annule tout et n'enregistre que l'erreur sur la clé.
    """
    key_id = UUID(str(api_key_id))
    async with session_factory() as session:
        key = await session.get(APIKey, key_id)
        if key is None or not key.is_active:
            return SyncOutcome(success=False, error=UNKNOWN_KEY)
        user_id = key.user_id
        try:
            outcome = await _run(session, key, heal_fx)
            key.last_sync_at = now()
            key.mark_success()
            await session.commit()
        except Exception as exc:  # noqa: BLE001
            await rollback_and_mark(session, key_id, exc)
            return SyncOutcome(success=False, error=FAILED)
    invalidate_dashboard_cache(str(user_id))
    return outcome


async def active_key_ids() -> list[str]:
    async with session_factory() as session:
        query = select(APIKey.id).where(APIKey.is_active.is_(True))
        return [str(key_id) for key_id in (await session.execute(query)).scalars()]


async def sync_all() -> SyncSummary:
    """Synchronise les clés actives l'une après l'autre : les exchanges d'un utilisateur partagent un portefeuille."""
    results = [await sync_account(key_id) for key_id in await active_key_ids()]
    succeeded = sum(1 for r in results if r.success)
    return SyncSummary(total=len(results), success=succeeded, failed=len(results) - succeeded)
