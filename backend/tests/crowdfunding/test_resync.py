from decimal import Decimal
from typing import Any

import pytest
import time_machine
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.crowdfunding.models import CrowdfundingPaymentSchedule, CrowdfundingProject
from app.domains.crowdfunding.resync import DOUBLE_CAPITAL, apply_resync, plan_resync
from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from tests.crowdfunding.recorder import BASE
from tests.sample_portfolio import FROZEN_NOW

pytestmark = pytest.mark.usefixtures("empty_test_redis", "offline")

AMORTIZABLE = {
    "platform": "Homunity",
    "project_name": "Bureaux",
    "invested_amount": "1200",
    "annual_rate": "10",
    "duration_months": 12,
    "repayment_type": "amortizable",
    "start_date": "2026-01-15",
    "tax_rate": "0",
}
ANNUAL = {
    "platform": "Wiseed",
    "project_name": "Hôtel Lac",
    "invested_amount": "1000",
    "annual_rate": "12",
    "duration_months": 18,
    "start_date": "2026-01-01",
    "interest_frequency": "annual",
    "tax_rate": "0",
}


async def _project(client: AsyncClient, db: AsyncSession, user: User, body: dict[str, Any]) -> CrowdfundingProject:
    headers = {"Authorization": f"Bearer {create_token(str(user.id))}"}
    created = await client.post(BASE, headers=headers, json=body)
    assert created.status_code == 201, created.text
    project = await db.get(CrowdfundingProject, created.json()["id"])
    assert project is not None
    return project


async def _schedule(db: AsyncSession, project: CrowdfundingProject) -> list[CrowdfundingPaymentSchedule]:
    query = (
        select(CrowdfundingPaymentSchedule)
        .where(CrowdfundingPaymentSchedule.project_id == project.id)
        .order_by(CrowdfundingPaymentSchedule.due_date)
        .execution_options(populate_existing=True)
    )
    return list((await db.execute(query)).scalars().all())


async def test_resync_recomputes_open_installments_and_keeps_settled_ones(
    client: AsyncClient, db_session: AsyncSession, regular_user: User
) -> None:
    with time_machine.travel(FROZEN_NOW, tick=False):
        project = await _project(client, db_session, regular_user, AMORTIZABLE)
        first = (await _schedule(db_session, project))[0]
        await db_session.execute(
            update(CrowdfundingPaymentSchedule)
            .where(CrowdfundingPaymentSchedule.project_id == project.id)
            .values(expected_interest=Decimal("10.00"))
        )
        await db_session.execute(
            update(CrowdfundingPaymentSchedule)
            .where(CrowdfundingPaymentSchedule.id == first.id)
            .values(is_completed=True)
        )
        await db_session.commit()
        legacy = await plan_resync(db_session, project)
        await apply_resync(db_session, legacy)
        after = await _schedule(db_session, project)
        again = await plan_resync(db_session, project)
    assert legacy.changed and legacy.blocker is None
    assert (after[0].id, after[0].is_completed) == (first.id, True)
    assert [entry.expected_interest for entry in after[1:3]] == [Decimal("9.17"), Decimal("8.33")]
    assert not again.changed


async def test_resync_refuses_to_expect_settled_capital_twice(
    client: AsyncClient, db_session: AsyncSession, regular_user: User
) -> None:
    with time_machine.travel(FROZEN_NOW, tick=False):
        project = await _project(client, db_session, regular_user, ANNUAL)
        coupon, final = await _schedule(db_session, project)
        await db_session.execute(
            update(CrowdfundingPaymentSchedule)
            .where(CrowdfundingPaymentSchedule.id == coupon.id)
            .values(expected_capital=Decimal("1000.00"), is_completed=True)
        )
        await db_session.commit()
        plan = await plan_resync(db_session, project)
        with pytest.raises(ValueError, match="seconde fois"):
            await apply_resync(db_session, plan)
    assert plan.blocker == DOUBLE_CAPITAL
