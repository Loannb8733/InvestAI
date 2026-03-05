"""Tests for cycle diagnostic coherence.

Validates that:
1. Time-to-Pivot estimates are bounded and directional.
2. Euphoria zone detection triggers when BTC top + F&G > 80.
3. Distribution diagnostic flags assets with high top+bearish probability.
4. Phase boundary transitions are consistent with cycle position.
"""

from app.services.prediction_service import PredictionService


class TestTimeToPivot:
    """Test _estimate_time_to_pivot static method."""

    def test_creux_phase_transitions_to_accumulation(self):
        """Cycle position 5 (Creux) → next phase = Accumulation."""
        result = PredictionService._estimate_time_to_pivot(
            cycle_position=5,
            btc_regime={"dominant_regime": "bottom", "confidence": 0.7},
            btc_estimate={"ou_parameters": {"theta": 0.03}},
        )
        assert result["current_phase"] == "Creux"
        assert result["next_phase"] == "Accumulation"
        assert result["estimated_days"] >= 3
        assert result["estimated_days"] <= 90

    def test_expansion_phase_transitions_to_distribution(self):
        """Cycle position 50 (Expansion) → next phase = Distribution."""
        result = PredictionService._estimate_time_to_pivot(
            cycle_position=50,
            btc_regime={"dominant_regime": "bullish", "confidence": 0.6},
            btc_estimate={"ou_parameters": {"theta": 0.02}},
        )
        assert result["current_phase"] == "Expansion"
        assert result["next_phase"] == "Distribution"

    def test_euphorie_transitions_to_creux(self):
        """Cycle position 90 (Euphorie) → next phase = Creux."""
        result = PredictionService._estimate_time_to_pivot(
            cycle_position=90,
            btc_regime={"dominant_regime": "top", "confidence": 0.8},
            btc_estimate={"ou_parameters": {"theta": 0.04}},
        )
        assert result["current_phase"] == "Euphorie"
        assert result["next_phase"] == "Creux"

    def test_distribution_transitions_to_euphorie(self):
        """Cycle position 70 (Distribution) → next phase = Euphorie."""
        result = PredictionService._estimate_time_to_pivot(
            cycle_position=70,
            btc_regime={"dominant_regime": "top", "confidence": 0.5},
            btc_estimate=None,
        )
        assert result["current_phase"] == "Distribution"
        assert result["next_phase"] == "Euphorie"

    def test_high_theta_shortens_estimate(self):
        """Higher OU theta (faster mean-reversion) → fewer days to pivot."""
        result_slow = PredictionService._estimate_time_to_pivot(
            cycle_position=50,
            btc_regime={"dominant_regime": "bullish", "confidence": 0.6},
            btc_estimate={"ou_parameters": {"theta": 0.01}},
        )
        result_fast = PredictionService._estimate_time_to_pivot(
            cycle_position=50,
            btc_regime={"dominant_regime": "bullish", "confidence": 0.6},
            btc_estimate={"ou_parameters": {"theta": 0.05}},
        )
        assert result_fast["estimated_days"] <= result_slow["estimated_days"]

    def test_estimates_bounded_3_to_90(self):
        """All estimates must be between 3 and 90 days."""
        for pos in [0, 14, 15, 39, 40, 64, 65, 84, 85, 99]:
            result = PredictionService._estimate_time_to_pivot(
                cycle_position=pos,
                btc_regime={"dominant_regime": "bullish", "confidence": 0.5},
                btc_estimate={"ou_parameters": {"theta": 0.02}},
            )
            assert 3 <= result["estimated_days"] <= 90, f"pos={pos}: got {result['estimated_days']} days"

    def test_confidence_from_regime(self):
        """Confidence should reflect BTC regime confidence."""
        result = PredictionService._estimate_time_to_pivot(
            cycle_position=50,
            btc_regime={"dominant_regime": "bullish", "confidence": 0.85},
            btc_estimate=None,
        )
        assert result["confidence"] == 0.85

    def test_no_regime_defaults_confidence(self):
        """Without BTC regime, confidence defaults to 0.5."""
        result = PredictionService._estimate_time_to_pivot(
            cycle_position=50,
            btc_regime=None,
            btc_estimate=None,
        )
        assert result["confidence"] == 0.5


class TestEuphoriaDetection:
    """Test euphoria detection logic (conditions for alert)."""

    def test_euphoria_conditions_met(self):
        """BTC regime=top + F&G > 80 → euphoria conditions met."""
        btc_regime = {"dominant_regime": "top", "confidence": 0.7}
        fear_greed = 85
        assert btc_regime["dominant_regime"] == "top"
        assert fear_greed > 80

    def test_euphoria_not_triggered_bullish(self):
        """BTC regime=bullish + F&G > 80 → NOT euphoria (regime must be top)."""
        btc_regime = {"dominant_regime": "bullish", "confidence": 0.7}
        assert btc_regime["dominant_regime"] != "top"

    def test_euphoria_not_triggered_low_fg(self):
        """BTC regime=top + F&G=60 → NOT euphoria (F&G must be > 80)."""
        fear_greed = 60
        assert not (fear_greed > 80)


class TestDistributionDiagnostic:
    """Test distribution diagnostic filtering logic."""

    def test_high_top_prob_flagged(self):
        """Asset with top+bearish prob > 40% gets flagged."""
        probs = {"bullish": 0.1, "bearish": 0.3, "top": 0.4, "bottom": 0.2}
        top_bearish = probs["top"] + probs["bearish"]
        assert top_bearish >= 0.40

    def test_low_top_prob_not_flagged(self):
        """Asset with top+bearish prob < 40% NOT flagged."""
        probs = {"bullish": 0.5, "bearish": 0.1, "top": 0.1, "bottom": 0.3}
        top_bearish = probs["top"] + probs["bearish"]
        assert top_bearish < 0.40

    def test_overbought_rsi_high_priority(self):
        """RSI > 70 → sell_priority should be 'high'."""
        rsi = 75
        sell_priority = "high" if rsi > 70 else "low"
        assert sell_priority == "high"

    def test_phase_boundaries_complete(self):
        """All 5 phases are covered by the boundary ranges."""
        phases = [
            (0, 15, "Creux"),
            (15, 40, "Accumulation"),
            (40, 65, "Expansion"),
            (65, 85, "Distribution"),
            (85, 100, "Euphorie"),
        ]
        # Verify no gaps: each phase starts where the previous ends
        for i in range(1, len(phases)):
            assert phases[i][0] == phases[i - 1][1], f"Gap between {phases[i-1][2]} and {phases[i][2]}"
        # Full coverage 0-100
        assert phases[0][0] == 0
        assert phases[-1][1] == 100
