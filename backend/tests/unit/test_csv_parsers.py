"""Tests for CSV parsers (Binance, Kraken, Crypto.com, Generic).

Covers: row parsing, auto-detection, date parsing edge cases, malformed data,
delimiter handling, and the detect_csv_format/get_parser_by_name utilities.
"""

from datetime import datetime
from decimal import Decimal

import pytest

from app.services.csv_parsers import (
    AVAILABLE_PARSERS,
    BinanceCSVParser,
    CryptoComCSVParser,
    GenericCSVParser,
    KrakenCSVParser,
    ParsedTransaction,
    detect_csv_format,
    get_available_platforms,
    get_parser_by_name,
    parse_timestamp,
)


# ---------------------------------------------------------------------------
# parse_timestamp
# ---------------------------------------------------------------------------
class TestParseTimestamp:
    """Tests for the parse_timestamp utility."""

    def test_iso_format(self):
        ts = parse_timestamp("2025-06-15 14:30:00")
        assert ts == datetime(2025, 6, 15, 14, 30, 0)

    def test_iso_format_with_t(self):
        ts = parse_timestamp("2025-06-15T14:30:00")
        assert ts == datetime(2025, 6, 15, 14, 30, 0)

    def test_iso_with_z(self):
        ts = parse_timestamp("2025-06-15T14:30:00Z")
        assert ts == datetime(2025, 6, 15, 14, 30, 0)

    def test_iso_with_milliseconds(self):
        ts = parse_timestamp("2025-06-15T14:30:00.123456")
        assert ts.year == 2025
        assert ts.second == 0

    def test_european_format(self):
        ts = parse_timestamp("15/06/2025 14:30:00")
        assert ts == datetime(2025, 6, 15, 14, 30, 0)

    def test_european_format_no_seconds(self):
        ts = parse_timestamp("15/06/2025 14:30")
        assert ts == datetime(2025, 6, 15, 14, 30, 0)

    def test_american_format(self):
        ts = parse_timestamp("06/15/2025 14:30:00")
        assert ts == datetime(2025, 6, 15, 14, 30, 0)

    def test_strips_whitespace(self):
        ts = parse_timestamp("  2025-06-15 14:30:00  ")
        assert ts == datetime(2025, 6, 15, 14, 30, 0)

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="Invalid timestamp"):
            parse_timestamp("not-a-date")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            parse_timestamp("")


