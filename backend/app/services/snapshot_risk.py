"""Portfolio risk metrics (TWR volatility, Sharpe, drawdown, VaR, beta, alpha,
HHI, stress test), extracted from snapshot_service as a mixin.

SnapshotService mixes in SnapshotRiskMixin; these methods read the value series
via ``self.build_portfolio_value_series`` (provided by the base class through
the MRO) and operate on the returned history / allocation lists.
"""

from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.finance_constants import CALENDAR_DAYS_PER_YEAR, RISK_FREE_RATE

logger = logging.getLogger(__name__)


class SnapshotRiskMixin:
    """Mixed into SnapshotService — portfolio risk analytics."""

    def _estimate_interval_days(self, history: List[Dict]) -> float:
        """Estimate the average interval in days between data points.

        When data is subsampled (e.g. every 3 or 7 days), we need the actual
        interval to correctly annualize volatility and Sharpe.
        """
        if len(history) < 2:
            return 1.0

        try:
            from datetime import datetime as _dt

            dates = []
            for h in history:
                fd = h.get("full_date")
                if fd:
                    dates.append(_dt.fromisoformat(fd))
            if len(dates) >= 2:
                total_days = (dates[-1] - dates[0]).days
                intervals = len(dates) - 1
                if intervals > 0 and total_days > 0:
                    return total_days / intervals
        except Exception as exc:
            logger.debug("Failed to estimate data-point interval, defaulting to 1 day: %s", exc)

        return 1.0

    def _compute_twr_log_returns(self, history: List[Dict]) -> List[float]:
        """Compute Time-Weighted log returns that exclude capital flow effects.

        Standard log returns (log(V_t / V_{t-1})) are inflated by DCA buys
        because new money in looks like positive returns. TWR adjusts for this:
        return_t = log((V_t - capital_flow_t) / V_{t-1})
        where capital_flow_t = net_capital_t - net_capital_{t-1}.

        Returns are clipped to [-1.0, +1.0] per interval to prevent outliers
        (e.g. from missing price data) from inflating volatility/Sharpe.
        """
        # Max log-return per interval: ±1.0 ≈ ±172% gain / -63% loss
        MAX_LOG_RETURN = 1.0

        returns = []
        for i in range(1, len(history)):
            prev_value = history[i - 1]["value"]
            curr_value = history[i]["value"]
            if prev_value <= 0:
                continue
            # Exclude capital flows (buys add capital, sells remove it)
            prev_net_cap = history[i - 1].get("net_capital", 0)
            curr_net_cap = history[i].get("net_capital", 0)
            capital_flow = curr_net_cap - prev_net_cap
            adjusted_value = curr_value - capital_flow
            # Skip interval when TWR is undefined (adjusted value non-positive)
            if adjusted_value <= 0:
                continue
            log_return = math.log(adjusted_value / prev_value)
            # Clip extreme returns to prevent single outliers from dominating
            log_return = max(-MAX_LOG_RETURN, min(MAX_LOG_RETURN, log_return))
            returns.append(log_return)
        return returns

    async def calculate_volatility(
        self,
        db: AsyncSession,
        user_id: str,
        days: int = 30,
        history: Optional[List[Dict]] = None,
    ) -> float:
        """Calculate portfolio volatility based on TWR log returns.

        Uses Time-Weighted Returns (excludes capital flow effects) and
        annualization adjusted for the actual data interval.
        """
        if history is None:
            history = await self.build_portfolio_value_series(db, user_id, days)

        if len(history) < 2:
            return 0.0

        returns = self._compute_twr_log_returns(history)

        if len(returns) < 2:
            return 0.0

        # Annualized volatility: std(returns) * sqrt(periods_per_year)
        # periods_per_year = 365 / interval_days (adjusts for subsampled data)
        interval_days = self._estimate_interval_days(history)
        periods_per_year = CALENDAR_DAYS_PER_YEAR / interval_days

        n = len(returns)
        mean_return = sum(returns) / n
        variance = sum((r - mean_return) ** 2 for r in returns) / (n - 1)  # ddof=1
        volatility = math.sqrt(variance) * math.sqrt(periods_per_year) * 100

        return round(volatility, 2)

    async def calculate_sharpe_ratio(
        self,
        db: AsyncSession,
        user_id: str,
        days: int = 30,
        risk_free_rate: float = RISK_FREE_RATE,
        history: Optional[List[Dict]] = None,
        roi_annualized: Optional[float] = None,
    ) -> float:
        """Calculate Sharpe ratio for the portfolio.

        Uses roi_annualized (CAGR) as the return component to ensure
        consistency: a negative CAGR always produces a negative Sharpe.
        Volatility is computed from TWR log returns.
        """
        if history is None:
            history = await self.build_portfolio_value_series(db, user_id, days)

        if len(history) < 2:
            return 0.0

        returns = self._compute_twr_log_returns(history)

        if len(returns) < 2:
            return 0.0

        # Volatility from TWR log returns (annualized)
        interval_days = self._estimate_interval_days(history)
        periods_per_year = CALENDAR_DAYS_PER_YEAR / interval_days

        n = len(returns)
        mean_return = sum(returns) / n
        variance = sum((r - mean_return) ** 2 for r in returns) / (n - 1)  # ddof=1
        volatility = math.sqrt(variance) * math.sqrt(periods_per_year)

        if volatility == 0:
            return 0.0

        # Use roi_annualized (CAGR) when available for return component.
        # This ensures a portfolio with negative CAGR always gets a negative Sharpe.
        if roi_annualized is not None:
            annualized_return = roi_annualized / 100.0  # convert percentage to decimal
        else:
            annualized_return = mean_return * periods_per_year

        sharpe = (annualized_return - risk_free_rate) / volatility
        return round(sharpe, 2)

    async def calculate_max_drawdown(
        self,
        db: AsyncSession,
        user_id: str,
        days: int = 30,
        history: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        Calculate Maximum Drawdown (MDD) - the largest peak-to-trough decline.
        Returns both the percentage and the period.
        """
        if history is None:
            history = await self.build_portfolio_value_series(db, user_id, days)

        if len(history) < 2:
            return {"max_drawdown_percent": 0.0, "peak_date": None, "trough_date": None}

        values = [h["value"] for h in history]
        dates = [h.get("full_date", h["date"]) for h in history]

        max_drawdown = 0.0
        peak_value = values[0]
        peak_idx = 0
        max_peak_idx = 0
        max_trough_idx = 0

        for i, value in enumerate(values):
            if value > peak_value:
                peak_value = value
                peak_idx = i

            drawdown = (peak_value - value) / peak_value if peak_value > 0 else 0

            if drawdown > max_drawdown:
                max_drawdown = drawdown
                max_peak_idx = peak_idx
                max_trough_idx = i

        return {
            "max_drawdown_percent": round(max_drawdown * 100, 2),
            "peak_date": dates[max_peak_idx] if max_drawdown > 0 else None,
            "trough_date": dates[max_trough_idx] if max_drawdown > 0 else None,
            "peak_value": values[max_peak_idx] if max_drawdown > 0 else None,
            "trough_value": values[max_trough_idx] if max_drawdown > 0 else None,
        }

    async def calculate_var(
        self,
        db: AsyncSession,
        user_id: str,
        days: int = 30,
        confidence_level: float = 0.95,
        current_value: float = 0,
        history: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        Calculate Value at Risk (VaR) using historical simulation method.
        Returns the potential loss at the given confidence level.
        """
        if history is None:
            history = await self.build_portfolio_value_series(db, user_id, days)

        if len(history) < 5:
            return {
                "var_percent": 0.0,
                "var_amount": 0.0,
                "confidence_level": confidence_level,
            }

        # Use TWR log returns (consistent with Sharpe/Volatility calculations)
        # Raw simple returns are distorted by capital flows (DCA buys appear as gains)
        returns = self._compute_twr_log_returns(history)

        if not returns:
            return {
                "var_percent": 0.0,
                "var_amount": 0.0,
                "confidence_level": confidence_level,
            }

        # Sort returns and find the percentile
        sorted_returns = sorted(returns)
        n = len(sorted_returns)
        # For VaR at 95%, we want the 5th percentile of returns
        # With < 20 returns, we don't have enough data for reliable VaR
        if n < 20:
            return {
                "var_percent": 0.0,
                "var_amount": 0.0,
                "confidence_level": confidence_level,
            }
        # Use ceil-based index for correct empirical percentile
        var_index = max(0, math.ceil((1 - confidence_level) * n) - 1)
        # VaR is a LOSS: only a negative return counts. If the 5th-percentile
        # return is positive (no loss in the left tail), VaR is 0 — abs() would
        # wrongly invent a loss.
        var_percent = max(0.0, -sorted_returns[var_index]) * 100

        # Calculate VaR amount
        var_amount = current_value * (var_percent / 100) if current_value > 0 else 0

        return {
            "var_percent": round(var_percent, 2),
            "var_amount": round(var_amount, 2),
            "confidence_level": confidence_level,
        }

    async def calculate_beta(
        self,
        portfolio_returns: List[float],
        benchmark_returns: List[float],
    ) -> float:
        """
        Calculate Beta - measure of portfolio's volatility relative to the market.
        Beta > 1: More volatile than market
        Beta < 1: Less volatile than market
        Beta = 1: Same volatility as market
        """
        if len(portfolio_returns) < 2 or len(benchmark_returns) < 2:
            return 1.0

        # Ensure same length
        min_len = min(len(portfolio_returns), len(benchmark_returns))
        portfolio_returns = portfolio_returns[:min_len]
        benchmark_returns = benchmark_returns[:min_len]

        # Calculate means
        port_mean = sum(portfolio_returns) / len(portfolio_returns)
        bench_mean = sum(benchmark_returns) / len(benchmark_returns)

        # Calculate covariance and variance (unbiased, ddof=1, consistent with Sharpe/Volatility)
        n = len(portfolio_returns)
        covariance = sum((p - port_mean) * (b - bench_mean) for p, b in zip(portfolio_returns, benchmark_returns)) / (
            n - 1
        )

        bench_variance = sum((b - bench_mean) ** 2 for b in benchmark_returns) / (n - 1)

        if bench_variance == 0:
            return 1.0

        beta = covariance / bench_variance
        return round(beta, 2)

    async def calculate_alpha(
        self,
        portfolio_return: float,
        benchmark_return: float,
        beta: float,
        risk_free_rate: float = RISK_FREE_RATE,
    ) -> float:
        """
        Calculate Alpha - excess return compared to benchmark.
        Alpha > 0: Outperforming the benchmark
        Alpha < 0: Underperforming the benchmark
        """
        # Jensen's Alpha = Portfolio Return - [Risk Free Rate + Beta * (Benchmark Return - Risk Free Rate)]
        expected_return = risk_free_rate + beta * (benchmark_return - risk_free_rate)
        alpha = portfolio_return - expected_return
        return round(alpha * 100, 2)  # Return as percentage

    def calculate_hhi(self, allocations: List[Dict]) -> Dict:
        """
        Calculate Herfindahl-Hirschman Index (HHI) for portfolio concentration.
        HHI ranges from 0 to 10000:
        - < 1500: Diversified
        - 1500-2500: Moderate concentration
        - > 2500: High concentration
        """
        if not allocations:
            return {
                "hhi": 0,
                "interpretation": "N/A",
                "is_concentrated": False,
                "top_concentration": None,
            }

        # Calculate HHI (sum of squared market shares)
        total_value = sum(a.get("value", 0) or a.get("current_value", 0) for a in allocations)
        if total_value == 0:
            return {
                "hhi": 0,
                "interpretation": "N/A",
                "is_concentrated": False,
                "top_concentration": None,
            }

        hhi = 0
        max_concentration = 0
        top_asset = None

        for a in allocations:
            value = a.get("value", 0) or a.get("current_value", 0)
            share = (value / total_value) * 100
            hhi += share**2

            if share > max_concentration:
                max_concentration = share
                top_asset = a.get("symbol", "Unknown")

        hhi = round(hhi, 0)

        # Interpretation
        if hhi < 1500:
            interpretation = "Bien diversifié"
            is_concentrated = False
        elif hhi < 2500:
            interpretation = "Concentration modérée"
            is_concentrated = False
        else:
            interpretation = "Forte concentration"
            is_concentrated = True

        return {
            "hhi": hhi,
            "interpretation": interpretation,
            "is_concentrated": is_concentrated,
            "top_asset": top_asset,
            "top_concentration": round(max_concentration, 1),
        }

    def calculate_stress_test(self, current_value: float, allocations: List[Dict], scenario_drop: float = 0.20) -> Dict:
        """
        Calculate portfolio value under stress scenario.
        Default scenario: 20% market drop.
        """
        if current_value == 0:
            return {
                "scenario_name": f"Correction -{int(scenario_drop * 100)}%",
                "current_value": 0,
                "stressed_value": 0,
                "potential_loss": 0,
                "potential_loss_percent": scenario_drop * 100,
            }

        # Simple stress test: apply uniform drop
        # More sophisticated: apply different drops per asset class
        stressed_value = current_value * (1 - scenario_drop)
        potential_loss = current_value - stressed_value

        return {
            "scenario_name": f"Correction -{int(scenario_drop * 100)}%",
            "current_value": round(current_value, 2),
            "stressed_value": round(stressed_value, 2),
            "potential_loss": round(potential_loss, 2),
            "potential_loss_percent": round(scenario_drop * 100, 1),
        }

    async def get_all_risk_metrics(
        self,
        db: AsyncSession,
        user_id: str,
        current_value: float,
        allocations: List[Dict],
        days: int = 30,
        history: Optional[List[Dict]] = None,
        roi_annualized: Optional[float] = None,
    ) -> Dict:
        """Get all risk metrics in one call (builds price series once)."""
        # Build portfolio value series once and share across all metric functions
        if history is None:
            history = await self.build_portfolio_value_series(db, user_id, days)
        volatility = await self.calculate_volatility(db, user_id, days, history=history)
        sharpe = await self.calculate_sharpe_ratio(db, user_id, days, history=history, roi_annualized=roi_annualized)
        mdd = await self.calculate_max_drawdown(db, user_id, days, history=history)
        var = await self.calculate_var(db, user_id, days, 0.95, current_value, history=history)
        hhi = self.calculate_hhi(allocations)
        stress_20 = self.calculate_stress_test(current_value, allocations, 0.20)
        stress_40 = self.calculate_stress_test(current_value, allocations, 0.40)

        return {
            "volatility": volatility,
            "sharpe_ratio": sharpe,
            "max_drawdown": mdd,
            "var_95": var,
            "concentration": hhi,
            "stress_test_20": stress_20,
            "stress_test_40": stress_40,
        }


# Singleton instance
