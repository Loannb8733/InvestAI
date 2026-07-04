"""Characterization tests for the TWO FIFO cost-basis replays, pre-unification.

These pin TODAY's behaviour of:
  * ``MetricsService.get_portfolio_metrics``  (dashboard FIFO replay)
  * ``ReportService.compute_tax_2086``        (2086 tax FIFO replay)
  * ``ReportService._estimate_rebalancing_tax`` (simplified 3rd replay)

They are executable documentation for the refactor that will unify the
replays: every place the implementations DISAGREE is asserted with BOTH
values and tagged ``# DIVERGENCE #N``. Any refactor that changes one of
those numbers is a behaviour change that must be signed off explicitly.

Divergence index
----------------
#1 Conversion destination basis: metrics uses the RECORDED CONVERSION_IN
   price; tax carries the consumed source cost.
#2 Unmatched CONVERSION_OUT: metrics preserves the source layers (cost
   unchanged); tax consumes them AND emits a taxable cession.
#3 Fee in portfolio currency (EUR) on a USD trade: metrics adds the fee
   as-is; tax multiplies the EUR fee by the trade's conversion_rate.
#4 Fee in foreign currency (USD): metrics converts it at the LIVE forex
   rate and adds it post-FIFO (fee survives sells); tax bakes it into the
   BUY layer where it is consumed proportionally by sells.
#5 Transfer network fee (out 1.0 / in 0.995): metrics trims the burned
   qty from the basis; tax keeps the phantom qty and its cost.
#6 Unmatched TRANSFER_IN: metrics recovers a basis from the asset's
   avg_buy_price; tax books a zero-cost layer (full proceeds taxable).
#7 STAKING_REWARD with recorded price: metrics basis = market price at
   receipt; tax basis = zero.
#8 Rebalancing tax estimate ignores conversion_rate (raw tx-currency
   price as cost), unlike the metrics FIFO which applies FX.

Conventions copied from the existing goldens
(test_fin_cost_basis_golden.py / test_tax_2086_fx_golden.py):
  * price_service is mocked for metrics runs; compute_tax_2086 needs no
    mock (its portfolio_value comes from asset_price_history, which is
    empty in the test DB — pinned as such where it matters).
  * conversion_rate = EUR per 1 unit of the trade currency.
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from app.models.asset import Asset, AssetType
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction, TransactionType
from app.services.metrics_service import MetricsService
from app.services.report_service import RebalanceOrder, ReportService

TxType = TransactionType


# ── Fixture helpers (golden-file patterns) ──────────────────────────


def _fake_price_service(crypto_prices: dict[str, float], forex: dict[tuple[str, str], float]):
    """AsyncMock price service returning fixed current prices + forex rates."""
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


async def _make_portfolio(db_session, user, name="Characterization"):
    portfolio = Portfolio(user_id=user.id, name=name)
    db_session.add(portfolio)
    await db_session.commit()
    await db_session.refresh(portfolio)
    return portfolio


async def _make_asset(db_session, portfolio, *, symbol, qty, current_price, avg_buy_price=None, exchange="binance"):
    asset = Asset(
        portfolio_id=portfolio.id,
        symbol=symbol,
        asset_type=AssetType.CRYPTO,
        quantity=Decimal(str(qty)),
        avg_buy_price=Decimal(str(avg_buy_price if avg_buy_price is not None else current_price)),
        current_price=Decimal(str(current_price)),
        exchange=exchange,
    )
    db_session.add(asset)
    await db_session.commit()
    await db_session.refresh(asset)
    return asset


def _tx(
    asset,
    ttype,
    *,
    qty,
    price,
    when,
    currency="EUR",
    rate=None,
    fee=0,
    fee_currency=None,
    ext=None,
    notes=None,
    exchange=None,
):
    return Transaction(
        asset_id=asset.id,
        transaction_type=ttype,
        quantity=Decimal(str(qty)),
        price=Decimal(str(price)),
        fee=Decimal(str(fee)),
        fee_currency=fee_currency,
        currency=currency,
        conversion_rate=Decimal(str(rate)) if rate is not None else None,
        executed_at=when,
        exchange=exchange or asset.exchange,
        external_id=ext,
        notes=notes,
    )


def _dt(y, m, d, hh=12, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


def _asset_entry(result, symbol, exchange):
    for entry in result["assets"]:
        if entry["symbol"].upper() == symbol.upper() and (entry.get("exchange") or "") == exchange:
            return entry
    raise AssertionError(f"asset {symbol}@{exchange} not found in metrics result")


async def _metrics(db_session, portfolio, crypto_prices, forex=None, **kwargs):
    ps = _fake_price_service(crypto_prices, forex or {})
    with patch("app.services.metrics_service.price_service", ps):
        return await MetricsService().get_portfolio_metrics(db_session, str(portfolio.id), currency="EUR", **kwargs)


# ── Scenario 1 — multi-buy then partial sells (agreement) ───────────


@pytest.mark.asyncio
async def test_multibuy_partial_sells_metrics_and_tax_agree(db_session, regular_user):
    """3 BUYs at different prices/dates, SELL spanning 1.5 layers, then a
    second SELL consuming the tail of layer 2.

    Both replays agree on the FIFO math here; the test pins the agreement
    AND the holding-period split (oldest lot >= 730 days -> long_terme,
    second sell's oldest lot 639 days -> court_terme).
    """
    portfolio = await _make_portfolio(db_session, regular_user)
    btc = await _make_asset(db_session, portfolio, symbol="BTC", qty=1, current_price=40000)
    db_session.add(_tx(btc, TxType.BUY, qty=1, price=10000, when=_dt(2023, 1, 1), ext="s1b1"))
    db_session.add(_tx(btc, TxType.BUY, qty=1, price=20000, when=_dt(2024, 6, 1), ext="s1b2"))
    db_session.add(_tx(btc, TxType.BUY, qty=1, price=30000, when=_dt(2025, 6, 1), ext="s1b3"))
    # SELL #1 spans 1.5 layers: all of lot 1 (2023, >=730d) + half of lot 2.
    db_session.add(_tx(btc, TxType.SELL, qty=1.5, price=40000, when=_dt(2026, 3, 1), ext="s1s1"))
    # SELL #2 consumes the remaining 0.5 of lot 2 (2024-06-01, 639d -> court).
    db_session.add(_tx(btc, TxType.SELL, qty=0.5, price=40000, when=_dt(2026, 3, 2), ext="s1s2"))
    await db_session.commit()

    result = await _metrics(db_session, portfolio, {"BTC": 40000.0})

    # Remaining FIFO layers: 1 BTC @ 30000 (lot 3 only).
    assert result["total_invested"] == pytest.approx(30000.0, abs=1e-6)
    assert result["total_value"] == pytest.approx(40000.0, abs=1e-6)
    assert result["total_gain_loss"] == pytest.approx(10000.0, abs=1e-6)
    entry = _asset_entry(result, "BTC", "binance")
    assert entry["total_invested"] == pytest.approx(30000.0, abs=1e-6)
    # Displayed PRU is CUMP (fee-inclusive weighted average of all buys): 60000/3.
    assert entry["avg_buy_price"] == pytest.approx(20000.0, abs=1e-6)
    assert entry["breakeven_price"] == pytest.approx(30000.0, abs=0.01)

    summary = await ReportService().compute_tax_2086(db_session, str(regular_user.id), 2026)

    assert summary.nb_cessions == 2
    ev1, ev2 = summary.events

    # Event 1: cost_removed = 10000 + 0.5*20000 = 20000 (surfaced via
    # total_acquisition_cost = 60000 - 20000 = 40000). Same layers the
    # metrics replay consumed — the engines agree on plain BUY/SELL FIFO.
    assert ev1.quantity == pytest.approx(1.5, abs=1e-9)
    assert ev1.cession_price == pytest.approx(60000.0, abs=1e-6)
    assert ev1.total_acquisition_cost == pytest.approx(40000.0, abs=1e-6)
    # portfolio_value at cession = remaining 1.5 BTC * cession unit price.
    assert ev1.portfolio_value == pytest.approx(60000.0, abs=1e-6)
    assert ev1.acquisition_fraction == pytest.approx(40000.0, abs=1e-6)
    assert ev1.gain_loss == pytest.approx(20000.0, abs=1e-6)
    assert ev1.holding_period == "long_terme"  # oldest consumed lot: 2023-01-01

    assert ev2.cession_price == pytest.approx(20000.0, abs=1e-6)
    assert ev2.total_acquisition_cost == pytest.approx(30000.0, abs=1e-6)
    assert ev2.portfolio_value == pytest.approx(40000.0, abs=1e-6)
    assert ev2.acquisition_fraction == pytest.approx(15000.0, abs=1e-6)
    assert ev2.gain_loss == pytest.approx(5000.0, abs=1e-6)
    assert ev2.holding_period == "court_terme"  # oldest consumed lot: 2024-06-01 (639d)

    assert summary.total_cessions == pytest.approx(80000.0, abs=1e-6)
    assert summary.net_plus_value == pytest.approx(25000.0, abs=1e-6)
    assert summary.nb_court_terme == 1
    assert summary.nb_long_terme == 1
    assert summary.ir_12_8 == pytest.approx(3200.0, abs=1e-6)
    assert summary.ps_17_2 == pytest.approx(4300.0, abs=1e-6)
    assert summary.flat_tax_30 == pytest.approx(7500.0, abs=1e-6)

    # Cross-engine agreement: metrics' remaining basis == tax's remaining
    # total_acquisition_cost after the last cession.
    assert result["total_invested"] == pytest.approx(ev2.total_acquisition_cost, abs=1e-6)


# ── Scenario 2 — matched conversion chain (Kraken format) ───────────


@pytest.mark.asyncio
async def test_conversion_chain_dest_basis_diverges(db_session, regular_user):
    """BUY BTC -> CONVERSION_OUT BTC / CONVERSION_IN ETH matched via the
    Kraken notes format (trade_id:convert_sell_X / convert_buy_X), then a
    partial SELL of the destination ETH to surface both remaining bases.
    """
    portfolio = await _make_portfolio(db_session, regular_user)
    # BTC fully converted away -> qty 0 (row excluded from metrics output,
    # but its transactions still feed the FIFO replay).
    btc = await _make_asset(db_session, portfolio, symbol="BTC", qty=0, current_price=25000, exchange="kraken")
    eth = await _make_asset(db_session, portfolio, symbol="ETH", qty=5, current_price=3000, exchange="kraken")

    db_session.add(_tx(btc, TxType.BUY, qty=1, price=20000, when=_dt(2024, 1, 1), ext="s2b1"))
    db_session.add(
        _tx(
            btc,
            TxType.CONVERSION_OUT,
            qty=1,
            price=25000,
            when=_dt(2026, 2, 1, 10, 0),
            ext="convert_sell_X1",
            notes="trade_id:convert_sell_X1",
        )
    )
    db_session.add(
        _tx(
            eth,
            TxType.CONVERSION_IN,
            qty=10,
            price=2600,  # recorded dest market price at conversion (EUR)
            when=_dt(2026, 2, 1, 10, 1),
            ext="convert_buy_X1",
            notes="trade_id:convert_buy_X1",
        )
    )
    db_session.add(_tx(eth, TxType.SELL, qty=5, price=3000, when=_dt(2026, 3, 1), ext="s2s1"))
    await db_session.commit()

    result = await _metrics(db_session, portfolio, {"ETH": 3000.0})

    # DIVERGENCE #1: conversion dest basis.
    # metrics: dest layer priced at the RECORDED CONVERSION_IN price
    #   (10 ETH @ 2600) -> after selling 5, remaining basis = 5 * 2600 = 13000.
    assert result["total_invested"] == pytest.approx(13000.0, abs=1e-6)
    assert result["total_value"] == pytest.approx(15000.0, abs=1e-6)
    assert result["total_gain_loss"] == pytest.approx(2000.0, abs=1e-6)

    summary = await ReportService().compute_tax_2086(db_session, str(regular_user.id), 2026)
    assert summary.nb_cessions == 2
    ev_conv, ev_sell = summary.events

    # The CONVERSION_OUT is itself a taxable cession in the tax replay.
    assert ev_conv.symbol == "BTC"
    assert ev_conv.event_type == "conversion_out"
    assert ev_conv.cession_price == pytest.approx(25000.0, abs=1e-6)
    # Consumed source cost (20000) re-enters as the dest basis:
    # total_acquisition_cost = 20000 - 20000 + 20000 = 20000.
    assert ev_conv.total_acquisition_cost == pytest.approx(20000.0, abs=1e-6)
    # No asset_price_history rows and the destination ETH is booked by the
    # LATER CONVERSION_IN tx -> portfolio_value 0 at the CONVERSION_OUT,
    # so acquisition_fraction collapses to 0 and gain = full cession.
    assert ev_conv.portfolio_value == pytest.approx(0.0, abs=1e-9)
    assert ev_conv.acquisition_fraction == pytest.approx(0.0, abs=1e-9)
    assert ev_conv.gain_loss == pytest.approx(25000.0, abs=1e-6)
    assert ev_conv.holding_period == "long_terme"  # lot 2024-01-01, 762d

    # DIVERGENCE #1 (tax side): dest layer carries the consumed SOURCE cost
    #   (10 ETH @ 20000/10 = 2000) -> after selling 5, remaining acquisition
    #   cost = 5 * 2000 = 10000 (vs metrics 13000 above).
    assert ev_sell.symbol == "ETH"
    assert ev_sell.cession_price == pytest.approx(15000.0, abs=1e-6)
    assert ev_sell.total_acquisition_cost == pytest.approx(10000.0, abs=1e-6)
    assert ev_sell.portfolio_value == pytest.approx(15000.0, abs=1e-6)
    assert ev_sell.acquisition_fraction == pytest.approx(10000.0, abs=1e-6)
    assert ev_sell.gain_loss == pytest.approx(5000.0, abs=1e-6)
    assert ev_sell.holding_period == "court_terme"  # dest lot acquired at conversion


# ── Scenario 3 — unmatched CONVERSION_OUT ───────────────────────────


@pytest.mark.asyncio
async def test_unmatched_conversion_out_diverges(db_session, regular_user):
    """CONVERSION_OUT with no matching CONVERSION_IN anywhere."""
    portfolio = await _make_portfolio(db_session, regular_user)
    btc = await _make_asset(
        db_session, portfolio, symbol="BTC", qty=0, current_price=25000, avg_buy_price=20000, exchange="kraken"
    )
    db_session.add(_tx(btc, TxType.BUY, qty=1, price=20000, when=_dt(2024, 1, 1), ext="s3b1"))
    db_session.add(
        _tx(
            btc,
            TxType.CONVERSION_OUT,
            qty=1,
            price=25000,
            when=_dt(2026, 2, 1),
            ext="convert_sell_ORPHan",
            notes="trade_id:convert_sell_ORPHan",
        )
    )
    await db_session.commit()

    # include_zero_quantity so the qty-0 BTC row is reported at all.
    result = await _metrics(db_session, portfolio, {"BTC": 25000.0}, include_zero_quantity=True)

    # DIVERGENCE #2: metrics does NOT consume the source layers on an
    # unmatched CONVERSION_OUT — the 20000 cost basis is preserved on a
    # position whose quantity is 0 (latent G/L shows -20000).
    assert result["total_invested"] == pytest.approx(20000.0, abs=1e-6)
    assert result["total_value"] == pytest.approx(0.0, abs=1e-9)
    assert result["total_gain_loss"] == pytest.approx(-20000.0, abs=1e-6)

    summary = await ReportService().compute_tax_2086(db_session, str(regular_user.id), 2026)

    # DIVERGENCE #2 (tax side): tax consumes the layers (acquisition cost
    # drops to 0) AND emits a taxable cession for the full 25000.
    assert summary.nb_cessions == 1
    ev = summary.events[0]
    assert ev.event_type == "conversion_out"
    assert ev.cession_price == pytest.approx(25000.0, abs=1e-6)
    assert ev.total_acquisition_cost == pytest.approx(0.0, abs=1e-9)
    assert ev.portfolio_value == pytest.approx(0.0, abs=1e-9)  # nothing held after
    assert ev.acquisition_fraction == pytest.approx(0.0, abs=1e-9)
    assert ev.gain_loss == pytest.approx(25000.0, abs=1e-6)
    assert ev.holding_period == "long_terme"


# ── Scenario 4 — FX conversion & fee-currency semantics ─────────────


@pytest.mark.asyncio
async def test_usd_buy_sell_no_fee_agreement(db_session, regular_user):
    """USD-quoted BUY+SELL with conversion_rate: base FX path agrees."""
    portfolio = await _make_portfolio(db_session, regular_user)
    btc = await _make_asset(db_session, portfolio, symbol="BTC", qty=1, current_price=138)
    db_session.add(
        _tx(btc, TxType.BUY, qty=2, price=100, currency="USD", rate="0.92", when=_dt(2024, 1, 15), ext="s4b")
    )
    db_session.add(
        _tx(btc, TxType.SELL, qty=1, price=150, currency="USD", rate="0.95", when=_dt(2026, 6, 15), ext="s4s")
    )
    await db_session.commit()

    result = await _metrics(db_session, portfolio, {"BTC": 138.0}, forex={("USD", "EUR"): 0.92})

    # Remaining layer: 1 BTC @ 100 USD * 0.92 = 92 EUR.
    assert result["total_invested"] == pytest.approx(92.0, abs=1e-6)
    assert result["total_value"] == pytest.approx(138.0, abs=1e-6)

    summary = await ReportService().compute_tax_2086(db_session, str(regular_user.id), 2026)
    assert summary.nb_cessions == 1
    ev = summary.events[0]
    assert ev.cession_price == pytest.approx(142.5, abs=1e-6)  # 150 USD * 0.95
    assert ev.total_acquisition_cost == pytest.approx(92.0, abs=1e-6)  # agrees with metrics
    assert ev.portfolio_value == pytest.approx(142.5, abs=1e-6)
    assert ev.acquisition_fraction == pytest.approx(92.0, abs=1e-6)
    assert ev.gain_loss == pytest.approx(50.5, abs=1e-6)
    assert ev.holding_period == "long_terme"  # 2024-01-15 -> 2026-06-15 (>=730d)


@pytest.mark.asyncio
async def test_eur_fee_on_usd_trade_diverges(db_session, regular_user):
    """BUY 2 BTC @ 100 USD (rate 0.92) with a 10 EUR fee (fee_currency=EUR),
    then SELL 1."""
    portfolio = await _make_portfolio(db_session, regular_user)
    btc = await _make_asset(db_session, portfolio, symbol="BTC", qty=1, current_price=138)
    db_session.add(
        _tx(
            btc,
            TxType.BUY,
            qty=2,
            price=100,
            currency="USD",
            rate="0.92",
            fee=10,
            fee_currency="EUR",
            when=_dt(2024, 1, 15),
            ext="s4eb",
        )
    )
    db_session.add(
        _tx(btc, TxType.SELL, qty=1, price=150, currency="USD", rate="0.95", when=_dt(2026, 6, 15), ext="s4es")
    )
    await db_session.commit()

    result = await _metrics(db_session, portfolio, {"BTC": 138.0}, forex={("USD", "EUR"): 0.92})

    # DIVERGENCE #3: fee currency semantics (EUR fee on a USD trade).
    # metrics: fee_currency == portfolio currency -> fee added AS-IS.
    #   Layer = (2*100*0.92 + 10)/2 = 97/unit -> remaining 1 unit = 97.
    assert result["total_invested"] == pytest.approx(97.0, abs=1e-6)

    summary = await ReportService().compute_tax_2086(db_session, str(regular_user.id), 2026)
    ev = summary.events[0]
    # DIVERGENCE #3 (tax side): tax IGNORES fee_currency and multiplies the
    # EUR fee by conversion_rate anyway: fee = 10 * 0.92 = 9.2.
    #   Layer = (184 + 9.2)/2 = 96.6/unit -> remaining acquisition = 96.6.
    assert ev.total_acquisition_cost == pytest.approx(96.6, abs=1e-6)
    assert ev.cession_price == pytest.approx(142.5, abs=1e-6)
    assert ev.acquisition_fraction == pytest.approx(96.6, abs=1e-6)
    assert ev.gain_loss == pytest.approx(45.9, abs=1e-6)


@pytest.mark.asyncio
async def test_usd_fee_on_usd_trade_diverges(db_session, regular_user):
    """Same trade but the 10 fee is denominated in USD (fee_currency=USD)."""
    portfolio = await _make_portfolio(db_session, regular_user)
    btc = await _make_asset(db_session, portfolio, symbol="BTC", qty=1, current_price=138)
    db_session.add(
        _tx(
            btc,
            TxType.BUY,
            qty=2,
            price=100,
            currency="USD",
            rate="0.92",
            fee=10,
            fee_currency="USD",
            when=_dt(2024, 1, 15),
            ext="s4ub",
        )
    )
    db_session.add(
        _tx(btc, TxType.SELL, qty=1, price=150, currency="USD", rate="0.95", when=_dt(2026, 6, 15), ext="s4us")
    )
    await db_session.commit()

    result = await _metrics(db_session, portfolio, {"BTC": 138.0}, forex={("USD", "EUR"): 0.92})

    # DIVERGENCE #4: foreign-currency fee.
    # metrics: fee converted at the LIVE forex rate (mocked 0.92 -> 9.2 EUR)
    # and added POST-FIFO, so the sell does not consume any of it:
    #   remaining = 1 * 92 + 9.2 = 101.2.
    assert result["total_invested"] == pytest.approx(101.2, abs=1e-6)

    summary = await ReportService().compute_tax_2086(db_session, str(regular_user.id), 2026)
    ev = summary.events[0]
    # DIVERGENCE #4 (tax side): tax bakes fee*conversion_rate (10*0.92=9.2)
    # into the BUY layer; the sell consumes half of it proportionally:
    #   remaining acquisition = (184 + 9.2)/2 = 96.6  (vs metrics 101.2).
    assert ev.total_acquisition_cost == pytest.approx(96.6, abs=1e-6)
    assert ev.gain_loss == pytest.approx(45.9, abs=1e-6)


# ── Scenario 5 — transfers ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_matched_transfer_exact_qty_agreement(db_session, regular_user):
    """TRANSFER_OUT (binance) -> TRANSFER_IN (kraken) with exact quantity:
    both replays carry the basis unchanged."""
    portfolio = await _make_portfolio(db_session, regular_user)
    btc_bin = await _make_asset(db_session, portfolio, symbol="BTC", qty=1, current_price=30000, exchange="binance")
    btc_krk = await _make_asset(db_session, portfolio, symbol="BTC", qty=0.5, current_price=30000, exchange="kraken")

    db_session.add(_tx(btc_bin, TxType.BUY, qty=2, price=20000, when=_dt(2024, 1, 1), ext="s5ab"))
    db_session.add(_tx(btc_bin, TxType.TRANSFER_OUT, qty=1, price=0, when=_dt(2025, 1, 1), ext="s5ao"))
    db_session.add(_tx(btc_krk, TxType.TRANSFER_IN, qty=1, price=0, when=_dt(2025, 1, 2), ext="s5ai"))
    db_session.add(_tx(btc_krk, TxType.SELL, qty=0.5, price=30000, when=_dt(2026, 6, 1), ext="s5as"))
    await db_session.commit()

    result = await _metrics(db_session, portfolio, {"BTC": 30000.0})

    # binance keeps 1 @ 20000; kraken received 1 @ 20000 and sold 0.5.
    assert result["total_invested"] == pytest.approx(30000.0, abs=1e-6)
    assert _asset_entry(result, "BTC", "binance")["total_invested"] == pytest.approx(20000.0, abs=1e-6)
    assert _asset_entry(result, "BTC", "kraken")["total_invested"] == pytest.approx(10000.0, abs=1e-6)

    summary = await ReportService().compute_tax_2086(db_session, str(regular_user.id), 2026)
    assert summary.nb_cessions == 1
    ev = summary.events[0]
    assert ev.cession_price == pytest.approx(15000.0, abs=1e-6)
    # Transfers do not change acquisition cost: 40000 - 0.5*20000 = 30000
    # — identical to the metrics remaining basis (agreement).
    assert ev.total_acquisition_cost == pytest.approx(30000.0, abs=1e-6)
    assert ev.portfolio_value == pytest.approx(45000.0, abs=1e-6)  # 1.5 BTC * 30000
    assert ev.acquisition_fraction == pytest.approx(10000.0, abs=1e-6)
    assert ev.gain_loss == pytest.approx(5000.0, abs=1e-6)
    assert ev.holding_period == "long_terme"  # layer date travels with the transfer

    assert result["total_invested"] == pytest.approx(ev.total_acquisition_cost, abs=1e-6)


@pytest.mark.asyncio
async def test_transfer_network_fee_diverges(db_session, regular_user):
    """TRANSFER_OUT 1.0 but TRANSFER_IN only 0.995 (network fee burned)."""
    portfolio = await _make_portfolio(db_session, regular_user)
    btc_bin = await _make_asset(db_session, portfolio, symbol="BTC", qty=1, current_price=30000, exchange="binance")
    btc_krk = await _make_asset(db_session, portfolio, symbol="BTC", qty=0.495, current_price=30000, exchange="kraken")

    db_session.add(_tx(btc_bin, TxType.BUY, qty=2, price=20000, when=_dt(2024, 1, 1), ext="s5bb"))
    db_session.add(_tx(btc_bin, TxType.TRANSFER_OUT, qty=1.0, price=0, when=_dt(2025, 1, 1), ext="s5bo"))
    db_session.add(_tx(btc_krk, TxType.TRANSFER_IN, qty=0.995, price=0, when=_dt(2025, 1, 2), ext="s5bi"))
    db_session.add(_tx(btc_krk, TxType.SELL, qty=0.5, price=30000, when=_dt(2026, 6, 1), ext="s5bs"))
    await db_session.commit()

    result = await _metrics(db_session, portfolio, {"BTC": 30000.0})

    # DIVERGENCE #5: network-fee transfer.
    # metrics: trims the burned 0.005 BTC from the basis on arrival
    #   (kraken gets 0.995 @ 20000 = 19900; after selling 0.5 -> 9900).
    #   Total = 20000 (binance) + 9900 = 29900.
    assert result["total_invested"] == pytest.approx(29900.0, abs=1e-6)
    assert _asset_entry(result, "BTC", "kraken")["total_invested"] == pytest.approx(9900.0, abs=1e-6)

    summary = await ReportService().compute_tax_2086(db_session, str(regular_user.id), 2026)
    ev = summary.events[0]
    # DIVERGENCE #5 (tax side): tax appends the FULL transit (1.0 @ 20000 —
    # phantom 0.005 qty + 100 EUR of cost kept). After selling 0.5:
    #   total_acquisition_cost = 40000 - 10000 = 30000 (vs metrics 29900).
    assert ev.total_acquisition_cost == pytest.approx(30000.0, abs=1e-6)
    assert ev.cession_price == pytest.approx(15000.0, abs=1e-6)
    # holdings replay: 2 - 1 + 0.995 - 0.5 = 1.495 BTC * 30000 = 44850.
    assert ev.portfolio_value == pytest.approx(44850.0, abs=1e-6)
    assert ev.acquisition_fraction == pytest.approx(10033.444816, abs=1e-3)
    assert ev.gain_loss == pytest.approx(4966.555184, abs=1e-3)


@pytest.mark.asyncio
async def test_unmatched_transfer_in_diverges(db_session, regular_user):
    """Unmatched TRANSFER_IN (no TRANSFER_OUT anywhere) on an asset row
    that carries an avg_buy_price."""
    portfolio = await _make_portfolio(db_session, regular_user)
    btc = await _make_asset(
        db_session, portfolio, symbol="BTC", qty=1, current_price=100, avg_buy_price=80, exchange="kraken"
    )
    db_session.add(_tx(btc, TxType.TRANSFER_IN, qty=2, price=0, when=_dt(2024, 1, 1), ext="s5ci"))
    db_session.add(_tx(btc, TxType.SELL, qty=1, price=100, when=_dt(2026, 6, 1), ext="s5cs"))
    await db_session.commit()

    result = await _metrics(db_session, portfolio, {"BTC": 100.0})

    # DIVERGENCE #6: unmatched TRANSFER_IN cost recovery.
    # metrics (F-06): recovers the asset's avg_buy_price as the layer cost
    #   (2 @ 80); after selling 1 -> remaining basis 80, latent gain 20.
    assert result["total_invested"] == pytest.approx(80.0, abs=1e-6)
    assert result["total_value"] == pytest.approx(100.0, abs=1e-6)
    assert result["total_gain_loss"] == pytest.approx(20.0, abs=1e-6)

    summary = await ReportService().compute_tax_2086(db_session, str(regular_user.id), 2026)
    assert summary.nb_cessions == 1
    ev = summary.events[0]
    # DIVERGENCE #6 (tax side): tax books the unmatched TRANSFER_IN at ZERO
    # cost — the entire cession is taxed as gain (100 vs the economic 20).
    assert ev.cession_price == pytest.approx(100.0, abs=1e-6)
    assert ev.total_acquisition_cost == pytest.approx(0.0, abs=1e-9)
    assert ev.portfolio_value == pytest.approx(100.0, abs=1e-6)
    assert ev.acquisition_fraction == pytest.approx(0.0, abs=1e-9)
    assert ev.gain_loss == pytest.approx(100.0, abs=1e-6)
    assert ev.holding_period == "long_terme"


# ── Scenario 6 — staking reward basis ───────────────────────────────


@pytest.mark.asyncio
async def test_staking_reward_basis_diverges(db_session, regular_user):
    """STAKING_REWARD with a recorded market price at receipt, then SELL."""
    portfolio = await _make_portfolio(db_session, regular_user)
    eth = await _make_asset(db_session, portfolio, symbol="ETH", qty=1, current_price=1500, exchange="kraken")
    db_session.add(_tx(eth, TxType.STAKING_REWARD, qty=2, price=1000, when=_dt(2024, 1, 1), ext="s6r"))
    db_session.add(_tx(eth, TxType.SELL, qty=1, price=1500, when=_dt(2026, 6, 1), ext="s6s"))
    await db_session.commit()

    result = await _metrics(db_session, portfolio, {"ETH": 1500.0})

    # DIVERGENCE #7: staking-reward cost basis.
    # metrics: layer priced at the recorded market value at receipt
    #   (2 @ 1000); after selling 1 -> remaining basis 1000, latent gain 500.
    assert result["total_invested"] == pytest.approx(1000.0, abs=1e-6)
    assert result["total_gain_loss"] == pytest.approx(500.0, abs=1e-6)

    summary = await ReportService().compute_tax_2086(db_session, str(regular_user.id), 2026)
    assert summary.nb_cessions == 1
    ev = summary.events[0]
    # DIVERGENCE #7 (tax side): tax books rewards at ZERO cost — the full
    # 1500 cession is gain (vs the metrics-implied realized 500).
    assert ev.cession_price == pytest.approx(1500.0, abs=1e-6)
    assert ev.total_acquisition_cost == pytest.approx(0.0, abs=1e-9)
    assert ev.acquisition_fraction == pytest.approx(0.0, abs=1e-9)
    assert ev.gain_loss == pytest.approx(1500.0, abs=1e-6)
    assert ev.holding_period == "long_terme"  # reward layer carries its receipt date


# ── Scenario 7 — _estimate_rebalancing_tax (previously untested) ────


@pytest.mark.asyncio
async def test_estimate_rebalancing_tax_two_assets(db_session, regular_user):
    """Direct call with a known 2-asset FIFO state and one sell order.

    BTC: 1 @ 20000 (now 30000) — full 30000 sold  -> gain 10000
    ETH: 5 @ 1000  (now 2000)  — 5000 EUR sold (2.5 units) -> gain 2500
    estimated_gain = 12500, estimated_tax = 30% PFU = 3750.
    """
    portfolio = await _make_portfolio(db_session, regular_user)
    btc = await _make_asset(db_session, portfolio, symbol="BTC", qty=1, current_price=30000)
    eth = await _make_asset(db_session, portfolio, symbol="ETH", qty=5, current_price=2000)
    db_session.add(_tx(btc, TxType.BUY, qty=1, price=20000, when=_dt(2024, 1, 1), ext="s7b1"))
    db_session.add(_tx(eth, TxType.BUY, qty=5, price=1000, when=_dt(2024, 2, 1), ext="s7b2"))
    await db_session.commit()

    order = RebalanceOrder(
        category="L1",
        action="sell",
        amount_eur=35000.0,
        current_pct=100.0,
        target_pct=50.0,
        drift_pct=50.0,
    )
    class_assets = {
        "L1": [
            {"symbol": "BTC", "current_price": 30000.0, "value": 30000.0},
            {"symbol": "ETH", "current_price": 2000.0, "value": 10000.0},
        ]
    }

    await ReportService()._estimate_rebalancing_tax(db_session, str(regular_user.id), [order], class_assets, "EUR")

    assert order.estimated_gain == pytest.approx(12500.0, abs=1e-6)
    assert order.estimated_tax == pytest.approx(3750.0, abs=1e-6)


@pytest.mark.asyncio
async def test_estimate_rebalancing_tax_ignores_conversion_rate(db_session, regular_user):
    """BUY 1 BTC @ 100 USD with conversion_rate 0.92.

    The rebalancing replay reads tx.price RAW (100), ignoring the FX rate,
    so the estimated gain at a 150 EUR current price is 50 — while the
    metrics FIFO basis for the same buy would be 92 EUR (gain 58).
    """
    portfolio = await _make_portfolio(db_session, regular_user)
    btc = await _make_asset(db_session, portfolio, symbol="BTC", qty=1, current_price=150)
    db_session.add(_tx(btc, TxType.BUY, qty=1, price=100, currency="USD", rate="0.92", when=_dt(2024, 1, 1), ext="s7c"))
    await db_session.commit()

    order = RebalanceOrder(
        category="L1",
        action="sell",
        amount_eur=150.0,
        current_pct=100.0,
        target_pct=0.0,
        drift_pct=100.0,
    )
    class_assets = {"L1": [{"symbol": "BTC", "current_price": 150.0, "value": 150.0}]}

    await ReportService()._estimate_rebalancing_tax(db_session, str(regular_user.id), [order], class_assets, "EUR")

    # DIVERGENCE #8: rebalancing estimate ignores conversion_rate — basis
    # is the raw 100 (tx currency), not the 92 EUR the metrics FIFO books.
    assert order.estimated_gain == pytest.approx(50.0, abs=1e-6)
    assert order.estimated_tax == pytest.approx(15.0, abs=1e-6)

    # Cross-check the metrics side of the same trade for the record.
    result = await _metrics(db_session, portfolio, {"BTC": 150.0}, forex={("USD", "EUR"): 0.92})
    assert result["total_invested"] == pytest.approx(92.0, abs=1e-6)  # DIVERGENCE #8 (metrics side)
    assert result["total_gain_loss"] == pytest.approx(58.0, abs=1e-6)
