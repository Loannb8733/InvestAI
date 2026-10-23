from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest

from app.domains.exchanges.failures import mark_failure
from app.domains.exchanges.models import APIKey, APIKeyStatus
from app.domains.exchanges.sync.feed import unseen_converts
from app.domains.exchanges.sync.pairs import fiat_anchor, split_pair
from app.domains.exchanges.sync.pricing import TradeFx, market_price
from app.domains.exchanges.sync.rules import (
    CREDITED,
    SENT,
    as_utc,
    balance_gap,
    cold_wallet_for,
    has_status,
    undoes_recent_move,
)
from app.domains.exchanges.sync.symbols import base_symbol, conversion_base, holdings, trade_base
from app.domains.market_data.prices.quote import PriceQuote
from app.services.exchanges.base import ExchangeBalance, ExchangeFiatOrder

D = Decimal


class TestSymbols:
    @pytest.mark.parametrize(
        ("symbol", "base"),
        [("WBTC", "BTC"), ("WETH", "ETH"), ("LDBTC", "BTC"), ("BFUSD", "USD"), ("ADAU", "ADA"), ("OMKA", "OM")],
    )
    def test_variants_fold_into_their_asset(self, symbol: str, base: str) -> None:
        assert base_symbol(symbol) == base

    @pytest.mark.parametrize("symbol", ["WAVES", "WAXP", "WIF", "WLD", "ETHFI", "SOLV", "OMNI", "OMG", "LDO", "TAO"])
    def test_real_tokens_are_never_altered(self, symbol: str) -> None:
        assert base_symbol(symbol) == symbol

    def test_the_longest_known_asset_wins_and_nothing_is_guessed(self) -> None:
        assert conversion_base("DOGEPEPE", {"DO", "DOGE"}) == "DOGE"
        assert conversion_base("PENDLEUSDC", {"PENDLE", "USDC"}) == "PENDLE"
        assert conversion_base("PENDLEPEPE", set()) is None
        assert conversion_base("DOGEPEPE", {"PEPE"}) is None

    @pytest.mark.parametrize(
        ("symbol", "known", "expected"),
        [
            ("BTCEUR", set(), ("BTC", "EUR")),
            ("ETHFIEUR", {"ETH"}, ("ETHFI", "EUR")),
            ("BTC-USDT", set(), ("BTC", "USDT")),
            ("XYZTRY", {"XYZ"}, ("XYZ", None)),
            ("EURUSDT", set(), (None, "USDT")),
        ],
    )
    def test_trade_pairs(self, symbol: str, known: set[str], expected: tuple[str | None, str | None]) -> None:
        assert trade_base(symbol, known) == expected

    def test_balances_fold_earn_and_skip_fiat(self) -> None:
        def balance(symbol: str, total: str) -> ExchangeBalance:
            return ExchangeBalance(symbol=symbol, free=D(total), locked=D("0"), total=D(total))

        held = holdings([balance("BTC", "1"), balance("LDBTC", "0.5"), balance("WETH", "2"), balance("EUR", "9")])
        assert held.totals == {"BTC": D("1.5"), "ETH": D("2")}
        assert held.staked == {"BTC": D("0.5")}


class TestPairs:
    def test_split(self) -> None:
        assert split_pair("BTCFDUSD") == ("BTC", "FDUSD")
        assert split_pair("btc/eur") == ("BTC", "EUR")
        assert split_pair("BTC") == ("BTC", None)
        assert split_pair("") == (None, None)

    @pytest.mark.parametrize(
        ("quote", "anchor"), [("USDT", "USD"), ("FDUSD", "USD"), ("EURC", "EUR"), ("GBP", "GBP"), ("BTC", None)]
    )
    def test_fiat_anchor(self, quote: str, anchor: str | None) -> None:
        assert fiat_anchor(quote) == anchor


class TestBalanceGap:
    def test_noise_dust_and_transfer(self) -> None:
        assert balance_gap(D("1.5"), D("1.5")) == "none"
        assert balance_gap(D("1"), D("1.000000005")) == "none"
        assert balance_gap(D("1000000000") - D("10"), D("1000000000")) == "dust"
        assert balance_gap(D("1"), D("1.5")) == "transfer"
        assert balance_gap(D("0.5"), D("0")) == "transfer"

    def test_an_adjustment_that_undoes_a_recent_move_is_recognised(self) -> None:
        assert undoes_recent_move(D("-0.00332921"), [D("0.00332921")]) is True
        assert undoes_recent_move(D("-0.003329213100"), [D("0.003329209400")]) is True
        assert undoes_recent_move(D("-0.5"), [D("0.1"), None, D("0")]) is False
        assert undoes_recent_move(D("-1"), [D("0.001")]) is False
        assert undoes_recent_move(D("0"), [D("0.5")]) is False