# ---------------------------------------------------------------------------
# Binance CSV Parser
# ---------------------------------------------------------------------------
class TestBinanceCSVParser:
    """Tests for BinanceCSVParser."""

    @pytest.fixture
    def parser(self):
        return BinanceCSVParser()

    def test_can_parse_valid_headers(self, parser):
        headers = ["UTC_Time", "Operation", "Coin", "Change"]
        assert BinanceCSVParser.can_parse(headers)

    def test_cannot_parse_wrong_headers(self, parser):
        headers = ["date", "type", "amount"]
        assert not BinanceCSVParser.can_parse(headers)

    def test_parse_buy_row(self, parser):
        row = {
            "utc_time": "2025-01-15 10:00:00",
            "operation": "Buy",
            "coin": "BTC",
            "change": "0.5",
        }
        txs = parser.parse_row(row)
        assert len(txs) == 1
        assert txs[0].symbol == "BTC"
        assert txs[0].transaction_type == "buy"
        assert txs[0].quantity == Decimal("0.5")

    def test_parse_sell_row(self, parser):
        row = {
            "utc_time": "2025-01-15 10:00:00",
            "operation": "Sell",
            "coin": "ETH",
            "change": "-2.0",
        }
        txs = parser.parse_row(row)
        assert len(txs) == 1
        assert txs[0].transaction_type == "sell"
        assert txs[0].quantity == Decimal("2.0")  # Absolute value

    def test_parse_deposit(self, parser):
        row = {
            "utc_time": "2025-03-01 08:00:00",
            "operation": "Deposit",
            "coin": "SOL",
            "change": "100",
        }
        txs = parser.parse_row(row)
        assert len(txs) == 1
        assert txs[0].transaction_type == "transfer_in"

    def test_parse_withdrawal(self, parser):
        row = {
            "utc_time": "2025-03-01 08:00:00",
            "operation": "Withdraw",
            "coin": "SOL",
            "change": "-50",
        }
        txs = parser.parse_row(row)
        assert len(txs) == 1
        assert txs[0].transaction_type == "transfer_out"
        assert txs[0].quantity == Decimal("50")

    def test_parse_staking_reward(self, parser):
        row = {
            "utc_time": "2025-02-01 00:00:00",
            "operation": "Staking Rewards",
            "coin": "DOT",
            "change": "1.23",
        }
        txs = parser.parse_row(row)
        assert len(txs) == 1
        assert txs[0].transaction_type == "staking_reward"

    def test_parse_eth_staking_reward(self, parser):
        row = {
            "utc_time": "2025-02-01 00:00:00",
            "operation": "ETH 2.0 Staking Rewards",
            "coin": "ETH",
            "change": "0.01",
        }
        txs = parser.parse_row(row)
        assert len(txs) == 1
        assert txs[0].transaction_type == "staking_reward"

    def test_parse_airdrop(self, parser):
        row = {
            "utc_time": "2025-04-01 12:00:00",
            "operation": "Distribution",
            "coin": "ARB",
            "change": "50",
        }
        txs = parser.parse_row(row)
        assert len(txs) == 1
        assert txs[0].transaction_type == "airdrop"

    def test_parse_conversion_positive(self, parser):
        row = {
            "utc_time": "2025-04-01 12:00:00",
            "operation": "Small assets exchange BNB",
            "coin": "BNB",
            "change": "0.1",
        }
        txs = parser.parse_row(row)
        assert len(txs) == 1
        assert txs[0].transaction_type == "conversion_in"

    def test_parse_conversion_negative(self, parser):
        row = {
            "utc_time": "2025-04-01 12:00:00",
            "operation": "Small assets exchange BNB",
            "coin": "SHIB",
            "change": "-10000",
        }
        txs = parser.parse_row(row)
        assert len(txs) == 1
        assert txs[0].transaction_type == "conversion_out"

    def test_unknown_operation_skipped(self, parser):
        row = {
            "utc_time": "2025-04-01 12:00:00",
            "operation": "Unknown Op",
            "coin": "BTC",
            "change": "1",
        }
        txs = parser.parse_row(row)
        assert len(txs) == 0

    def test_zero_change_skipped(self, parser):
        row = {
            "utc_time": "2025-04-01 12:00:00",
            "operation": "Buy",
            "coin": "BTC",
            "change": "0",
        }
        txs = parser.parse_row(row)
        assert len(txs) == 0

    def test_invalid_amount_raises(self, parser):
        row = {
            "utc_time": "2025-04-01 12:00:00",
            "operation": "Buy",
            "coin": "BTC",
            "change": "not_a_number",
        }
        with pytest.raises(ValueError, match="Invalid change amount"):
            parser.parse_row(row)

    def test_parse_full_csv(self, parser):
        csv_content = (
            "UTC_Time,Operation,Coin,Change\n"
            "2025-01-15 10:00:00,Buy,BTC,0.5\n"
            "2025-01-16 11:00:00,Sell,ETH,-2.0\n"
            "2025-01-17 12:00:00,Staking Rewards,DOT,1.0\n"
        )
        txs, errors = parser.parse_csv(csv_content)
        assert len(txs) == 3
        assert len(errors) == 0

    def test_parse_csv_with_errors(self, parser):
        csv_content = (
            "UTC_Time,Operation,Coin,Change\n"
            "2025-01-15 10:00:00,Buy,BTC,0.5\n"
            "invalid-date,Buy,ETH,1.0\n"
        )
        txs, errors = parser.parse_csv(csv_content)
        assert len(txs) == 1
        assert len(errors) == 1
        assert "Row 3" in errors[0]


