"""Unit tests for cold-wallet destination routing (Ticket 1f).

A withdrawal address is mapped (case-insensitively) to a named cold wallet;
unknown / missing addresses fall back to the default destination.
"""

from app.services.transfer_service import COLD_WALLET_DESTINATION
from app.tasks.sync_exchanges import _resolve_cold_wallet_destination


class TestResolveColdWalletDestination:
    def test_known_address_routes_to_label(self):
        wallet_map = {"0xabc123": "Ledger"}
        assert _resolve_cold_wallet_destination("0xABC123", wallet_map) == "Ledger"

    def test_address_is_stripped_and_lowercased(self):
        wallet_map = {"bc1qxyz": "Trezor"}
        assert _resolve_cold_wallet_destination("  BC1QXYZ  ", wallet_map) == "Trezor"

    def test_unknown_address_falls_back_to_default(self):
        assert _resolve_cold_wallet_destination("0xunknown", {"0xabc": "Ledger"}) == COLD_WALLET_DESTINATION

    def test_none_address_falls_back_to_default(self):
        assert _resolve_cold_wallet_destination(None, {"0xabc": "Ledger"}) == COLD_WALLET_DESTINATION

    def test_empty_map_falls_back_to_default(self):
        assert _resolve_cold_wallet_destination("0xabc", {}) == COLD_WALLET_DESTINATION
