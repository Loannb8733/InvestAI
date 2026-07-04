"""Pure unit tests for the unified FIFO replay engine (no DB).

Each ReplayConfig knob is exercised in both positions, pinning the exact
behaviour the two legacy replays (metrics_service / report_service tax 2086)
exhibited before unification.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.models.transaction import TransactionType as TxType
from app.services.fifo_replay import (
    ConversionDestBasis,
    FeeHandling,
    ReplayConfig,
    RewardBasis,
    UnmatchedConversionOutPolicy,
    UnmatchedTransferInPolicy,
    replay,
    sort_transactions,
)

D = Decimal
T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)

_seq = iter(range(1, 10_000))


def _tx(
    ttype,
    qty,
    price=0,
    *,
    asset="a1",
    fee=0,
    fee_currency=None,
    currency="EUR",
    conversion_rate=None,
    exchange="Binance",
    notes="",
    external_id=None,
    executed_at=T0,
    tx_id=None,
):
    return SimpleNamespace(
        id=tx_id or f"tx{next(_seq):04d}",
        asset_id=asset,
        transaction_type=ttype,
        quantity=D(str(qty)),
        price=D(str(price)),
        fee=D(str(fee)),
        fee_currency=fee_currency,
        currency=currency,
        conversion_rate=conversion_rate,
        exchange=exchange,
        notes=notes,
        external_id=external_id,
        executed_at=executed_at,
    )


SYMS = {"a1": "BTC", "a2": "ETH", "a3": "USDC"}

METRICS_CFG = ReplayConfig(
    portfolio_currency="EUR",
    reward_basis=RewardBasis.MARKET_PRICE,
    conversion_dest_basis=ConversionDestBasis.RECORDED_PRICE,
    unmatched_transfer_in=UnmatchedTransferInPolicy.RECOVER,
    unmatched_conversion_out=UnmatchedConversionOutPolicy.PRESERVE,
    fee_handling=FeeHandling.FEE_CURRENCY_AWARE,
    trim_transfer_network_fee=True,
    seed_stablecoin_layers=True,
)

TAX_CFG = ReplayConfig(
    portfolio_currency="EUR",
    reward_basis=RewardBasis.ZERO,
    conversion_dest_basis=ConversionDestBasis.CARRY_COST,
    unmatched_transfer_in=UnmatchedTransferInPolicy.ZERO,
    unmatched_conversion_out=UnmatchedConversionOutPolicy.CONSUME,
    fee_handling=FeeHandling.TX_CURRENCY,
    trim_transfer_network_fee=False,
    seed_stablecoin_layers=False,
    conversion_external_id_fallback=False,
    skip_null_executed_at=True,
)


def _book_cost(result, key):
    return sum(ly["qty"] * ly["unit_cost"] for ly in result.fifo.get(key, []))


def _book_qty(result, key):
    return sum(ly["qty"] for ly in result.fifo.get(key, []))


# ---------------------------------------------------------------------------
# BUY / SELL + FX + fees
# ---------------------------------------------------------------------------


class TestBuySell:
    def test_buy_creates_layer_in_portfolio_ccy(self):
        txs = [_tx(TxType.BUY, 2, 100, currency="USD", conversion_rate=0.9)]
        res = replay(txs, SYMS, METRICS_CFG)
        (layer,) = res.fifo[("BTC", "Binance")]
        assert layer["unit_cost"] == D("90")  # 100 USD * 0.9
        assert layer["unit_cost_base"] == D("100")
        assert layer["currency"] == "USD"
        assert layer["fx_rate"] == D("0.9")
        assert layer["is_paid"] is True

    def test_sell_consumes_fifo_and_emits_event(self):
        txs = [
            _tx(TxType.BUY, 1, 100, executed_at=T0),
            _tx(TxType.BUY, 1, 200, executed_at=T0 + timedelta(days=1)),
            _tx(TxType.SELL, D("1.5"), 300, executed_at=T0 + timedelta(days=2)),
        ]
        res = replay(txs, SYMS, METRICS_CFG)
        assert _book_qty(res, ("BTC", "Binance")) == D("0.5")
        assert _book_cost(res, ("BTC", "Binance")) == D("100")  # 0.5 left of the 200-layer
        ev = [e for e in res.events if e.kind == "SELL"][0]
        assert ev.cost_removed == D("200")  # 1*100 + 0.5*200
        assert ev.oldest_acquired_at == T0

    def test_oversell_warns_and_consumes_available(self):
        txs = [_tx(TxType.BUY, 1, 100), _tx(TxType.SELL, 2, 100)]
        res = replay(txs, SYMS, METRICS_CFG)
        assert _book_qty(res, ("BTC", "Binance")) == D("0")
        assert any("Oversell" in w for w in res.warnings)

    def test_buy_fee_metrics_portfolio_ccy_in_basis(self):
        txs = [_tx(TxType.BUY, 2, 100, fee=10, fee_currency="EUR")]
        res = replay(txs, SYMS, METRICS_CFG)
        assert _book_cost(res, ("BTC", "Binance")) == D("210")
        assert res.pending_fee_conversions == []

    def test_buy_fee_metrics_foreign_ccy_deferred(self):
        txs = [_tx(TxType.BUY, 2, 100, fee=10, fee_currency="USD")]
        res = replay(txs, SYMS, METRICS_CFG)
        assert _book_cost(res, ("BTC", "Binance")) == D("200")  # fee NOT in basis yet
        assert res.pending_fee_conversions == [(("BTC", "Binance"), D("10"), "USD")]

    def test_buy_fee_tax_always_fx_converted(self):
        # Tax mode: fee assumed in tx currency, converted with the trade fx,
        # fee_currency ignored (frozen historical behaviour).
        txs = [_tx(TxType.BUY, 2, 100, fee=10, fee_currency="JPY", currency="USD", conversion_rate=0.9)]
        res = replay(txs, SYMS, TAX_CFG)
        assert _book_cost(res, ("BTC", "Binance")) == D("189")  # (2*100 + 10) * 0.9
        assert res.pending_fee_conversions == []

    def test_tax_skips_null_executed_at(self):
        txs = [_tx(TxType.BUY, 1, 100, executed_at=None)]
        assert replay(txs, SYMS, TAX_CFG).fifo == {}
        assert replay(txs, SYMS, METRICS_CFG).fifo != {}

    def test_out_of_scope_asset_skipped(self):
        txs = [_tx(TxType.BUY, 1, 100, asset="unknown")]
        assert replay(txs, SYMS, METRICS_CFG).fifo == {}


# ---------------------------------------------------------------------------
# Canonical ordering
# ---------------------------------------------------------------------------


class TestSortTransactions:
    def test_transfer_out_before_transfer_in_same_timestamp(self):
        t_in = _tx(TxType.TRANSFER_IN, 1, exchange="Kraken", tx_id="b")
        t_out = _tx(TxType.TRANSFER_OUT, 1, exchange="Binance", tx_id="a")
        assert [t.id for t in sort_transactions([t_in, t_out])] == ["a", "b"]

    def test_null_executed_at_sorts_first_and_id_breaks_ties(self):
        t1 = _tx(TxType.BUY, 1, executed_at=None, tx_id="z")
        t2 = _tx(TxType.BUY, 1, executed_at=T0, tx_id="a")
        t3 = _tx(TxType.BUY, 1, executed_at=T0, tx_id="b")
        assert [t.id for t in sort_transactions([t3, t2, t1])] == ["z", "a", "b"]


# ---------------------------------------------------------------------------
# Rewards
# ---------------------------------------------------------------------------


class TestRewards:
    def test_reward_market_price_basis(self):
        txs = [_tx(TxType.STAKING_REWARD, 2, 50, currency="USD", conversion_rate=0.9)]
        res = replay(txs, SYMS, METRICS_CFG)
        (layer,) = res.fifo[("BTC", "Binance")]
        assert layer["unit_cost"] == D("45")
        assert layer["is_paid"] is True

    def test_reward_zero_basis_for_tax(self):
        txs = [_tx(TxType.AIRDROP, 2, 50)]
        res = replay(txs, SYMS, TAX_CFG)
        (layer,) = res.fifo[("BTC", "Binance")]
        assert layer["unit_cost"] == D("0")
        assert layer["is_paid"] is False


# ---------------------------------------------------------------------------
# Transfers
# ---------------------------------------------------------------------------


class TestTransfers:
    def _pair(self, out_qty, in_qty):
        return [
            _tx(TxType.BUY, out_qty, 100, exchange="Binance"),
            _tx(TxType.TRANSFER_OUT, out_qty, exchange="Binance", executed_at=T0 + timedelta(days=1)),
            _tx(TxType.TRANSFER_IN, in_qty, exchange="Kraken", executed_at=T0 + timedelta(days=1)),
        ]

    def test_matched_transfer_carries_basis(self):
        res = replay(self._pair(1, 1), SYMS, METRICS_CFG)
        assert _book_cost(res, ("BTC", "Kraken")) == D("100")
        assert _book_qty(res, ("BTC", "Binance")) == D("0")
        assert res.orphan_transit == {}

    def test_network_fee_trimmed_when_enabled(self):
        res = replay(self._pair(D("1.0"), D("0.995")), SYMS, METRICS_CFG)
        assert _book_qty(res, ("BTC", "Kraken")) == D("0.995")
        assert _book_cost(res, ("BTC", "Kraken")) == D("99.5")  # burned excess discarded

    def test_network_fee_kept_when_disabled(self):
        # Frozen tax behaviour: phantom qty + overstated basis.
        res = replay(self._pair(D("1.0"), D("0.995")), SYMS, TAX_CFG)
        assert _book_qty(res, ("BTC", "Kraken")) == D("1.0")
        assert _book_cost(res, ("BTC", "Kraken")) == D("100")

    def test_unmatched_recover_uses_row_price_first(self):
        txs = [_tx(TxType.TRANSFER_IN, 1, 42, exchange="Kraken")]
        res = replay(txs, SYMS, METRICS_CFG)
        (layer,) = res.fifo[("BTC", "Kraken")]
        assert layer["unit_cost"] == D("42")
        assert layer["is_paid"] is True

    def test_unmatched_recover_falls_back_to_avg_then_symbol(self):
        txs = [_tx(TxType.TRANSFER_IN, 1, 0, exchange="Kraken")]
        res = replay(txs, SYMS, METRICS_CFG, aid_to_avg_price={"a1": D("30")})
        assert res.fifo[("BTC", "Kraken")][0]["unit_cost"] == D("30")
        res2 = replay(txs, SYMS, METRICS_CFG, sym_avg_price={"BTC": D("25")})
        assert res2.fifo[("BTC", "Kraken")][0]["unit_cost"] == D("25")
        res3 = replay(txs, SYMS, METRICS_CFG)
        assert res3.fifo[("BTC", "Kraken")][0]["unit_cost"] == D("0")
        assert any("no recoverable cost basis" in w for w in res3.warnings)

    def test_unmatched_zero_policy_for_tax(self):
        txs = [_tx(TxType.TRANSFER_IN, 1, 42, exchange="Kraken")]
        res = replay(txs, SYMS, TAX_CFG, aid_to_avg_price={"a1": D("30")})
        (layer,) = res.fifo[("BTC", "Kraken")]
        assert layer["unit_cost"] == D("0")  # tax: unproven basis is zero

    def test_orphan_transit_isolated_in_result(self):
        txs = [
            _tx(TxType.BUY, 1, 100),
            _tx(TxType.TRANSFER_OUT, 1, executed_at=T0 + timedelta(days=1)),
        ]
        res = replay(txs, SYMS, METRICS_CFG)
        assert _book_qty(res, ("BTC", "Binance")) == D("0")
        assert len(res.orphan_transit) == 1
        (orphans,) = res.orphan_transit.values()
        assert sum(ly["qty"] for ly in orphans) == D("1")


# ---------------------------------------------------------------------------
# Conversions
# ---------------------------------------------------------------------------


def _conversion_pair(*, notes_based=True, src_cost=100, ci_price=20, ci_qty=10, external=False):
    """BUY 1 BTC @src_cost, then convert it into ci_qty ETH."""
    if notes_based:
        co_notes, ci_notes, ext_co, ext_ci = "trade_id:convert_sell_X1", "trade_id:convert_buy_X1", None, None
    elif external:
        co_notes, ci_notes, ext_co, ext_ci = "", "", "convert_sell_X1", "convert_buy_X1"
    else:
        co_notes, ci_notes, ext_co, ext_ci = "", "", None, None
    return [
        _tx(TxType.BUY, 1, src_cost, exchange="Kraken"),
        _tx(
            TxType.CONVERSION_OUT,
            1,
            110,
            exchange="Kraken",
            notes=co_notes,
            external_id=ext_co,
            executed_at=T0 + timedelta(days=1),
        ),
        _tx(
            TxType.CONVERSION_IN,
            ci_qty,
            ci_price,
            asset="a2",
            exchange="Kraken",
            notes=ci_notes,
            external_id=ext_ci,
            executed_at=T0 + timedelta(days=1),
        ),
    ]


class TestConversions:
    def test_matched_recorded_price_basis(self):
        res = replay(_conversion_pair(), SYMS, METRICS_CFG)
        (layer,) = res.fifo[("ETH", "Kraken")]
        assert layer["unit_cost"] == D("20")  # recorded CONVERSION_IN price
        assert _book_qty(res, ("BTC", "Kraken")) == D("0")

    def test_matched_carry_cost_basis_for_tax(self):
        res = replay(_conversion_pair(), SYMS, TAX_CFG)
        (layer,) = res.fifo[("ETH", "Kraken")]
        assert layer["unit_cost"] == D("10")  # 100 consumed / 10 ETH
        ev = [e for e in res.events if e.kind == "CONVERSION_OUT"][0]
        assert ev.matched is True
        assert ev.cost_removed == D("100")
        assert ev.dest_cost == D("100")

    def test_recorded_price_falls_back_to_carry_when_no_price(self):
        res = replay(_conversion_pair(ci_price=0), SYMS, METRICS_CFG)
        (layer,) = res.fifo[("ETH", "Kraken")]
        assert layer["unit_cost"] == D("10")

    def test_external_id_fallback_toggle(self):
        txs = _conversion_pair(notes_based=False, external=True)
        res_on = replay(txs, SYMS, METRICS_CFG)
        assert ("ETH", "Kraken") in res_on.fifo  # matched via external_id
        res_off = replay(_conversion_pair(notes_based=False, external=True), SYMS, TAX_CFG)
        assert ("ETH", "Kraken") not in res_off.fifo  # tax: fallback disabled

    def test_unmatched_preserve_keeps_source_layers(self):
        txs = _conversion_pair(notes_based=False)  # no way to match
        res = replay(txs, SYMS, METRICS_CFG)
        assert _book_cost(res, ("BTC", "Kraken")) == D("100")  # untouched
        assert _book_qty(res, ("BTC", "Kraken")) == D("1")
        ev = [e for e in res.events if e.kind == "CONVERSION_OUT"][0]
        assert ev.matched is False and ev.cost_removed == D("0")

    def test_unmatched_consume_destroys_source_for_tax(self):
        txs = _conversion_pair(notes_based=False)
        res = replay(txs, SYMS, TAX_CFG)
        assert _book_qty(res, ("BTC", "Kraken")) == D("0")
        ev = [e for e in res.events if e.kind == "CONVERSION_OUT"][0]
        assert ev.matched is False and ev.cost_removed == D("100")

    def test_same_symbol_match_rejected(self):
        txs = [
            _tx(TxType.BUY, 1, 100, exchange="Kraken"),
            _tx(
                TxType.CONVERSION_OUT,
                1,
                110,
                exchange="Kraken",
                notes="trade_id:convert_sell_X1",
                executed_at=T0 + timedelta(days=1),
            ),
            # CONVERSION_IN on the SAME symbol (BTC) — M3 must reject
            _tx(
                TxType.CONVERSION_IN,
                1,
                110,
                asset="a1",
                exchange="Kraken",
                notes="trade_id:convert_buy_X1",
                executed_at=T0 + timedelta(days=1),
            ),
        ]
        res = replay(txs, SYMS, METRICS_CFG)
        assert _book_cost(res, ("BTC", "Kraken")) == D("100")  # preserved (unmatched)
        assert any("rejected" in w for w in res.warnings)

    def test_crypto_com_notes_exchange_match(self):
        txs = [
            _tx(TxType.BUY, 1, 100, exchange="Crypto.com"),
            _tx(
                TxType.CONVERSION_OUT,
                1,
                0,
                exchange="Crypto.com",
                notes="swap#42",
                executed_at=T0 + timedelta(days=1),
            ),
            _tx(
                TxType.CONVERSION_IN,
                5,
                22,
                asset="a2",
                exchange="Crypto.com",
                notes="swap#42",
                executed_at=T0 + timedelta(days=1),
            ),
        ]
        res = replay(txs, SYMS, METRICS_CFG)
        (layer,) = res.fifo[("ETH", "Crypto.com")]
        assert layer["qty"] == D("5")
        assert layer["unit_cost"] == D("22")

    def test_stablecoin_seeding_usd_peg(self):
        txs = [
            _tx(
                TxType.CONVERSION_OUT,
                100,
                1,
                asset="a3",
                exchange="Kraken",
                notes="trade_id:convert_sell_S1",
            ),
            _tx(
                TxType.CONVERSION_IN,
                D("0.05"),
                2000,
                asset="a2",
                exchange="Kraken",
                notes="trade_id:convert_buy_S1",
            ),
        ]
        res = replay(txs, SYMS, METRICS_CFG, usd_to_portfolio=D("0.9"))
        ev = [e for e in res.events if e.kind == "CONVERSION_OUT"][0]
        assert ev.cost_removed == D("90")  # 100 USDC seeded at 0.9 EUR
        assert res.fifo[("ETH", "Kraken")][0]["unit_cost"] == D("2000")  # recorded price

    def test_no_seeding_for_tax(self):
        txs = [
            _tx(TxType.CONVERSION_OUT, 100, 1, asset="a3", exchange="Kraken", notes="trade_id:convert_sell_S1"),
            _tx(TxType.CONVERSION_IN, D("0.05"), 2000, asset="a2", exchange="Kraken", notes="trade_id:convert_buy_S1"),
        ]
        res = replay(txs, SYMS, TAX_CFG, usd_to_portfolio=D("0.9"))
        ev = [e for e in res.events if e.kind == "CONVERSION_OUT"][0]
        assert ev.cost_removed == D("0")  # empty pool, nothing seeded
        assert res.fifo[("ETH", "Kraken")][0]["unit_cost"] == D("0")  # zero-cost dest


# ---------------------------------------------------------------------------
# CONVERSION_IN fees & dividends
# ---------------------------------------------------------------------------


class TestConversionInFeesAndDividends:
    def test_tax_fee_applied_to_last_layer(self):
        txs = [
            _tx(TxType.BUY, 2, 100, asset="a2"),
            _tx(TxType.CONVERSION_IN, 2, 0, asset="a2", fee=10, executed_at=T0 + timedelta(days=1)),
        ]
        res = replay(txs, SYMS, TAX_CFG)
        assert _book_cost(res, ("ETH", "Binance")) == D("210")
        assert [e.kind for e in res.events if e.kind == "CONVERSION_IN_FEE"] == ["CONVERSION_IN_FEE"]

    def test_tax_fee_dropped_when_no_layer(self):
        txs = [_tx(TxType.CONVERSION_IN, 2, 0, asset="a2", fee=10)]
        res = replay(txs, SYMS, TAX_CFG)
        assert res.pending_fee_conversions == []  # frozen tax behaviour: silent drop
        assert res.events == []

    def test_metrics_fee_deferred_when_no_layer(self):
        txs = [_tx(TxType.CONVERSION_IN, 2, 0, asset="a2", fee=10, fee_currency="EUR")]
        res = replay(txs, SYMS, METRICS_CFG)
        assert res.pending_fee_conversions == [(("ETH", "Binance"), D("10"), "EUR")]

    def test_dividend_same_ccy_tracked(self):
        txs = [_tx(TxType.DIVIDEND, 10, 2)]
        res = replay(txs, SYMS, METRICS_CFG)
        assert res.dividend_income[("BTC", "Binance")] == D("20")

    def test_dividend_foreign_ccy_with_rate(self):
        txs = [_tx(TxType.DIVIDEND, 10, 2, currency="USD", conversion_rate=0.9)]
        res = replay(txs, SYMS, METRICS_CFG)
        assert res.dividend_income[("BTC", "Binance")] == D("18")

    def test_dividend_foreign_ccy_without_rate_deferred(self):
        txs = [_tx(TxType.DIVIDEND, 10, 2, currency="USD")]
        res = replay(txs, SYMS, METRICS_CFG)
        assert res.dividend_income == {}
        assert res.pending_fee_conversions == [("__div__BTC", D("20"), "USD")]


# ---------------------------------------------------------------------------
# Tax ledger reconstruction through events (API sufficiency proof)
# ---------------------------------------------------------------------------


class TestTaxLedgerViaEvents:
    def test_total_acquisition_cost_ledger(self):
        """The 2086 running ledger must be fully derivable from events."""
        txs = [
            _tx(TxType.BUY, 1, 100, fee=5),  # +105
            _tx(TxType.BUY, 1, 300, executed_at=T0 + timedelta(days=1)),  # +300
            _tx(TxType.SELL, D("0.5"), 400, executed_at=T0 + timedelta(days=2)),  # -50 (0.5 of 105-layer? no: 0.5*105)
        ]
        ledger = D("0")

        def on_event(ev):
            nonlocal ledger
            if ev.kind == "BUY":
                ledger += ev.total_cost
            elif ev.kind in ("SELL", "CONVERSION_OUT"):
                ledger -= ev.cost_removed
                ledger += ev.dest_cost  # matched conversion re-enters
            elif ev.kind == "CONVERSION_IN_FEE":
                ledger += ev.fee

        replay(txs, SYMS, TAX_CFG, on_event=on_event)
        assert ledger == D("105") + D("300") - (D("0.5") * D("105"))

    def test_holding_period_source_field(self):
        old = T0 - timedelta(days=800)
        txs = [
            _tx(TxType.BUY, 1, 100, executed_at=old),
            _tx(TxType.SELL, D("0.5"), 200, executed_at=T0),
        ]
        res = replay(txs, SYMS, TAX_CFG)
        ev = [e for e in res.events if e.kind == "SELL"][0]
        assert (ev.tx_dt - ev.oldest_acquired_at).days >= 730