# ---------------------------------------------------------------------------
# Kraken CSV Parser
# ---------------------------------------------------------------------------
class TestKrakenCSVParser:
    """Tests for KrakenCSVParser."""

    @pytest.fixture
    def parser(self):
        return KrakenCSVParser()

    def test_can_parse_valid_headers(self):
        headers = ["txid", "refid", "time", "type", "asset", "amount", "fee"]
        assert KrakenCSVParser.can_parse(headers)

    def test_normalize_xxbt_to_btc(self, parser):
        assert parser._normalize_asset("XXBT") == "BTC"

    def test_normalize_xeth_to_eth(self, parser):
        assert parser._normalize_asset("XETH") == "ETH"

    def test_normalize_zusd_to_usd(self, parser):
        assert parser._normalize_asset("ZUSD") == "USD"

    def test_normalize_zeur_to_eur(self, parser):
        assert parser._normalize_asset("ZEUR") == "EUR"

    def test_normalize_4char_x_prefix(self, parser):
        assert parser._normalize_asset("XLTC") == "LTC"

    def test_normalize_regular_symbol(self, parser):
        assert parser._normalize_asset("SOL") == "SOL"

    def test_parse_trade_buy(self, parser):
        row = {
            "txid": "TXID1",
            "refid": "REF1",
            "time": "2025-01-15 10:00:00",
            "type": "trade",
            "asset": "XXBT",
            "amount": "0.1",
            "fee": "0.0001",
        }
        txs = parser.parse_row(row)
        assert len(txs) == 1
        assert txs[0].symbol == "BTC"
        assert txs[0].transaction_type == "buy"
        assert txs[0].quantity == Decimal("0.1")
        assert txs[0].fee == Decimal("0.0001")

    def test_parse_trade_sell(self, parser):
        row = {
            "txid": "TXID2",
            "refid": "REF2",
            "time": "2025-01-15 10:00:00",
            "type": "trade",
            "asset": "XETH",
            "amount": "-1.5",
            "fee": "0.001",
        }
        txs = parser.parse_row(row)
        assert len(txs) == 1
        assert txs[0].transaction_type == "sell"
        assert txs[0].quantity == Decimal("1.5")

    def test_parse_deposit(self, parser):
        row = {
            "txid": "TXID3",
            "refid": "REF3",
            "time": "2025-02-01 08:00:00",
            "type": "deposit",
            "asset": "SOL",
            "amount": "50",
            "fee": "0",
        }
        txs = parser.parse_row(row)
        assert len(txs) == 1
        assert txs[0].transaction_type == "transfer_in"

    def test_parse_staking(self, parser):
        row = {
            "txid": "TXID4",
            "refid": "REF4",
            "time": "2025-03-01 00:00:00",
            "type": "staking",
            "asset": "DOT",
            "amount": "2.5",
            "fee": "0",
        }
        txs = parser.parse_row(row)
        assert len(txs) == 1
        assert txs[0].transaction_type == "staking_reward"

    def test_skip_fiat_entries(self, parser):
        """Fiat rows (EUR, USD) should be skipped."""
        row = {
            "txid": "TXID5",
            "refid": "REF5",
            "time": "2025-01-15 10:00:00",
            "type": "trade",
            "asset": "ZEUR",
            "amount": "-500",
            "fee": "0.5",
        }
        txs = parser.parse_row(row)
        assert len(txs) == 0

    def test_unknown_type_skipped(self, parser):
        row = {
            "txid": "TXID6",
            "refid": "REF6",
            "time": "2025-01-15 10:00:00",
            "type": "margin",
            "asset": "XXBT",
            "amount": "0.5",
            "fee": "0",
        }
        txs = parser.parse_row(row)
        assert len(txs) == 0

    def test_timestamp_with_fractional_seconds(self, parser):
        """Kraken sometimes includes fractional seconds."""
        row = {
            "txid": "TXID7",
            "refid": "REF7",
            "time": "2025-01-15 10:00:00.1234",
            "type": "trade",
            "asset": "XXBT",
            "amount": "0.1",
            "fee": "0",
        }
        txs = parser.parse_row(row)
        assert len(txs) == 1

    def test_invalid_timestamp_raises(self, parser):
        row = {
            "txid": "TXID8",
            "refid": "REF8",
            "time": "not-a-date",
            "type": "trade",
            "asset": "XXBT",
            "amount": "0.1",
            "fee": "0",
        }
        with pytest.raises(ValueError, match="Invalid timestamp"):
            parser.parse_row(row)

    def test_invalid_amount_raises(self, parser):
        row = {
            "txid": "TXID9",
            "refid": "REF9",
            "time": "2025-01-15 10:00:00",
            "type": "trade",
            "asset": "XXBT",
            "amount": "abc",
            "fee": "0",
        }
        with pytest.raises(ValueError, match="Invalid amount"):
            parser.parse_row(row)

    def test_parse_full_csv(self, parser):
        csv_content = (
            "txid,refid,time,type,asset,amount,fee\n"
            "T1,R1,2025-01-15 10:00:00,trade,XXBT,0.1,0.0001\n"
            "T2,R2,2025-01-15 10:00:00,trade,ZEUR,-5000,0.5\n"
            "T3,R3,2025-02-01 08:00:00,staking,DOT,2.5,0\n"
        )
        txs, errors = parser.parse_csv(csv_content)
        # Row 2 (ZEUR) is skipped, so 2 transactions
        assert len(txs) == 2
        assert len(errors) == 0


