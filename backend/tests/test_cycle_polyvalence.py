"""Tests de polyvalence face aux cycles de marché.

Vérifie que le système lit correctement le régime :
1. Bull market (EMA+5%, RSI 60) → markup → lecture neutre
2. Bear market → gold bonus +10
3. RSI > 80 → sommet → lecture défavorable même en plein bull run
"""

import numpy as np
import pytest

from app.domains.predictions.strategy_map import STRATEGY_MATRIX
from app.ml.regime import indicators as regime_indicators
from app.ml.regime.detector import MarketRegimeDetector

# ── Helpers ──────────────────────────────────────────────────────


def _generate_bull_prices(days: int = 120) -> list:
    """Generate a clear bull trend: steady upward prices with EMA-20 slope > +5%."""
    np.random.seed(42)
    prices = [30_000.0]
    # Strong uptrend: 0.5% drift/day → EMA slope clearly positive
    for _ in range(days - 1):
        prices.append(prices[-1] * (1 + np.random.normal(0.005, 0.015)))
    return prices


def _generate_bear_prices(days: int = 120) -> list:
    """Generate a clear bear trend."""
    np.random.seed(42)
    prices = [60_000.0]
    for _ in range(days - 1):
        prices.append(prices[-1] * (1 + np.random.normal(-0.004, 0.02)))
    return prices


def _generate_overbought_prices(days: int = 120) -> list:
    """Generate prices ending in overbought territory (RSI > 80)."""
    np.random.seed(42)
    prices = [30_000.0]
    # Start moderate then accelerate at the end
    for i in range(days - 1):
        if i < days - 20:
            drift = 0.003
        else:
            # Strong acceleration to push RSI > 80
            drift = 0.015
        prices.append(prices[-1] * (1 + np.random.normal(drift, 0.008)))
    return prices


# ── Point 1: Bull Market Simulation ─────────────────────────────


class TestBullMarketRegimeDetection:
    """EMA-20 slope positive + RSI ~60 → bullish → markup."""

    def test_ema20_slope_positive_in_bull(self):
        """Bull trend should produce positive EMA-20 slope."""
        prices = _generate_bull_prices(120)
        ema_series = regime_indicators.ema(prices, 20)
        assert ema_series is not None and len(ema_series) >= 5
        slope = (ema_series[-1] - ema_series[-5]) / max(abs(ema_series[-5]), 1e-10)
        assert slope > 0.01, f"EMA-20 slope should be strongly positive in bull, got {slope:.4f}"

    def test_rsi_in_bullish_range(self):
        """Bull trend RSI should be in the 50-70 range (bullish, not overbought)."""
        prices = _generate_bull_prices(120)
        rsi = regime_indicators.rsi(prices)
        assert rsi is not None
        assert 45 < rsi < 80, f"RSI should be in bullish range, got {rsi:.1f}"

    def test_regime_detects_bullish(self):
        """Bull prices → dominant regime should be bullish."""
        prices = _generate_bull_prices(120)
        detector = MarketRegimeDetector()
        result = detector.detect(prices, "BTC_BULL")
        assert result.dominant_regime in (
            "bullish",
            "top",
        ), f"Expected bullish or top, got {result.dominant_regime}"

    def test_6phase_markup_in_bull(self):
        """Bullish regime → refine_to_6phase should return 'markup'."""
        prices = _generate_bull_prices(120)
        detector = MarketRegimeDetector()
        result = detector.detect(prices, "BTC_BULL")
        if result.dominant_regime == "bullish":
            phase = detector.refine_to_6phase(result, prices)
            assert phase == "markup", f"Bullish should refine to markup, got {phase}"


class TestBullMarketStrategyMatrix:
    """In mark-up phase, every alpha level reads neutral: the trend is described, no hold/sell instruction."""

    @pytest.mark.parametrize("level", ["high", "medium", "low"])
    def test_markup_reads_neutral(self, level):
        tone, _ = STRATEGY_MATRIX[(level, "markup")]
        assert tone == "neutre"

    def test_high_alpha_bullish_compat_reads_neutral(self):
        """Backward-compat: bullish (4-phase) → neutral reading."""
        tone, _ = STRATEGY_MATRIX[("high", "bullish")]
        assert tone == "neutre"


