"""Unit tests for strategy execution P&L pure functions (simulated prices)."""

import pytest

from app.services.strategy_service import (
    aggregate_strategy_performance,
    classify_action_direction,
    compute_action_performance,
)


class TestClassifyActionDirection:
    def test_buy_labels(self):
        for label in ("BUY", "ACHAT", "ACHAT FORT", "DCA", "RENFORCER", "ACCUMULER"):
            assert classify_action_direction(label) == "buy", label

    def test_sell_labels(self):
        for label in ("SELL", "VENDRE", "ALLÉGER", "PRENDRE PROFITS"):
            assert classify_action_direction(label) == "sell", label

    def test_undecidable_labels(self):
        for label in ("HOLD", "OBSERVER", "SWAP", "", None):
            assert classify_action_direction(label) is None, label

    def test_case_insensitive(self):
        assert classify_action_direction("dca") == "buy"
        assert classify_action_direction("vendre") == "sell"


class TestComputeActionPerformance:
    def test_buy_gain(self):
        # 100 € invested at 100, price now 120 → +20 € (+20 %), baseline 0 (no buy = no exposure)
        perf = compute_action_performance("buy", 100.0, 100.0, 120.0)
        assert perf == {"pnl_eur": 20.0, "pnl_pct": 20.0, "baseline_eur": 0.0}

    def test_buy_loss(self):
        # 200 € invested at 50, price now 40 → −40 € (−20 %)
        perf = compute_action_performance("buy", 200.0, 50.0, 40.0)
        assert perf == {"pnl_eur": -40.0, "pnl_pct": -20.0, "baseline_eur": 0.0}

    def test_sell_avoided_loss(self):
        # Sold 100 € at 100, price dropped to 80 → impact +20 € (loss avoided).
        # Baseline (kept the position): −20 € → acting beat doing nothing by 40 €.
        perf = compute_action_performance("sell", 100.0, 100.0, 80.0)
        assert perf == {"pnl_eur": 20.0, "pnl_pct": 20.0, "baseline_eur": -20.0}

    def test_sell_missed_gain(self):
        # Sold 100 € at 100, price rallied to 150 → impact −50 € (missed gain).
        # Baseline (kept): +50 €.
        perf = compute_action_performance("sell", 100.0, 100.0, 150.0)
        assert perf == {"pnl_eur": -50.0, "pnl_pct": -50.0, "baseline_eur": 50.0}

    def test_invalid_inputs_raise(self):
        with pytest.raises(ValueError):
            compute_action_performance("hold", 100.0, 100.0, 110.0)
        with pytest.raises(ValueError):
            compute_action_performance("buy", 0.0, 100.0, 110.0)
        with pytest.raises(ValueError):
            compute_action_performance("buy", 100.0, 0.0, 110.0)
        with pytest.raises(ValueError):
            compute_action_performance("sell", 100.0, 100.0, 0.0)


class TestAggregateStrategyPerformance:
    def test_totals_and_follow_rate(self):
        evaluated = [
            compute_action_performance("buy", 100.0, 100.0, 120.0),  # +20, baseline 0
            compute_action_performance("sell", 100.0, 100.0, 80.0),  # +20, baseline −20
        ]
        summary = aggregate_strategy_performance(
            evaluated, executed_count=2, skipped_count=2, pending_count=1, non_evaluable_count=0
        )
        assert summary["total_impact_eur"] == 40.0
        assert summary["baseline_no_action_eur"] == -20.0
        assert summary["vs_baseline_eur"] == 60.0
        assert summary["follow_rate_pct"] == 50.0
        assert summary["evaluated_count"] == 2
        assert summary["pending_count"] == 1

    def test_follow_rate_none_when_nothing_decided(self):
        summary = aggregate_strategy_performance(
            [], executed_count=0, skipped_count=0, pending_count=3, non_evaluable_count=0
        )
        assert summary["follow_rate_pct"] is None
        assert summary["total_impact_eur"] == 0.0
        assert summary["vs_baseline_eur"] == 0.0

    def test_non_evaluable_counted_but_excluded_from_totals(self):
        evaluated = [compute_action_performance("buy", 50.0, 10.0, 11.0)]  # +5
        summary = aggregate_strategy_performance(
            evaluated, executed_count=3, skipped_count=0, pending_count=0, non_evaluable_count=2
        )
        assert summary["total_impact_eur"] == 5.0
        assert summary["non_evaluable_count"] == 2
        assert summary["follow_rate_pct"] == 100.0