# ---------------------------------------------------------------------------
# Crypto.com CSV Parser
# ---------------------------------------------------------------------------
class TestCryptoComCSVParser:
    """Tests for CryptoComCSVParser."""

    @pytest.fixture
    def parser(self):
        return CryptoComCSVParser()

    def test_can_parse_valid_headers(self):
        headers = [
            "Timestamp (UTC)",
            "Transaction Description",
            "Currency",
            "Amount",
            "Transaction Kind",
        ]
        assert CryptoComCSVParser.can_parse(headers)

    def test_parse_buy_with_to_currency(self, parser):
        """Crypto.com purchase where crypto is in To Currency field."""
        row = {
            "timestamp (utc)": "2025-01-15 10:00:00",
            "transaction description": "Buy BTC",
            "currency": "EUR",
            "amount": "-500",
            "to currency": "BTC",
            "to amount": "0.01",
            "native currency": "EUR",
            "native amount": "500",
            "transaction kind": "viban_purchase",
        }
        txs = parser.parse_row(row)
        assert len(txs) == 1
        assert txs[0].symbol == "BTC"
        assert txs[0].transaction_type == "buy"
        assert txs[0].quantity == Decimal("0.01")
        assert txs[0].price == Decimal("50000")  # 500 / 0.01

    def test_parse_sell(self, parser):
        row = {
            "timestamp (utc)": "2025-02-01 12:00:00",
            "transaction description": "Sell ETH",
            "currency": "ETH",
            "amount": "-2.0",
            "to currency": "",
            "to amount": "0",
            "native currency": "EUR",
            "native amount": "3000",
            "transaction kind": "crypto_viban_exchange",
        }
        txs = parser.parse_row(row)
        assert len(txs) == 1
        assert txs[0].transaction_type == "sell"
        assert txs[0].quantity == Decimal("2.0")

    def test_parse_deposit(self, parser):
        row = {
            "timestamp (utc)": "2025-03-01 08:00:00",
            "transaction description": "Deposit SOL",
            "currency": "SOL",
            "amount": "100",
            "to currency": "",
            "to amount": "0",
            "native currency": "EUR",
            "native amount": "500",
            "transaction kind": "crypto_deposit",
        }
        txs = parser.parse_row(row)
        assert len(txs) == 1
        assert txs[0].transaction_type == "transfer_in"
        assert txs[0].quantity == Decimal("100")

    def test_parse_withdrawal(self, parser):
        row = {
            "timestamp (utc)": "2025-03-15 08:00:00",
            "transaction description": "Withdraw BTC",
            "currency": "BTC",
            "amount": "-0.5",
            "to currency": "",
            "to amount": "0",
            "native currency": "EUR",
            "native amount": "25000",
            "transaction kind": "crypto_withdrawal",
        }
        txs = parser.parse_row(row)
        assert len(txs) == 1
        assert txs[0].transaction_type == "transfer_out"
        assert txs[0].quantity == Decimal("0.5")

    def test_parse_staking_reward(self, parser):
        row = {
            "timestamp (utc)": "2025-04-01 00:00:00",
            "transaction description": "CRO Stake Reward",
            "currency": "CRO",
            "amount": "10",
            "to currency": "",
            "to amount": "0",
            "native currency": "EUR",
            "native amount": "1.5",
            "transaction kind": "staking_reward",
        }
        txs = parser.parse_row(row)
        assert len(txs) == 1
        assert txs[0].transaction_type == "staking_reward"
        assert txs[0].quantity == Decimal("10")

    def test_parse_airdrop(self, parser):
        row = {
            "timestamp (utc)": "2025-05-01 00:00:00",
            "transaction description": "Referral Bonus",
            "currency": "CRO",
            "amount": "25",
            "to currency": "",
            "to amount": "0",
            "native currency": "EUR",
            "native amount": "5",
            "transaction kind": "referral_bonus",
        }
        txs = parser.parse_row(row)
        assert len(txs) == 1
        assert txs[0].transaction_type == "airdrop"

    def test_parse_crypto_exchange_conversion(self, parser):
        """Crypto-to-crypto exchange generates two transactions."""
        row = {
            "timestamp (utc)": "2025-06-01 10:00:00",
            "transaction description": "Convert BTC to ETH",
            "currency": "BTC",
            "amount": "-0.1",
            "to currency": "ETH",
            "to amount": "1.5",
            "native currency": "EUR",
            "native amount": "5000",
            "transaction kind": "crypto_exchange",
        }
        txs = parser.parse_row(row)
        assert len(txs) == 2
        # First: conversion_out for BTC
        assert txs[0].symbol == "BTC"
        assert txs[0].transaction_type == "conversion_out"
        assert txs[0].quantity == Decimal("0.1")
        assert txs[0].to_symbol == "ETH"
        assert txs[0].to_quantity == Decimal("1.5")
        # Second: conversion_in for ETH
        assert txs[1].symbol == "ETH"
        assert txs[1].transaction_type == "conversion_in"
        assert txs[1].quantity == Decimal("1.5")

    def test_parse_wallet_swap_debited(self, parser):
        row = {
            "timestamp (utc)": "2025-06-01 10:00:00",
            "transaction description": "Balance Conversion",
            "currency": "USDC",
            "amount": "-100",
            "to currency": "",
            "to amount": "0",
            "native currency": "EUR",
            "native amount": "92",
            "transaction kind": "crypto_wallet_swap_debited",
        }
        txs = parser.parse_row(row)
        assert len(txs) == 1
        assert txs[0].transaction_type == "conversion_out"
        assert txs[0].quantity == Decimal("100")

    def test_parse_wallet_swap_credited(self, parser):
        row = {
            "timestamp (utc)": "2025-06-01 10:00:00",
            "transaction description": "Balance Conversion",
            "currency": "ETH",
            "amount": "0.5",
            "to currency": "",
            "to amount": "0",
            "native currency": "EUR",
            "native amount": "1000",
            "transaction kind": "crypto_wallet_swap_credited",
        }
        txs = parser.parse_row(row)
        assert len(txs) == 1
        assert txs[0].transaction_type == "conversion_in"
        assert txs[0].quantity == Decimal("0.5")

    def test_unknown_kind_skipped(self, parser):
        row = {
            "timestamp (utc)": "2025-06-01 10:00:00",
            "transaction description": "Unknown",
            "currency": "BTC",
            "amount": "1",
            "to currency": "",
            "to amount": "0",
            "native currency": "EUR",
            "native amount": "50000",
            "transaction kind": "some_unknown_kind",
        }
        txs = parser.parse_row(row)
        assert len(txs) == 0

    def test_invalid_amount_raises(self, parser):
        row = {
            "timestamp (utc)": "2025-06-01 10:00:00",
            "transaction description": "Buy",
            "currency": "BTC",
            "amount": "not_a_number",
            "to currency": "",
            "to amount": "0",
            "native currency": "EUR",
            "native amount": "0",
            "transaction kind": "viban_purchase",
        }
        with pytest.raises(ValueError, match="Invalid amount"):
            parser.parse_row(row)

    def test_google_pay_direct_purchase(self, parser):
        """Direct crypto purchase where crypto is the Currency field."""
        row = {
            "timestamp (utc)": "2025-01-15 10:00:00",
            "transaction description": "Buy BTC via Google Pay",
            "currency": "BTC",
            "amount": "0.005",
            "to currency": "",
            "to amount": "0",
            "native currency": "EUR",
            "native amount": "200",
            "transaction kind": "trading.crypto_purchase.google_pay",
        }
        txs = parser.parse_row(row)
        assert len(txs) == 1
        assert txs[0].symbol == "BTC"
        assert txs[0].transaction_type == "buy"
        assert txs[0].quantity == Decimal("0.005")
        assert txs[0].price == Decimal("40000")  # 200 / 0.005