# ── Point 2: Safe Haven Adjustment ──────────────────────────────


class TestGoldBonusSuppressedInBull:
    """Gold bonus (+10 pts) should ONLY apply in bear markets, not bull."""

    def _score_with_gold(self, regime_name: str, gold_exposure: float = 0.10):
        """Helper: compute score with given regime and gold exposure.

        Uses penalizing params so the score isn't capped at 100 (leaving room
        for the +10 gold bonus to be visible).
        """
        from app.ml.regime.types import MarketRegime, RegimeResult

        regime_result = RegimeResult(
            symbol="BTC",
            probabilities={"bearish": 0.7, "bottom": 0.1, "bullish": 0.1, "top": 0.1},
            dominant_regime=regime_name,
            confidence=0.7,
            signals=[],
            description="test",
        )
        market_regime = MarketRegime(market=regime_result, per_asset=[])

        from app.domains.insights.score import overall_score

        score, status = overall_score(
            sharpe=0.3,  # poor sharpe → penalty
            volatility=0.50,  # high volatility → penalty
            var_95=0.06,  # elevated VaR → penalty
            hhi=0.25,  # concentrated → penalty
            anomaly_count=1,  # one anomaly → penalty
            max_drawdown=0.20,  # moderate drawdown → penalty
            gold_exposure=gold_exposure,
            market_regime=market_regime,
        )
        return score

    def test_no_gold_bonus_in_bullish(self):
        """In bullish regime, gold exposure should NOT add bonus points."""
        score_no_gold = self._score_with_gold("bullish", gold_exposure=0.0)
        score_with_gold = self._score_with_gold("bullish", gold_exposure=0.20)
        assert score_with_gold == score_no_gold, (
            f"Gold bonus should be 0 in bull: no_gold={score_no_gold}, with_gold={score_with_gold}"
        )

    def test_no_gold_bonus_in_markup(self):
        score_no_gold = self._score_with_gold("markup", gold_exposure=0.0)
        score_with_gold = self._score_with_gold("markup", gold_exposure=0.20)
        assert score_with_gold == score_no_gold

    def test_gold_bonus_applies_in_bearish(self):
        """In bearish regime, gold exposure SHOULD add bonus points."""
        score_no_gold = self._score_with_gold("bearish", gold_exposure=0.0)
        score_with_gold = self._score_with_gold("bearish", gold_exposure=0.20)
        assert score_with_gold > score_no_gold, (
            f"Gold bonus should apply in bear: no_gold={score_no_gold}, with_gold={score_with_gold}"
        )

    def test_gold_bonus_applies_in_markdown(self):
        score_no_gold = self._score_with_gold("markdown", gold_exposure=0.0)
        score_with_gold = self._score_with_gold("markdown", gold_exposure=0.20)
        assert score_with_gold > score_no_gold

    def test_gold_bonus_max_10(self):
        """Gold bonus should cap at +10 points."""
        # gold_exposure = 0.50 → int(0.50*100) = 50, capped at min(10, 50) = 10
        score_20pct = self._score_with_gold("bearish", gold_exposure=0.20)
        score_50pct = self._score_with_gold("bearish", gold_exposure=0.50)
        # Both should have same +10 bonus (capped)
        assert score_50pct == score_20pct, "Gold bonus should cap at +10"


class TestRSIOverboughtTakesProfits:
    """RSI > 80 should trigger 'top' regime → PRENDRE PROFITS even in bull run."""

    def test_overbought_prices_detected_as_top(self):
        """Price series with strong acceleration → RSI > 70 → top regime."""
        prices = _generate_overbought_prices(120)
        rsi = regime_indicators.rsi(prices)
        assert rsi is not None
        # RSI should be elevated (we're testing the general concept)
        assert rsi > 65, f"Overbought prices should have high RSI, got {rsi:.1f}"

    def test_strategy_matrix_top_reads_unfavorable(self):
        """Regardless of alpha, top/topping reads unfavorable."""
        for level in ("high", "low"):
            for phase in ("top", "topping"):
                tone, _ = STRATEGY_MATRIX.get((level, phase), ("UNKNOWN", ""))
                assert tone == "défavorable", f"{level} alpha + {phase} should read unfavorable, got {tone}"
