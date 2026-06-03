"""Unit tests for FX handling of Kraken "instant buy" orders in the exchange sync.

The instant-buys branch of ``_sync_detailed_transactions`` used to hardcode
``currency="EUR"`` with no ``conversion_rate`` and had no heal path — so a USD-quoted
instant buy got a wrong cost basis (the exact ~8-9% FIN-01 error) and could never be
repaired. This pins the fix: the branch now resolves (currency, rate) from the symbol's
quote suffix and repairs existing rows in heal mode.

No real DB/HTTP: the session, FX service and exchange service are faked. Only the
instant-buys + (empty) trades branches run; every other branch is hasattr-gated off.
"""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

import app.tasks.sync_exchanges as sync_mod
from app.tasks.sync_exchanges import _sync_detailed_transactions

_TS = datetime(2024, 1, 17, 12, 0, tzinfo=timezone.utc)


class _FakeResult:
    """One result object serving every db.execute() call site.

    Each call site uses a distinct accessor, so a single object disambiguates:
    - line that loads existing external_ids -> .fetchall()
    - _add_transaction_if_new dup check    -> .scalar_one_or_none()
    - _heal_transaction_fx row load        -> .scalars().all()
    """

    def __init__(self, ext_ids, heal_rows):
        self._ext_ids = ext_ids
        self._heal_rows = heal_rows

    def fetchall(self):
        return [(eid,) for eid in self._ext_ids]

    def scalar_one_or_none(self):
        return None  # never a hash dup -> new rows get added

    def scalars(self):
        return SimpleNamespace(all=lambda: self._heal_rows)


class _FakeDB:
    def __init__(self, ext_ids=(), heal_rows=()):
        self._result = _FakeResult(list(ext_ids), list(heal_rows))
        self.added = []

    async def execute(self, *args, **kwargs):
        return self._result

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None


class _FakeFx:
    """Patched in for FxHistoryService(db): seeding is a no-op, rates are preset."""

    def __init__(self, db=None):
        pass

    async def ensure_seeded(self, *args, **kwargs):
        return None

    async def get_rate(self, rate_date, from_ccy, to_ccy):
        if (from_ccy, to_ccy) == ("USD", "EUR"):
            return Decimal("0.91")
        return None


class _FakeService:
    """Plain object (NOT a Mock) so hasattr() is honest for the gated branches."""

    exchange_name = "kraken"

    def __init__(self, instant_buys):
        self._instant_buys = instant_buys

    async def get_instant_buys(self, limit=500):
        return self._instant_buys, []

    async def get_trades(self, limit=500):
        return []


def _instant_buy(symbol, trade_id, price="2000", qty="0.01"):
    return SimpleNamespace(
        trade_id=trade_id,
        symbol=symbol,
        quantity=Decimal(qty),
        price=Decimal(price),
        fee=Decimal("0"),
        fee_currency="USD",
        timestamp=_TS,
    )


def _portfolio_and_assets():
    portfolio = SimpleNamespace(id="pf-1")
    asset = SimpleNamespace(id="asset-paxg", quantity=0.0, avg_buy_price=0.0)
    return portfolio, {"PAXG": asset}


@pytest.mark.asyncio
async def test_usd_instant_buy_gets_usd_currency_and_rate(monkeypatch):
    """A fresh USD-quoted instant buy must be stored as USD with a real rate."""
    monkeypatch.setattr(sync_mod, "FxHistoryService", _FakeFx)
    db = _FakeDB()
    portfolio, assets = _portfolio_and_assets()
    service = _FakeService([_instant_buy("PAXGUSD", "INSTANT-USD-1")])

    synced, healed = await _sync_detailed_transactions(db, service, portfolio, assets, heal_fx=False)

    assert synced == 1
    assert healed == 0
    tx = next(t for t in db.added if getattr(t, "external_id", None) == "INSTANT-USD-1")
    assert tx.currency == "USD"
    assert Decimal(str(tx.conversion_rate)) == Decimal("0.91")


@pytest.mark.asyncio
async def test_eur_instant_buy_stays_eur(monkeypatch):
    """An EUR-quoted instant buy stays EUR with no conversion rate (no regression)."""
    monkeypatch.setattr(sync_mod, "FxHistoryService", _FakeFx)
    db = _FakeDB()
    portfolio, assets = _portfolio_and_assets()
    service = _FakeService([_instant_buy("PAXGEUR", "INSTANT-EUR-1")])

    synced, _ = await _sync_detailed_transactions(db, service, portfolio, assets, heal_fx=False)

    assert synced == 1
    tx = next(t for t in db.added if getattr(t, "external_id", None) == "INSTANT-EUR-1")
    assert tx.currency == "EUR"
    assert tx.conversion_rate is None


@pytest.mark.asyncio
async def test_heal_repairs_existing_usd_instant_buy(monkeypatch):
    """In heal mode an already-imported USD instant buy is repaired in place, no new row."""
    monkeypatch.setattr(sync_mod, "FxHistoryService", _FakeFx)

    legacy_row = SimpleNamespace(price=2000.0, currency="EUR", conversion_rate=None)
    db = _FakeDB(ext_ids=["INSTANT-USD-1"], heal_rows=[legacy_row])
    portfolio, assets = _portfolio_and_assets()
    service = _FakeService([_instant_buy("PAXGUSD", "INSTANT-USD-1")])

    synced, healed = await _sync_detailed_transactions(db, service, portfolio, assets, heal_fx=True)

    assert healed == 1
    assert synced == 0  # nothing newly imported
    assert db.added == []  # no duplicate row created
    assert legacy_row.currency == "USD"
    assert Decimal(str(legacy_row.conversion_rate)) == Decimal("0.91")
