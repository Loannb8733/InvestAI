"""Tests for cycle advice coherence and risk guard.

Validates that:
1. Extreme Fear → accumulation (DCA), not selling.
2. Extreme Greed → profit-taking, not buying.
3. High risk concentration → DIVERSIFIER warning.
4. DCA hints include EUR amounts when portfolio_value is provided.
"""

from app.services.prediction_service import PredictionService


class TestCycleAdviceCoherence:
    """Test _get_cycle_advice static method directly."""

    def test_extreme_fear_suggests_accumulation(self):
        """Extreme Fear (F&G < 20) must suggest DCA, never VENDRE."""
        advice = PredictionService._get_cycle_advice(
            regime="bearish",
            cycle_pos=85,
            fear_greed=10,  # Extreme Fear
            portfolio_value=863.90,
        )
        actions = [a["action"] for a in advice]
        assert "DCA" in actions, f"Expected DCA in {actions}"
        assert "VENDRE" not in actions, "Should not suggest selling during Extreme Fear"

    def test_bottom_regime_suggests_dca(self):
        """Bottom regime must always suggest DCA accumulation."""
        advice = PredictionService._get_cycle_advice(
            regime="bottom",
            cycle_pos=10,
            fear_greed=25,
            portfolio_value=1000.0,
        )
        actions = [a["action"] for a in advice]
        assert "DCA" in actions
        # Must include DCA hint with EUR amounts
        dca_items = [a for a in advice if a["action"] == "DCA"]
        assert any("€" in a["description"] for a in dca_items), "DCA advice should include EUR amount suggestion"

    def test_extreme_greed_suggests_profit_taking(self):
        """Extreme Greed (F&G > 80) must suggest VENDRE, not buying."""
        advice = PredictionService._get_cycle_advice(
            regime="bullish",
            cycle_pos=75,
            fear_greed=90,  # Extreme Greed
            portfolio_value=5000.0,
        )
        actions = [a["action"] for a in advice]
        assert "VENDRE" in actions, f"Expected VENDRE in {actions}"
        assert "DCA" not in actions, "Should not suggest buying during Extreme Greed"

    def test_high_concentration_warns_diversify(self):
        """When max_risk_weight > 60%, must warn DIVERSIFIER."""
        advice = PredictionService._get_cycle_advice(
            regime="bottom",
            cycle_pos=10,
            fear_greed=15,
            portfolio_value=863.90,
            max_risk_weight=75.0,  # 75% risk in single asset
        )
        actions = [a["action"] for a in advice]
        assert "DIVERSIFIER" in actions, f"Expected DIVERSIFIER warning in {actions}"
        # DIVERSIFIER should be critical priority
        diversify = [a for a in advice if a["action"] == "DIVERSIFIER"]
        assert diversify[0]["priority"] == "critical"

    def test_no_concentration_warning_when_balanced(self):
        """No DIVERSIFIER warning when risk is well-distributed."""
        advice = PredictionService._get_cycle_advice(
            regime="bottom",
            cycle_pos=10,
            fear_greed=15,
            portfolio_value=863.90,
            max_risk_weight=30.0,  # Balanced
        )
        actions = [a["action"] for a in advice]
        assert "DIVERSIFIER" not in actions

    def test_dca_amount_scales_with_portfolio(self):
        """DCA suggestion amounts are proportional to portfolio value."""
        advice_small = PredictionService._get_cycle_advice(
            regime="bottom",
            cycle_pos=10,
            fear_greed=15,
            portfolio_value=1000.0,
        )
        advice_large = PredictionService._get_cycle_advice(
            regime="bottom",
            cycle_pos=10,
            fear_greed=15,
            portfolio_value=100000.0,
        )
        # Small portfolio: 2-5% of 1000 × risk_multiplier (0.7 for bottom) = 14-35€
        dca_small = [a for a in advice_small if a["action"] == "DCA"][0]
        assert (
            "14" in dca_small["description"] or "35" in dca_small["description"]
        ), f"DCA amounts should reflect regime multiplier: {dca_small['description']}"
        # Large portfolio: 2-5% of 100000 × 0.7 = 1400-3500€
        dca_large = [a for a in advice_large if a["action"] == "DCA"][0]
        assert (
            "1400" in dca_large["description"] or "3500" in dca_large["description"]
        ), f"DCA amounts should scale with portfolio: {dca_large['description']}"

    def test_bearish_regime_no_panic_sell(self):
        """Bearish regime advises patience/conservation, not panic selling."""
        advice = PredictionService._get_cycle_advice(
            regime="bearish",
            cycle_pos=80,
            fear_greed=30,
            portfolio_value=863.90,
        )
        actions = [a["action"] for a in advice]
        assert "CONSERVER" in actions
        assert "VENDRE" not in actions, "Bearish should not trigger panic sell"

    def test_no_dca_amount_without_portfolio_value(self):
        """Without portfolio value, DCA advice has no EUR amount."""
        advice = PredictionService._get_cycle_advice(
            regime="bottom",
            cycle_pos=10,
            fear_greed=15,
            portfolio_value=0.0,
        )
        dca_items = [a for a in advice if a["action"] == "DCA"]
        for a in dca_items:
            assert "€" not in a["description"], "No EUR amount without portfolio value"
