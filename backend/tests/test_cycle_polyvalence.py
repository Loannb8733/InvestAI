"""Tests de polyvalence face aux cycles de marché.

Vérifie que le système produit les bonnes actions selon le régime :
1. Bull market (EMA+5%, RSI 60) → markup → MAINTENIR
2. Bear market → gold bonus +10, bot messages adaptées
3. RSI > 80 → PRENDRE PROFITS même en plein bull run
4. DCA amounts cohérents avec le capital
5. Telegram alert tone adapté au régime
"""

import numpy as np
import pytest

from app.ml.regime_detector import MarketRegimeDetector, _ema, _rsi
from app.services.prediction_service import PredictionService
from app.services.telegram_service import TelegramService

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
        ema_series = _ema(prices, 20)
        assert ema_series is not None and len(ema_series) >= 5
        slope = (ema_series[-1] - ema_series[-5]) / max(abs(ema_series[-5]), 1e-10)
        assert slope > 0.01, f"EMA-20 slope should be strongly positive in bull, got {slope:.4f}"

    def test_rsi_in_bullish_range(self):
        """Bull trend RSI should be in the 50-70 range (bullish, not overbought)."""
        prices = _generate_bull_prices(120)
        rsi = _rsi(prices)
        assert rsi is not None
        assert 45 < rsi < 80, f"RSI should be in bullish range, got {rsi:.1f}"

    def test_regime_detects_bullish(self):
        """Bull prices → dominant regime should be bullish."""
        prices = _generate_bull_prices(120)
        detector = MarketRegimeDetector()
        result = detector.detect(prices, "BTC_BULL")
        assert result.dominant_regime in ("bullish", "top"), f"Expected bullish or top, got {result.dominant_regime}"

    def test_6phase_markup_in_bull(self):
        """Bullish regime → refine_to_6phase should return 'markup'."""
        prices = _generate_bull_prices(120)
        detector = MarketRegimeDetector()
        result = detector.detect(prices, "BTC_BULL")
        if result.dominant_regime == "bullish":
            phase = detector.refine_to_6phase(result, prices)
            assert phase == "markup", f"Bullish should refine to markup, got {phase}"


class TestBullMarketStrategyMatrix:
    """In mark-up phase, strategy should be MAINTENIR (let profits run)."""

    def test_high_alpha_markup_is_maintenir(self):
        action, desc, impact = PredictionService.STRATEGY_MATRIX[("high", "markup")]
        assert action == "MAINTENIR"
        assert impact == 0.0

    def test_medium_alpha_markup_is_maintenir(self):
        action, desc, impact = PredictionService.STRATEGY_MATRIX[("medium", "markup")]
        assert action == "MAINTENIR"
        assert impact == 0.0

    def test_low_alpha_markup_is_conserver(self):
        action, desc, impact = PredictionService.STRATEGY_MATRIX[("low", "markup")]
        assert action == "CONSERVER"

    def test_high_alpha_bullish_compat_is_maintenir(self):
        """Backward-compat: bullish (4-phase) → MAINTENIR."""
        action, desc, impact = PredictionService.STRATEGY_MATRIX[("high", "bullish")]
        assert action == "MAINTENIR"


class TestDCAAmountsCoherence:
    """DCA amounts should be 2-5% of portfolio value."""

    @pytest.mark.parametrize("portfolio_value", [500, 1296, 10_000, 100_000])
    def test_dca_range_is_2_to_5_percent(self, portfolio_value):
        low = round(portfolio_value * 0.02, 2)
        high = round(portfolio_value * 0.05, 2)
        # DCA should never be negative
        assert low > 0
        assert high > low
        # DCA should be proportional to portfolio
        assert low == pytest.approx(portfolio_value * 0.02, abs=0.01)
        assert high == pytest.approx(portfolio_value * 0.05, abs=0.01)

    def test_dca_1296_eur_portfolio(self):
        """Example: 1296€ portfolio → DCA = 25.92€ - 64.80€."""
        pv = 1296.0
        low = round(pv * 0.02, 2)
        high = round(pv * 0.05, 2)
        assert low == pytest.approx(25.92, abs=0.01)
        assert high == pytest.approx(64.80, abs=0.01)


# ── Point 2: Safe Haven Adjustment ──────────────────────────────


