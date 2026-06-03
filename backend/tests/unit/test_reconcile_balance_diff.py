"""Unit tests for STEP 2 balance-reconciliation classification.

``_reconcile_balance_diff`` decides whether a gap between our stored quantity and the
exchange's reported quantity is:
- "none"     -> float noise, ignore;
- "dust"     -> sub-0.0001% rounding, snap silently (no phantom TRANSFER);
- "transfer" -> a real deposit/withdrawal worth recording.

The phantom-transfer bug (FIN/Funding) came from treating ANY diff > 1e-8 as a real
transfer, which spammed adjustments for high-supply tokens where 1e-8 absolute is
meaningless. These tests pin the conservative relative band and guarantee genuine
small transfers are still classified as transfers.
"""

from app.tasks.sync_exchanges import _RECONCILE_DUST_REL, _RECONCILE_EPSILON, _reconcile_balance_diff


class TestReconcileBalanceDiff:
    def test_exact_match_is_none(self):
        assert _reconcile_balance_diff(1.5, 1.5) == "none"

    def test_float_noise_below_epsilon_is_none(self):
        assert _reconcile_balance_diff(1.0, 1.0 + _RECONCILE_EPSILON / 2) == "none"

    def test_small_token_real_deposit_is_transfer(self):
        # 1 BTC -> 1.5 BTC: an unmistakable real transfer.
        assert _reconcile_balance_diff(1.0, 1.5) == "transfer"

    def test_high_supply_token_rounding_is_dust(self):
        # 1,000,000,000 SHIB-like units, off by 100 units (1e-7 relative) -> dust.
        exchange = 1_000_000_000.0
        ours = exchange - 100.0  # rel diff = 1e-7, below 1e-6 ceiling
        assert _reconcile_balance_diff(ours, exchange) == "dust"

    def test_high_supply_token_real_deposit_is_transfer(self):
        # Same big balance but off by 0.01% -> a real movement, not dust.
        exchange = 1_000_000_000.0
        ours = exchange * (1 - 1e-4)
        assert _reconcile_balance_diff(ours, exchange) == "transfer"

    def test_dust_ceiling_is_relative_to_exchange_magnitude(self):
        # Just inside the relative band counts as dust...
        exchange = 100.0
        dust_gap = exchange * _RECONCILE_DUST_REL * 0.9
        assert _reconcile_balance_diff(exchange - dust_gap, exchange) == "dust"
        # ...just outside it is a transfer.
        transfer_gap = exchange * _RECONCILE_DUST_REL * 2
        assert _reconcile_balance_diff(exchange - transfer_gap, exchange) == "transfer"

    def test_negative_diff_withdrawal_is_transfer(self):
        # We hold more than the exchange reports (withdrawal not captured by trades).
        assert _reconcile_balance_diff(5.0, 2.0) == "transfer"

    def test_zero_exchange_balance_uses_epsilon_floor(self):
        # exchange_quantity == 0 -> dust_ceiling collapses to epsilon, so any real
        # remaining balance is a transfer (will be zeroed as a withdrawal).
        assert _reconcile_balance_diff(0.5, 0.0) == "transfer"
        # but pure noise around zero stays "none".
        assert _reconcile_balance_diff(_RECONCILE_EPSILON / 2, 0.0) == "none"