# ---------------------------------------------------------------------------
# Generic CSV Parser
# ---------------------------------------------------------------------------
class TestGenericCSVParser:
    """Tests for GenericCSVParser (InvestAI format)."""

    @pytest.fixture
    def parser(self):
        return GenericCSVParser()

    def test_can_parse_valid_headers(self):
        headers = ["Symbol", "Type", "Quantity", "Price"]
        assert GenericCSVParser.can_parse(headers)

    def test_parse_buy(self, parser):
        row = {
            "symbol": "btc",
            "type": "buy",
            "quantity": "0.5",
            "price": "40000",
            "fee": "10",
            "date": "2025-01-15 10:00:00",
            "notes": "First BTC purchase",
        }
        txs = parser.parse_row(row)
        assert len(txs) == 1
        assert txs[0].symbol == "BTC"
        assert txs[0].transaction_type == "buy"
        assert txs[0].quantity == Decimal("0.5")
        assert txs[0].price == Decimal("40000")
        assert txs[0].fee == Decimal("10")
        assert txs[0].notes == "First BTC purchase"

    def test_parse_sell(self, parser):
        row = {
            "symbol": "ETH",
            "type": "sell",
            "quantity": "2",
            "price": "3000",
            "fee": "5",
            "date": "2025-02-01",
            "notes": "",
        }
        txs = parser.parse_row(row)
        assert len(txs) == 1
        assert txs[0].transaction_type == "sell"

    def test_french_type_mapping(self, parser):
        """French transaction types should be mapped."""
        row = {"symbol": "BTC", "type": "achat", "quantity": "1", "price": "50000", "fee": "0", "date": "", "notes": ""}
        txs = parser.parse_row(row)
        assert txs[0].transaction_type == "buy"

        row["type"] = "vente"
        txs = parser.parse_row(row)
        assert txs[0].transaction_type == "sell"

    def test_deposit_mapping(self, parser):
        row = {"symbol": "SOL", "type": "deposit", "quantity": "10", "price": "0", "fee": "0", "date": "", "notes": ""}
        txs = parser.parse_row(row)
        assert txs[0].transaction_type == "transfer_in"

    def test_empty_symbol_skipped(self, parser):
        row = {"symbol": "", "type": "buy", "quantity": "1", "price": "100", "fee": "0", "date": "", "notes": ""}
        txs = parser.parse_row(row)
        assert len(txs) == 0

    def test_empty_type_skipped(self, parser):
        row = {"symbol": "BTC", "type": "", "quantity": "1", "price": "100", "fee": "0", "date": "", "notes": ""}
        txs = parser.parse_row(row)
        assert len(txs) == 0

    def test_invalid_number_raises(self, parser):
        row = {"symbol": "BTC", "type": "buy", "quantity": "abc", "price": "100", "fee": "0", "date": "", "notes": ""}
        with pytest.raises(ValueError, match="Invalid number"):
            parser.parse_row(row)

    def test_date_parsing_iso(self, parser):
        row = {
            "symbol": "BTC",
            "type": "buy",
            "quantity": "1",
            "price": "100",
            "fee": "0",
            "date": "2025-06-15 14:30:00",
            "notes": "",
        }
        txs = parser.parse_row(row)
        assert txs[0].timestamp == datetime(2025, 6, 15, 14, 30, 0)

    def test_date_parsing_european(self, parser):
        row = {
            "symbol": "BTC",
            "type": "buy",
            "quantity": "1",
            "price": "100",
            "fee": "0",
            "date": "15/06/2025",
            "notes": "",
        }
        txs = parser.parse_row(row)
        assert txs[0].timestamp.year == 2025

    def test_no_date_uses_now(self, parser):
        row = {"symbol": "BTC", "type": "buy", "quantity": "1", "price": "100", "fee": "0", "date": "", "notes": ""}
        txs = parser.parse_row(row)
        # Should be close to now
        assert (datetime.now() - txs[0].timestamp).total_seconds() < 5

    def test_parse_full_csv(self, parser):
        csv_content = (
            "symbol,type,quantity,price,fee,date,notes\n"
            "BTC,buy,0.5,40000,10,2025-01-15 10:00:00,First purchase\n"
            "ETH,sell,2,3000,5,2025-02-01,Partial sell\n"
        )
        txs, errors = parser.parse_csv(csv_content)
        assert len(txs) == 2
        assert len(errors) == 0


