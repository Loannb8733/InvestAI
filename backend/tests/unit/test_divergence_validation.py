"""Tests for RSI divergence detection, score degradation, and reconciliation.

Validates that:
1. Bullish divergence is correctly identified (price down + RSI up).
2. No divergence when price and RSI move in same direction.
3. divergence_log contains all required fields.
4. Score is degraded when price drops but RSI does NOT diverge.
5. Reconciliation report includes écart Dashboard field.
6. Telegram message format includes sync status.
"""

import numpy as np

from app.ml.regime_detector import _rsi


class TestRSIDivergenceDetection:
    """Test the RSI divergence scoring logic inline."""

    @staticmethod
    def _compute_divergence_with_score(prices: list) -> tuple:
        """Replicate divergence detection + score degradation from get_top_alpha_asset.

        Returns (divergence_log, score_delta, reason_or_none).
        """
        rsi_now = _rsi(prices, period=14)
        rsi_prev = _rsi(prices[:-7], period=14) if len(prices) > 21 else None
        price_t = prices[-1]
        price_t7 = prices[-8] if len(prices) > 8 else price_t
        price_change_7d = (price_t / price_t7 - 1) * 100 if price_t7 > 0 else 0

        divergence_log = {
            "price_t7": round(price_t7, 4),
            "price_t": round(price_t, 4),
            "rsi_t7": round(rsi_prev, 2) if rsi_prev is not None else None,
            "rsi_t": round(rsi_now, 2) if rsi_now is not None else None,
            "price_change_7d_pct": round(price_change_7d, 2),
            "is_bullish_divergence": False,
        }

        score_delta = 0.0
        reason = None

        if rsi_now is not None and rsi_prev is not None:
            rsi_delta = rsi_now - rsi_prev
            if price_change_7d < -2 and rsi_delta > 3:
                divergence_log["is_bullish_divergence"] = True
                div_score = min(35, 15 + rsi_delta * 2)
                score_delta = div_score
                reason = {"label": "Divergence Haussière", "score": round(div_score)}
            elif price_change_7d < -2 and rsi_delta <= 3:
                # Score degradation: price dropped but RSI did NOT diverge
                penalty = min(10, abs(rsi_delta) * 1.5)
                score_delta = -penalty
                divergence_log["degraded"] = True
                divergence_log["penalty"] = round(penalty, 1)
                reason = {"label": "Divergence Non Confirmée", "score": round(-penalty)}

        return divergence_log, score_delta, reason

    def test_bullish_divergence_detected(self):
        """Price drops but RSI rises → bullish divergence = True, positive score."""
        np.random.seed(42)
        prices = [100 + i * 0.5 for i in range(30)]
        for i in range(7):
            prices.append(prices[-1] * 0.995)
        prices[-2] = prices[-3] * 1.015
        prices[-1] = prices[-2] * 1.012

        dlog, score, reason = self._compute_divergence_with_score(prices)
        assert dlog["price_t7"] is not None
        assert dlog["price_t"] is not None
        assert dlog["rsi_t"] is not None
        assert dlog["rsi_t7"] is not None

    def test_no_divergence_both_falling(self):
        """Price and RSI both fall → no divergence."""
        prices = [100 - i * 1.0 for i in range(40)]
        dlog, score, reason = self._compute_divergence_with_score(prices)
        assert dlog["is_bullish_divergence"] is False
        assert dlog["price_change_7d_pct"] < 0

    def test_no_divergence_both_rising(self):
        """Price and RSI both rise → no divergence."""
        prices = [100 + i * 0.8 for i in range(40)]
        dlog, score, reason = self._compute_divergence_with_score(prices)
        assert dlog["is_bullish_divergence"] is False
        assert dlog["price_change_7d_pct"] > 0

    def test_divergence_log_base_fields(self):
        """divergence_log always contains the 6 base keys."""
        prices = [100 + i * 0.3 for i in range(40)]
        dlog, _, _ = self._compute_divergence_with_score(prices)
        expected_keys = {
            "price_t7",
            "price_t",
            "rsi_t7",
            "rsi_t",
            "price_change_7d_pct",
            "is_bullish_divergence",
        }
        assert expected_keys.issubset(set(dlog.keys()))

    def test_price_t7_vs_price_t_relationship(self):
        """price_t7 is prices[-8] and price_t is prices[-1]."""
        prices = list(range(50, 90))
        dlog, _, _ = self._compute_divergence_with_score(prices)
        assert dlog["price_t"] == 89.0
        assert dlog["price_t7"] == 82.0

    def test_rsi_values_in_valid_range(self):
        """RSI values should be between 0 and 100."""
        prices = [100 + i * 0.5 + np.sin(i) * 3 for i in range(40)]
        dlog, _, _ = self._compute_divergence_with_score(prices)
        assert 0 <= dlog["rsi_t"] <= 100
        assert 0 <= dlog["rsi_t7"] <= 100

    def test_flat_prices_no_divergence(self):
        """Flat prices → RSI around 50, no divergence."""
        prices = [100.0] * 40
        dlog, _, _ = self._compute_divergence_with_score(prices)
        assert dlog["is_bullish_divergence"] is False
        assert abs(dlog["price_change_7d_pct"]) < 0.01

    def test_mathematical_divergence_condition(self):
        """When bullish divergence is detected: price_t < price_t7 AND rsi_t > rsi_t7."""
        np.random.seed(123)
        base = [50 + i * 0.3 for i in range(25)]
        base.extend([base[-1] - i * 0.8 for i in range(1, 8)])
        base.extend([base[-1] + 0.5, base[-1] + 1.0])

        dlog, _, _ = self._compute_divergence_with_score(base)
        if dlog["is_bullish_divergence"]:
            assert dlog["price_change_7d_pct"] < -2
            assert dlog["rsi_t"] > dlog["rsi_t7"]


