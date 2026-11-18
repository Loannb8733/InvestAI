"""La lecture Alpha × Cycle reste de l'information générale.

Contrat vérifié :
1. Chaque cellule de la matrice donne une tonalité (favorable, neutre, défavorable) et un constat descriptif.
2. Aucun constat ne contient de verbe d'action (acheter, vendre, alléger…) ni de montant.
3. Les lignes produites n'exposent ni action, ni impact chiffré, ni montant à engager.
4. Le résumé compte les tonalités et colle aux lignes.
5. En marché global baissier, une configuration favorable sans divergence RSI est ramenée à neutre.
"""

import re

import pytest

from app.domains.predictions.strategy_map import (
    FAVORABLE,
    NEUTRAL,
    STRATEGY_MATRIX,
    TONES,
    UNFAVORABLE,
    strategy_map,
)

ADVICE_WORDS = re.compile(
    r"\b(achat|achetez|acheter|vendre|vendez|vente|allég|prendre profits|prenez|renforcer|renforcez|accumuler|"
    r"accumulez|sortir|sécuriser|investir|investissez|DCA|stop-loss)\b",
    re.IGNORECASE,
)


class TestStrategyMatrix:
    def test_every_cell_is_a_tone_and_a_description(self) -> None:
        for key, (tone, description) in STRATEGY_MATRIX.items():
            assert tone in TONES, key
            assert isinstance(description, str) and description, key

    def test_no_cell_tells_the_user_what_to_do(self) -> None:
        for key, (_tone, description) in STRATEGY_MATRIX.items():
            assert not ADVICE_WORDS.search(description), f"{key}: « {description} » formule une consigne"
            assert "€" not in description and "%" not in description, f"{key}: montant ou pourcentage"

    def test_all_12_core_cells_exist(self) -> None:
        for alpha in ("high", "medium", "low"):
            for regime in ("bottom", "bearish", "bullish", "top"):
                assert (alpha, regime) in STRATEGY_MATRIX

    @pytest.mark.parametrize(
        ("key", "tone"),
        [
            (("high", "bottom"), FAVORABLE),
            (("medium", "bottom"), FAVORABLE),
            (("low", "top"), UNFAVORABLE),
            (("high", "top"), UNFAVORABLE),
            (("high", "bullish"), NEUTRAL),
        ],
    )
    def test_reference_cells_keep_their_reading(self, key: tuple[str, str], tone: str) -> None:
        assert STRATEGY_MATRIX[key][0] == tone


def _alpha(*scores: tuple[str, float]) -> dict[str, object]:
    return {
        "all_scores": [
            {"symbol": sym, "score": score, "value": 1000.0, "weight_pct": 10.0, "reasons": []} for sym, score in scores
        ],
        "total_portfolio_value": 10_000.0,
    }


def _cycle(dominant: str, per_asset: dict[str, str]) -> dict[str, object]:
    return {
        "market_regime": {"dominant_regime": dominant},
        "per_asset": [{"symbol": s, "regime_6phase": r, "confidence": 0.7} for s, r in per_asset.items()],
        "fear_greed": 40,
    }


class TestStrategyMapRows:
    def test_rows_expose_no_action_amount_or_impact(self) -> None:
        result = strategy_map(_alpha(("BTC", 95.0), ("ETH", 10.0)), _cycle("bullish", {"BTC": "bottom", "ETH": "top"}))
        for row in result["rows"]:
            assert row["tone"] in TONES
            for forbidden in ("action", "impact_pct", "impact_eur", "order_eur", "trailing_stop"):
                assert forbidden not in row

    def test_summary_counts_tones(self) -> None:
        result = strategy_map(
            _alpha(("BTC", 95.0), ("ETH", 10.0), ("SOL", 50.0)),
            _cycle("bullish", {"BTC": "bottom", "ETH": "top", "SOL": "markup"}),
        )
        tones = [row["tone"] for row in result["rows"]]
        assert result["summary"] == {
            "favorable": tones.count(FAVORABLE),
            "neutral": tones.count(NEUTRAL),
            "unfavorable": tones.count(UNFAVORABLE),
        }

    def test_bear_market_without_divergence_tones_down_favorable(self) -> None:
        result = strategy_map(_alpha(("BTC", 99.0)), _cycle("bearish", {"BTC": "bottom"}))
        row = result["rows"][0]
        assert row["tone"] == NEUTRAL
        assert "divergence RSI non confirmée" in row["description"]

    def test_bear_market_with_divergence_keeps_favorable(self) -> None:
        alpha = _alpha(("BTC", 99.0))
        alpha["all_scores"][0]["reasons"] = [{"label": "Divergence Haussière", "detail": "RSI"}]  # type: ignore[index]
        result = strategy_map(alpha, _cycle("bearish", {"BTC": "bottom"}))
        assert result["rows"][0]["tone"] == FAVORABLE
