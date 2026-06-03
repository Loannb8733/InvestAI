"""Unit tests for in-place FX repair of imported trades (FIN-01 heal).

The exchange import dedups against already-imported trades and *skips* them, so the
FIN-01 fix (historical USD→EUR) never reaches legacy rows — they keep a wrong cost basis.
``_heal_transaction_fx`` re-derives ``(price, currency, conversion_rate)`` from authoritative
exchange data and updates the matching row(s) in place, without deletion. These tests fake
the DB session so there is no I/O: only the mutation/idempotency logic is exercised.
"""

from decimal import Decimal

import pytest

from app.tasks.sync_exchanges import _heal_transaction_fx


class _FakeRow:
    """Minimal stand-in for a Transaction ORM row (only the fields heal touches)."""

    def __init__(self, price, currency, conversion_rate):
        self.price = price
        self.currency = currency
        self.conversion_rate = conversion_rate


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalars(self._rows)


class _FakeDb:
    """Returns preset rows for any select; records whether a query ran."""

    def __init__(self, rows):
        self._rows = rows
        self.executed = False

    async def execute(self, *_args, **_kwargs):
        self.executed = True
        return _FakeResult(self._rows)


class TestHealTransactionFx:
    @pytest.mark.asyncio
    async def test_heals_usd_row_mislabeled_as_eur(self):
        # Legacy sync rows stored the RAW USD price but tagged currency="EUR", rate=None,
        # so the cost engine read a USD number as EUR. Heal sets the real anchor + rate;
        # the raw price is already correct and stays untouched.
        row = _FakeRow(price=30000.0, currency="EUR", conversion_rate=None)
        db = _FakeDb([row])
        changed = await _heal_transaction_fx(db, ["t1"], 30000.0, "USD", Decimal("0.82"))
        assert changed is True
        assert row.currency == "USD"
        assert row.conversion_rate == Decimal("0.82")
        assert row.price == 30000.0

    @pytest.mark.asyncio
    async def test_heals_preconverted_price_row(self):
        # Legacy api_keys rows pre-converted the price with a single spot rate. Heal
        # reconstructs the raw price from exchange data so the row converges regardless.
        row = _FakeRow(price=27000.0, currency="EUR", conversion_rate=None)
        db = _FakeDb([row])
        changed = await _heal_transaction_fx(db, ["t1"], 30000.0, "USD", Decimal("0.82"))
        assert changed is True
        assert row.price == 30000.0
        assert row.currency == "USD"
        assert row.conversion_rate == Decimal("0.82")

    @pytest.mark.asyncio
    async def test_noop_for_correct_eur_row(self):
        # An EUR-quoted trade resolves to ("EUR", None): nothing to change.
        row = _FakeRow(price=100.0, currency="EUR", conversion_rate=None)
        db = _FakeDb([row])
        changed = await _heal_transaction_fx(db, ["t1"], 100.0, "EUR", None)
        assert changed is False
        assert row.currency == "EUR"
        assert row.conversion_rate is None

    @pytest.mark.asyncio
    async def test_idempotent_second_run_is_noop(self):
        row = _FakeRow(price=30000.0, currency="EUR", conversion_rate=None)
        db = _FakeDb([row])
        assert await _heal_transaction_fx(db, ["t1"], 30000.0, "USD", Decimal("0.82")) is True
        # Second pass over an already-healed row makes no change.
        assert await _heal_transaction_fx(db, ["t1"], 30000.0, "USD", Decimal("0.82")) is False

    @pytest.mark.asyncio
    async def test_no_matching_row_returns_false(self):
        db = _FakeDb([])
        assert await _heal_transaction_fx(db, ["missing"], 1.0, "USD", Decimal("0.9")) is False

    @pytest.mark.asyncio
    async def test_empty_external_ids_skips_query(self):
        db = _FakeDb([_FakeRow(price=1.0, currency="EUR", conversion_rate=None)])
        assert await _heal_transaction_fx(db, [None], 1.0, "USD", Decimal("0.9")) is False
        # No candidates -> never hit the DB.
        assert db.executed is False