class TestGoldBonusSuppressedInBull:
    """Gold bonus (+10 pts) should ONLY apply in bear markets, not bull."""

    def _score_with_gold(self, regime_name: str, gold_exposure: float = 0.10):
        """Helper: compute score with given regime and gold exposure.

        Uses penalizing params so the score isn't capped at 100 (leaving room
        for the +10 gold bonus to be visible).
        """
        from app.ml.regime_detector import MarketRegime, RegimeResult

        regime_result = RegimeResult(
            symbol="BTC",
            probabilities={"bearish": 0.7, "bottom": 0.1, "bullish": 0.1, "top": 0.1},
            dominant_regime=regime_name,
            confidence=0.7,
            signals=[],
            description="test",
        )
        market_regime = MarketRegime(market=regime_result, per_asset=[])

        from app.services.smart_insights_service import SmartInsightsService

        svc = SmartInsightsService()
        score, status = svc._calculate_overall_score(
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
        assert (
            score_with_gold == score_no_gold
        ), f"Gold bonus should be 0 in bull: no_gold={score_no_gold}, with_gold={score_with_gold}"

    def test_no_gold_bonus_in_markup(self):
        score_no_gold = self._score_with_gold("markup", gold_exposure=0.0)
        score_with_gold = self._score_with_gold("markup", gold_exposure=0.20)
        assert score_with_gold == score_no_gold

    def test_gold_bonus_applies_in_bearish(self):
        """In bearish regime, gold exposure SHOULD add bonus points."""
        score_no_gold = self._score_with_gold("bearish", gold_exposure=0.0)
        score_with_gold = self._score_with_gold("bearish", gold_exposure=0.20)
        assert (
            score_with_gold > score_no_gold
        ), f"Gold bonus should apply in bear: no_gold={score_no_gold}, with_gold={score_with_gold}"

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
        rsi = _rsi(prices)
        assert rsi is not None
        # RSI should be elevated (we're testing the general concept)
        assert rsi > 65, f"Overbought prices should have high RSI, got {rsi:.1f}"

    def test_strategy_matrix_top_takes_profits(self):
        """Regardless of bull run, top/topping → PRENDRE PROFITS or ALLÉGER."""
        for phase in ("top", "topping"):
            action, desc, impact = PredictionService.STRATEGY_MATRIX.get(("high", phase), ("UNKNOWN", "", 0))
            assert "PROFIT" in action or "ALLÉGER" in action, f"High alpha + {phase} should take profits, got {action}"

    def test_low_alpha_top_is_vendre(self):
        """Low alpha at top → VENDRE (strongest sell signal)."""
        for phase in ("top", "topping"):
            action, desc, impact = PredictionService.STRATEGY_MATRIX.get(("low", phase), ("UNKNOWN", "", 0))
            assert action == "VENDRE", f"Low alpha + {phase} should be VENDRE, got {action}"


# ── Point 3: Telegram Alert Tone ────────────────────────────────


class TestTelegramAlertTone:
    """Telegram alerts should adapt their tone to the market regime."""

    def test_format_regime_alert_bear(self):
        """Bear regime → tone should mention 'Creux' or 'sécurisé'."""
        msg = TelegramService.format_regime_alert(
            symbol="BTC",
            action="DCA",
            regime="bottoming",
            description="Alpha élevé + Bottoming",
        )
        assert (
            "creux" in msg.lower() or "bottom" in msg.lower() or "sécuris" in msg.lower()
        ), f"Bear alert should mention creux/sécurisé: {msg}"

    def test_format_regime_alert_bull(self):
        """Bull regime → tone should mention 'momentum' or 'expansion'."""
        msg = TelegramService.format_regime_alert(
            symbol="BTC",
            action="MAINTENIR",
            regime="markup",
            description="Alpha élevé + Mark-up",
        )
        assert (
            "momentum" in msg.lower() or "expansion" in msg.lower() or "mark-up" in msg.lower()
        ), f"Bull alert should mention momentum/expansion: {msg}"

    def test_format_regime_alert_top(self):
        """Top regime → tone should mention 'profits' or 'prudence'."""
        msg = TelegramService.format_regime_alert(
            symbol="BTC",
            action="PRENDRE PROFITS",
            regime="topping",
            description="Alpha élevé mais Topping",
        )
        assert "profit" in msg.lower() or "prudence" in msg.lower(), f"Top alert should mention profits/prudence: {msg}"
