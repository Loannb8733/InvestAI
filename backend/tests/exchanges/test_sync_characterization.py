from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encrypt_api_key
from app.domains.exchanges.connectors.base import (
    ExchangeBalance,
    ExchangeDeposit,
    ExchangeFiatOrder,
    ExchangeTrade,
    ExchangeWithdrawal,
)
from app.domains.exchanges.models import APIKey, APIKeyStatus, ColdWalletAddress
from app.domains.exchanges.sync.runner import SyncOutcome, SyncSummary, sync_account, sync_all
from app.domains.identity.models import User
from app.domains.market_data.prices.quote import PriceQuote
from app.domains.portfolio.models import Asset, AssetType, Portfolio
from app.domains.transactions.models import Transaction, TransactionType
from tests.conftest import TestSessionLocal

pytestmark = pytest.mark.usefixtures("empty_test_redis")
DAY = datetime(2025, 3, 10, 12, 0, tzinfo=UTC)
EARN = (TransactionType.STAKING, TransactionType.UNSTAKING)
USD_EUR = Decimal("0.9")
BTC_EUR = Decimal("60000")


def _balance(symbol: str, total: str) -> ExchangeBalance:
    amount = Decimal(total)
    return ExchangeBalance(symbol=symbol, free=amount, locked=Decimal("0"), total=amount)


def _trade(trade_id: str, symbol: str, side: str, qty: str, price: str, when: datetime = DAY) -> ExchangeTrade:
    return ExchangeTrade(
        trade_id=trade_id,
        symbol=symbol,
        side=side,
        quantity=Decimal(qty),
        price=Decimal(price),
        fee=Decimal("0"),
        fee_currency="EUR",
        timestamp=when,
    )


def _order(order_id: str, symbol: str, qty: str, price: str, fiat: str = "EUR") -> ExchangeFiatOrder:
    return ExchangeFiatOrder(
        order_id=order_id,
        crypto_symbol=symbol,
        fiat_currency=fiat,
        side="buy",
        crypto_amount=Decimal(qty),
        fiat_amount=Decimal(qty) * Decimal(price),
        price=Decimal(price),
        fee=Decimal("1"),
        status="completed",
        timestamp=DAY,
    )


class FakeClient:
    exchange_name = "binance"

    def __init__(self) -> None:
        self.balances: list[ExchangeBalance] = []
        self.trades: list[ExchangeTrade] = []

    async def get_balances(self) -> list[ExchangeBalance]:
        return self.balances

    async def get_trades(self, limit: int = 500) -> list[ExchangeTrade]:
        return self.trades

    async def get_fiat_orders(self) -> list[ExchangeFiatOrder]:
        return []

    async def get_deposits(self, limit: int = 500) -> list[ExchangeDeposit]:
        return []

    async def get_withdrawals(self, limit: int = 500) -> list[ExchangeWithdrawal]:
        return []


class FullClient(FakeClient):
    def __init__(self) -> None:
        super().__init__()
        self.conversions: list[ExchangeTrade] = []
        self.instant_buys: list[ExchangeTrade] = []
        self.fiat_orders: list[ExchangeFiatOrder] = []
        self.auto_invest: list[ExchangeFiatOrder] = []
        self.rewards: list[ExchangeTrade] = []
        self.deposits: list[ExchangeDeposit] = []
        self.withdrawals: list[ExchangeWithdrawal] = []

    async def get_crypto_conversions(self, limit: int = 500) -> list[ExchangeTrade]:
        return self.conversions

    async def get_instant_buys(self, limit: int = 500) -> tuple[list[ExchangeTrade], set[str]]:
        return self.instant_buys, set()

    async def get_fiat_orders(self) -> list[ExchangeFiatOrder]:
        return self.fiat_orders

    async def get_auto_invest_history(self) -> list[ExchangeFiatOrder]:
        return self.auto_invest

    async def get_rewards(self, limit: int = 500) -> list[ExchangeTrade]:
        return self.rewards

    async def get_deposits(self, limit: int = 500) -> list[ExchangeDeposit]:
        return self.deposits

    async def get_withdrawals(self, limit: int = 500) -> list[ExchangeWithdrawal]:
        return self.withdrawals