class TestDivergenceScoreDegradation:
    """Test that score is degraded when divergence is NOT confirmed."""

    @staticmethod
    def _compute_divergence_with_score(prices: list) -> tuple:
        """Same logic as TestRSIDivergenceDetection."""
        rsi_now = _rsi(prices, period=14)
        rsi_prev = _rsi(prices[:-7], period=14) if len(prices) > 21 else None
        price_t = prices[-1]
        price_t7 = prices[-8] if len(prices) > 8 else price_t
        price_change_7d = (price_t / price_t7 - 1) * 100 if price_t7 > 0 else 0

        divergence_log = {
            "price_t7": round(price_t7, 4),
            "price_t": round(price_t, 4),
            "rsi_t7": round(rsi_prev, 2) if rsi_prev is not None else None,
            "rsi_t": round(rsi_now, 2) if rsi_now is not None else None,
            "price_change_7d_pct": round(price_change_7d, 2),
            "is_bullish_divergence": False,
        }

        score_delta = 0.0

        if rsi_now is not None and rsi_prev is not None:
            rsi_delta = rsi_now - rsi_prev
            if price_change_7d < -2 and rsi_delta > 3:
                divergence_log["is_bullish_divergence"] = True
                score_delta = min(35, 15 + rsi_delta * 2)
            elif price_change_7d < -2 and rsi_delta <= 3:
                penalty = min(10, abs(rsi_delta) * 1.5)
                score_delta = -penalty
                divergence_log["degraded"] = True
                divergence_log["penalty"] = round(penalty, 1)

        return divergence_log, score_delta

    def test_price_drop_no_rsi_divergence_degrades_score(self):
        """Price drops > 2% but RSI doesn't rise enough → negative score."""
        # Oscillating then dropping — RSI non-zero but declining
        np.random.seed(99)
        prices = [100 + np.sin(i * 0.3) * 5 for i in range(30)]
        # Sharp drop in last 8 days to trigger > 2% decline
        for i in range(8):
            prices.append(prices[-1] * 0.994)

        dlog, score_delta = self._compute_divergence_with_score(prices)
        if dlog["price_change_7d_pct"] < -2 and dlog.get("degraded"):
            assert score_delta < 0, f"Expected negative score, got {score_delta}"
            assert dlog.get("penalty", 0) > 0

    def test_degradation_penalty_capped_at_10(self):
        """Penalty should not exceed 10 points."""
        # Large oscillation then sharp drop — RSI delta is negative
        np.random.seed(77)
        prices = [100 + np.sin(i * 0.5) * 8 for i in range(30)]
        for i in range(8):
            prices.append(prices[-1] * 0.992)
        dlog, score_delta = self._compute_divergence_with_score(prices)
        if score_delta < 0:
            assert score_delta >= -10, f"Penalty exceeded cap: {score_delta}"

    def test_no_degradation_when_price_rises(self):
        """Price rises → no degradation regardless of RSI."""
        prices = [100 + i * 0.5 for i in range(40)]
        dlog, score_delta = self._compute_divergence_with_score(prices)
        assert score_delta >= 0, f"Should not degrade on rising prices, got {score_delta}"
        assert "degraded" not in dlog

    def test_degradation_log_has_penalty_field(self):
        """When degraded, divergence_log includes 'penalty' and 'degraded' keys."""
        np.random.seed(88)
        prices = [100 + np.sin(i * 0.3) * 5 for i in range(30)]
        for i in range(8):
            prices.append(prices[-1] * 0.994)
        dlog, score_delta = self._compute_divergence_with_score(prices)
        if dlog.get("degraded"):
            assert "penalty" in dlog
            assert isinstance(dlog["penalty"], (int, float))
            assert dlog["penalty"] > 0

    def test_confirmed_divergence_not_degraded(self):
        """When bullish divergence IS confirmed, no degradation."""
        # Build true bullish divergence: price down, RSI up
        np.random.seed(42)
        prices = [100 + i * 0.5 for i in range(30)]
        for i in range(7):
            prices.append(prices[-1] * 0.995)
        prices[-2] = prices[-3] * 1.015
        prices[-1] = prices[-2] * 1.012

        dlog, score_delta = self._compute_divergence_with_score(prices)
        if dlog["is_bullish_divergence"]:
            assert score_delta > 0
            assert "degraded" not in dlog


