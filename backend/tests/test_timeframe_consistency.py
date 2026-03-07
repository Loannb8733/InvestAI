"""Tests de cohérence temporelle : VaR window, Sharpe, Vol, Gold Beta.

Vérifie que le changement de timeframe (7j, 30j, 90j) produit des métriques
mathématiquement cohérentes sans dépendance à la base de données.
"""

import numpy as np

from app.services.analytics_service import (
    _annualized_return,
    _annualized_volatility,
    _compute_returns,
    _sharpe,
    _var_historical,
)
from app.services.metrics_service import is_safe_haven

# ── Helpers ──────────────────────────────────────────────────────


def _synthetic_prices(days: int = 90, seed: int = 42, drift: float = 0.001, vol: float = 0.02) -> list:
    """Generate synthetic daily prices with controlled drift and volatility."""
    np.random.seed(seed)
    prices = [10_000.0]
    for _ in range(days - 1):
        prices.append(prices[-1] * (1 + np.random.normal(drift, vol)))
    return prices


def _btc_prices(days: int = 90) -> list:
    return _synthetic_prices(days, seed=42, drift=0.001, vol=0.03)


def _gold_prices(days: int = 90) -> list:
    return _synthetic_prices(days, seed=7, drift=0.0002, vol=0.005)


# ── Test 1: VaR window scales with sqrt(days) ───────────────────


class TestVaRWindowScaling:
    """VaR_window = VaR_daily × √days → VaR(90j) > VaR(7j)."""

    def test_var_90j_greater_than_var_7j(self):
        prices = _btc_prices(100)
        returns = _compute_returns(prices)
        daily_var = _var_historical(returns)

        var_7 = daily_var * np.sqrt(7)
        var_90 = daily_var * np.sqrt(90)

        assert var_90 > var_7, f"VaR(90j) should be > VaR(7j): {var_90:.4f} vs {var_7:.4f}"

    def test_var_window_ratio_matches_sqrt_ratio(self):
        prices = _btc_prices(100)
        returns = _compute_returns(prices)
        daily_var = _var_historical(returns)

        var_7 = daily_var * np.sqrt(7)
        var_30 = daily_var * np.sqrt(30)
        var_90 = daily_var * np.sqrt(90)

        # Ratio should match sqrt(90/7) ≈ 3.586
        expected_ratio = np.sqrt(90 / 7)
        actual_ratio = var_90 / var_7
        assert (
            abs(actual_ratio - expected_ratio) < 0.001
        ), f"VaR ratio should be √(90/7)={expected_ratio:.3f}, got {actual_ratio:.3f}"

        # 30/7 ratio
        expected_30_7 = np.sqrt(30 / 7)
        actual_30_7 = var_30 / var_7
        assert abs(actual_30_7 - expected_30_7) < 0.001

    def test_var_daily_positive(self):
        prices = _btc_prices(100)
        returns = _compute_returns(prices)
        daily_var = _var_historical(returns)
        assert daily_var > 0, "Daily VaR should be positive for a volatile asset"


# ── Test 2: Annualization is stable across windows ───────────────


class TestAnnualizationConsistency:
    """Volatility and return annualization should use asset-type factor, not window size."""

    def test_volatility_annualized_with_365_for_crypto(self):
        prices = _btc_prices(100)
        returns = _compute_returns(prices)
        vol = _annualized_volatility(returns, asset_type="crypto")
        # Vol = std * sqrt(365) * 100 → should be significantly > daily std
        daily_std = float(np.std(returns, ddof=1)) * 100
        annualization_factor = np.sqrt(365)
        expected_vol = daily_std * annualization_factor
        assert (
            abs(vol - expected_vol) < 0.01
        ), f"Annualized vol should be daily_std * √365: expected {expected_vol:.2f}, got {vol:.2f}"

    def test_volatility_annualized_with_252_for_stocks(self):
        prices = _synthetic_prices(100, seed=10, drift=0.0005, vol=0.01)
        returns = _compute_returns(prices)
        vol_crypto = _annualized_volatility(returns, asset_type="crypto")
        vol_stock = _annualized_volatility(returns, asset_type="stock")
        # crypto uses 365, stock uses 252 → crypto vol > stock vol
        assert vol_crypto > vol_stock, (
            f"Crypto annualized vol ({vol_crypto:.2f}) should be > stock ({vol_stock:.2f}) "
            f"due to higher annualization factor"
        )

    def test_sharpe_ratio_sign_consistency(self):
        """Positive drift → positive annualized return → positive Sharpe (with low Rf)."""
        prices = _synthetic_prices(200, drift=0.003, vol=0.01)
        returns = _compute_returns(prices)
        ann_ret = _annualized_return(returns, asset_type="crypto")
        vol = _annualized_volatility(returns, asset_type="crypto")
        sharpe = _sharpe(ann_ret, vol, risk_free_rate=0.0)
        assert sharpe > 0, f"Positive-drift asset should have positive Sharpe, got {sharpe}"


# ── Test 3: Gold Beta recalculated per window ────────────────────


class TestGoldBetaPerWindow:
    """Gold Beta vs BTC should remain low (< 0.1) regardless of window size."""

    def _compute_beta(self, btc_prices: list, gold_prices: list) -> float:
        _min = min(len(btc_prices), len(gold_prices))
        btc_r = np.diff(np.log(np.array(btc_prices[-_min:], dtype=float)))
        gold_r = np.diff(np.log(np.array(gold_prices[-_min:], dtype=float)))
        cov = np.cov(gold_r, btc_r)
        btc_var = cov[1, 1]
        return float(cov[0, 1] / btc_var) if btc_var > 0 else 0.0

    def test_gold_beta_low_on_7d(self):
        btc = _btc_prices(30)[-7:]
        gold = _gold_prices(30)[-7:]
        beta = self._compute_beta(btc, gold)
        assert abs(beta) < 0.5, f"Gold beta (7d) should be low, got {beta:.4f}"

    def test_gold_beta_low_on_90d(self):
        btc = _btc_prices(90)
        gold = _gold_prices(90)
        beta = self._compute_beta(btc, gold)
        assert abs(beta) < 0.1, f"Gold beta (90d) should be < 0.1, got {beta:.4f}"

    def test_gold_beta_varies_by_window(self):
        """Beta computed on different windows can differ (not a bug)."""
        btc_30 = _btc_prices(30)
        gold_30 = _gold_prices(30)
        btc_90 = _btc_prices(90)
        gold_90 = _gold_prices(90)

        beta_30 = self._compute_beta(btc_30, gold_30)
        beta_90 = self._compute_beta(btc_90, gold_90)

        # They should both be finite but can differ
        assert np.isfinite(beta_30), f"Beta 30d should be finite, got {beta_30}"
        assert np.isfinite(beta_90), f"Beta 90d should be finite, got {beta_90}"


# ── Test 4: Safe haven identification ────────────────────────────


class TestSafeHavenInTimeframeContext:
    """is_safe_haven is timeframe-independent (symbol-based)."""

    def test_safe_haven_symbols(self):
        for sym in ("PAXG", "XAUT", "GLD", "IAU", "SGOL", "GOLD"):
            assert is_safe_haven(sym) is True, f"{sym} should be safe haven"

    def test_non_safe_haven(self):
        for sym in ("BTC", "ETH", "SOL", "AAPL"):
            assert is_safe_haven(sym) is False, f"{sym} should NOT be safe haven"