class FakeFx:
    def __init__(self, repository: Any) -> None:
        pass

    async def refresh(self, *args: Any) -> None:
        return None

    async def rate_on(self, day: Any, base: str, quote: str) -> Decimal | None:
        return USD_EUR if (base, quote) == ("USD", "EUR") else None


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> FullClient:
    fake = FullClient()

    async def quote(symbol: str, kind: str) -> PriceQuote | None:
        return PriceQuote(price=BTC_EUR) if symbol == "BTC" else None

    monkeypatch.setattr("app.domains.exchanges.sync.runner.session_factory", TestSessionLocal)
    monkeypatch.setattr("app.domains.exchanges.sync.runner.open_client", lambda key: fake)
    monkeypatch.setattr("app.domains.exchanges.sync.pricing.FxService", FakeFx)
    monkeypatch.setattr("app.domains.exchanges.sync.pricing.price_feed.quote", quote)
    monkeypatch.setattr("app.domains.exchanges.sync.book.schedule_refresh", lambda *a: None)
    return fake


async def _key(db: AsyncSession, user: User, last_sync_at: datetime | None = None) -> str:
    key = APIKey(
        user_id=user.id,
        exchange="binance",
        encrypted_api_key=encrypt_api_key("k"),
        encrypted_secret_key=encrypt_api_key("s"),
        is_active=True,
        last_sync_at=last_sync_at,
    )
    db.add(key)
    await db.commit()
    return str(key.id)


async def _sync(key: str, heal_fx: bool = False) -> SyncOutcome:
    return await sync_account(key, heal_fx=heal_fx)


async def _rows(db: AsyncSession) -> list[tuple[str, str, TransactionType, Decimal, Decimal, str, str | None]]:
    db.expire_all()
    query = (
        select(Asset.symbol, Asset.exchange, Transaction)
        .join(Transaction, Transaction.asset_id == Asset.id)
        .order_by(Asset.symbol, Transaction.transaction_type, Transaction.quantity)
    )
    return [
        (s, e, t.transaction_type, t.quantity, t.price, t.currency, t.external_id)
        for s, e, t in (await db.execute(query)).all()
    ]


async def _assets(db: AsyncSession) -> dict[tuple[str, str], tuple[Decimal, Decimal]]:
    db.expire_all()
    rows = (await db.execute(select(Asset))).scalars().all()
    return {(a.symbol, a.exchange): (a.quantity, a.avg_buy_price) for a in rows}


