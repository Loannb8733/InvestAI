from unittest.mock import AsyncMock, MagicMock

import pytest
import time_machine
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from app.domains.notifications import reports as notification_reports
from app.domains.notifications import tasks as notification_tasks
from app.domains.reports.service import report_service
from tests.sample_portfolio import FROZEN_NOW, TARGETS, seed_history, seed_portfolio

USDC_VALUE = 2000 * 0.92

pytestmark = pytest.mark.usefixtures("empty_test_redis", "offline")


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(str(user.id))}"}


async def _seed(client: AsyncClient, db: AsyncSession, user: User) -> None:
    await seed_history(db)
    await seed_portfolio(client, _headers(user))


@pytest.mark.usefixtures("live_quotes")
async def test_monthly_email_attaches_the_performance_pdf(
    client: AsyncClient, db_session: AsyncSession, regular_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    mailer = MagicMock(is_configured=True, send_monthly_report=AsyncMock(return_value=True))
    monkeypatch.setattr(notification_reports, "report_mailer", mailer)
    with time_machine.travel(FROZEN_NOW, tick=False):
        await _seed(client, db_session, regular_user)
        assert await notification_tasks.run_monthly_reports() == {"sent": 1, "failed": 0}
    pdf = mailer.send_monthly_report.await_args.kwargs["pdf_content"]
    assert pdf is not None and pdf.startswith(b"%PDF")


async def test_rebalancing_without_live_quotes_still_estimates_tax(
    client: AsyncClient, db_session: AsyncSession, regular_user: User
) -> None:
    with time_machine.travel(FROZEN_NOW, tick=False):
        await _seed(client, db_session, regular_user)
        response = await client.post(
            "/api/v1/reports/rebalancing", json={"target_allocations": TARGETS}, headers=_headers(regular_user)
        )
    assert response.status_code == 200, response.text
    sells = [o for o in response.json()["orders"] if o["action"] == "sell"]
    assert sells and all(o["estimated_tax"] > 0 for o in sells)


@pytest.mark.usefixtures("live_quotes")
async def test_report_data_includes_risk_metrics(
    client: AsyncClient, db_session: AsyncSession, regular_user: User
) -> None:
    with time_machine.travel(FROZEN_NOW, tick=False):
        await _seed(client, db_session, regular_user)
        data = await report_service.get_report_data(db_session, str(regular_user.id))
    assert data["risk_metrics"]


async def test_unknown_class_error_lists_the_classes_in_a_fixed_order(client: AsyncClient, regular_user: User) -> None:
    response = await client.post(
        "/api/v1/reports/rebalancing", json={"target_allocations": {"NFT": 1.0}}, headers=_headers(regular_user)
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"].endswith("Allowed: DeFi, L1, L2, Meme, Other, Stable")


@pytest.mark.usefixtures("live_quotes")
async def test_stablecoins_held_count_in_the_stable_class(
    client: AsyncClient, db_session: AsyncSession, regular_user: User
) -> None:
    with time_machine.travel(FROZEN_NOW, tick=False):
        await _seed(client, db_session, regular_user)
        response = await client.post(
            "/api/v1/reports/rebalancing", json={"target_allocations": TARGETS}, headers=_headers(regular_user)
        )
    stable = next(c for c in response.json()["categories"] if c["category"] == "Stable")
    assert stable["current_value"] == pytest.approx(USDC_VALUE)


@pytest.mark.usefixtures("live_quotes")
async def test_liquidity_is_attributed_to_munitions(
    client: AsyncClient, db_session: AsyncSession, regular_user: User
) -> None:
    with time_machine.travel(FROZEN_NOW, tick=False):
        await _seed(client, db_session, regular_user)
        data = await report_service.get_report_data(db_session, str(regular_user.id))
    assert data["attribution"]["munitions"] == pytest.approx(USDC_VALUE)
