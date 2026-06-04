"""Unit tests for the dedup hash precision fix (Ticket 4).

The old formula formatted quantity/price as float ``.8f``, collapsing
micro-price assets (PEPE ~1e-9) to "0.00000000" so two distinct same-day
trades hashed identically and the second was dropped. The new formula hashes
at full Numeric(12) precision via Decimal.
"""

from app.models.transaction import _canonical_decimal, compute_transaction_hash

ASSET = "11111111-1111-1111-1111-111111111111"
DATE = "2026-06-01"


class TestCanonicalDecimal:
    def test_micro_price_is_not_collapsed_to_zero(self):
        assert _canonical_decimal("0.0000000012", 12) == "0.000000001200"
        assert _canonical_decimal("0.0000000034", 12) != _canonical_decimal("0.0000000012", 12)

    def test_high_supply_quantity_no_overflow(self):
        # ~1e15 units (SHIB-scale) must not degrade to "0".
        out = _canonical_decimal("1000000000000000.123456789012", 12)
        assert out.startswith("1000000000000000.")

    def test_invalid_input_degrades_to_zero(self):
        assert _canonical_decimal("not-a-number", 12) == "0"


class TestComputeTransactionHash:
    def test_micro_price_trades_hash_differently(self):
        # Same asset/day/type/qty, different micro price → must NOT collide now.
        h1 = compute_transaction_hash(ASSET, "BUY", "1000000", "0.0000000012", DATE)
        h2 = compute_transaction_hash(ASSET, "BUY", "1000000", "0.0000000034", DATE)
        assert h1 != h2

    def test_identical_inputs_are_stable(self):
        h1 = compute_transaction_hash(ASSET, "BUY", "1.5", "30000", DATE)
        h2 = compute_transaction_hash(ASSET, "BUY", "1.5", "30000", DATE)
        assert h1 == h2 and len(h1) == 40
