"""Golden numeric tests for multi-currency cost basis (FIN-01 / FIN-TEST).

These exercise the REAL FIFO engine in ``MetricsService.get_portfolio_metrics`` against
the test DB, with the price service mocked so only the cost-basis math is under test.

The convention under test (see metrics_service FIFO layer contract):
    invested (EUR) = Σ qty * price_in_tx_ccy * conversion_rate
where ``conversion_rate`` = EUR per 1 unit of the trade currency (≈0.92 for USD).

``test_usd_buy_cost_basis_converted_to_eur`` is the canary: a 100 USD buy with
rate 0.92 must yield 92 EUR invested, NOT 100. If the BUY layer forgets to apply
``fx_rate`` (the bug FIN-01 surfaced), invested comes out at 100 and this test fails.
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from app.models.asset import Asset, AssetType
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction, TransactionType
from app.services.metrics_service import MetricsService


def _fake_price_service(crypto_prices: dict[str, float], forex: dict[tuple[str, str], float]):
    """Build an AsyncMock price service returning fixed current prices + forex rates."""
    ps = AsyncMock()

    async def _get_multiple_crypto_prices(symbols, ccy):
        return {
            s.upper(): {"price": crypto_prices[s.upper()], "change_percent_24h": 0}
            for s in symbols
            if s.upper() in crypto_prices
        }

    async def _get_forex_rate(from_ccy, to_ccy):
        return forex.get((from_ccy.upper(), to_ccy.upper()), 1.0)

    ps.get_multiple_crypto_prices = AsyncMock(side_effect=_get_multiple_crypto_prices)
    ps.get_forex_rate = AsyncMock(side_effect=_get_forex_rate)
    return ps


async def _make_portfolio(db_session, user):
    portfolio = Portfolio(user_id=user.id, name="Golden")
    db_session.add(portfolio)
    await db_session.commit()
    await db_session.refresh(portfolio)
    return portfolio


async def _make_asset(db_session, portfolio, *, symbol, qty, current_price, exchange="binance"):
    asset = Asset(
        portfolio_id=portfolio.id,
        symbol=symbol,
        asset_type=AssetType.CRYPTO,
        quantity=Decimal(str(qty)),
        avg_buy_price=Decimal(str(current_price)),
        current_price=Decimal(str(current_price)),
        exchange=exchange,
    )
    db_session.add(asset)
    await db_session.commit()
    await db_session.refresh(asset)
    return asset


def _buy(asset, *, qty, price, currency, rate, ext, when=datetime(2024, 1, 15, tzinfo=timezone.utc)):
    return Transaction(
        asset_id=asset.id,
        transaction_type=TransactionType.BUY,
        quantity=Decimal(str(qty)),
        price=Decimal(str(price)),
        fee=Decimal("0"),
        currency=currency,
        conversion_rate=Decimal(str(rate)) if rate is not None else None,
        executed_at=when,
        exchange=asset.exchange,
        external_id=ext,
    )


def _sell(asset, *, qty, price, currency, rate, ext, when=datetime(2024, 6, 15, tzinfo=timezone.utc)):
    return Transaction(
        asset_id=asset.id,
        transaction_type=TransactionType.SELL,
        quantity=Decimal(str(qty)),
        price=Decimal(str(price)),
        fee=Decimal("0"),
        currency=currency,
        conversion_rate=Decimal(str(rate)) if rate is not None else None,
        executed_at=when,
        exchange=asset.exchange,
        external_id=ext,
    )


def _transfer_in(asset, *, qty, price=0, ext, when=datetime(2024, 3, 1, tzinfo=timezone.utc)):
    return Transaction(
        asset_id=asset.id,
        transaction_type=TransactionType.TRANSFER_IN,
        quantity=Decimal(str(qty)),
        price=Decimal(str(price)),
        fee=Decimal("0"),
        currency="EUR",
        conversion_rate=None,
        executed_at=when,
        exchange=asset.exchange,
        external_id=ext,
    )


@pytest.mark.asyncio
async def test_usd_buy_cost_basis_converted_to_eur(db_session, regular_user):
    """1 BTC bought at 100 USD (rate 0.92) -> 92 EUR invested, current value 100 EUR."""
    portfolio = await _make_portfolio(db_session, regular_user)
    btc = await _make_asset(db_session, portfolio, symbol="BTC", qty=1, current_price=100)
    db_session.add(_buy(btc, qty=1, price=100, currency="USD", rate="0.92", ext="usd1"))
    await db_session.commit()

    ps = _fake_price_service({"BTC": 100.0}, {("USD", "EUR"): 0.92})
    with patch("app.services.metrics_service.price_service", ps):
        result = await MetricsService().get_portfolio_metrics(db_session, str(portfolio.id), currency="EUR")

    assert result["total_invested"] == pytest.approx(92.0, abs=0.01)
    assert result["total_value"] == pytest.approx(100.0, abs=0.01)
    assert result["total_gain_loss"] == pytest.approx(8.0, abs=0.01)


@pytest.mark.asyncio
async def test_eur_buy_no_conversion_is_unchanged(db_session, regular_user):
    """EUR buy (conversion_rate None -> fx=1) must keep invested == price. No regression."""
    portfolio = await _make_portfolio(db_session, regular_user)
    btc = await _make_asset(db_session, portfolio, symbol="BTC", qty=1, current_price=120)
    db_session.add(_buy(btc, qty=1, price=100, currency="EUR", rate=None, ext="eur1"))
    await db_session.commit()

    ps = _fake_price_service({"BTC": 120.0}, {})
    with patch("app.services.metrics_service.price_service", ps):
        result = await MetricsService().get_portfolio_metrics(db_session, str(portfolio.id), currency="EUR")

    assert result["total_invested"] == pytest.approx(100.0, abs=0.01)
    assert result["total_value"] == pytest.approx(120.0, abs=0.01)
    assert result["total_gain_loss"] == pytest.approx(20.0, abs=0.01)


@pytest.mark.asyncio
async def test_mixed_currency_portfolio_aggregates_in_eur(db_session, regular_user):
    """USD-quoted + EUR-quoted holdings sum correctly in EUR."""
    portfolio = await _make_portfolio(db_session, regular_user)
    btc = await _make_asset(db_session, portfolio, symbol="BTC", qty=1, current_price=100)
    eth = await _make_asset(db_session, portfolio, symbol="ETH", qty=2, current_price=50)
    db_session.add(_buy(btc, qty=1, price=100, currency="USD", rate="0.92", ext="m_usd"))
    db_session.add(_buy(eth, qty=2, price=40, currency="EUR", rate=None, ext="m_eur"))
    await db_session.commit()

    ps = _fake_price_service({"BTC": 100.0, "ETH": 50.0}, {("USD", "EUR"): 0.92})
    with patch("app.services.metrics_service.price_service", ps):
        result = await MetricsService().get_portfolio_metrics(db_session, str(portfolio.id), currency="EUR")

    # BTC invested 92 EUR + ETH invested 80 EUR = 172 ; value 100 + 100 = 200.
    assert result["total_invested"] == pytest.approx(172.0, abs=0.01)
    assert result["total_value"] == pytest.approx(200.0, abs=0.01)
    assert result["total_gain_loss"] == pytest.approx(28.0, abs=0.01)


@pytest.mark.asyncio
async def test_usd_sell_realized_gain_converted_to_eur(db_session, regular_user):
    """Realized P&L must be EUR-denominated.

    Buy 1 BTC @ 100 USD (rate 0.92) -> 92 EUR invested.
    Sell 1 BTC @ 150 USD (rate 0.95) -> 142.5 EUR proceeds.
    Realized gain = 142.5 - 92 = 50.5 EUR.

    Without the FX fix in get_portfolio_history both sides stay in USD and the
    realized gain comes out at 50 (USD mislabelled EUR), so this test fails.
    """
    portfolio = await _make_portfolio(db_session, regular_user)
    btc = await _make_asset(db_session, portfolio, symbol="BTC", qty=0, current_price=150)
    db_session.add(_buy(btc, qty=1, price=100, currency="USD", rate="0.92", ext="s_buy"))
    db_session.add(_sell(btc, qty=1, price=150, currency="USD", rate="0.95", ext="s_sell"))
    await db_session.commit()

    result = await MetricsService().get_portfolio_history(db_session, str(portfolio.id), currency="EUR")

    assert result["total_invested_all_time"] == pytest.approx(92.0, abs=0.01)
    assert result["realized_gains"] == pytest.approx(50.5, abs=0.01)


@pytest.mark.asyncio
async def test_eur_sell_realized_gain_unchanged(db_session, regular_user):
    """EUR buy+sell (rate None -> fx=1) keeps realized P&L untouched. No regression."""
    portfolio = await _make_portfolio(db_session, regular_user)
    btc = await _make_asset(db_session, portfolio, symbol="BTC", qty=0, current_price=150)
    db_session.add(_buy(btc, qty=1, price=100, currency="EUR", rate=None, ext="se_buy"))
    db_session.add(_sell(btc, qty=1, price=150, currency="EUR", rate=None, ext="se_sell"))
    await db_session.commit()

    result = await MetricsService().get_portfolio_history(db_session, str(portfolio.id), currency="EUR")

    assert result["total_invested_all_time"] == pytest.approx(100.0, abs=0.01)
    assert result["realized_gains"] == pytest.approx(50.0, abs=0.01)


@pytest.mark.asyncio
async def test_unmatched_transfer_in_uses_avg_buy_price_not_zero(db_session, regular_user):
    """FIN-03 / F-06: an unmatched, zero-price TRANSFER_IN must recover a cost basis
    from the asset's avg_buy_price instead of landing at zero cost.

    Asset avg_buy_price = 80 EUR, current price = 100 EUR, 1 unit received via an
    external transfer with no price and no matching TRANSFER_OUT.
    Expected: invested 80 (not 0), value 100, gain 20 (not a phantom 100).
    """
    portfolio = await _make_portfolio(db_session, regular_user)
    # avg_buy_price carried by the asset row is the recovery proxy.
    btc = await _make_asset(db_session, portfolio, symbol="BTC", qty=1, current_price=100)
    btc.avg_buy_price = Decimal("80")
    await db_session.commit()
    db_session.add(_transfer_in(btc, qty=1, price=0, ext="ti_unmatched"))
    await db_session.commit()

    ps = _fake_price_service({"BTC": 100.0}, {})
    with patch("app.services.metrics_service.price_service", ps):
        result = await MetricsService().get_portfolio_metrics(db_session, str(portfolio.id), currency="EUR")

    assert result["total_invested"] == pytest.approx(80.0, abs=0.01)
    assert result["total_value"] == pytest.approx(100.0, abs=0.01)
    assert result["total_gain_loss"] == pytest.approx(20.0, abs=0.01)
