"""Tests for prediction service helper methods."""

from datetime import datetime

import numpy as np
import pytest

from app.ml.forecaster import PriceForecaster
from app.services.prediction_service import PredictionService, PricePrediction


class TestGenerateRecommendation:
    """Tests for _generate_recommendation."""

    @pytest.fixture
    def svc(self):
        """Create service without initializing external dependencies."""
        svc = object.__new__(PredictionService)
        return svc

    def test_strong_bullish(self, svc):
        result = svc._generate_recommendation("bullish", 60, 100, 90, 110)
        assert "haussière forte" in result
        assert "renforcer" in result

    def test_weak_bullish(self, svc):
        result = svc._generate_recommendation("bullish", 30, 100, 90, 110)
        assert "légèrement haussière" in result

    def test_strong_bearish(self, svc):
        result = svc._generate_recommendation("bearish", 60, 100, 90, 110)
        assert "baissière forte" in result

    def test_weak_bearish(self, svc):
        result = svc._generate_recommendation("bearish", 30, 100, 90, 110)
        assert "légèrement baissière" in result

    def test_neutral(self, svc):
        result = svc._generate_recommendation("neutral", 10, 100, 90, 110)
        assert "neutre" in result


class TestGetDailyVolatility:
    """Tests for _get_daily_volatility."""

    @pytest.fixture
    def svc(self):
        svc = object.__new__(PredictionService)
        return svc

    def test_crypto_highest_volatility(self, svc):
        from app.models.asset import AssetType
        crypto = svc._get_daily_volatility(AssetType.CRYPTO)
        stock = svc._get_daily_volatility(AssetType.STOCK)
        etf = svc._get_daily_volatility(AssetType.ETF)
        assert crypto > stock > etf

    def test_unknown_type_default(self, svc):
        result = svc._get_daily_volatility("unknown_type")
        assert result == 0.02


class TestRandomWalkFallback:
    """Tests for _random_walk_fallback."""

    @pytest.fixture
    def svc(self):
        svc = object.__new__(PredictionService)
        return svc

    def test_returns_correct_structure(self, svc):
        from app.models.asset import AssetType
        predictions, trend, strength = svc._random_walk_fallback(100.0, AssetType.CRYPTO, 7)
        assert len(predictions) == 7
        assert trend in ("bullish", "bearish", "neutral")
        assert isinstance(strength, float)

    def test_predictions_have_required_keys(self, svc):
        from app.models.asset import AssetType
        predictions, _, _ = svc._random_walk_fallback(100.0, AssetType.STOCK, 3)
        for p in predictions:
            assert "date" in p
            assert "price" in p
            assert "confidence_low" in p
            assert "confidence_high" in p

    def test_no_negative_prices(self, svc):
        from app.models.asset import AssetType
        # Run multiple times to reduce randomness
        for _ in range(10):
            predictions, _, _ = svc._random_walk_fallback(1.0, AssetType.CRYPTO, 7)
            for p in predictions:
                assert p["confidence_low"] >= 0


class TestEmptyPrediction:
    """Tests for _empty_prediction."""

    @pytest.fixture
    def svc(self):
        svc = object.__new__(PredictionService)
        return svc

    def test_returns_prediction_object(self, svc):
        result = svc._empty_prediction("BTC")
        assert isinstance(result, PricePrediction)
        assert result.symbol == "BTC"
        assert result.current_price == 0
        assert result.predictions == []
        assert result.trend == "neutral"
        assert result.model_used == "none"