class TestFirstSync:
    async def test_every_source_is_imported_then_balances_reconcile(
        self, db_session: AsyncSession, regular_user: User, client: FullClient
    ) -> None:
        client.trades = [_trade("t1", "BTCEUR", "buy", "0.1", "50000"), _trade("t2", "ETHUSDT", "buy", "1", "3000")]
        client.fiat_orders = [_order("f1", "BTC", "0.05", "40000")]
        client.auto_invest = [_order("a1", "BTC", "0.01", "45000", fiat="USD")]
        client.instant_buys = [_trade("i1", "SOLEUR", "buy", "2", "100")]
        client.rewards = [_trade("staking_r1", "BTC", "buy", "0.001", "0")]
        client.deposits = [
            ExchangeDeposit(deposit_id="d1", symbol="BTC", amount=Decimal("0.2"), timestamp=DAY, status="Completed"),
            ExchangeDeposit(deposit_id="d2", symbol="BTC", amount=Decimal("9"), timestamp=DAY, status="pending"),
        ]
        client.withdrawals = [
            ExchangeWithdrawal(
                withdrawal_id="w1",
                symbol="BTC",
                amount=Decimal("0.01"),
                fee=Decimal("0"),
                timestamp=DAY,
                status="completed",
            )
        ]
        client.balances = [_balance("BTC", "0.4"), _balance("ETH", "1"), _balance("SOL", "2"), _balance("EUR", "5")]
        key = await _key(db_session, regular_user)

        assert await _sync(key) == SyncOutcome(success=True, synced=8)

        rows = await _rows(db_session)
        assert [(s, k, q, p, c, x) for s, _, k, q, p, c, x in rows if not (x or "").startswith("binance_")] == [
            ("BTC", TransactionType.BUY, Decimal("0.01"), Decimal("45000"), "USD", "fiat_a1"),
            ("BTC", TransactionType.BUY, Decimal("0.05"), Decimal("40000"), "EUR", "fiat_f1"),
            ("BTC", TransactionType.BUY, Decimal("0.1"), Decimal("50000"), "EUR", "t1"),
            ("BTC", TransactionType.TRANSFER_IN, Decimal("0.2"), BTC_EUR, "EUR", "deposit_d1"),
            ("BTC", TransactionType.STAKING_REWARD, Decimal("0.001"), Decimal("0"), "EUR", "staking_r1"),
            ("ETH", TransactionType.BUY, Decimal("1"), Decimal("3000"), "USD", "t2"),
            ("SOL", TransactionType.BUY, Decimal("2"), Decimal("100"), "EUR", "i1"),
        ]
        adjustments = [(s, k, q) for s, _, k, q, _, _, x in rows if (x or "").startswith("binance_sync_")]
        assert adjustments == [("BTC", TransactionType.TRANSFER_IN, Decimal("0.039"))]
        assets = await _assets(db_session)
        assert {k: q for k, (q, _) in assets.items()} == {
            ("BTC", "binance"): Decimal("0.4"),
            ("ETH", "binance"): Decimal("1"),
            ("SOL", "binance"): Decimal("2"),
        }
        db_session.expire_all()
        stored = (await db_session.execute(select(APIKey))).scalar_one()
        assert stored.last_sync_at is not None and stored.status == APIKeyStatus.ACTIVE

    async def test_usd_quoted_trades_keep_usd_with_the_rate_of_the_day(
        self, db_session: AsyncSession, regular_user: User, client: FullClient
    ) -> None:
        client.trades = [_trade("t1", "BTCUSD", "buy", "0.1", "50000")]
        client.balances = [_balance("BTC", "0.1")]
        key = await _key(db_session, regular_user)
        await _sync(key)
        db_session.expire_all()
        tx = (await db_session.execute(select(Transaction))).scalar_one()
        assert (tx.currency, tx.conversion_rate) == ("USD", USD_EUR)

    async def test_a_new_balance_only_asset_is_created_at_market_price(
        self, db_session: AsyncSession, regular_user: User, client: FullClient
    ) -> None:
        client.balances = [_balance("BTC", "0.3"), _balance("LDBTC", "0.2"), _balance("XYZ", "10")]
        key = await _key(db_session, regular_user)
        assert await _sync(key) == SyncOutcome(success=True, synced=3)
        assert await _assets(db_session) == {
            ("BTC", "binance"): (Decimal("0.5"), BTC_EUR),
            ("XYZ", "binance"): (Decimal("10"), Decimal("0")),
        }
        kinds = [(s, k, q, p) for s, _, k, q, p, _, _ in await _rows(db_session)]
        assert kinds == [
            ("BTC", TransactionType.TRANSFER_IN, Decimal("0.5"), BTC_EUR),
            ("BTC", TransactionType.STAKING, Decimal("0.2"), Decimal("0")),
            ("XYZ", TransactionType.TRANSFER_IN, Decimal("10"), Decimal("0")),
        ]

    async def test_a_conversion_finds_the_asset_bought_in_the_same_sync(
        self, db_session: AsyncSession, regular_user: User, client: FullClient
    ) -> None:
        client.trades = [_trade("t1", "DOGEEUR", "buy", "100", "0.1")]
        client.conversions = [
            _trade("convert_sell_9", "DOGEPEPE", "sell", "50", "0.1"),
            _trade("convert_buy_9", "PEPEDOGE", "buy", "1000", "0"),
        ]
        client.balances = [_balance("DOGE", "50")]
        key = await _key(db_session, regular_user)
        await _sync(key)
        kinds = [(s, k, q) for s, _, k, q, _, _, _ in await _rows(db_session)]
        assert ("DOGE", TransactionType.CONVERSION_OUT, Decimal("50")) in kinds
        assert {s for s, _, _ in kinds} == {"DOGE"}
        assert (await _assets(db_session))[("DOGE", "binance")][0] == Decimal("50")


