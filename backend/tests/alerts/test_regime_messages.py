from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domains.alerts import regime
from app.ml.regime.types import RegimeConfig

REGIMES = ("bearish", "markdown", "bottom", "accumulation", "markup", "bullish", "topping", "top")


class TestMutationMessage:
    def test_bear_to_bull_shows_expansion_parameters(self) -> None:
        message = regime.mutation_message("bearish", "bullish")
        for expected in ("MUTATION DE CYCLE", "BEARISH", "BULLISH", "×0.8", "×1.5", "60", "85", "ALLÉGER"):
            assert expected in message

    def test_bull_to_bear_shows_accumulation_parameters(self) -> None:
        message = regime.mutation_message("bullish", "bearish")
        for expected in ("×1.5", "×0.8", "RENFORCER", "Mode Accumulation Actif"):
            assert expected in message

    def test_a_sub_phase_change_still_alerts(self) -> None:
        message = regime.mutation_message("bottom", "accumulation")
        for expected in ("BOTTOM", "ACCUMULATION", "Mode Accumulation"):
            assert expected in message

    def test_risk_arrow_follows_the_multiplier(self) -> None:
        """Dimensionnement à contre-courant : vers le haussier le multiplicateur baisse, vers le baissier il monte."""
        assert "↓" in regime.mutation_message("bearish", "bullish")
        assert "↑" in regime.mutation_message("bullish", "bearish")

    def test_a_neutral_regime_keeps_the_gold_shield(self) -> None:
        assert "MAINTENIR" in regime.mutation_message("bearish", "bottom")

    def test_message_is_telegram_html(self) -> None:
        message = regime.mutation_message("bearish", "bullish")
        assert "<b>" in message
        assert "<i>" in message

    def test_every_regime_pair_has_a_message(self) -> None:
        for old in REGIMES:
            for new in REGIMES:
                if old != new:
                    message = regime.mutation_message(old, new)
                    assert len(message) > 100, f"{old} → {new}"
                    assert "MUTATION DE CYCLE" in message


@pytest.mark.parametrize(
    ("name", "multiplier", "alpha", "gold"),
    [
        ("bearish", 1.5, 85, "high"),
        ("markdown", 1.5, 85, "high"),
        ("bottom", 1.8, 75, "medium"),
        ("accumulation", 1.5, 70, "medium"),
        ("bullish", 0.8, 60, "low"),
        ("markup", 0.8, 60, "low"),
        ("topping", 0.4, 75, "medium"),
        ("top", 0.4, 75, "medium"),
    ],
)
def test_regime_trading_parameters(name: str, multiplier: float, alpha: int, gold: str) -> None:
    config = RegimeConfig.from_regime(name)
    assert (config.risk_multiplier, config.alpha_threshold, config.gold_relevance) == (multiplier, alpha, gold)


def _regimes(current: str | None, last: str | None) -> tuple[AsyncMock, AsyncMock, AsyncMock]:
    return AsyncMock(return_value=current), AsyncMock(return_value=last), AsyncMock()


class TestCheckRegimeMutation:
    async def test_first_run_seeds_without_alerting(self) -> None:
        current, last, remember = _regimes("bullish", None)
        with (
            patch.object(regime, "current_regime", current),
            patch.object(regime, "last_regime", last),
            patch.object(regime, "remember_regime", remember),
        ):
            result = await regime.check_regime_mutation()
        assert result == {"status": "seed", "regime": "bullish"}
        remember.assert_awaited_once_with("bullish")

    async def test_unchanged_regime_does_not_alert(self) -> None:
        current, last, remember = _regimes("bearish", "bearish")
        with (
            patch.object(regime, "current_regime", current),
            patch.object(regime, "last_regime", last),
            patch.object(regime, "remember_regime", remember),
        ):
            result = await regime.check_regime_mutation()
        assert result["status"] == "unchanged"

    async def test_mutation_alerts_enabled_users(self) -> None:
        current, last, remember = _regimes("bullish", "bearish")
        user = MagicMock(id="user-123", telegram_chat_id="12345")
        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=[user])))
        session = MagicMock()
        session.return_value.__aenter__ = AsyncMock(return_value=db)
        session.return_value.__aexit__ = AsyncMock(return_value=False)
        telegram = MagicMock(send_smart_alert=AsyncMock(return_value={"ok": True}))
        with (
            patch.object(regime, "current_regime", current),
            patch.object(regime, "last_regime", last),
            patch.object(regime, "remember_regime", remember),
            patch.object(regime, "session_factory", session),
            patch.object(regime, "telegram_service", telegram),
        ):
            result = await regime.check_regime_mutation()
        assert result == {"status": "mutation", "old_regime": "bearish", "new_regime": "bullish", "users_notified": 1}
        sent = telegram.send_smart_alert.call_args.kwargs
        assert (sent["priority"], sent["chat_id"]) == ("critical", "12345")
        assert "MUTATION DE CYCLE" in sent["message"]

    async def test_detection_failure_skips(self) -> None:
        with patch.object(regime, "current_regime", AsyncMock(return_value=None)):
            assert (await regime.check_regime_mutation())["status"] == "skip"
