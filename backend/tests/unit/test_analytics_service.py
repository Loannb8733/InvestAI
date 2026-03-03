"""Tests for analytics service helper functions and computations.

Covers: Sharpe ratio, Sortino ratio, Calmar ratio, VaR (historical &
parametric), CVaR, max drawdown, correlation matrix edge cases,
diversification scoring, XIRR, and various helper utilities.
"""

from datetime import datetime

import numpy as np
import pytest

from app.services.analytics_service import (
    RISK_FREE_RATE,
    AnalyticsService,
    _annualized_return,
    _annualized_volatility,
    _calmar,
    _compute_returns,
    _cvar_historical,
    _daily_return_pct,
    _downside_deviation,
    _max_drawdown,
    _sharpe,
    _sortino,
    _trading_days,
    _var_historical,
    _var_parametric,
    _xirr,
)


# ---------------------------------------------------------------------------
# _compute_returns
# ---------------------------------------------------------------------------
class TestComputeReturns:
    """Tests for the _compute_returns helper."""

    def test_basic_log_returns(self):
        prices = [100.0, 110.0, 105.0]
        rets = _compute_returns(prices)
        assert len(rets) == 2
        expected_first = np.log(110.0 / 100.0)
        assert pytest.approx(rets[0], rel=1e-9) == expected_first

    def test_single_price_returns_empty(self):
        assert len(_compute_returns([100.0])) == 0

    def test_empty_prices_returns_empty(self):
        assert len(_compute_returns([])) == 0

    def test_filters_zero_and_negative_prices(self):
        prices = [100.0, 0, 110.0, -5, 120.0]
        rets = _compute_returns(prices)
        # After filtering zeros/negatives: [100, 110, 120] -> 2 returns
        assert len(rets) == 2

    def test_all_zeros_returns_empty(self):
        assert len(_compute_returns([0, 0, 0])) == 0


# ---------------------------------------------------------------------------
# _trading_days
# ---------------------------------------------------------------------------
class TestTradingDays:
    """Tests for _trading_days helper."""

    def test_stock_252(self):
        assert _trading_days("stock") == 252

    def test_etf_252(self):
        assert _trading_days("etf") == 252

    def test_crypto_365(self):
        assert _trading_days("crypto") == 365

    def test_real_estate_365(self):
        assert _trading_days("real_estate") == 365

    def test_enum_style_asset_type(self):
        from app.models.asset import AssetType

        assert _trading_days(AssetType.STOCK) == 252
        assert _trading_days(AssetType.ETF) == 252
        assert _trading_days(AssetType.CRYPTO) == 365


# ---------------------------------------------------------------------------
# Sharpe ratio
# ---------------------------------------------------------------------------
class TestSharpeRatio:
    """Tests for _sharpe calculation."""

    def test_positive_sharpe(self):
        # Annualized return 20%, volatility 15%
        result = _sharpe(20.0, 15.0)
        expected = round((20.0 - RISK_FREE_RATE * 100) / 15.0, 2)
        assert result == expected

    def test_negative_sharpe(self):
        # Return lower than risk-free rate
        result = _sharpe(1.0, 15.0)
        assert result < 0

    def test_zero_volatility_returns_zero(self):
        result = _sharpe(20.0, 0.0)
        assert result == 0.0

    def test_zero_return_with_volatility(self):
        result = _sharpe(0.0, 15.0)
        expected = round((0.0 - RISK_FREE_RATE * 100) / 15.0, 2)
        assert result == expected

    def test_very_high_return(self):
        result = _sharpe(500.0, 30.0)
        assert result > 0
        expected = round((500.0 - RISK_FREE_RATE * 100) / 30.0, 2)
        assert result == expected


# ---------------------------------------------------------------------------
# Sortino ratio
# ---------------------------------------------------------------------------
class TestSortinoRatio:
    """Tests for _sortino calculation."""

    def test_positive_sortino(self):
        result = _sortino(20.0, 10.0)
        expected = round((20.0 - RISK_FREE_RATE * 100) / 10.0, 2)
        assert result == expected

    def test_zero_downside_returns_zero(self):
        result = _sortino(20.0, 0.0)
        assert result == 0.0

    def test_negative_sortino(self):
        result = _sortino(1.0, 10.0)
        assert result < 0


