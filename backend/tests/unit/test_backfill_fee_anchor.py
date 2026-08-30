"""Unit tests for the FIN-01 historical backfill discriminant.

The backfill has to recover a trade's quote currency from rows where the pair symbol is
no longer available (``transactions`` stores the base asset only). ``fee_currency`` is
the sole surviving clue, and it means different things per exchange:

- Kraken books ``fee_currency`` = the pair's quote currency (kraken.py), so it is exact.
- Binance books ``commissionAsset``: the received asset on a buy, BNB when the fee
  discount is on, the quote on a sell.

These pin the single rule that covers both without guessing, plus the false positive it
is specifically designed to neutralise. Pure function: no DB / HTTP / Docker.
"""

import pytest

from app.services.exchanges.pair_utils import fee_currency_quote_anchor


class TestKrakenIsExact:
    """Kraken always stores the quote, so every fiat/stable quote must resolve."""

    @pytest.mark.parametrize(
        "fee_currency,asset_symbol,expected",
        [
            ("USD", "XBT", "USD"),
            ("USDT", "ETH", "USD"),
            ("GBP", "BTC", "GBP"),
            ("EUR", "SOL", "EUR"),  # already EUR: caller skips, but the anchor is known
        ],
    )
    def test_quote_is_recovered(self, fee_currency, asset_symbol, expected):
        assert fee_currency_quote_anchor(fee_currency, asset_symbol) == expected


class TestBinanceSideDependent:
    def test_sell_fee_in_quote_is_recovered(self):
        # SELL BTCUSDT -> commission taken in USDT, the quote.
        assert fee_currency_quote_anchor("USDT", "BTC") == "USD"

    def test_buy_fee_in_base_proves_nothing(self):
        # BUY BTCUSDT -> commission taken in BTC, the asset itself.
        assert fee_currency_quote_anchor("BTC", "BTC") is None

    def test_fee_paid_in_bnb_proves_nothing(self):
        # The residual FIN-01 exposure: BNB says nothing about the quote.
        assert fee_currency_quote_anchor("BNB", "BTC") is None

    @pytest.mark.parametrize("fee_currency", ["ETH", "SOL", "DOGE"])
    def test_crypto_fee_proves_nothing(self, fee_currency):
        assert fee_currency_quote_anchor(fee_currency, "BTC") is None


class TestFalsePositiveIsNeutralised:
    def test_buying_a_usd_stablecoin_against_eur_is_skipped(self):
        # USDCEUR with the fee in USDC: naively USDC -> "USD" would mislabel a EUR-quoted
        # trade. Matching the row's own asset is what rules it out.
        assert fee_currency_quote_anchor("USDC", "USDC") is None

    def test_same_asset_match_is_case_insensitive(self):
        assert fee_currency_quote_anchor("usdt", "USDT") is None

    def test_a_different_stablecoin_still_resolves(self):
        # Buying USDC *with* USDT is genuinely USD-quoted.
        assert fee_currency_quote_anchor("USDT", "USDC") == "USD"


class TestDegradesSafely:
    @pytest.mark.parametrize("fee_currency", [None, "", "   "])
    def test_missing_fee_currency(self, fee_currency):
        assert fee_currency_quote_anchor(fee_currency, "BTC") is None

    def test_unknown_asset_symbol_still_resolves(self):
        # asset_symbol missing: we lose the false-positive guard but keep the mapping.
        assert fee_currency_quote_anchor("USD", None) == "USD"

    def test_whitespace_and_case_are_normalised(self):
        assert fee_currency_quote_anchor("  usd  ", "btc") == "USD"
