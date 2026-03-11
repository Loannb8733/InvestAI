"""Stress test service — compute degraded IRR for crowdfunding projects."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from dateutil.relativedelta import relativedelta

from app.models.crowdfunding_project import CrowdfundingProject, RepaymentType
from app.services.analytics_service import _xirr
from app.services.reconciliation_service import ReconciliationService

logger = logging.getLogger(__name__)

ALLOWED_DELAY_MONTHS = {0, 6, 12, 24}


@dataclass
class StressTestCashflow:
    date: str  # ISO date string
    capital: float
    interest: float
    total: float
    is_delayed: bool


@dataclass
class StressTestResult:
    base_irr: Optional[float]  # percentage, e.g. 8.5
    stressed_irr: Optional[float]
    delay_months: int
    cashflows: list[StressTestCashflow]


class StressTestService:
    """Compute degraded IRR by shifting payment dates forward."""

    def __init__(self) -> None:
        self._recon = ReconciliationService()

    def compute_stress_test(
        self,
        project: CrowdfundingProject,
        delay_months: int,
    ) -> StressTestResult:
        """Compute base and stressed IRR for a project.

        Args:
            project: The crowdfunding project ORM object.
            delay_months: Number of months to shift all payments (0, 6, 12, 24).

        Returns:
            StressTestResult with base_irr, stressed_irr, and cashflow details.

        Raises:
            ValueError: If project has no start_date or schedule is empty.
        """
        # Generate schedule entries (detached ORM objects, no DB needed)
        if project.repayment_type == RepaymentType.AMORTIZABLE:
            schedule = self._recon._generate_amortizable(project)
        else:
            schedule = self._recon._generate_in_fine(project)

        if not schedule:
            raise ValueError(
                "Impossible de calculer le stress test : échéancier vide "
                "(vérifiez la date de début et la durée du projet)."
            )

        invested = float(project.invested_amount)

        # Determine investment date (day 0)
        if project.start_date:
            invest_date = datetime.combine(project.start_date, datetime.min.time())
        else:
            raise ValueError("Le projet n'a pas de date de début.")

        # Build base cashflows: negative = outflow, positive = inflow
        base_xirr_flows = self._build_xirr_flows(schedule, invested, invest_date, 0)
        base_irr_raw = _xirr(base_xirr_flows)
        base_irr = round(base_irr_raw * 100, 2) if base_irr_raw is not None else None

        # Build stressed cashflows
        if delay_months == 0:
            stressed_irr = base_irr
            cashflows = self._build_display_cashflows(schedule, 0)
        else:
            stressed_xirr_flows = self._build_xirr_flows(schedule, invested, invest_date, delay_months)
            stressed_irr_raw = _xirr(stressed_xirr_flows)
            stressed_irr = round(stressed_irr_raw * 100, 2) if stressed_irr_raw is not None else None
            cashflows = self._build_display_cashflows(schedule, delay_months)

        return StressTestResult(
            base_irr=base_irr,
            stressed_irr=stressed_irr,
            delay_months=delay_months,
            cashflows=cashflows,
        )

    def _build_xirr_flows(
        self,
        schedule: list,
        invested: float,
        invest_date: datetime,
        delay_months: int,
    ) -> list[tuple[datetime, float]]:
        """Build (datetime, amount) tuples for XIRR calculation.

        Convention: positive = outflow (investment), negative = inflow (receipts).
        """
        flows: list[tuple[datetime, float]] = [(invest_date, invested)]

        for entry in schedule:
            payment = float(entry.expected_capital) + float(entry.expected_interest)
            if payment <= 0:
                continue
            due = datetime.combine(entry.due_date, datetime.min.time())
            if delay_months > 0:
                due += relativedelta(months=delay_months)
            flows.append((due, -payment))

        return flows

    def _build_display_cashflows(
        self,
        schedule: list,
        delay_months: int,
    ) -> list[StressTestCashflow]:
        """Build display cashflows for the API response."""
        cashflows = []
        for entry in schedule:
            due = entry.due_date
            if delay_months > 0:
                due = due + relativedelta(months=delay_months)
            capital = float(entry.expected_capital)
            interest = float(entry.expected_interest)
            cashflows.append(
                StressTestCashflow(
                    date=due.isoformat(),
                    capital=round(capital, 2),
                    interest=round(interest, 2),
                    total=round(capital + interest, 2),
                    is_delayed=delay_months > 0,
                )
            )
        return cashflows


stress_test_service = StressTestService()
