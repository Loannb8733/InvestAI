"""Tests for regime mutation alert service.

Covers:
- Alert message formatting (old → new regime parameters)
- Redis state transitions (seed, unchanged, mutation)
- Gold shield recommendation per regime
- alpha_threshold / risk_multiplier delta display
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ml.regime_detector import RegimeConfig
from app.services.regime_alert_service import RegimeAlertService

# ── Message Formatting ───────────────────────────────────────────


class TestFormatMutationAlert:
    """Verify alert content includes all required trading parameters."""

    def setup_method(self):
        self.svc = RegimeAlertService()

    def test_bear_to_bull_message(self):
        """Transition from bearish → bullish should show expansion parameters."""
        msg = self.svc.format_mutation_alert("bearish", "bullish")
        assert "MUTATION DE CYCLE" in msg
        assert "BEARISH" in msg
        assert "BULLISH" in msg
        # New risk multiplier
        assert "×1.5" in msg
        # Old risk multiplier
        assert "×0.5" in msg
        # Alpha threshold change
        assert "60" in msg  # new bull threshold
        assert "85" in msg  # old bear threshold
        # Gold shield: low relevance in bull → ALLÉGER
        assert "ALLÉGER" in msg

    def test_bull_to_bear_message(self):
        """Transition from bullish → bearish should show survival parameters."""
        msg = self.svc.format_mutation_alert("bullish", "bearish")
        assert "×0.5" in msg  # new bear multiplier
        assert "×1.5" in msg  # old bull multiplier
        assert "RENFORCER" in msg  # gold shield high in bear
        assert "Mode Survie" in msg

    def test_same_tier_transition(self):
        """Transition between sub-phases (bottom → accumulation) still alerts."""
        msg = self.svc.format_mutation_alert("bottom", "accumulation")
        assert "BOTTOM" in msg
        assert "ACCUMULATION" in msg
        assert "Mode Accumulation" in msg

    def test_risk_direction_arrows(self):
        """Arrow should indicate risk increase (↑) or decrease (↓)."""
        msg_up = self.svc.format_mutation_alert("bearish", "bullish")
        assert "↑" in msg_up
        msg_down = self.svc.format_mutation_alert("bullish", "bearish")
        assert "↓" in msg_down

    def test_gold_shield_maintain_neutral(self):
        """Neutral regimes should recommend MAINTENIR for gold."""
        msg = self.svc.format_mutation_alert("bearish", "bottom")
        assert "MAINTENIR" in msg  # bottom has gold_relevance="medium"

    def test_message_is_html(self):
        """Alert should be HTML formatted for Telegram."""
        msg = self.svc.format_mutation_alert("bearish", "bullish")
        assert "<b>" in msg
        assert "<i>" in msg

    def test_all_regime_pairs_produce_valid_message(self):
        """Every possible regime pair should produce a non-empty message."""
        regimes = ["bearish", "markdown", "bottom", "accumulation", "markup", "bullish", "topping", "top"]
        for old in regimes:
            for new in regimes:
                if old == new:
                    continue
                msg = self.svc.format_mutation_alert(old, new)
                assert len(msg) > 100, f"{old} → {new} produced too short message"
                assert "MUTATION DE CYCLE" in msg


# ── Trading Parameters Correctness ───────────────────────────────


class TestTradingParameters:
    """Verify RegimeConfig values match spec across regimes."""

    @pytest.mark.parametrize(
        "regime,expected_mult,expected_alpha,expected_gold",
        [
            ("bearish", 0.5, 85, "high"),
            ("markdown", 0.5, 85, "high"),
            ("bottom", 0.7, 75, "medium"),
            ("accumulation", 0.8, 70, "medium"),
            ("bullish", 1.5, 60, "low"),
            ("markup", 1.5, 60, "low"),
            ("topping", 0.8, 75, "medium"),
            ("top", 0.8, 75, "medium"),
        ],
    )
    def test_regime_config_values(self, regime, expected_mult, expected_alpha, expected_gold):
        cfg = RegimeConfig.from_regime(regime)
        assert cfg.risk_multiplier == expected_mult, f"{regime}: risk_multiplier"
        assert cfg.alpha_threshold == expected_alpha, f"{regime}: alpha_threshold"
        assert cfg.gold_relevance == expected_gold, f"{regime}: gold_relevance"


# ── State Machine (Redis transitions) ────────────────────────────


class TestCheckAndAlert:
    """Test the full check_and_alert flow with mocked Redis & detection."""

    def setup_method(self):
        self.svc = RegimeAlertService()

    @pytest.mark.asyncio
    async def test_first_run_seeds_cache(self):
        """First run (no Redis key) should seed without alerting."""
        self.svc._get_current_regime = AsyncMock(return_value="bullish")
        self.svc._get_last_regime = AsyncMock(return_value=None)
        self.svc._set_last_regime = AsyncMock()

        result = await self.svc.check_and_alert()
        assert result["status"] == "seed"
        assert result["regime"] == "bullish"
        self.svc._set_last_regime.assert_awaited_once_with("bullish")

    @pytest.mark.asyncio
    async def test_unchanged_regime_no_alert(self):
        """Same regime should return unchanged, no Telegram sent."""
        self.svc._get_current_regime = AsyncMock(return_value="bearish")
        self.svc._get_last_regime = AsyncMock(return_value="bearish")
        self.svc._set_last_regime = AsyncMock()

        result = await self.svc.check_and_alert()
        assert result["status"] == "unchanged"

    @pytest.mark.asyncio
    async def test_mutation_sends_alerts(self):
        """Regime change should send Telegram to all enabled users."""
        self.svc._get_current_regime = AsyncMock(return_value="bullish")
        self.svc._get_last_regime = AsyncMock(return_value="bearish")
        self.svc._set_last_regime = AsyncMock()

        # Mock DB + Telegram
        mock_user = MagicMock()
        mock_user.id = "user-123"
        mock_user.telegram_chat_id = "12345"

        with patch("app.services.regime_alert_service.AsyncSessionLocal") as mock_session_cls, patch(
            "app.services.regime_alert_service.telegram_service"
        ) as mock_tg:
            # Setup async context manager
            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_user]
            mock_db.execute = AsyncMock(return_value=mock_result)
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_tg.send_smart_alert = AsyncMock(return_value={"ok": True})

            result = await self.svc.check_and_alert()

        assert result["status"] == "mutation"
        assert result["old_regime"] == "bearish"
        assert result["new_regime"] == "bullish"
        assert result["users_notified"] == 1
        mock_tg.send_smart_alert.assert_awaited_once()
        call_kwargs = mock_tg.send_smart_alert.call_args.kwargs
        assert call_kwargs["priority"] == "critical"
        assert call_kwargs["alert_type"] == "regime_mutation"
        assert "MUTATION DE CYCLE" in call_kwargs["message"]

    @pytest.mark.asyncio
    async def test_detection_failure_skips(self):
        """If regime detection fails, return skip."""
        self.svc._get_current_regime = AsyncMock(return_value=None)

        result = await self.svc.check_and_alert()
        assert result["status"] == "skip"
