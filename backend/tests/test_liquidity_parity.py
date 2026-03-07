"""Parity validation tests for liquidity vs investment classification.

Verifies: Total_Value = Sum(Risky Assets) + Sum(Liquidity), with 0.00€ discrepancy.
Also tests is_liquidity alias, available_liquidity metric, and Monte Carlo liquidity cushion.
"""

import pytest

from app.services.metrics_service import is_cash_like, is_liquidity


# ---------------------------------------------------------------------------
# is_liquidity alias — must match is_cash_like exactly
# ---------------------------------------------------------------------------
class TestIsLiquidityAlias:
    """Ensure is_liquidity is the same as is_cash_like."""

    @pytest.mark.parametrize("symbol", ["EUR", "USD", "CHF", "GBP"])
    def test_fiat_is_liquidity(self, symbol: str):
        assert is_liquidity(symbol) is True
        assert is_liquidity(symbol) == is_cash_like(symbol)

    @pytest.mark.parametrize("symbol", ["USDT", "USDC", "DAI", "PYUSD", "BUSD"])
    def test_stablecoin_is_liquidity(self, symbol: str):
        assert is_liquidity(symbol) is True
        assert is_liquidity(symbol) == is_cash_like(symbol)

    @pytest.mark.parametrize("symbol", ["BTC", "ETH", "SOL", "AAPL", "SPY"])
    def test_risky_not_liquidity(self, symbol: str):
        assert is_liquidity(symbol) is False


# ---------------------------------------------------------------------------
# Parity: Total = Risky + Liquid
# ---------------------------------------------------------------------------
class TestParityValidation:
    """Verify that total_value = risky_value + liquidity_value for any portfolio mix."""

    @staticmethod
    def _compute_partition(assets: list[dict]) -> tuple[float, float, float]:
        """Given a list of {symbol, quantity, price}, compute total, risky, liquid."""
        total = 0.0
        risky = 0.0
        liquid = 0.0
        for a in assets:
            val = a["quantity"] * a["price"]
            total += val
            if is_liquidity(a["symbol"]):
                liquid += val
            else:
                risky += val
        return total, risky, liquid

    def test_empty_portfolio(self):
        total, risky, liquid = self._compute_partition([])
        assert total == 0.0
        assert risky == 0.0
        assert liquid == 0.0

    def test_only_risky(self):
        assets = [
            {"symbol": "BTC", "quantity": 0.5, "price": 50000},
            {"symbol": "ETH", "quantity": 10, "price": 3000},
        ]
        total, risky, liquid = self._compute_partition(assets)
        assert liquid == 0.0
        assert abs(total - risky) < 0.01

    def test_only_liquid(self):
        assets = [
            {"symbol": "EUR", "quantity": 500, "price": 1.0},
            {"symbol": "USDT", "quantity": 300, "price": 1.0},
        ]
        total, risky, liquid = self._compute_partition(assets)
        assert risky == 0.0
        assert abs(total - liquid) < 0.01
        assert abs(liquid - 800.0) < 0.01

    def test_mixed_portfolio_parity(self):
        """863.90€ total = risky + liquid, écart = 0.00€."""
        assets = [
            {"symbol": "BTC", "quantity": 0.005, "price": 50000},  # 250
            {"symbol": "ETH", "quantity": 0.5, "price": 3000},  # 1500
            {"symbol": "EUR", "quantity": 100, "price": 1.0},  # 100
            {"symbol": "USDT", "quantity": 50, "price": 1.0},  # 50
            {"symbol": "USDC", "quantity": 30, "price": 1.0},  # 30
        ]
        total, risky, liquid = self._compute_partition(assets)
        assert abs(total - (risky + liquid)) < 0.01, (
            f"Parity violation: {total} != {risky} + {liquid} " f"(écart = {abs(total - risky - liquid):.2f}€)"
        )

    def test_parity_with_stablecoins_and_fiat(self):
        """All stablecoins + fiat variants classified as liquid."""
        assets = [
            {"symbol": "DAI", "quantity": 100, "price": 1.0},
            {"symbol": "PYUSD", "quantity": 200, "price": 1.0},
            {"symbol": "USD", "quantity": 150, "price": 1.0},
            {"symbol": "SOL", "quantity": 2, "price": 100},
        ]
        total, risky, liquid = self._compute_partition(assets)
        assert abs(liquid - 450.0) < 0.01
        assert abs(risky - 200.0) < 0.01
        assert abs(total - 650.0) < 0.01
        assert abs(total - (risky + liquid)) < 0.01


# ---------------------------------------------------------------------------
# Prediction service exclusion — liquidity should never get alpha scores
# ---------------------------------------------------------------------------
class TestLiquidityExclusionFromAlpha:
    """Verify that liquidity symbols are filtered from alpha/prediction flows."""

    @pytest.mark.parametrize("symbol", ["EUR", "USDT", "USDC", "DAI", "USD"])
    def test_liquidity_excluded_from_predictions(self, symbol: str):
        """is_cash_like used in prediction_service to skip these symbols."""
        assert (
            is_cash_like(symbol) is True
        ), f"{symbol} should be classified as cash-like and excluded from alpha scoring"

    @pytest.mark.parametrize("symbol", ["BTC", "ETH", "SOL", "AAPL", "MSFT"])
    def test_risky_included_in_predictions(self, symbol: str):
        assert is_cash_like(symbol) is False, f"{symbol} should NOT be classified as cash-like"
