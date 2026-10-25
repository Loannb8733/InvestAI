from typing import Any

import pytest
import time_machine
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from tests.crowdfunding.recorder import BASE, UNKNOWN_ID, Recorder
from tests.sample_portfolio import FROZEN_NOW, seed_history, seed_portfolio

IN_FINE = {
    "platform": "Anaxago",
    "project_name": "Résidence des Tilleuls",
    "description": "Promotion de 24 logements",
    "project_url": "https://example.test/tilleuls",
    "invested_amount": "1000",
    "annual_rate": "10",
    "duration_months": 24,
    "repayment_type": "in_fine",
    "start_date": "2025-10-01",
    "estimated_end_date": "2027-10-01",
    "interest_frequency": "quarterly",
    "tax_rate": "12.8",
    "delay_months": 3,
}
AMORTIZABLE = {
    "platform": "Homunity",
    "project_name": "Bureaux Part-Dieu",
    "invested_amount": "2000",
    "annual_rate": "8",
    "duration_months": 12,
    "repayment_type": "amortizable",
    "start_date": "2026-01-15",
    "estimated_end_date": "2027-01-15",
    "interest_frequency": "monthly",
}
COMPLETED = {
    "platform": "Fundimmo",
    "project_name": "Lofts Canal",
    "invested_amount": "500",
    "annual_rate": "11",
    "duration_months": 12,
    "start_date": "2024-06-01",
    "estimated_end_date": "2025-06-01",
    "status": "completed",
}
DEFAULTED = {
    "platform": "Wiseed",
    "project_name": "Hôtel Lac",
    "invested_amount": "1500",
    "annual_rate": "12",
    "duration_months": 18,
    "start_date": "2024-01-01",
    "interest_frequency": "annual",
    "status": "defaulted",
}
FUNDING = {
    "platform": "Lymo",
    "project_name": "Entrepôt",
    "invested_amount": "300",
    "annual_rate": "9",
    "duration_months": 36,
}


async def _create_flow(rec: Recorder, headers: dict[str, str], other: dict[str, str]) -> dict[str, Any]:
    await rec.shot("projects_empty", "GET", BASE, headers)
    await rec.shot("dashboard_empty", "GET", f"{BASE}/dashboard", headers)
    await rec.shot("performance_empty", "GET", f"{BASE}/performance", headers)
    await rec.shot("cashflow_empty", "GET", f"{BASE}/cashflow-schedule", headers)
    await rec.shot("tax_report_empty", "GET", f"{BASE}/tax-report", headers)
    ids = {
        "in_fine": (await rec.shot("create_in_fine", "POST", BASE, headers, IN_FINE))["id"],
        "amortizable": (await rec.shot("create_amortizable", "POST", BASE, headers, AMORTIZABLE))["id"],
        "completed": (await rec.shot("create_completed", "POST", BASE, headers, COMPLETED))["id"],
        "defaulted": (await rec.shot("create_defaulted", "POST", BASE, headers, DEFAULTED))["id"],
        "funding": (await rec.shot("create_funding_no_start", "POST", BASE, headers, FUNDING))["id"],
    }
    portfolios = (await rec.client.get("/api/v1/portfolios", headers=headers)).json()
    own = next(p["id"] for p in portfolios if p["name"] != "Crowdfunding")
    explicit = {**FUNDING, "project_name": "Parking", "portfolio_id": own, "interest_frequency": "weekly"}
    ids["explicit"] = (await rec.shot("create_in_own_portfolio", "POST", BASE, headers, explicit))["id"]
    await rec.shot("create_other_user_portfolio", "POST", BASE, other, {**FUNDING, "portfolio_id": own})
    await rec.shot("create_unknown_portfolio", "POST", BASE, headers, {**FUNDING, "portfolio_id": UNKNOWN_ID})
    await rec.shot("create_rate_too_high", "POST", BASE, headers, {**FUNDING, "annual_rate": "101"})
    await rec.shot("create_zero_duration", "POST", BASE, headers, {**FUNDING, "duration_months": 0})
    await rec.shot("create_negative_amount", "POST", BASE, headers, {**FUNDING, "invested_amount": "-1"})
    await rec.shot("create_bad_status", "POST", BASE, headers, {**FUNDING, "status": "paused"})
    await rec.shot("portfolios_after_create", "GET", "/api/v1/portfolios", headers)
    project = await rec.shot("project_get", "GET", f"{BASE}/{ids['in_fine']}", headers)
    ids["in_fine_asset"] = project["asset_id"]
    await rec.shot("asset_after_create", "GET", f"/api/v1/assets/{project['asset_id']}", headers)
    await rec.shot("project_get_unknown", "GET", f"{BASE}/{UNKNOWN_ID}", headers)
    await rec.shot("project_get_other_user", "GET", f"{BASE}/{ids['in_fine']}", other)
    await rec.shot("project_get_malformed", "GET", f"{BASE}/not-a-uuid", headers)
    return ids