class TestStatusesAndWallets:
    def test_statuses(self) -> None:
        assert has_status(" Completed ", CREDITED) and has_status("credited", CREDITED)
        assert not has_status("pending", CREDITED) and not has_status(None, SENT)
        assert has_status("sent", SENT)

    def test_cold_wallet_by_address_else_default(self) -> None:
        wallets = {"bc1abc": "Ledger"}
        assert cold_wallet_for(" BC1ABC ", wallets) == "Ledger"
        assert cold_wallet_for("other", wallets) == "Tangem"
        assert cold_wallet_for(None, wallets) == "Tangem"

    def test_as_utc(self) -> None:
        assert as_utc(datetime(2025, 1, 1)) == datetime(2025, 1, 1, tzinfo=UTC)
        paris = datetime(2025, 1, 1, 13, tzinfo=timezone(timedelta(hours=1)))
        assert as_utc(paris) == datetime(2025, 1, 1, 12, tzinfo=UTC)
        assert as_utc(None) is None


class FakeFx:
    def __init__(self, rate: Decimal | None) -> None:
        self.rate = rate
        self.asked: list[tuple[date, str, str]] = []

    async def rate_on(self, day: date, base: str, quote: str) -> Decimal | None:
        self.asked.append((day, base, quote))
        return self.rate


class TestTradeFx:
    async def test_dollar_quotes_take_the_rate_of_their_day(self) -> None:
        service = FakeFx(D("0.9"))
        fx = TradeFx(service)
        assert await fx.resolve("USDT", datetime(2024, 1, 17, 12, tzinfo=UTC)) == ("USD", D("0.9"))
        assert service.asked == [(date(2024, 1, 17), "USD", "EUR")]

    @pytest.mark.parametrize("quote", ["EUR", "BTC", None, "XYZ"])
    async def test_euro_crypto_or_unknown_quotes_stay_in_euro(self, quote: str | None) -> None:
        assert await TradeFx(FakeFx(D("0.9"))).resolve(quote, datetime.now(UTC)) == ("EUR", None)

    async def test_without_rate_or_service_the_order_stays_in_euro(self) -> None:
        assert await TradeFx(FakeFx(None)).resolve("USD", datetime.now(UTC)) == ("EUR", None)
        assert await TradeFx(None).resolve("USD", datetime.now(UTC)) == ("EUR", None)


class TestMarketPrice:
    async def test_live_price_then_last_known_then_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        answers: list[PriceQuote | None] = [PriceQuote(price=D("100")), None, None]

        async def quote(symbol: str, kind: str) -> PriceQuote | None:
            return answers.pop(0)

        monkeypatch.setattr("app.domains.exchanges.sync.pricing.price_feed.quote", quote)
        assert await market_price("ETH", D("90")) == D("100")
        assert await market_price("ETH", D("90")) == D("90")
        assert await market_price("XYZ", None) == D("0")


class TestConvertDedup:
    def test_a_convert_already_seen_as_a_fiat_order_is_dropped(self) -> None:
        def order(order_id: str, qty: str, when: datetime) -> ExchangeFiatOrder:
            return ExchangeFiatOrder(
                order_id=order_id,
                crypto_symbol="BTC",
                fiat_currency="EUR",
                side="buy",
                crypto_amount=D(qty),
                fiat_amount=D("100"),
                price=D("1"),
                fee=D("0"),
                status="Completed",
                timestamp=when,
            )

        moment = datetime(2025, 3, 1, 12, tzinfo=UTC)
        fiat = [order("f", "0.0010", moment)]
        converts = [
            order("c1", "0.001", moment + timedelta(seconds=50)),
            order("c2", "0.001", moment + timedelta(hours=1)),
        ]
        assert [c.order_id for c in unseen_converts(converts, fiat)] == ["c2"]


def _key() -> APIKey:
    return APIKey(id=uuid4(), error_count=0, is_active=True, status=APIKeyStatus.ACTIVE)


def _http(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://exchange.test")
    return httpx.HTTPStatusError(str(status), request=request, response=httpx.Response(status, request=request))


class TestFailures:
    @pytest.mark.parametrize(
        ("exc", "status", "active"),
        [
            (_http(401), APIKeyStatus.EXPIRED, False),
            (_http(429), APIKeyStatus.RATE_LIMITED, True),
            (Exception("EAPI:Invalid key"), APIKeyStatus.EXPIRED, False),
            (Exception("panne"), APIKeyStatus.ERROR, True),
        ],
    )
    def test_classification(self, exc: Exception, status: APIKeyStatus, active: bool) -> None:
        key = _key()
        mark_failure(key, exc)
        assert (key.status, key.is_active, key.error_count) == (status, active, 1)

    def test_five_generic_failures_disable_the_key(self) -> None:
        key = _key()
        for _ in range(5):
            mark_failure(key, Exception("panne"))
        assert key.is_active is False
