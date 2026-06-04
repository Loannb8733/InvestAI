"""Golden tests for crowdfunding schedule generation (Ticket 5).

Covers the previously untested pure schedule builders in ReconciliationService:
net-of-tax multiplier, IN_FINE (at-maturity + periodic), and AMORTIZABLE
(equal capital + rounding remainder on the last installment).
"""

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services.reconciliation_service import ReconciliationService


def _project(**overrides):
    base = dict(
        id=uuid.uuid4(),
        invested_amount=Decimal("10000"),
        annual_rate=Decimal("10"),  # 10% / year
        tax_rate=Decimal("30"),  # 30% flat tax → net multiplier 0.70
        duration_months=12,
        delay_months=0,
        interest_frequency="at_maturity",
        start_date=date(2026, 1, 1),
        estimated_end_date=date(2027, 1, 1),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


SVC = ReconciliationService()


class TestNetMultiplier:
    def test_default_30_when_unset(self):
        assert SVC._get_net_multiplier(_project(tax_rate=None)) == Decimal("0.70")

    def test_zero_tax_is_not_defaulted(self):
        # Bug fix: a 0% tax project must keep 0% (multiplier 1), not become 30%.
        assert SVC._get_net_multiplier(_project(tax_rate=Decimal("0"))) == Decimal("1")

    def test_custom_rate(self):
        assert SVC._get_net_multiplier(_project(tax_rate=Decimal("17.2"))) == Decimal("0.828")


class TestInFine:
    def test_at_maturity_single_entry(self):
        entries = SVC._generate_in_fine(_project(interest_frequency="at_maturity"))
        assert len(entries) == 1
        e = entries[0]
        # 10000 * 10% * 12/12 = 1000 gross → 700 net.
        assert e.expected_interest == Decimal("700.00")
        assert Decimal(str(e.expected_capital)) == Decimal("10000")
        assert e.due_date == date(2027, 1, 1)

    def test_quarterly_periodic(self):
        entries = SVC._generate_in_fine(_project(interest_frequency="quarterly"))
        assert len(entries) == 4  # 12 months / 3
        # 10000 * 10% / 4 = 250 gross → 175 net per period.
        assert all(e.expected_interest == Decimal("175.00") for e in entries)
        # Capital repaid only on the last entry.
        assert sum(Decimal(str(e.expected_capital)) for e in entries) == Decimal("10000")
        assert Decimal(str(entries[-1].expected_capital)) == Decimal("10000")
        assert entries[0].due_date == date(2026, 4, 1)

    def test_at_maturity_without_end_date_is_empty(self):
        assert SVC._generate_in_fine(_project(estimated_end_date=None)) == []


class TestAmortizable:
    def test_equal_capital_and_interest(self):
        p = _project(invested_amount=Decimal("12000"), duration_months=12)
        entries = SVC._generate_amortizable(p)
        assert len(entries) == 12
        # 12000 * 10% / 12 = 100 gross → 70 net interest per month.
        assert all(e.expected_interest == Decimal("70.00") for e in entries)
        assert sum(Decimal(str(e.expected_capital)) for e in entries) == Decimal("12000")

    def test_last_installment_absorbs_rounding(self):
        p = _project(invested_amount=Decimal("10000"), duration_months=3)
        entries = SVC._generate_amortizable(p)
        assert len(entries) == 3
        # 10000 / 3 = 3333.33 each, last = 10000 - 3333.33*2 = 3333.34.
        assert Decimal(str(entries[0].expected_capital)) == Decimal("3333.33")
        assert Decimal(str(entries[-1].expected_capital)) == Decimal("3333.34")
        assert sum(Decimal(str(e.expected_capital)) for e in entries) == Decimal("10000")

    def test_no_start_date_is_empty(self):
        assert SVC._generate_amortizable(_project(start_date=None)) == []