async def _repayments_flow(rec: Recorder, headers: dict[str, str], other: dict[str, str], ids: dict[str, Any]) -> None:
    def url(key: str) -> str:
        return f"{BASE}/{ids[key]}/repayments"

    coupon = {"payment_date": "2026-01-02", "amount": "25", "payment_type": "interest", "tax_amount": "3.2"}
    ids["coupon"] = (await rec.shot("repay_coupon", "POST", url("in_fine"), headers, coupon))["id"]
    split = {
        "payment_date": "2026-02-16",
        "amount": "180",
        "payment_type": "both",
        "capital_amount": "166.67",
        "interest_amount": "13.33",
        "tax_amount": "4",
    }
    await rec.shot("repay_split", "POST", url("amortizable"), headers, split)
    unsplit = {"payment_date": "2026-03-15", "amount": "180", "payment_type": "both"}
    await rec.shot("repay_unsplit", "POST", url("amortizable"), headers, unsplit)
    referral = {"payment_date": "2026-03-20", "amount": "10", "payment_type": "referral", "notes": "Parrainage"}
    await rec.shot("repay_referral", "POST", url("amortizable"), headers, referral)
    final = {"payment_date": "2025-06-03", "amount": "555", "payment_type": "both", "capital_amount": "500"}
    await rec.shot("repay_completed_final", "POST", url("completed"), headers, {**final, "interest_amount": "55"})
    late = {"payment_date": "2025-01-05", "amount": "180", "payment_type": "interest"}
    await rec.shot("repay_defaulted_coupon", "POST", url("defaulted"), headers, late)
    await rec.shot("repay_zero_amount", "POST", url("in_fine"), headers, {**coupon, "amount": "0"})
    await rec.shot("repay_bad_type", "POST", url("in_fine"), headers, {**coupon, "payment_type": "bonus"})
    await rec.shot("repay_unknown_project", "POST", f"{BASE}/{UNKNOWN_ID}/repayments", headers, coupon)
    await rec.shot("repay_other_user", "POST", url("in_fine"), other, coupon)


async def _reads_flow(rec: Recorder, headers: dict[str, str], ids: dict[str, Any]) -> None:
    await rec.shot("projects_all", "GET", BASE, headers)
    await rec.shot("dashboard", "GET", f"{BASE}/dashboard", headers)
    await rec.shot("performance", "GET", f"{BASE}/performance", headers)
    await rec.shot("cashflow", "GET", f"{BASE}/cashflow-schedule", headers)
    await rec.shot("tax_report_current", "GET", f"{BASE}/tax-report", headers)
    await rec.shot("tax_report_2025", "GET", f"{BASE}/tax-report?year=2025", headers)
    await rec.shot("tax_report_bad_year", "GET", f"{BASE}/tax-report?year=1999", headers)
    await rec.shot("sync_calendar", "POST", f"{BASE}/sync-calendar", headers)
    stress = f"{BASE}/{ids['in_fine']}/stress-test"
    await rec.shot("stress_default", "GET", stress, headers)
    await rec.shot("stress_12", "GET", f"{stress}?delay_months=12", headers)
    await rec.shot("stress_amortizable_6", "GET", f"{BASE}/{ids['amortizable']}/stress-test?delay_months=6", headers)
    await rec.shot("stress_not_allowed", "GET", f"{stress}?delay_months=5", headers)
    await rec.shot("stress_out_of_range", "GET", f"{stress}?delay_months=30", headers)
    await rec.shot("stress_no_start", "GET", f"{BASE}/{ids['funding']}/stress-test", headers)
    await rec.shot("stress_unknown", "GET", f"{BASE}/{UNKNOWN_ID}/stress-test", headers)