# ---------------------------------------------------------------------------
# CSV format auto-detection
# ---------------------------------------------------------------------------
class TestDetectCSVFormat:
    """Tests for detect_csv_format."""

    def test_detect_binance(self):
        csv_content = "UTC_Time,Operation,Coin,Change\n2025-01-15 10:00:00,Buy,BTC,0.5\n"
        parser = detect_csv_format(csv_content)
        assert parser is not None
        assert isinstance(parser, BinanceCSVParser)

    def test_detect_kraken(self):
        csv_content = "txid,refid,time,type,asset,amount,fee\nT1,R1,2025-01-15 10:00:00,trade,XXBT,0.1,0.0001\n"
        parser = detect_csv_format(csv_content)
        assert parser is not None
        assert isinstance(parser, KrakenCSVParser)

    def test_detect_cryptocom(self):
        csv_content = (
            "Timestamp (UTC),Transaction Description,Currency,Amount,Transaction Kind\n"
            "2025-01-15 10:00:00,Buy BTC,BTC,0.5,viban_purchase\n"
        )
        parser = detect_csv_format(csv_content)
        assert parser is not None
        assert isinstance(parser, CryptoComCSVParser)

    def test_detect_generic(self):
        csv_content = "symbol,type,quantity,price\nBTC,buy,1,50000\n"
        parser = detect_csv_format(csv_content)
        assert parser is not None
        assert isinstance(parser, GenericCSVParser)

    def test_detect_empty_content(self):
        parser = detect_csv_format("")
        assert parser is None

    def test_detect_single_column_csv(self):
        """A single column CSV should not match any parser."""
        csv_content = "justonecolumn\nvalue1\nvalue2\n"
        parser = detect_csv_format(csv_content)
        assert parser is None

    def test_detect_semicolon_delimiter(self):
        csv_content = "symbol;type;quantity;price\nBTC;buy;1;50000\n"
        parser = detect_csv_format(csv_content)
        assert parser is not None
        assert isinstance(parser, GenericCSVParser)


