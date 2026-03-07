"""Goal projection service.

Computes Required Monthly Contribution (RMC), probability of reaching
the goal, and projected growth curves using Monte Carlo simulation
adapted to the current market regime and goal strategy type.
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ── Return assumptions by strategy × regime ─────────────────────

# Annual return assumptions (conservative / moderate / aggressive)
# adjusted by regime (bear = lower, bull = higher)
_ANNUAL_RETURN = {
    # (strategy, vol_regime) → expected annual return
    ("conservative", "stress"): 0.02,
    ("conservative", "normal"): 0.05,
    ("conservative", "low"): 0.07,
    ("moderate", "stress"): 0.04,
    ("moderate", "normal"): 0.08,
    ("moderate", "low"): 0.12,
    ("aggressive", "stress"): 0.06,
    ("aggressive", "normal"): 0.12,
    ("aggressive", "low"): 0.20,
}

_ANNUAL_VOL = {
    ("conservative", "stress"): 0.10,
    ("conservative", "normal"): 0.08,
    ("conservative", "low"): 0.06,
    ("moderate", "stress"): 0.25,
    ("moderate", "normal"): 0.18,
    ("moderate", "low"): 0.14,
    ("aggressive", "stress"): 0.40,
    ("aggressive", "normal"): 0.30,
    ("aggressive", "low"): 0.22,
}


@dataclass
class ProjectionPoint:
    """A single point on the projection curve."""

    month: int
    date_label: str  # "Mar 2026"
    projected_p50: float
    projected_p25: float
    projected_p75: float
    target_line: float


@dataclass
class GoalProjection:
    """Complete goal projection result."""

    goal_id: str
    current_amount: float
    target_amount: float
    months_remaining: int
    rmc: float  # Required Monthly Contribution
    rmc_with_returns: float  # RMC factoring in expected returns
    probability_on_track: float  # 0-100%
    probability_label: str  # "Forte", "Moyenne", "Faible"
    alert_message: Optional[str] = None
    regime_label: str = ""
    strategy_type: str = "moderate"
    gold_shield_active: bool = False
    eta_date: Optional[str] = None  # "Mar 2027" — estimated time of arrival
    eta_months: int = 0
    gold_shield_advice: Optional[str] = None
    curve: List[ProjectionPoint] = field(default_factory=list)


class GoalProjectionService:
    """Compute goal trajectory projections with regime awareness."""

    def compute_rmc(
        self,
        current: float,
        target: float,
        months: int,
        annual_return: float = 0.0,
    ) -> float:
        """Required Monthly Contribution to reach target.

        Without returns: simple (target - current) / months.
        With returns: uses future value of annuity formula.
        """
        gap = target - current
        if gap <= 0 or months <= 0:
            return 0.0

        if annual_return <= 0:
            return round(gap / months, 2)

        # Monthly rate
        r = annual_return / 12
        # Future value of current amount after `months` periods
        fv_current = current * (1 + r) ** months
        # Remaining gap after growth
        remaining = target - fv_current
        if remaining <= 0:
            return 0.0  # Growth alone covers it

        # FV of annuity formula: PMT = FV * r / ((1+r)^n - 1)
        rmc = remaining * r / ((1 + r) ** months - 1)
        return round(max(rmc, 0), 2)

    def compute_probability(
        self,
        current: float,
        target: float,
        months: int,
        monthly_contribution: float,
        annual_return: float,
        annual_vol: float,
        num_simulations: int = 5000,
        coupon_schedule: Optional[Dict[int, float]] = None,
    ) -> float:
        """Monte Carlo probability of reaching target by deadline.

        Returns probability 0-100%.
        coupon_schedule: optional dict mapping month_index → extra income.
        """
        if current >= target:
            return 100.0
        if months <= 0:
            return 0.0

        r_monthly = annual_return / 12
        vol_monthly = annual_vol / math.sqrt(12)

        rng = np.random.default_rng(42)
        # Simulate monthly returns
        returns = rng.normal(r_monthly, vol_monthly, size=(num_simulations, months))

        # Portfolio value path with contributions
        values = np.full(num_simulations, current)
        for m in range(months):
            extra = coupon_schedule.get(m, 0.0) if coupon_schedule else 0.0
            values = values * (1 + returns[:, m]) + monthly_contribution + extra

        # Count successes
        successes = np.sum(values >= target)
        return round(float(successes / num_simulations) * 100, 1)

    def build_curve(
        self,
        current: float,
        target: float,
        months: int,
        monthly_contribution: float,
        annual_return: float,
        annual_vol: float,
        start_date: date,
        coupon_schedule: Optional[Dict[int, float]] = None,
    ) -> List[ProjectionPoint]:
        """Build projection curve with p25/p50/p75 bands."""
        if months <= 0:
            return []

        r_monthly = annual_return / 12
        vol_monthly = annual_vol / math.sqrt(12)
        num_sims = 2000

        rng = np.random.default_rng(42)
        returns = rng.normal(r_monthly, vol_monthly, size=(num_sims, months))

        # Simulate all paths
        all_values = np.full((num_sims, months + 1), current)
        for m in range(months):
            extra = coupon_schedule.get(m, 0.0) if coupon_schedule else 0.0
            all_values[:, m + 1] = all_values[:, m] * (1 + returns[:, m]) + monthly_contribution + extra

        # Sample monthly points (max 36 points for UI)
        step = max(1, months // 36)
        points: List[ProjectionPoint] = []

        for m in range(0, months + 1, step):
            month_date = date(
                start_date.year + (start_date.month + m - 1) // 12,
                (start_date.month + m - 1) % 12 + 1,
                1,
            )
            col = all_values[:, min(m, months)]
            target_at_m = current + (target - current) * m / months if months > 0 else target

            points.append(
                ProjectionPoint(
                    month=m,
                    date_label=month_date.strftime("%b %Y"),
                    projected_p50=round(float(np.median(col)), 2),
                    projected_p25=round(float(np.percentile(col, 25)), 2),
                    projected_p75=round(float(np.percentile(col, 75)), 2),
                    target_line=round(target_at_m, 2),
                )
            )

        # Always include the last month
        if points[-1].month != months:
            end_date = date(
                start_date.year + (start_date.month + months - 1) // 12,
                (start_date.month + months - 1) % 12 + 1,
                1,
            )
            col = all_values[:, months]
            points.append(
                ProjectionPoint(
                    month=months,
                    date_label=end_date.strftime("%b %Y"),
                    projected_p50=round(float(np.median(col)), 2),
                    projected_p25=round(float(np.percentile(col, 25)), 2),
                    projected_p75=round(float(np.percentile(col, 75)), 2),
                    target_line=round(float(target), 2),
                )
            )

        return points

    def calculate_eta(
        self,
        current: float,
        target: float,
        monthly_contribution: float,
        annual_return: float,
        annual_vol: float,
        max_months: int = 120,
    ) -> tuple[int, float]:
        """Estimate months to reach target with ≥50% probability.

        Uses binary search over months to find the earliest month where
        Monte Carlo probability >= 50%.

        Returns (months_to_target, probability_at_that_month).
        If unreachable within max_months, returns (max_months, best_prob).
        """
        if current >= target:
            return (0, 100.0)

        # Binary search for the first month where prob >= 50%
        lo, hi = 1, max_months
        best_months = max_months
        best_prob = 0.0

        while lo <= hi:
            mid = (lo + hi) // 2
            prob = self.compute_probability(
                current,
                target,
                mid,
                monthly_contribution,
                annual_return,
                annual_vol,
                num_simulations=3000,
            )
            if prob >= 50.0:
                best_months = mid
                best_prob = prob
                hi = mid - 1
            else:
                best_prob = max(best_prob, prob)
                lo = mid + 1

        # Refine: get exact prob at best_months
        if best_months < max_months:
            best_prob = self.compute_probability(
                current,
                target,
                best_months,
                monthly_contribution,
                annual_return,
                annual_vol,
                num_simulations=5000,
            )

        return (best_months, best_prob)

    async def project_goal(
        self,
        db: AsyncSession,
        user_id: str,
        goal_id: str,
        current_amount: float,
        target_amount: float,
        deadline: Optional[date],
        strategy_type: str = "moderate",
        monthly_contribution: float = 0.0,
        coupon_income: Optional[List[dict]] = None,
    ) -> GoalProjection:
        """Full goal projection with regime awareness."""
        # Get current regime
        vol_regime = "normal"
        regime_label = "Normal"
        try:
            from app.services.smart_insights_service import smart_insights_service

            vol_regime = await smart_insights_service.get_current_vol_regime(db, user_id)
            regime_label = {"stress": "Bear", "normal": "Normal", "low": "Bull"}.get(vol_regime, "Normal")
        except Exception:
            pass

        # Lookup return/vol for this strategy × regime
        annual_return = _ANNUAL_RETURN.get((strategy_type, vol_regime), 0.08)
        annual_vol = _ANNUAL_VOL.get((strategy_type, vol_regime), 0.18)

        # Gold Shield: conservative strategy in bear uses lower vol (gold-weighted)
        gold_shield = strategy_type == "conservative" and vol_regime == "stress"
        if gold_shield:
            annual_vol *= 0.7  # Gold dampens volatility further

        # Months remaining
        if deadline:
            delta = (deadline - date.today()).days
            months = max(int(delta / 30.44), 1)
        else:
            months = 60  # Default 5 years

        # RMC without returns (simple linear)
        rmc_simple = self.compute_rmc(current_amount, target_amount, months)
        # RMC with expected returns
        rmc_returns = self.compute_rmc(current_amount, target_amount, months, annual_return)

        # Use the RMC as contribution if user hasn't specified one
        effective_contribution = monthly_contribution if monthly_contribution > 0 else rmc_returns

        # Build coupon schedule: {month_index: total_amount}
        coupon_schedule: Optional[Dict[int, float]] = None
        if coupon_income:
            coupon_schedule = {}
            for entry in coupon_income:
                m = entry.get("month_offset", 0)
                coupon_schedule[m] = coupon_schedule.get(m, 0.0) + entry.get("amount", 0.0)

        # Probability
        prob = self.compute_probability(
            current_amount,
            target_amount,
            months,
            effective_contribution,
            annual_return,
            annual_vol,
            coupon_schedule=coupon_schedule,
        )

        # Probability label
        if prob >= 75:
            prob_label = "Forte"
        elif prob >= 40:
            prob_label = "Moyenne"
        else:
            prob_label = "Faible"

        # ETA: estimated time to target
        eta_months_val, eta_prob = self.calculate_eta(
            current_amount,
            target_amount,
            effective_contribution,
            annual_return,
            annual_vol,
        )
        eta_date_obj = date(
            date.today().year + (date.today().month + eta_months_val - 1) // 12,
            (date.today().month + eta_months_val - 1) % 12 + 1,
            1,
        )
        eta_date_str = eta_date_obj.strftime("%b %Y")

        # Alert message
        alert = None
        if prob < 50 and deadline:
            deadline_str = deadline.strftime("%B %Y")
            alert = f"DCA insuffisant pour atteindre la cible en {deadline_str}. Contribution mensuelle recommandée : {rmc_returns:.0f} €."
        elif prob < 75 and deadline:
            alert = (
                f"Objectif atteignable mais incertain. Augmentez votre DCA à {rmc_returns:.0f} €/mois pour sécuriser."
            )

        # Gold Shield advice when prob < 50% in bear regime
        gold_shield_advice = None
        if prob < 50 and vol_regime == "stress":
            gold_shield_advice = "Renforcer l'exposition Or (Bouclier) pour stabiliser la trajectoire."

        # Projection curve
        curve = self.build_curve(
            current_amount,
            target_amount,
            months,
            effective_contribution,
            annual_return,
            annual_vol,
            start_date=date.today(),
            coupon_schedule=coupon_schedule,
        )

        return GoalProjection(
            goal_id=goal_id,
            current_amount=current_amount,
            target_amount=target_amount,
            months_remaining=months,
            rmc=rmc_simple,
            rmc_with_returns=rmc_returns,
            probability_on_track=prob,
            probability_label=prob_label,
            alert_message=alert,
            regime_label=regime_label,
            strategy_type=strategy_type,
            gold_shield_active=gold_shield,
            eta_date=eta_date_str,
            eta_months=eta_months_val,
            gold_shield_advice=gold_shield_advice,
            curve=curve,
        )


# Singleton
goal_projection_service = GoalProjectionService()