async def _mutations_flow(rec: Recorder, headers: dict[str, str], other: dict[str, str], ids: dict[str, Any]) -> None:
    coupon_url = f"{BASE}/{ids['in_fine']}/repayments/{ids['coupon']}"
    await rec.shot(
        "repay_delete_wrong_project", "DELETE", f"{BASE}/{ids['amortizable']}/repayments/{ids['coupon']}", headers
    )
    await rec.shot("repay_delete_other_user", "DELETE", coupon_url, other)
    await rec.shot("repay_delete", "DELETE", coupon_url, headers)
    await rec.shot("repay_delete_again", "DELETE", coupon_url, headers)
    project = f"{BASE}/{ids['in_fine']}"
    await rec.shot("project_after_repay_delete", "GET", project, headers)
    await rec.shot("patch_text", "PATCH", project, headers, {"project_name": "Les Tilleuls", "description": None})
    await rec.shot("patch_amount_rate", "PATCH", project, headers, {"invested_amount": "1200", "annual_rate": "9.5"})
    await rec.shot("asset_after_patch", "GET", f"/api/v1/assets/{ids['in_fine_asset']}", headers)
    await rec.shot("patch_platform", "PATCH", project, headers, {"platform": "Anaxago Capital"})
    await rec.shot("patch_status_delayed", "PATCH", project, headers, {"status": "delayed", "delay_months": 6})
    await rec.shot("patch_status_completed", "PATCH", f"{BASE}/{ids['amortizable']}", headers, {"status": "completed"})
    await rec.shot("patch_status_active", "PATCH", f"{BASE}/{ids['funding']}", headers, {"status": "active"})
    await rec.shot("patch_total_received", "PATCH", f"{BASE}/{ids['completed']}", headers, {"total_received": "600"})
    await rec.shot("patch_zero_amount", "PATCH", project, headers, {"invested_amount": "0"})
    await rec.shot("patch_other_user", "PATCH", project, other, {"project_name": "X"})
    await rec.shot("dashboard_after_patch", "GET", f"{BASE}/dashboard", headers)
    await rec.shot("delete_other_user", "DELETE", project, other)
    await rec.shot("delete", "DELETE", project, headers)
    await rec.shot("delete_again", "DELETE", project, headers)
    await rec.shot("asset_after_delete", "GET", f"/api/v1/assets/{ids['in_fine_asset']}", headers)
    await rec.shot("projects_after_delete", "GET", BASE, headers)


@pytest.mark.usefixtures("empty_test_redis", "offline", "live_quotes")
async def test_crowdfunding_project_routes_match_golden(
    client: AsyncClient, db_session: AsyncSession, regular_user: User, admin_user: User
) -> None:
    headers = {"Authorization": f"Bearer {create_token(str(regular_user.id))}"}
    other = {"Authorization": f"Bearer {create_token(str(admin_user.id))}"}
    rec = Recorder(client)
    with time_machine.travel(FROZEN_NOW, tick=False):
        await seed_history(db_session)
        await seed_portfolio(client, headers)
        ids = await _create_flow(rec, headers, other)
        await _repayments_flow(rec, headers, other, ids)
        await _reads_flow(rec, headers, ids)
        await _mutations_flow(rec, headers, other, ids)
        await rec.shot("unauthenticated", "GET", BASE, {})
    assert not rec.mismatches, f"golden crowdfunding différent : {rec.mismatches} (GOLDEN_UPDATE=1 pour accepter)"