# ---------------------------------------------------------------------------
# get_parser_by_name and get_available_platforms
# ---------------------------------------------------------------------------
class TestParserUtilities:
    """Tests for get_parser_by_name and get_available_platforms."""

    def test_get_binance_parser(self):
        parser = get_parser_by_name("Binance")
        assert parser is not None
        assert isinstance(parser, BinanceCSVParser)

    def test_get_kraken_parser(self):
        parser = get_parser_by_name("Kraken")
        assert parser is not None
        assert isinstance(parser, KrakenCSVParser)

    def test_get_cryptocom_parser(self):
        parser = get_parser_by_name("Crypto.com")
        assert parser is not None
        assert isinstance(parser, CryptoComCSVParser)

    def test_get_generic_parser(self):
        parser = get_parser_by_name("Generic")
        assert parser is not None
        assert isinstance(parser, GenericCSVParser)

    def test_case_insensitive_search(self):
        parser = get_parser_by_name("binance")
        assert parser is not None
        assert isinstance(parser, BinanceCSVParser)

    def test_unknown_parser_returns_none(self):
        parser = get_parser_by_name("CoinbasePro")
        assert parser is None

    def test_available_platforms(self):
        platforms = get_available_platforms()
        assert len(platforms) == len(AVAILABLE_PARSERS)
        assert "Binance" in platforms
        assert "Kraken" in platforms
        assert "Crypto.com" in platforms