# ---------------------------------------------------------------------------
# Calmar ratio
# ---------------------------------------------------------------------------
class TestCalmarRatio:
    """Tests for _calmar calculation."""

    def test_positive_calmar(self):
        result = _calmar(20.0, -10.0)
        expected = round(20.0 / 10.0, 2)
        assert result == expected

    def test_zero_drawdown_returns_zero(self):
        result = _calmar(20.0, 0.0)
        assert result == 0.0

    def test_negative_return_with_drawdown(self):
        result = _calmar(-5.0, -20.0)
        expected = round(-5.0 / 20.0, 2)
        assert result == expected


# ---------------------------------------------------------------------------
# Max Drawdown
# ---------------------------------------------------------------------------
class TestMaxDrawdown:
    """Tests for _max_drawdown calculation."""

    def test_simple_drawdown(self):
        # Peak at 100, trough at 80 -> -20%
        prices = [100, 110, 90, 80, 100]
        dd = _max_drawdown(prices)
        # Peak is 110, trough is 80 -> (80-110)/110 = -27.27%
        expected = (80 - 110) / 110 * 100
        assert pytest.approx(dd, abs=0.01) == expected

    def test_no_drawdown_monotonic_increase(self):
        prices = [100, 110, 120, 130]
        dd = _max_drawdown(prices)
        assert dd == 0.0

    def test_complete_loss(self):
        prices = [100, 50, 25, 10, 5]
        dd = _max_drawdown(prices)
        # From 100 to 5 -> -95%
        assert pytest.approx(dd, abs=0.01) == -95.0

    def test_single_price_returns_zero(self):
        assert _max_drawdown([100]) == 0.0

    def test_empty_returns_zero(self):
        assert _max_drawdown([]) == 0.0

    def test_constant_prices(self):
        prices = [50, 50, 50, 50]
        assert _max_drawdown(prices) == 0.0


# ---------------------------------------------------------------------------
# Daily return pct
# ---------------------------------------------------------------------------
class TestDailyReturnPct:
    """Tests for _daily_return_pct."""

    def test_positive_return(self):
        result = _daily_return_pct([100, 110])
        assert pytest.approx(result) == 10.0

    def test_negative_return(self):
        result = _daily_return_pct([100, 90])
        assert pytest.approx(result) == -10.0

    def test_single_price(self):
        assert _daily_return_pct([100]) == 0.0

    def test_empty_prices(self):
        assert _daily_return_pct([]) == 0.0

    def test_zero_previous_price(self):
        assert _daily_return_pct([0, 100]) == 0.0

    def test_uses_last_two_prices(self):
        # Should only look at the last two prices
        result = _daily_return_pct([50, 200, 100, 110])
        assert pytest.approx(result) == 10.0


# ---------------------------------------------------------------------------
# VaR (Historical)
# ---------------------------------------------------------------------------
class TestVaRHistorical:
    """Tests for historical VaR calculation."""

    def test_basic_var(self):
        np.random.seed(42)
        returns = np.random.normal(0.001, 0.02, 500)
        var = _var_historical(returns, 0.95)
        # VaR should be positive (represents loss) and reasonable
        assert var > 0
        assert var < 20  # Not absurdly large

    def test_too_few_data_returns_zero(self):
        returns = np.array([0.01, 0.02])
        assert _var_historical(returns) == 0.0

    def test_exactly_five_points(self):
        returns = np.array([-0.05, -0.02, 0.01, 0.03, 0.04])
        var = _var_historical(returns, 0.95)
        assert var >= 0

    def test_all_positive_returns(self):
        returns = np.array([0.01, 0.02, 0.03, 0.04, 0.05])
        var = _var_historical(returns, 0.95)
        # 5th percentile of all-positive should yield negative VaR (loss = positive)
        # but since all positive, the VaR should be negative (gain), returned as -(-) = positive
        # Actually: percentile(5%) of [0.01..0.05] > 0 so VaR = -q*100 < 0
        # wait, -q*100 where q > 0 => var < 0. It returns float, no clamp.
        # The function does: -q * 100, so with q > 0, result < 0
        # This means "no loss at 95% confidence"
        assert var < 0

    def test_all_negative_returns_high_var(self):
        returns = np.array([-0.05, -0.04, -0.03, -0.06, -0.02])
        var = _var_historical(returns, 0.95)
        assert var > 0


