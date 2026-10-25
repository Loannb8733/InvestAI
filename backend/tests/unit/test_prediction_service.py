"""Tests des fonctions d'appui des prédictions : recommandation, volatilité, replis."""

import pytest

from app.domains.portfolio.models import AssetType
from app.domains.predictions.fallbacks import daily_volatility, empty_prediction, random_walk_forecast
from app.domains.predictions.recommendation import generate_recommendation
from app.domains.predictions.types import PricePrediction


class TestGenerateRecommendation:
    def test_strong_bullish(self):
        assert "haussière forte" in generate_recommendation("bullish", 60, 100, 90, 110)

    def test_disclaimer_always_appended(self):
        # Trust & Safety: every recommendation must carry the non-advice disclaimer.
        assert "ne constitue pas un conseil en" in generate_recommendation("bullish", 60, 100, 90, 110)

    def test_no_prescriptive_imperatives(self):
        # Recommendations must read as observations, not orders.
        regime = {"dominant_regime": "bearish", "confidence": 0.9}
        result = generate_recommendation("bearish", 60, 100, 90, 110, regime_info=regime).lower()
        for verb in ("accumulez", "prenez des profits", "renforcez", "placez des stop", "laissez courir"):
            assert verb not in result, f"prescriptive verb leaked: {verb}"

    def test_weak_bullish(self):
        assert "légèrement haussière" in generate_recommendation("bullish", 30, 100, 90, 110)

    def test_strong_bearish(self):
        assert "baissière forte" in generate_recommendation("bearish", 60, 100, 90, 110)

    def test_weak_bearish(self):
        assert "légèrement baissière" in generate_recommendation("bearish", 30, 100, 90, 110)

    def test_neutral(self):
        assert "neutre" in generate_recommendation("neutral", 10, 100, 90, 110)


class TestDailyVolatility:
    async def test_crypto_highest_volatility(self):
        crypto = await daily_volatility("BTC", AssetType.CRYPTO)
        stock = await daily_volatility("AAPL", AssetType.STOCK)
        etf = await daily_volatility("SPY", AssetType.ETF)
        assert crypto > stock > etf

    async def test_unknown_type_default(self):
        assert await daily_volatility("X", "unknown_type") == 0.02


@pytest.mark.usefixtures("db_session")
class TestRandomWalkForecast:
    async def test_returns_correct_structure(self):
        predictions, trend, strength = await random_walk_forecast("BTC", 100.0, AssetType.CRYPTO, 7)
        assert len(predictions) == 7
        assert trend in ("bullish", "bearish", "neutral")
        assert isinstance(strength, float)

    async def test_predictions_have_required_keys(self):
        predictions, _, _ = await random_walk_forecast("AAPL", 100.0, AssetType.STOCK, 3)
        for p in predictions:
            assert {"date", "price", "confidence_low", "confidence_high"} <= set(p)

    async def test_no_negative_prices(self):
        # Run multiple times to reduce randomness
        for _ in range(10):
            predictions, _, _ = await random_walk_forecast("BTC", 1.0, AssetType.CRYPTO, 7)
            for p in predictions:
                assert p["confidence_low"] >= 0


class TestEmptyPrediction:
    def test_returns_prediction_object(self):
        result = empty_prediction("BTC")
        assert isinstance(result, PricePrediction)
        assert result.symbol == "BTC"
        assert result.current_price == 0
        assert result.predictions == []
        assert result.trend == "neutral"
        assert result.model_used == "none"