# ---------------------------------------------------------------------------
# Malformed CSV handling
# ---------------------------------------------------------------------------
class TestMalformedCSV:
    """Tests for handling of malformed CSV data."""

    def test_binance_missing_fields(self):
        parser = BinanceCSVParser()
        csv_content = "UTC_Time,Operation,Coin,Change\n2025-01-15 10:00:00,Buy\n"
        txs, errors = parser.parse_csv(csv_content)
        # The row is incomplete but should not crash
        assert isinstance(txs, list)

    def test_extra_columns_ignored(self):
        parser = GenericCSVParser()
        csv_content = (
            "symbol,type,quantity,price,extra_col1,extra_col2\n"
            "BTC,buy,1,50000,foo,bar\n"
        )
        txs, errors = parser.parse_csv(csv_content)
        assert len(txs) == 1
        assert len(errors) == 0

    def test_tab_delimiter(self):
        parser = GenericCSVParser()
        csv_content = "symbol\ttype\tquantity\tprice\nBTC\tbuy\t1\t50000\n"
        txs, errors = parser.parse_csv(csv_content)
        assert len(txs) == 1


# ---------------------------------------------------------------------------
# ParsedTransaction dataclass
# ---------------------------------------------------------------------------
class TestParsedTransaction:
    """Tests for the ParsedTransaction dataclass."""

    def test_creation(self):
        tx = ParsedTransaction(
            symbol="BTC",
            transaction_type="buy",
            quantity=Decimal("0.5"),
            price=Decimal("50000"),
            fee=Decimal("10"),
            currency="EUR",
            timestamp=datetime(2025, 1, 15),
        )
        assert tx.symbol == "BTC"
        assert tx.to_symbol is None
        assert tx.to_quantity is None
        assert tx.notes is None

    def test_with_conversion_fields(self):
        tx = ParsedTransaction(
            symbol="BTC",
            transaction_type="conversion_out",
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
            fee=Decimal("0"),
            currency="EUR",
            timestamp=datetime(2025, 1, 15),
            to_symbol="ETH",
            to_quantity=Decimal("1.5"),
            notes="Crypto.com conversion",
        )
        assert tx.to_symbol == "ETH"
        assert tx.to_quantity == Decimal("1.5")
        assert tx.notes == "Crypto.com conversion"
