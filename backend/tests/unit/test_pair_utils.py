"""Unit tests for exchange pair parsing (FIN-01 foundation).

These pin the quote-currency detection that the sync + backfill rely on to record the
real trade currency instead of the hard-coded ``EUR``. Pure functions: no DB/HTTP/Docker.
"""

import pytest

from app.services.exchanges.pair_utils import is_crypto_quote, quote_fx_currency, split_pair


class TestSplitPair:
    @pytest.mark.parametrize(
        "symbol,expected",
        [
            ("BTCUSDT", ("BTC", "USDT")),
            ("ETHUSDC", ("ETH", "USDC")),
            ("BTCUSD", ("BTC", "USD")),
            ("PAXGEUR", ("PAXG", "EUR")),
            ("BTCFDUSD", ("BTC", "FDUSD")),  # 5-char quote beats USD/USDT
            ("SOLBUSD", ("SOL", "BUSD")),
            ("DOGEBTC", ("DOGE", "BTC")),  # crypto quote
            ("ADAETH", ("ADA", "ETH")),
        ],
    )
    def test_concatenated_pairs(self, symbol, expected):
        assert split_pair(symbol) == expected

    @pytest.mark.parametrize(
        "symbol,expected",
        [
            ("BTC-USDT", ("BTC", "USDT")),
            ("BTC/USDT", ("BTC", "USDT")),
            ("BTC_USDT", ("BTC", "USDT")),
            ("eth-eur", ("ETH", "EUR")),
        ],
    )
    def test_separated_pairs(self, symbol, expected):
        assert split_pair(symbol) == expected

    def test_longest_quote_wins(self):
        # "USDT" must win over "USD" so the base is not polluted with a trailing 'T'.
        assert split_pair("XRPUSDT") == ("XRP", "USDT")

    def test_bare_asset_has_no_quote(self):
        assert split_pair("BTC") == ("BTC", None)

    def test_empty(self):
        assert split_pair("") == (None, None)

    def test_case_insensitive(self):
        assert split_pair("btcusdt") == ("BTC", "USDT")


class TestQuoteFxCurrency:
    @pytest.mark.parametrize("stable", ["USDT", "USDC", "BUSD", "TUSD", "FDUSD", "DAI", "USD"])
    def test_usd_pegged_collapse_to_usd(self, stable):
        assert quote_fx_currency(stable) == "USD"

    @pytest.mark.parametrize("eur", ["EUR", "EURT", "EURC"])
    def test_eur_pegged_collapse_to_eur(self, eur):
        assert quote_fx_currency(eur) == "EUR"

    @pytest.mark.parametrize("fiat", ["GBP", "JPY", "CHF", "CAD", "AUD"])
    def test_other_fiats_passthrough(self, fiat):
        assert quote_fx_currency(fiat) == fiat

    @pytest.mark.parametrize("crypto", ["BTC", "ETH", "BNB"])
    def test_crypto_quotes_have_no_fiat_anchor(self, crypto):
        assert quote_fx_currency(crypto) is None

    def test_none_and_unknown(self):
        assert quote_fx_currency(None) is None
        assert quote_fx_currency("WAT") is None


class TestIsCryptoQuote:
    @pytest.mark.parametrize("crypto", ["BTC", "ETH", "BNB", "btc"])
    def test_true_for_crypto(self, crypto):
        assert is_crypto_quote(crypto) is True

    @pytest.mark.parametrize("notcrypto", ["USDT", "USD", "EUR", None, ""])
    def test_false_otherwise(self, notcrypto):
        assert is_crypto_quote(notcrypto) is False