class TestLaterSyncs:
    async def test_a_second_identical_sync_writes_nothing(
        self, db_session: AsyncSession, regular_user: User, client: FullClient
    ) -> None:
        client.trades = [_trade("t1", "BTCEUR", "buy", "0.1", "50000")]
        client.balances = [_balance("BTC", "0.1")]
        key = await _key(db_session, regular_user)
        await _sync(key)
        before = await _rows(db_session)
        assert await _sync(key) == SyncOutcome(success=True, synced=0)
        assert await _rows(db_session) == before

    async def test_a_new_withdrawal_moves_to_the_named_cold_wallet(
        self, db_session: AsyncSession, regular_user: User, client: FullClient
    ) -> None:
        client.trades = [_trade("t1", "BTCEUR", "buy", "1", "50000")]
        client.balances = [_balance("BTC", "1")]
        key = await _key(db_session, regular_user)
        await _sync(key)
        db_session.add(ColdWalletAddress(user_id=regular_user.id, address="bc1abc", label="Ledger"))
        await db_session.commit()
        client.withdrawals = [
            ExchangeWithdrawal(
                withdrawal_id="w1",
                symbol="BTC",
                amount=Decimal("0.4"),
                fee=Decimal("0.0001"),
                timestamp=datetime.now(UTC) + timedelta(minutes=1),
                status="completed",
                address=" BC1ABC ",
            )
        ]
        client.balances = [_balance("BTC", "0.6")]
        assert await _sync(key) == SyncOutcome(success=True, synced=1)
        assets = await _assets(db_session)
        assert assets[("BTC", "binance")][0] == Decimal("0.6")
        assert assets[("BTC", "Ledger")] == (Decimal("0.4"), Decimal("50000"))
        rows = [(s, e, k, q) for s, e, k, q, _, _, _ in await _rows(db_session)]
        assert ("BTC", "binance", TransactionType.TRANSFER_OUT, Decimal("0.4")) in rows
        assert ("BTC", "Ledger", TransactionType.TRANSFER_IN, Decimal("0.4")) in rows

    async def test_a_withdrawal_still_pending_at_a_sync_reaches_the_cold_wallet_at_the_next(
        self, db_session: AsyncSession, regular_user: User, client: FullClient
    ) -> None:
        client.trades = [_trade("t1", "BTCEUR", "buy", "1", "50000")]
        client.balances = [_balance("BTC", "1")]
        key = await _key(db_session, regular_user)
        await _sync(key)
        withdrawal = ExchangeWithdrawal(
            withdrawal_id="w1",
            symbol="BTC",
            amount=Decimal("0.3999"),
            fee=Decimal("0.0001"),
            timestamp=datetime.now(UTC),
            status="pending",
        )
        client.withdrawals = [withdrawal]
        client.balances = [_balance("BTC", "0.6")]
        await _sync(key)
        withdrawal.status = "completed"
        await _sync(key)
        assets = await _assets(db_session)
        assert (assets[("BTC", "binance")][0], assets[("BTC", "Tangem")]) == (
            Decimal("0.6"),
            (Decimal("0.3999"), Decimal("50000")),
        )
        outs = [(q, x) for _, e, k, q, _, _, x in await _rows(db_session) if k == TransactionType.TRANSFER_OUT]
        assert outs == [(Decimal("0.4"), "withdrawal_w1")]

    async def test_an_asset_gone_from_the_exchange_is_zeroed_at_cost(
        self, db_session: AsyncSession, regular_user: User, client: FullClient
    ) -> None:
        client.trades = [_trade("t1", "ETHEUR", "buy", "2", "3000")]
        client.balances = [_balance("ETH", "2")]
        key = await _key(db_session, regular_user)
        await _sync(key)
        client.balances = [_balance("BTC", "0")]
        await _sync(key)
        zero = [(k, q, p) for s, _, k, q, p, _, x in await _rows(db_session) if (x or "").startswith("binance_zero_")]
        assert zero == [(TransactionType.TRANSFER_OUT, Decimal("2"), Decimal("3000"))]
        assert (await _assets(db_session))[("ETH", "binance")][0] == Decimal("0")

    async def test_an_asset_held_elsewhere_is_left_alone(
        self, db_session: AsyncSession, regular_user: User, client: FullClient
    ) -> None:
        portfolio = Portfolio(user_id=regular_user.id, name="Crypto")
        db_session.add(portfolio)
        await db_session.flush()
        db_session.add(
            Asset(
                portfolio_id=portfolio.id,
                symbol="BTC",
                name="BTC",
                asset_type=AssetType.CRYPTO,
                quantity=Decimal("1"),
                avg_buy_price=Decimal("1"),
                exchange="Ledger",
            )
        )
        key = await _key(db_session, regular_user)
        client.balances = [_balance("BTC", "0.2")]
        await _sync(key)
        assets = await _assets(db_session)
        assert assets[("BTC", "Ledger")][0] == Decimal("1")
        assert assets[("BTC", "binance")][0] == Decimal("0.2")