# ---------------------------------------------------------------------------
# VaR (Parametric)
# ---------------------------------------------------------------------------
class TestVaRParametric:
    """Tests for parametric (Gaussian) VaR calculation."""

    def test_basic_parametric_var(self):
        np.random.seed(42)
        returns = np.random.normal(0.001, 0.02, 500)
        var = _var_parametric(returns, 0.95)
        assert var > 0
        assert var < 20

    def test_too_few_data_returns_zero(self):
        returns = np.array([0.01, 0.02])
        assert _var_parametric(returns) == 0.0

    def test_consistent_with_historical_order_of_magnitude(self):
        """Parametric and historical VaR should be in the same ballpark."""
        np.random.seed(42)
        returns = np.random.normal(0.0, 0.02, 1000)
        var_h = _var_historical(returns, 0.95)
        var_p = _var_parametric(returns, 0.95)
        # Both should be positive and within 2x of each other
        assert var_h > 0
        assert var_p > 0
        ratio = max(var_h, var_p) / max(min(var_h, var_p), 1e-10)
        assert ratio < 3

    def test_zero_volatility_returns_zero_or_positive(self):
        """Constant returns => zero std => VaR should be 0 (clamped)."""
        returns = np.array([0.01, 0.01, 0.01, 0.01, 0.01])
        var = _var_parametric(returns)
        # With zero sigma, var = -(mu + z*0) = -mu
        # mu = 0.01 => var = -0.01*100 = -1 => clamped to 0
        assert var == 0.0


# ---------------------------------------------------------------------------
# CVaR (Expected Shortfall)
# ---------------------------------------------------------------------------
class TestCVaRHistorical:
    """Tests for conditional VaR calculation."""

    def test_cvar_gte_var(self):
        """CVaR should always be >= VaR (it includes the tail)."""
        np.random.seed(42)
        returns = np.random.normal(-0.001, 0.03, 500)
        var = _var_historical(returns, 0.95)
        cvar = _cvar_historical(returns, 0.95)
        assert cvar >= var

    def test_too_few_data_returns_zero(self):
        returns = np.array([0.01])
        assert _cvar_historical(returns) == 0.0


# ---------------------------------------------------------------------------
# Annualized volatility
# ---------------------------------------------------------------------------
class TestAnnualizedVolatility:
    """Tests for _annualized_volatility."""

    def test_basic_volatility(self):
        np.random.seed(42)
        returns = np.random.normal(0, 0.02, 100)
        vol = _annualized_volatility(returns)
        # With daily std ~0.02 and 365 days: ~0.02 * sqrt(365) * 100 ~ 38%
        assert 20 < vol < 60

    def test_zero_returns_zero_vol(self):
        returns = np.array([0.0, 0.0, 0.0, 0.0, 0.0])
        vol = _annualized_volatility(returns)
        assert vol == 0.0

    def test_single_return_is_zero(self):
        returns = np.array([0.01])
        vol = _annualized_volatility(returns)
        assert vol == 0.0

    def test_empty_returns_zero(self):
        returns = np.array([])
        vol = _annualized_volatility(returns)
        assert vol == 0.0

    def test_stock_annualization_uses_252(self):
        returns = np.array([0.01, -0.01, 0.01, -0.01, 0.01])
        vol_stock = _annualized_volatility(returns, asset_type="stock")
        vol_crypto = _annualized_volatility(returns, asset_type="crypto")
        # Crypto uses 365, stock uses 252 => crypto vol > stock vol
        assert vol_crypto > vol_stock


