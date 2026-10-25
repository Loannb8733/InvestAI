import math
from datetime import date
from typing import Any

import numpy as np
from dateutil.relativedelta import relativedelta
from numpy.typing import NDArray
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.planning.goals.assumptions import ANNUAL_RETURN, ANNUAL_VOL, current_vol_regime
from app.domains.planning.goals.months import long_month, short_month
from app.domains.planning.goals.projection_types import GoalProjection, ProjectionPoint


def _month_start(start: date, offset: int) -> date:
    return date(start.year + (start.month + offset - 1) // 12, (start.month + offset - 1) % 12 + 1, 1)


def _curve_point(month: int, month_date: date, col: NDArray[Any], target_line: float) -> ProjectionPoint:
    return ProjectionPoint(
        month=month,
        date_label=short_month(month_date),
        projected_p50=round(float(np.median(col)), 2),
        projected_p25=round(float(np.percentile(col, 25)), 2),
        projected_p75=round(float(np.percentile(col, 75)), 2),
        target_line=target_line,
    )


def _coupon_schedule(coupon_income: list[dict[str, Any]] | None) -> dict[int, float] | None:
    if not coupon_income:
        return None
    schedule: dict[int, float] = {}
    for entry in coupon_income:
        m = entry.get("month_offset", 0)
        schedule[m] = schedule.get(m, 0.0) + entry.get("amount", 0.0)
    return schedule


def _probability_label(prob: float) -> str:
    if prob >= 75:
        return "Forte"
    if prob >= 40:
        return "Moyenne"
    return "Faible"


def _alert_message(prob: float, deadline: date | None, rmc_returns: float) -> str | None:
    if prob < 50 and deadline:
        deadline_str = long_month(deadline)
        return (
            f"DCA insuffisant pour atteindre la cible en {deadline_str}. "
            f"Contribution mensuelle recommandée : {rmc_returns:.0f} €."
        )
    if prob < 75 and deadline:
        return f"Objectif atteignable mais incertain. Augmentez votre DCA à {rmc_returns:.0f} €/mois pour sécuriser."
    return None


class GoalProjectionService:
    """Trajectoire d'un objectif par Monte Carlo (graine fixe), selon la stratégie et le régime de volatilité."""

    def compute_rmc(self, current: float, target: float, months: int, annual_return: float = 0.0) -> float:
        """Effort mensuel requis : écart / mois sans rendement, sinon formule de la valeur future d'une annuité."""
        gap = target - current
        if gap <= 0 or months <= 0:
            return 0.0

        if annual_return <= 0:
            return round(gap / months, 2)

        r = annual_return / 12
        fv_current = current * (1 + r) ** months
        remaining = target - fv_current
        if remaining <= 0:
            return 0.0

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
        coupon_schedule: dict[int, float] | None = None,
    ) -> float:
        """Probabilité (0-100) d'atteindre la cible à l'échéance ; ``coupon_schedule`` : revenu ajouté par mois."""
        if current >= target:
            return 100.0
        if months <= 0:
            return 0.0

        r_monthly = annual_return / 12
        vol_monthly = annual_vol / math.sqrt(12)

        rng = np.random.default_rng(42)
        returns = rng.normal(r_monthly, vol_monthly, size=(num_simulations, months))

        values = np.full(num_simulations, current)
        for m in range(months):
            extra = coupon_schedule.get(m, 0.0) if coupon_schedule else 0.0
            values = values * (1 + returns[:, m]) + monthly_contribution + extra

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
        coupon_schedule: dict[int, float] | None = None,
    ) -> list[ProjectionPoint]:
        """Courbe p25/p50/p75 échantillonnée à 36 points au plus, dernier mois toujours inclus."""
        if months <= 0:
            return []

        r_monthly = annual_return / 12
        vol_monthly = annual_vol / math.sqrt(12)
        num_sims = 2000

        rng = np.random.default_rng(42)
        returns = rng.normal(r_monthly, vol_monthly, size=(num_sims, months))

        all_values = np.full((num_sims, months + 1), current)
        for m in range(months):
            extra = coupon_schedule.get(m, 0.0) if coupon_schedule else 0.0
            all_values[:, m + 1] = all_values[:, m] * (1 + returns[:, m]) + monthly_contribution + extra

        step = max(1, months // 36)
        points: list[ProjectionPoint] = []

        for m in range(0, months + 1, step):
            col = all_values[:, min(m, months)]
            target_at_m = current + (target - current) * m / months if months > 0 else target
            points.append(_curve_point(m, _month_start(start_date, m), col, round(target_at_m, 2)))

        if points[-1].month != months:
            col = all_values[:, months]
            points.append(_curve_point(months, _month_start(start_date, months), col, round(float(target), 2)))

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
        """Premier mois où la probabilité atteint 50 % (recherche dichotomique), avec cette probabilité ;
        ``(max_months, meilleure probabilité)`` si la cible reste hors d'atteinte."""
        if current >= target:
            return (0, 100.0)

        lo, hi = 1, max_months
        best_months = max_months
        best_prob = 0.0

        while lo <= hi:
            mid = (lo + hi) // 2
            prob = self.compute_probability(
                current, target, mid, monthly_contribution, annual_return, annual_vol, num_simulations=3000
            )
            if prob >= 50.0:
                best_months = mid
                best_prob = prob
                hi = mid - 1
            else:
                best_prob = max(best_prob, prob)
                lo = mid + 1

        if best_months < max_months:
            best_prob = self.compute_probability(
                current, target, best_months, monthly_contribution, annual_return, annual_vol, num_simulations=5000
            )

        return (best_months, best_prob)

    @staticmethod
    def _months_remaining(deadline: date | None) -> int:
        if not deadline:
            return 60
        gap = relativedelta(deadline, date.today())
        months: int = max(gap.years * 12 + gap.months, 1)
        return months

    async def project_goal(
        self,
        db: AsyncSession,
        user_id: str,
        goal_id: str,
        current_amount: float,
        target_amount: float,
        deadline: date | None,
        strategy_type: str = "moderate",
        monthly_contribution: float = 0.0,
        coupon_income: list[dict[str, Any]] | None = None,
    ) -> GoalProjection:
        """Projection complète. Les mois restants sont des mois calendaires, au moins un (FIN-07 : ``jours / 30,44``
        se trompait d'un mois dans 3 % des échéances), 60 sans échéance ; sans contribution saisie, la simulation
        utilise l'effort requis avec rendement ; le « Bouclier Or » (prudent en régime de stress) réduit la volatilité
        de 30 %."""
        vol_regime, regime_label = await current_vol_regime(db, user_id)

        annual_return = ANNUAL_RETURN.get((strategy_type, vol_regime), 0.08)
        annual_vol = ANNUAL_VOL.get((strategy_type, vol_regime), 0.18)

        gold_shield = strategy_type == "conservative" and vol_regime == "stress"
        if gold_shield:
            annual_vol *= 0.7

        months = self._months_remaining(deadline)

        rmc_simple = self.compute_rmc(current_amount, target_amount, months)
        rmc_returns = self.compute_rmc(current_amount, target_amount, months, annual_return)

        effective_contribution = monthly_contribution if monthly_contribution > 0 else rmc_returns
        coupon_schedule = _coupon_schedule(coupon_income)

        prob = self.compute_probability(
            current_amount,
            target_amount,
            months,
            effective_contribution,
            annual_return,
            annual_vol,
            coupon_schedule=coupon_schedule,
        )

        prob_label = _probability_label(prob)

        eta_months_val, _eta_prob = self.calculate_eta(
            current_amount, target_amount, effective_contribution, annual_return, annual_vol
        )
        eta_date_str = short_month(_month_start(date.today(), eta_months_val))

        alert = _alert_message(prob, deadline, rmc_returns)

        gold_shield_advice = None
        if prob < 50 and vol_regime == "stress":
            gold_shield_advice = "Renforcer l'exposition Or (Bouclier) pour stabiliser la trajectoire."

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


goal_projection_service = GoalProjectionService()