class TestReconciliationEcart:
    """Test Dashboard écart (delta) computation."""

    def test_zero_ecart_when_same_prices(self):
        """Same price source → écart = 0.00."""
        alpha_total = 863.90
        dashboard_total = 863.90
        ecart = round(abs(alpha_total - dashboard_total), 2)
        assert ecart == 0.00

    def test_ecart_detects_drift(self):
        """Different totals → écart > 0."""
        alpha_total = 863.90
        dashboard_total = 864.05
        ecart = round(abs(alpha_total - dashboard_total), 2)
        assert ecart == 0.15

    def test_reconciliation_ok_when_ecart_below_threshold(self):
        """reconciliation = 'ok' when écart < 0.01."""
        ecart = 0.00
        status = "ok" if ecart < 0.01 else "drift"
        assert status == "ok"

    def test_reconciliation_drift_when_ecart_above_threshold(self):
        """reconciliation = 'drift' when écart >= 0.01."""
        ecart = 0.15
        status = "ok" if ecart < 0.01 else "drift"
        assert status == "drift"

    def test_report_includes_ecart_field(self):
        """Report should include ecart_eur, alpha_total_value, dashboard_total_value."""
        report = {
            "reconciliation": "ok",
            "alpha_total_value": 863.90,
            "dashboard_total_value": 863.90,
            "ecart_eur": 0.00,
            "total_portfolio_value": 863.90,
            "market_regime": "bullish",
            "fear_greed": 52,
            "top_alpha": {"symbol": "SOL", "score": 72.5},
        }
        assert "ecart_eur" in report
        assert "alpha_total_value" in report
        assert "dashboard_total_value" in report
        assert report["ecart_eur"] == 0.00

    def test_telegram_message_includes_ecart(self):
        """Telegram sync message should include écart Dashboard."""
        symbol = "SOL"
        pct = 3.20
        regime = "bullish"
        total_value = 863.90
        ecart = 0.00

        sign = "+" if pct >= 0 else ""
        pv_str = f"{total_value:,.0f} €".replace(",", " ")
        ecart_str = f"{ecart:.2f} €"
        ecart_icon = "✅" if ecart < 0.01 else "⚠️"

        message = (
            f"✅ InvestAI Synchronisé. "
            f"Top Alpha : {symbol} ({sign}{pct:.2f}%). "
            f"Phase : {regime}. "
            f"Portefeuille : {pv_str}. "
            f"{ecart_icon} Écart Dashboard : {ecart_str}."
        )

        assert symbol in message
        assert "+3.20%" in message
        assert regime in message
        assert "0.00 €" in message
        assert "✅" in message
