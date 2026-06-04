"""Unit tests for the scheduled withdrawal-sync helpers (Ticket 1b).

The scheduled sync now records exchange withdrawals as TRANSFER_OUT and mirrors
them to the cold wallet. These tests pin the pure helpers:
- status vocabularies are normalised and cover the "completed" connectors;
- ``_to_aware_utc`` always yields a comparable UTC datetime (naive == UTC).
"""

from datetime import datetime, timezone

from app.tasks.sync_exchanges import _SUCCESSFUL_DEPOSIT_STATUSES, _SUCCESSFUL_WITHDRAWAL_STATUSES, _to_aware_utc


class TestStatusVocabularies:
    def test_completed_is_accepted_for_deposits(self):
        # Crypto.com / Gate.io / Bitstamp / Coinbase map to "completed".
        assert "completed" in _SUCCESSFUL_DEPOSIT_STATUSES
        assert "success" in _SUCCESSFUL_DEPOSIT_STATUSES
        assert "credited" in _SUCCESSFUL_DEPOSIT_STATUSES

    def test_pending_is_not_accepted(self):
        assert "pending" not in _SUCCESSFUL_DEPOSIT_STATUSES
        assert "processing" not in _SUCCESSFUL_WITHDRAWAL_STATUSES
        assert "failed" not in _SUCCESSFUL_WITHDRAWAL_STATUSES
        assert "cancelled" not in _SUCCESSFUL_WITHDRAWAL_STATUSES

    def test_withdrawal_success_vocabulary(self):
        for ok in ("completed", "success", "sent", "done"):
            assert ok in _SUCCESSFUL_WITHDRAWAL_STATUSES


class TestToAwareUtc:
    def test_none_passthrough(self):
        assert _to_aware_utc(None) is None

    def test_naive_is_assumed_utc(self):
        naive = datetime(2026, 6, 1, 10, 0, 0)
        aware = _to_aware_utc(naive)
        assert aware.tzinfo is not None
        assert aware == datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)

    def test_aware_is_converted_to_utc(self):
        aware_in = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        assert _to_aware_utc(aware_in) == aware_in

    def test_comparison_naive_vs_aware_does_not_raise(self):
        cutoff = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
        ts = _to_aware_utc(datetime(2026, 6, 2, 0, 0, 0))  # naive → UTC
        assert ts > cutoff
