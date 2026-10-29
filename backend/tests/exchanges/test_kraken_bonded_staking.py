import importlib.util
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.exchanges.connectors.kraken.connector import KrakenService
from app.domains.exchanges.sync.symbols import holdings
from app.domains.identity.models import User
from app.domains.portfolio.models import Asset, AssetType, Portfolio
from app.domains.transactions.models import Transaction, TransactionType
from tests.http_stubs import HttpStub

D = Decimal
DAY = datetime(2026, 9, 10, 16, tzinfo=UTC)


def _kraken() -> KrakenService:
    return KrakenService(api_key="cle-de-test", secret_key="c2VjcmV0")


def _migration() -> ModuleType:
    path = next(Path(__file__).parents[2].glob("alembic/versions/*_kraken_bonded_staking.py"))
    spec = importlib.util.spec_from_file_location("kraken_bonded_staking", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_bonded_staking_balance_is_its_asset() -> None:
    assert _kraken()._normalize_asset("SOL03.S") == "SOL"


async def test_spot_and_bonded_staking_balances_add_up(http_stub: HttpStub) -> None:
    http_stub.json("api.kraken.com", {"error": [], "result": {"SOL": "0.5", "SOL03.S": "1.0636"}})
    assert holdings(await _kraken().get_balances()).totals == {"SOL": D("1.5636")}


async def test_a_move_between_two_balances_of_one_asset_is_not_a_conversion() -> None:
    legs = [
        {"refid": "R1", "asset": "SOL", "amount": D("-1.05"), "fee": D("0"), "time": DAY},
        {"refid": "R1", "asset": "SOL", "amount": D("1.05"), "fee": D("0"), "time": DAY},
    ]
    assert await _kraken().get_crypto_conversions(ledgers=legs) == []


async def _asset(db: AsyncSession, portfolio: Portfolio, symbol: str, quantity: str) -> Asset:
    asset = Asset(
        portfolio_id=portfolio.id,
        symbol=symbol,
        name=symbol,
        asset_type=AssetType.CRYPTO,
        quantity=D(quantity),
        avg_buy_price=D("0"),
        exchange="Kraken",
    )
    db.add(asset)
    await db.flush()
    return asset


def _tx(asset: Asset, kind: TransactionType, quantity: str, price: str = "0", **fields: Any) -> Transaction:
    values: dict[str, Any] = {"fee": D("0"), "currency": "EUR", "executed_at": DAY}
    values.update(fields)
    return Transaction(asset_id=asset.id, transaction_type=kind, quantity=D(quantity), price=D(price), **values)


async def test_the_bonded_staking_asset_joins_its_kraken_asset(db_session: AsyncSession, regular_user: User) -> None:
    portfolio = Portfolio(user_id=regular_user.id, name="Crypto")
    db_session.add(portfolio)
    await db_session.flush()
    sol = await _asset(db_session, portfolio, "SOL", "0.0012")
    staked = await _asset(db_session, portfolio, "SOL03", "1.0596")
    db_session.add_all(
        [
            _tx(sol, TransactionType.BUY, "1.06", "70", executed_at=DAY - timedelta(days=30)),
            _tx(sol, TransactionType.TRANSFER_OUT, "1.0587527692", notes="Ajustement balance Kraken"),
            _tx(
                staked,
                TransactionType.TRANSFER_IN,
                "1.0587527727",
                external_id="Kraken_init_SOL03_1789057138",
                notes="Import initial depuis Kraken",
            ),
            _tx(staked, TransactionType.STAKING_REWARD, "0.001", executed_at=DAY + timedelta(days=3)),
        ]
    )
    await db_session.flush()
    await (await db_session.connection()).run_sync(_migration().merge_bonded_staking)
    db_session.expire_all()
    assets = (await db_session.execute(select(Asset))).scalars().all()
    assert [(a.symbol, a.quantity, a.avg_buy_price) for a in assets] == [("SOL", D("1.0608"), D("70"))]
    kinds = (await db_session.execute(select(Transaction.transaction_type).order_by(Transaction.executed_at))).all()
    assert [k for (k,) in kinds] == [TransactionType.BUY, TransactionType.STAKING_REWARD]