# ---------------------------------------------------------------------------
# Downside deviation
# ---------------------------------------------------------------------------
class TestDownsideDeviation:
    """Tests for _downside_deviation."""

    def test_no_negative_returns(self):
        returns = np.array([0.01, 0.02, 0.03, 0.01, 0.02])
        dd = _downside_deviation(returns)
        assert dd == 0.0

    def test_all_negative_returns(self):
        returns = np.array([-0.01, -0.02, -0.03, -0.01, -0.02])
        dd = _downside_deviation(returns)
        assert dd > 0

    def test_empty_returns_zero(self):
        dd = _downside_deviation(np.array([]))
        assert dd == 0.0

    def test_single_return_zero(self):
        dd = _downside_deviation(np.array([0.01]))
        assert dd == 0.0


# ---------------------------------------------------------------------------
# Annualized return
# ---------------------------------------------------------------------------
class TestAnnualizedReturn:
    """Tests for _annualized_return."""

    def test_positive_mean_return(self):
        returns = np.array([0.001] * 100)  # ~0.1% daily log-return
        ann = _annualized_return(returns)
        # Discrete compound: (exp(0.001 * 365) - 1) * 100 ≈ 44.05%
        assert pytest.approx(ann, abs=0.1) == 44.05

    def test_empty_returns_zero(self):
        assert _annualized_return(np.array([])) == 0.0

    def test_single_return_zero(self):
        assert _annualized_return(np.array([0.01])) == 0.0


# ---------------------------------------------------------------------------
# XIRR
# ---------------------------------------------------------------------------
class TestXIRR:
    """Tests for the XIRR calculation."""

    def test_simple_investment_positive_return(self):
        """Invest 1000, get 1100 back after one year => ~10% return."""
        cashflows = [
            (datetime(2024, 1, 1), -1000),
            (datetime(2025, 1, 1), 1100),
        ]
        rate = _xirr(cashflows)
        assert rate is not None
        assert pytest.approx(rate, abs=0.01) == 0.10

    def test_simple_investment_negative_return(self):
        """Invest 1000, get 900 back => ~-10%."""
        cashflows = [
            (datetime(2024, 1, 1), -1000),
            (datetime(2025, 1, 1), 900),
        ]
        rate = _xirr(cashflows)
        assert rate is not None
        assert rate < 0

    def test_insufficient_cashflows(self):
        cashflows = [(datetime(2024, 1, 1), -1000)]
        assert _xirr(cashflows) is None

    def test_empty_cashflows(self):
        assert _xirr([]) is None


# ---------------------------------------------------------------------------
# Diversification helpers
# ---------------------------------------------------------------------------
class TestDiversificationHelpers:
    """Tests for HHI and diversification scoring."""

    def test_hhi_single_asset(self):
        allocation = {"BTC": 100.0}
        result = AnalyticsService._hhi(allocation)
        assert pytest.approx(result) == 1.0

    def test_hhi_equal_two_assets(self):
        allocation = {"BTC": 50.0, "ETH": 50.0}
        result = AnalyticsService._hhi(allocation)
        assert pytest.approx(result) == 0.5

    def test_hhi_empty(self):
        assert AnalyticsService._hhi({}) == 0

    def test_diversification_score_high(self):
        # 10 assets, 4 types, low concentration
        score = AnalyticsService._diversification_score(10, 4, 0.1)
        assert score > 60

    def test_diversification_score_low(self):
        # 1 asset, 1 type, max concentration
        score = AnalyticsService._diversification_score(1, 1, 1.0)
        assert score < 20

    def test_diversification_rating_excellent(self):
        assert AnalyticsService._diversification_rating(85) == "Excellent"

    def test_diversification_rating_bon(self):
        assert AnalyticsService._diversification_rating(65) == "Bon"

    def test_diversification_rating_moyen(self):
        assert AnalyticsService._diversification_rating(45) == "Moyen"

    def test_diversification_rating_faible(self):
        assert AnalyticsService._diversification_rating(25) == "Faible"

    def test_diversification_rating_tres_faible(self):
        assert AnalyticsService._diversification_rating(10) == "Très faible"