class TestHealFx:
    async def test_existing_rows_get_their_currency_back_and_nothing_else_is_written(
        self, db_session: AsyncSession, regular_user: User, client: FullClient
    ) -> None:
        client.trades = [_trade("t1", "BTCUSD", "buy", "0.1", "50000")]
        client.balances = [_balance("BTC", "0.1")]
        key = await _key(db_session, regular_user)
        await _sync(key)
        db_session.expire_all()
        tx = (await db_session.execute(select(Transaction))).scalar_one()
        tx.currency, tx.conversion_rate, tx.price = "EUR", None, Decimal("45000")
        await db_session.commit()
        client.balances = [_balance("BTC", "5")]
        assert await _sync(key, heal_fx=True) == SyncOutcome(success=True, synced=1, healed=1)
        rows = await _rows(db_session)
        assert [(k, q, p, c) for _, _, k, q, p, c, _ in rows] == [
            (TransactionType.BUY, Decimal("0.1"), Decimal("50000"), "USD")
        ]


class TestFailures:
    async def test_an_inactive_key_is_not_synced(
        self, db_session: AsyncSession, regular_user: User, client: FullClient
    ) -> None:
        key = await _key(db_session, regular_user)
        (await db_session.execute(select(APIKey))).scalar_one().is_active = False
        await db_session.commit()
        assert await _sync(key) == SyncOutcome(success=False, error="API key not found or inactive")

    async def test_an_exchange_error_rolls_back_and_marks_the_key(
        self, db_session: AsyncSession, regular_user: User, client: FullClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def broken() -> list[ExchangeBalance]:
            raise RuntimeError("boom")

        monkeypatch.setattr(client, "get_balances", broken)
        key = await _key(db_session, regular_user)
        assert await _sync(key) == SyncOutcome(success=False, error="sync_failed")
        db_session.expire_all()
        stored = (await db_session.execute(select(APIKey))).scalar_one()
        assert (stored.status, stored.last_error) == (APIKeyStatus.ERROR, "boom")
        assert (await db_session.execute(select(Portfolio))).first() is None

    async def test_sync_all_counts_each_key(
        self, db_session: AsyncSession, regular_user: User, admin_user: User, client: FullClient
    ) -> None:
        client.balances = [_balance("BTC", "1")]
        await _key(db_session, regular_user)
        await _key(db_session, admin_user)
        assert await sync_all() == SyncSummary(total=2, success=2, failed=0)


class LedgerClient(FakeClient):
    exchange_name = "kraken"

    def __init__(self) -> None:
        super().__init__()
        self.ledger_calls: list[int] = []
        self.excluded: set[str] | None = None

    async def get_ledgers(self, *, limit: int = 10000) -> list[dict[str, Any]]:
        self.ledger_calls.append(limit)
        return [{"refid": "R1"}]

    async def get_instant_buys(
        self, limit: int = 500, ledgers: list[dict[str, Any]] | None = None
    ) -> tuple[list[ExchangeTrade], set[str]]:
        assert ledgers == [{"refid": "R1"}]
        return [_trade("R1", "BTCEUR", "buy", "0.1", "50000")], {"R1"}

    async def get_crypto_conversions(
        self, limit: int = 500, exclude_refids: set[str] | None = None, ledgers: list[dict[str, Any]] | None = None
    ) -> list[ExchangeTrade]:
        self.excluded = exclude_refids
        return []

    async def get_rewards(self, limit: int = 500, ledgers: list[dict[str, Any]] | None = None) -> list[ExchangeTrade]:
        assert ledgers == [{"refid": "R1"}]
        return []


class ConvertClient(FullClient):
    def __init__(self) -> None:
        super().__init__()
        self.convert_since: list[datetime | None] = []
        self.converts: list[ExchangeFiatOrder] = []

    async def get_convert_history(self, start_time: datetime | None = None) -> list[ExchangeFiatOrder]:
        self.convert_since.append(start_time)
        return self.converts


class TestSourcesOfThisRewrite:
    async def test_kraken_ledgers_are_read_once_and_shared(
        self, db_session: AsyncSession, regular_user: User, monkeypatch: pytest.MonkeyPatch, client: FullClient
    ) -> None:
        kraken = LedgerClient()
        kraken.balances = [_balance("BTC", "0.1")]
        monkeypatch.setattr("app.domains.exchanges.sync.runner.open_client", lambda key: kraken)
        key = await _key(db_session, regular_user)
        await _sync(key)
        await _sync(key)
        assert kraken.ledger_calls == [10000, 1000]
        assert kraken.excluded == {"R1"}
        rows = [(s, e, k, x) for s, e, k, _, _, _, x in await _rows(db_session)]
        assert rows == [("BTC", "kraken", TransactionType.BUY, "R1")]

    async def test_binance_fiat_converts_are_imported_once(
        self, db_session: AsyncSession, regular_user: User, monkeypatch: pytest.MonkeyPatch, client: FullClient
    ) -> None:
        binance = ConvertClient()
        binance.fiat_orders = [_order("f1", "BTC", "0.05", "40000")]
        binance.converts = [_order("c-same", "BTC", "0.05", "40000"), _order("c2", "ETH", "1", "3000")]
        binance.balances = [_balance("BTC", "0.05"), _balance("ETH", "1")]
        monkeypatch.setattr("app.domains.exchanges.sync.runner.open_client", lambda key: binance)
        last = datetime(2025, 3, 1, tzinfo=UTC)
        key = await _key(db_session, regular_user, last_sync_at=last)
        assert await _sync(key) == SyncOutcome(success=True, synced=2)
        assert binance.convert_since == [last - timedelta(days=30)]
        rows = [(s, k, q, x) for s, _, k, q, _, _, x in await _rows(db_session)]
        assert rows == [
            ("BTC", TransactionType.BUY, Decimal("0.05"), "fiat_f1"),
            ("ETH", TransactionType.BUY, Decimal("1"), "fiat_c2"),
        ]

    async def test_earn_positions_are_opened_grown_and_closed(
        self, db_session: AsyncSession, regular_user: User, client: FullClient
    ) -> None:
        client.balances = [_balance("BTC", "0.3"), _balance("LDBTC", "0.2")]
        key = await _key(db_session, regular_user)
        await _sync(key)
        client.balances = [_balance("BTC", "0.3"), _balance("LDBTC", "0.25")]
        await _sync(key)
        markers = [(k, q) for _, _, k, q, _, _, _ in await _rows(db_session) if k in EARN]
        assert markers == [(TransactionType.STAKING, Decimal("0.25"))]
        client.balances = [_balance("BTC", "0.55")]
        await _sync(key)
        markers = [(k, q) for _, _, k, q, _, _, _ in await _rows(db_session) if k in EARN]
        assert markers == [(TransactionType.STAKING, Decimal("0.25")), (TransactionType.UNSTAKING, Decimal("0.25"))]
        assert (await _assets(db_session))[("BTC", "binance")][0] == Decimal("0.55")

    async def test_an_asset_without_platform_is_adopted_with_its_transactions(
        self, db_session: AsyncSession, regular_user: User, client: FullClient
    ) -> None:
        portfolio = Portfolio(user_id=regular_user.id, name="Crypto")
        db_session.add(portfolio)
        await db_session.flush()
        db_session.add(
            Asset(
                portfolio_id=portfolio.id,
                symbol="BTC",
                name="BTC",
                asset_type=AssetType.CRYPTO,
                quantity=Decimal("0"),
                avg_buy_price=Decimal("0"),
                exchange="",
            )
        )
        key = await _key(db_session, regular_user)
        client.trades = [_trade("t1", "BTCEUR", "buy", "0.1", "50000")]
        client.balances = [_balance("BTC", "0.1")]
        await _sync(key)
        assert list((await _assets(db_session)).items()) == [(("BTC", "binance"), (Decimal("0.1"), Decimal("50000")))]
        db_session.expire_all()
        exchanges = (await db_session.execute(select(Transaction.exchange))).scalars().all()
        assert exchanges == ["binance"]

    async def test_a_portfolio_named_after_the_exchange_becomes_the_crypto_portfolio(
        self, db_session: AsyncSession, regular_user: User, client: FullClient
    ) -> None:
        db_session.add(Portfolio(user_id=regular_user.id, name="binance"))
        key = await _key(db_session, regular_user)
        client.balances = [_balance("BTC", "0.1")]
        await _sync(key)
        db_session.expire_all()
        assert (await db_session.execute(select(Portfolio.name))).scalars().all() == ["Crypto"]

    async def test_fx_recalculation_never_imports_new_orders(
        self, db_session: AsyncSession, regular_user: User, client: FullClient
    ) -> None:
        client.trades = [_trade("t1", "BTCUSD", "buy", "0.1", "50000")]
        client.balances = [_balance("BTC", "0.1")]
        key = await _key(db_session, regular_user, last_sync_at=datetime(2025, 1, 1, tzinfo=UTC))
        assert await _sync(key, heal_fx=True) == SyncOutcome(success=True, synced=0, healed=0)
        assert await _rows(db_session) == []
