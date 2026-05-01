"""Tests for metrics service calculations.

Covers: asset metrics (gain/loss, current value), ROI, CAGR,
fiat/stablecoin classification, and edge cases (empty data, single point, zero invested).
"""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.services.metrics_service import (
    FIAT_SYMBOLS,
    STABLECOIN_SYMBOLS,
    MetricsService,
    is_cash_like,
    is_fiat,
    is_stablecoin,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def metrics_service():
    """Create a MetricsService instance."""
    return MetricsService()


def _make_asset(symbol="BTC", quantity="1.0", avg_buy_price="30000.0", asset_type_val="crypto"):
    """Build a mock Asset object."""
    from app.models.asset import AssetType

    asset = MagicMock()
    asset.symbol = symbol
    asset.name = symbol
    asset.quantity = Decimal(quantity)
    asset.avg_buy_price = Decimal(avg_buy_price)
    asset.asset_type = AssetType(asset_type_val)
    asset.id = "mock-asset-id"
    return asset


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------
class TestClassificationHelpers:
    """Tests for is_fiat, is_stablecoin, is_cash_like."""

    def test_is_fiat_eur(self):
        assert is_fiat("EUR") is True

    def test_is_fiat_usd(self):
        assert is_fiat("USD") is True

    def test_is_fiat_case_insensitive(self):
        assert is_fiat("eur") is True
        assert is_fiat("Usd") is True

    def test_is_fiat_crypto_symbol(self):
        assert is_fiat("BTC") is False

    def test_is_stablecoin_usdt(self):
        assert is_stablecoin("USDT") is True

    def test_is_stablecoin_usdc(self):
        assert is_stablecoin("USDC") is True

    def test_is_stablecoin_dai(self):
        assert is_stablecoin("DAI") is True

    def test_is_stablecoin_btc_false(self):
        assert is_stablecoin("BTC") is False

    def test_is_cash_like_fiat(self):
        assert is_cash_like("EUR") is True

    def test_is_cash_like_stablecoin(self):
        assert is_cash_like("USDT") is True

    def test_is_cash_like_crypto(self):
        assert is_cash_like("BTC") is False

    def test_all_fiat_symbols_recognized(self):
        for sym in FIAT_SYMBOLS:
            assert is_fiat(sym) is True

    def test_all_stablecoin_symbols_recognized(self):
        for sym in STABLECOIN_SYMBOLS:
            assert is_stablecoin(sym) is True


# ---------------------------------------------------------------------------
# get_asset_metrics
# ---------------------------------------------------------------------------
class TestGetAssetMetrics:
    """Tests for get_asset_metrics."""

    @pytest.mark.asyncio
    async def test_with_current_price_gain(self, metrics_service):
        asset = _make_asset(quantity="2.0", avg_buy_price="100.0")
        result = await metrics_service.get_asset_metrics(asset, current_price=Decimal("150"))

        assert result["quantity"] == 2.0
        assert result["avg_buy_price"] == 100.0
        assert result["total_invested"] == 200.0
        assert result["current_price"] == 150.0
        assert result["current_value"] == 300.0
        assert result["gain_loss"] == 100.0
        assert pytest.approx(result["gain_loss_percent"]) == 50.0

    @pytest.mark.asyncio
    async def test_with_current_price_loss(self, metrics_service):
        asset = _make_asset(quantity="2.0", avg_buy_price="100.0")
        result = await metrics_service.get_asset_metrics(asset, current_price=Decimal("50"))

        assert result["current_value"] == 100.0
        assert result["gain_loss"] == -100.0
        assert pytest.approx(result["gain_loss_percent"]) == -50.0

    @pytest.mark.asyncio
    async def test_without_current_price(self, metrics_service):
        asset = _make_asset(quantity="2.0", avg_buy_price="100.0")
        result = await metrics_service.get_asset_metrics(asset, current_price=None)

        assert result["current_price"] is None
        assert result["current_value"] == 200.0  # Falls back to total_invested
        assert result["gain_loss"] == 0.0
        assert result["gain_loss_percent"] == 0.0

    @pytest.mark.asyncio
    async def test_zero_quantity(self, metrics_service):
        asset = _make_asset(quantity="0.0", avg_buy_price="100.0")
        result = await metrics_service.get_asset_metrics(asset, current_price=Decimal("150"))

        assert result["quantity"] == 0.0
        assert result["total_invested"] == 0.0
        assert result["current_value"] == 0.0
        assert result["gain_loss"] == 0.0
        assert result["gain_loss_percent"] == 0.0

    @pytest.mark.asyncio
    async def test_zero_avg_buy_price(self, metrics_service):
        """When avg_buy_price is 0 (e.g., airdrop), gain_loss_percent should be 0."""
        asset = _make_asset(quantity="10.0", avg_buy_price="0.0")
        result = await metrics_service.get_asset_metrics(asset, current_price=Decimal("5.0"))

        assert result["total_invested"] == 0.0
        assert result["current_value"] == 50.0
        assert result["gain_loss"] == 50.0
        assert result["gain_loss_percent"] == 0.0  # Cannot divide by 0

    @pytest.mark.asyncio
    async def test_fractional_quantities(self, metrics_service):
        """Handle crypto-style fractional quantities."""
        asset = _make_asset(quantity="0.00050000", avg_buy_price="45000.12345678")
        result = await metrics_service.get_asset_metrics(asset, current_price=Decimal("50000"))

        assert result["quantity"] == 0.0005
        assert result["current_value"] == pytest.approx(25.0)

    @pytest.mark.asyncio
    async def test_current_price_passed_as_float(self, metrics_service):
        """current_price should be cast from float to Decimal internally."""
        asset = _make_asset(quantity="1.0", avg_buy_price="100.0")
        result = await metrics_service.get_asset_metrics(asset, current_price=150.0)

        assert result["current_price"] == 150.0
        assert result["current_value"] == 150.0

    @pytest.mark.asyncio
    async def test_actual_invested_takes_priority_over_buy_pra(self, metrics_service):
        """FIFO actual_invested must override buy_pra for G/L so that assets bought
        at different prices on different exchanges aren't blended incorrectly."""
        # Kraken PAXG: 0.003 units bought at 3200€ → actual invested = 9.6€
        # Blended symbol buy_pra = 2550€ (contaminated by a cheaper exchange)
        asset = _make_asset(quantity="0.003", avg_buy_price="3200.0")
        result = await metrics_service.get_asset_metrics(
            asset,
            current_price=Decimal("2850"),
            actual_invested=9.6,
            buy_pra=2550.0,
        )

        assert pytest.approx(result["total_invested"], rel=1e-4) == 9.6
        assert pytest.approx(result["avg_buy_price"], rel=1e-2) == 3200.0
        assert pytest.approx(result["current_value"], rel=1e-4) == 8.55
        assert pytest.approx(result["gain_loss"], rel=1e-4) == 8.55 - 9.6

    @pytest.mark.asyncio
    async def test_buy_pra_used_as_fallback_when_no_actual_invested(self, metrics_service):
        """buy_pra should be the fallback when FIFO actual_invested is unavailable."""
        asset = _make_asset(quantity="2.0", avg_buy_price="50.0")
        result = await metrics_service.get_asset_metrics(
            asset,
            current_price=Decimal("80"),
            actual_invested=None,
            buy_pra=100.0,
        )

        assert result["total_invested"] == 200.0
        assert result["avg_buy_price"] == 100.0
        assert result["current_value"] == 160.0
        assert result["gain_loss"] == -40.0

    @pytest.mark.asyncio
    async def test_actual_invested_zero_gains_treated_as_free_tokens(self, metrics_service):
        """When actual_invested=0 (all free/airdrop), gain_loss equals current_value."""
        asset = _make_asset(quantity="5.0", avg_buy_price="0.0")
        result = await metrics_service.get_asset_metrics(
            asset,
            current_price=Decimal("10"),
            actual_invested=0.0,
            buy_pra=None,
        )

        assert result["total_invested"] == 0.0
        assert result["gain_loss"] == 50.0
        assert result["gain_loss_percent"] == 0.0


# ---------------------------------------------------------------------------
# ROI calculation
# ---------------------------------------------------------------------------
class TestCalculateROI:
    """Tests for calculate_roi."""

    @pytest.mark.asyncio
    async def test_positive_roi(self, metrics_service):
        roi = await metrics_service.calculate_roi(Decimal("1000"), Decimal("1500"))
        assert pytest.approx(roi) == 50.0

    @pytest.mark.asyncio
    async def test_negative_roi(self, metrics_service):
        roi = await metrics_service.calculate_roi(Decimal("1000"), Decimal("800"))
        assert pytest.approx(roi) == -20.0

    @pytest.mark.asyncio
    async def test_zero_invested_returns_zero(self, metrics_service):
        roi = await metrics_service.calculate_roi(Decimal("0"), Decimal("500"))
        assert roi == 0.0

    @pytest.mark.asyncio
    async def test_negative_invested_returns_zero(self, metrics_service):
        roi = await metrics_service.calculate_roi(Decimal("-100"), Decimal("200"))
        assert roi == 0.0

    @pytest.mark.asyncio
    async def test_breakeven_roi(self, metrics_service):
        roi = await metrics_service.calculate_roi(Decimal("1000"), Decimal("1000"))
        assert roi == 0.0

    @pytest.mark.asyncio
    async def test_double_value_roi(self, metrics_service):
        roi = await metrics_service.calculate_roi(Decimal("1000"), Decimal("2000"))
        assert pytest.approx(roi) == 100.0


# ---------------------------------------------------------------------------
# CAGR calculation
# ---------------------------------------------------------------------------
class TestCalculateCAGR:
    """Tests for calculate_cagr."""

    @pytest.mark.asyncio
    async def test_positive_cagr(self, metrics_service):
        # 1000 -> 1100 over 1 year => 10%
        cagr = await metrics_service.calculate_cagr(Decimal("1000"), Decimal("1100"), 1.0)
        assert pytest.approx(cagr, abs=0.01) == 10.0

    @pytest.mark.asyncio
    async def test_multi_year_cagr(self, metrics_service):
        # 1000 -> 2000 over 2 years => ~41.42%
        cagr = await metrics_service.calculate_cagr(Decimal("1000"), Decimal("2000"), 2.0)
        expected = (pow(2.0, 0.5) - 1) * 100
        assert pytest.approx(cagr, abs=0.01) == expected

    @pytest.mark.asyncio
    async def test_zero_initial_returns_zero(self, metrics_service):
        cagr = await metrics_service.calculate_cagr(Decimal("0"), Decimal("1000"), 2.0)
        assert cagr == 0.0

    @pytest.mark.asyncio
    async def test_zero_years_returns_zero(self, metrics_service):
        cagr = await metrics_service.calculate_cagr(Decimal("1000"), Decimal("1500"), 0.0)
        assert cagr == 0.0

    @pytest.mark.asyncio
    async def test_negative_initial_returns_zero(self, metrics_service):
        cagr = await metrics_service.calculate_cagr(Decimal("-100"), Decimal("200"), 1.0)
        assert cagr == 0.0

    @pytest.mark.asyncio
    async def test_negative_years_returns_zero(self, metrics_service):
        cagr = await metrics_service.calculate_cagr(Decimal("1000"), Decimal("1500"), -1.0)
        assert cagr == 0.0

    @pytest.mark.asyncio
    async def test_same_value_zero_cagr(self, metrics_service):
        cagr = await metrics_service.calculate_cagr(Decimal("1000"), Decimal("1000"), 5.0)
        assert cagr == 0.0

    @pytest.mark.asyncio
    async def test_fractional_year(self, metrics_service):
        # 6 months
        cagr = await metrics_service.calculate_cagr(Decimal("1000"), Decimal("1050"), 0.5)
        assert cagr > 0