# ---------------------------------------------------------------------------
# Beta calculation
# ---------------------------------------------------------------------------
class TestCalcBeta:
    """Tests for the static _calc_beta method."""

    def test_identical_returns_beta_one(self):
        """Identical series should have beta ~ 1."""
        np.random.seed(42)
        returns = np.random.normal(0, 0.02, 100)
        beta = AnalyticsService._calc_beta(returns, returns)
        assert beta is not None
        assert pytest.approx(beta, abs=0.01) == 1.0

    def test_double_returns_beta_two(self):
        """Series with 2x amplitude should have beta ~ 2."""
        np.random.seed(42)
        bench = np.random.normal(0, 0.01, 100)
        asset = bench * 2
        beta = AnalyticsService._calc_beta(asset, bench)
        assert beta is not None
        assert pytest.approx(beta, abs=0.1) == 2.0

    def test_insufficient_data_returns_none(self):
        asset = np.array([0.01] * 5)
        bench = np.array([0.01] * 5)
        assert AnalyticsService._calc_beta(asset, bench) is None

    def test_zero_variance_benchmark_returns_none(self):
        bench = np.zeros(20)
        asset = np.random.normal(0, 0.01, 20)
        assert AnalyticsService._calc_beta(asset, bench) is None

    def test_negative_beta(self):
        """Inversely correlated series should have negative beta."""
        np.random.seed(42)
        bench = np.random.normal(0, 0.02, 100)
        asset = -bench * 0.5
        beta = AnalyticsService._calc_beta(asset, bench)
        assert beta is not None
        assert beta < 0


# ---------------------------------------------------------------------------
# Interpret beta
# ---------------------------------------------------------------------------
class TestInterpretBeta:
    """Tests for _interpret_beta."""

    def test_none_beta(self):
        result = AnalyticsService._interpret_beta(None)
        assert "insuffisantes" in result.lower()

    def test_very_aggressive(self):
        result = AnalyticsService._interpret_beta(2.0)
        assert "agressif" in result.lower()

    def test_neutral(self):
        result = AnalyticsService._interpret_beta(0.9)
        assert "neutre" in result.lower()

    def test_defensive(self):
        result = AnalyticsService._interpret_beta(0.5)
        assert "défensif" in result.lower()

    def test_inversely_correlated(self):
        result = AnalyticsService._interpret_beta(-0.5)
        assert "inverse" in result.lower()


# ---------------------------------------------------------------------------
# Empty analytics
# ---------------------------------------------------------------------------
class TestEmptyAnalytics:
    """Tests for _empty_analytics."""

    def test_all_fields_zero(self):
        svc = object.__new__(AnalyticsService)
        result = svc._empty_analytics()
        assert result.total_value == 0
        assert result.sharpe_ratio == 0
        assert result.asset_count == 0
        assert result.assets == []
        assert result.best_performer is None
        assert result.worst_performer is None


# ---------------------------------------------------------------------------
# _build_portfolio_var_parametric
# ---------------------------------------------------------------------------
class TestBuildPortfolioVarParametric:
    """Tests for _build_portfolio_var_parametric."""

    def test_with_sufficient_data(self):
        svc = object.__new__(AnalyticsService)
        np.random.seed(42)
        port_returns = np.random.normal(-0.001, 0.02, 200)
        result = svc._build_portfolio_var_parametric(port_returns, 100000.0)

        assert "var_95_historical_pct" in result
        assert "var_95_parametric_pct" in result
        assert "var_95_historical_eur" in result
        assert "var_95_parametric_eur" in result
        assert "cvar_95_pct" in result
        assert "cvar_95_eur" in result
        # VaR in EUR should be proportional to total value
        assert result["var_95_historical_eur"] > 0
        assert result["var_95_parametric_eur"] > 0

    def test_with_insufficient_data(self):
        svc = object.__new__(AnalyticsService)
        port_returns = np.array([0.01, 0.02])
        result = svc._build_portfolio_var_parametric(port_returns, 100000.0)
        assert result["var_95_historical_pct"] == 0.0
        assert result["var_95_parametric_pct"] == 0.0
