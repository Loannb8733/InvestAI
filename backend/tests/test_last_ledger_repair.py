import importlib.util
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import User
from app.domains.portfolio.models import Asset, AssetType, Portfolio
from app.domains.transactions.models import Transaction, TransactionType

DAY = datetime(2025, 3, 10, 12, tzinfo=UTC)


def _migration() -> ModuleType:
    path = next(Path(__file__).parents[1].glob("alembic/versions/f7a2c9d1e3b4_*.py"))
    spec = importlib.util.spec_from_file_location("last_ledger_repair", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIGRATION = _migration()


async def _run(db: AsyncSession, step: Callable[[Connection], None]) -> None:
    await db.flush()
    await (await db.connection()).run_sync(step)
    db.expire_all()


@pytest.fixture
async def portfolio(db_session: AsyncSession, regular_user: User) -> Portfolio:
    portfolio = Portfolio(user_id=regular_user.id, name="Crypto")
    db_session.add(portfolio)
    await db_session.flush()
    return portfolio


async def _asset(db: AsyncSession, portfolio: Portfolio, exchange: str, quantity: str = "0") -> Asset:
    asset = Asset(
        portfolio_id=portfolio.id,
        symbol="BTC",
        name="BTC",
        asset_type=AssetType.CRYPTO,
        quantity=Decimal(quantity),
        avg_buy_price=Decimal("0"),
        exchange=exchange,
    )
    db.add(asset)
    await db.flush()
    return asset


def _tx(asset: Asset, kind: TransactionType, quantity: str, **fields: Any) -> Transaction:
    values: dict[str, Any] = {"price": Decimal("100"), "fee": Decimal("0"), "currency": "EUR", "executed_at": DAY}
    values.update(fields)
    return Transaction(asset_id=asset.id, transaction_type=kind, quantity=Decimal(quantity), **values)


async def _assets(db: AsyncSession) -> dict[str, tuple[Decimal, Decimal]]:
    return {a.exchange: (a.quantity, a.avg_buy_price) for a in (await db.execute(select(Asset))).scalars()}


class TestMultiplatform:
    async def test_a_transaction_moves_to_the_asset_of_its_platform(
        self, db_session: AsyncSession, portfolio: Portfolio
    ) -> None:
        binance = await _asset(db_session, portfolio, "binance", "3")
        db_session.add(_tx(binance, TransactionType.BUY, "3", exchange="binance"))
        db_session.add(_tx(binance, TransactionType.BUY, "1", exchange="Kraken", fee=Decimal("4")))
        await _run(db_session, MIGRATION.move_multiplatform)
        assert await _assets(db_session) == {
            "binance": (Decimal("2"), Decimal("100")),
            "Kraken": (Decimal("1"), Decimal("104")),
        }


class TestMirrors:
    async def test_an_outgoing_transfer_gets_its_default_wallet_mirror(
        self, db_session: AsyncSession, portfolio: Portfolio
    ) -> None:
        kraken = await _asset(db_session, portfolio, "Kraken", "3")
        db_session.add(_tx(kraken, TransactionType.TRANSFER_OUT, "2", fee=Decimal("0.1"), fee_currency="BTC"))
        db_session.add(_tx(kraken, TransactionType.TRANSFER_OUT, "1", notes="Ajustement balance kraken"))
        await _run(db_session, MIGRATION.mirror_transfers)
        await _run(db_session, MIGRATION.mirror_transfers)
        assert (await _assets(db_session))["Tangem"] == (Decimal("1.9"), Decimal("100"))
        rows = (await db_session.execute(select(Transaction).order_by(Transaction.quantity))).scalars().all()
        linked = [(r.transaction_type, r.related_transaction_id is not None) for r in rows]
        assert linked == [
            (TransactionType.TRANSFER_OUT, False),
            (TransactionType.TRANSFER_IN, True),
            (TransactionType.TRANSFER_OUT, True),
        ]

    async def test_an_existing_transfer_in_is_linked_not_doubled(
        self, db_session: AsyncSession, portfolio: Portfolio
    ) -> None:
        kraken = await _asset(db_session, portfolio, "Kraken", "3")
        tangem = await _asset(db_session, portfolio, "Tangem", "2")
        db_session.add(_tx(kraken, TransactionType.TRANSFER_OUT, "2"))
        db_session.add(_tx(tangem, TransactionType.TRANSFER_IN, "2", executed_at=DAY + timedelta(hours=5)))
        await _run(db_session, MIGRATION.mirror_transfers)
        assert (await _assets(db_session))["Tangem"][0] == Decimal("2")
        assert len((await db_session.execute(select(Transaction))).scalars().all()) == 2

    async def test_leaving_the_default_wallet_is_not_mirrored(
        self, db_session: AsyncSession, portfolio: Portfolio
    ) -> None:
        tangem = await _asset(db_session, portfolio, "Tangem", "3")
        db_session.add(_tx(tangem, TransactionType.TRANSFER_OUT, "2"))
        await _run(db_session, MIGRATION.mirror_transfers)
        assert len((await db_session.execute(select(Transaction))).scalars().all()) == 1


class TestRehash:
    async def test_the_frozen_hash_is_the_model_hash(self, db_session: AsyncSession, portfolio: Portfolio) -> None:
        asset = await _asset(db_session, portfolio, "Kraken")
        tx = _tx(asset, TransactionType.STAKING_REWARD, "0.123456789", price=Decimal("1.5"))
        expected = tx.compute_hash()
        tx.internal_hash = "stale"
        db_session.add(tx)
        db_session.add(_tx(asset, TransactionType.BUY, "1", executed_at=None))
        await _run(db_session, MIGRATION.rehash)
        rows = (await db_session.execute(select(Transaction).order_by(Transaction.transaction_type))).scalars().all()
        assert rows[1].internal_hash == expected
        undated = rows[0]
        assert undated.internal_hash == undated.compute_hash()

    async def test_on_collision_the_oldest_keeps_it_and_nothing_is_deleted(
        self, db_session: AsyncSession, portfolio: Portfolio
    ) -> None:
        asset = await _asset(db_session, portfolio, "Kraken")
        first = _tx(asset, TransactionType.BUY, "1", internal_hash="a" * 40, created_at=DAY)
        second = _tx(asset, TransactionType.BUY, "1", internal_hash="b" * 40, created_at=DAY + timedelta(seconds=1))
        db_session.add_all([first, second])
        await _run(db_session, MIGRATION.rehash)
        await _run(db_session, MIGRATION.rehash)
        rows = (await db_session.execute(select(Transaction).order_by(Transaction.created_at))).scalars().all()
        assert [r.internal_hash for r in rows] == [rows[0].compute_hash(), None]
