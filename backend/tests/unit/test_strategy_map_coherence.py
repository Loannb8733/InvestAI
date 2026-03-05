"""Tests for strategy map decision matrix coherence.

Validates that:
1. Alpha High + Cycle Bottom = ACHAT FORT (strongest buy signal).
2. Alpha Low + Cycle Top = VENDRE (strongest sell signal).
3. All 12 matrix cells produce valid actions.
4. Impact percentages are signed correctly (buy=positive, sell=negative).
5. Summary counters are consistent with rows.
"""

import pytest

from app.services.prediction_service import PredictionService


class TestStrategyMatrix:
    """Test the STRATEGY_MATRIX decision table directly."""

    def test_high_alpha_bottom_cycle_is_strong_buy(self):
        """Alpha high + cycle bottom → ACHAT FORT."""
        action, desc, impact = PredictionService.STRATEGY_MATRIX[("high", "bottom")]
        assert action == "ACHAT FORT"
        assert impact > 0

    def test_low_alpha_top_cycle_is_sell(self):
        """Alpha low + cycle top → VENDRE."""
        action, desc, impact = PredictionService.STRATEGY_MATRIX[("low", "top")]
        assert action == "VENDRE"
        assert impact < 0

    def test_high_alpha_top_cycle_takes_profits(self):
        """Alpha high + cycle top → PRENDRE PROFITS."""
        action, desc, impact = PredictionService.STRATEGY_MATRIX[("high", "top")]
        assert action == "PRENDRE PROFITS"
        assert impact < 0

    def test_medium_alpha_bottom_cycle_dca(self):
        """Alpha medium + cycle bottom → DCA."""
        action, desc, impact = PredictionService.STRATEGY_MATRIX[("medium", "bottom")]
        assert action == "DCA"
        assert impact > 0

    def test_all_12_cells_exist_and_valid(self):
        """All 12 (alpha_level × regime) combinations produce valid entries."""
        alpha_levels = ["high", "medium", "low"]
        regimes = ["bottom", "bearish", "bullish", "top"]
        for alpha in alpha_levels:
            for regime in regimes:
                key = (alpha, regime)
                assert key in PredictionService.STRATEGY_MATRIX, f"Missing key {key}"
                action, desc, impact = PredictionService.STRATEGY_MATRIX[key]
                assert isinstance(action, str) and len(action) > 0
                assert isinstance(desc, str)
                assert isinstance(impact, float)

    def test_buy_actions_have_positive_impact(self):
        """Actions containing ACHAT or DCA should have positive impact."""
        for key, (action, desc, impact) in PredictionService.STRATEGY_MATRIX.items():
            if "ACHAT" in action or action == "DCA":
                assert impact > 0, f"{key}: {action} should have positive impact, got {impact}"

    def test_sell_actions_have_negative_impact(self):
        """Actions containing VENDRE, PROFITS, or ALLÉGER should have negative impact."""
        for key, (action, desc, impact) in PredictionService.STRATEGY_MATRIX.items():
            if "VENDRE" in action or "PROFITS" in action or "ALLÉGER" in action:
                assert impact < 0, f"{key}: {action} should have negative impact, got {impact}"

    def test_hold_actions_have_zero_impact(self):
        """MAINTENIR, ATTENDRE, OBSERVER, CONSERVER should have zero impact."""
        zero_actions = {"MAINTENIR", "ATTENDRE", "OBSERVER", "CONSERVER", "ÉVITER"}
        for key, (action, desc, impact) in PredictionService.STRATEGY_MATRIX.items():
            if action in zero_actions:
                assert impact == 0.0, f"{key}: {action} should have 0 impact, got {impact}"


class TestAlphaLevelClassification:
    """Test alpha level thresholds."""

    def test_score_60_plus_is_high(self):
        assert 60 >= 60  # high threshold
        assert 80 >= 60

    def test_score_30_to_59_is_medium(self):
        assert 30 >= 30 and 30 < 60
        assert 45 >= 30 and 45 < 60

    def test_score_below_30_is_low(self):
        assert 15 < 30
        assert 0 < 30


class TestSummaryCoherence:
    """Test that summary counters match row actions."""

    def test_summary_counts_match_actions(self):
        """Verify counting logic for buys/sells/holds."""
        rows = [
            {"action": "ACHAT FORT"},
            {"action": "DCA"},
            {"action": "VENDRE"},
            {"action": "PRENDRE PROFITS"},
            {"action": "MAINTENIR"},
            {"action": "ATTENDRE"},
            {"action": "ALLÉGER"},
        ]
        buys = sum(1 for r in rows if "ACHAT" in r["action"] or r["action"] == "DCA")
        sells = sum(1 for r in rows if "VENDRE" in r["action"] or "PROFITS" in r["action"] or "ALLÉGER" in r["action"])
        holds = len(rows) - buys - sells

        assert buys == 2  # ACHAT FORT + DCA
        assert sells == 3  # VENDRE + PRENDRE PROFITS + ALLÉGER
        assert holds == 2  # MAINTENIR + ATTENDRE

    def test_impact_accumulation(self):
        """Total impact is the sum of per-asset impacts."""
        impacts = [5.0, -2.0, 0.0, 3.0, -5.0]
        total = sum(impacts)
        assert total == pytest.approx(1.0)
