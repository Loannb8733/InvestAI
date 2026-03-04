"""Test that simulation starting values are exactly synchronized with Dashboard.

Verifies that:
- /projection current_value == Dashboard total_value
- /what-if current_value == Dashboard total_value
- /fire uses live portfolio value when not overridden
- All simulation endpoints return the correct currency

Run inside Docker:
    TOKEN=... docker compose exec -e INVESTAI_TOKEN=$TOKEN backend python -m tests.test_simulation_sync
"""

import os
import sys

import httpx

BASE_URL = os.environ.get("INVESTAI_BASE_URL", "http://localhost:8000/api/v1")
TOKEN = os.environ.get("INVESTAI_TOKEN", "")


def get_headers():
    if not TOKEN:
        print("ERROR: Set INVESTAI_TOKEN environment variable")
        sys.exit(1)
    return {"Authorization": f"Bearer {TOKEN}"}


def main():
    headers = get_headers()

    print("=" * 60)
    print("SIMULATION ↔ DASHBOARD SYNC VERIFICATION")
    print("=" * 60)

    results = []

    def check(name: str, condition: bool, detail: str = ""):
        status = "PASS" if condition else "FAIL"
        results.append((name, condition))
        print(f"  {status}  {name}" + (f" -- {detail}" if detail else ""))

    # ── 1. Fetch Dashboard reference value ──
    print(f"\nFetching dashboard from {BASE_URL}/dashboard?days=0 ...")
    r = httpx.get(f"{BASE_URL}/dashboard", params={"days": 0}, headers=headers, timeout=30)
    r.raise_for_status()
    dashboard = r.json()
    total_value = dashboard["total_value"]
    print(f"  Dashboard total_value = {total_value:.2f}")

    # ── 2. Fetch user profile for currency ──
    r_me = httpx.get(f"{BASE_URL}/auth/me", headers=headers, timeout=10)
    r_me.raise_for_status()
    user_currency = r_me.json().get("preferred_currency", "EUR")
    print(f"  User preferred_currency = {user_currency}")

    # ── 3. Projection endpoint ──
    print(f"\nFetching projection from {BASE_URL}/simulations/projection ...")
    r_proj = httpx.post(
        f"{BASE_URL}/simulations/projection",
        json={"years": 1, "expected_return": 0.0, "monthly_contribution": 0},
        headers=headers,
        timeout=30,
    )
    r_proj.raise_for_status()
    proj = r_proj.json()
    proj_start = proj["current_value"]
    proj_currency = proj.get("currency", "EUR")
    print(f"  Projection current_value = {proj_start:.2f}")
    print(f"  Projection currency = {proj_currency}")

    check(
        "S1: Projection current_value == Dashboard total_value",
        abs(proj_start - total_value) < 0.02,
        f"projection={proj_start:.2f}, dashboard={total_value:.2f}, diff={abs(proj_start - total_value):.2f}",
    )
    check(
        "S1b: Projection currency matches user preference",
        proj_currency == user_currency,
        f"projection={proj_currency}, user={user_currency}",
    )

    # With 0% return and 0 contributions over 1 year, final should equal start
    proj_final_y0 = proj["projections"][0]["nominal_value"]
    check(
        "S1c: Projection year=0 == Dashboard total_value",
        abs(proj_final_y0 - total_value) < 0.02,
        f"year0={proj_final_y0:.2f}, dashboard={total_value:.2f}",
    )

    # ── 4. What-if endpoint ──
    print(f"\nFetching what-if from {BASE_URL}/simulations/what-if ...")
    r_whatif = httpx.post(
        f"{BASE_URL}/simulations/what-if",
        json={"scenario_type": "price_change", "asset_changes": {}},
        headers=headers,
        timeout=30,
    )
    r_whatif.raise_for_status()
    whatif = r_whatif.json()
    whatif_current = whatif["current_value"]
    whatif_projected = whatif["projected_value"]
    whatif_currency = whatif.get("currency", "EUR")
    print(f"  What-if current_value = {whatif_current:.2f}")
    print(f"  What-if projected_value = {whatif_projected:.2f}")

    check(
        "S2: What-if current_value == Dashboard total_value",
        abs(whatif_current - total_value) < 0.02,
        f"whatif={whatif_current:.2f}, dashboard={total_value:.2f}, diff={abs(whatif_current - total_value):.2f}",
    )
    check(
        "S2b: What-if currency matches user preference",
        whatif_currency == user_currency,
        f"whatif={whatif_currency}, user={user_currency}",
    )

    # No changes → projected should equal current
    check(
        "S2c: What-if no changes → projected == current",
        abs(whatif_projected - whatif_current) < 0.02,
        f"projected={whatif_projected:.2f}, current={whatif_current:.2f}",
    )

    # ── 5. What-if with market shock ──
    if total_value > 0:
        print(f"\nFetching what-if market=-20% from {BASE_URL}/simulations/what-if ...")
        r_shock = httpx.post(
            f"{BASE_URL}/simulations/what-if",
            json={
                "scenario_type": "price_change",
                "market_change": -20.0,
                "use_risk_weighting": True,
            },
            headers=headers,
            timeout=30,
        )
        r_shock.raise_for_status()
        shock = r_shock.json()
        shock_diff_pct = shock["difference_percent"]
        print(f"  Market -20% → portfolio change = {shock_diff_pct:.2f}%")

        # With risk weighting, the overall portfolio change should be approximately -20%
        # (may differ slightly due to risk weight distribution and capping)
        check(
            "S3: Market -20% shock → portfolio ~-20%",
            -30.0 < shock_diff_pct < -10.0,
            f"actual={shock_diff_pct:.2f}%, expected≈-20%",
        )

        # Verify risk_weight is present in breakdown
        has_risk_weights = all("risk_weight" in a for a in shock["asset_breakdown"])
        check(
            "S3b: Risk weights present in what-if breakdown",
            has_risk_weights,
        )

    # ── 6. FIRE with live value ──
    print(f"\nFetching FIRE (auto-detect value) from {BASE_URL}/simulations/fire ...")
    r_fire = httpx.post(
        f"{BASE_URL}/simulations/fire",
        json={"monthly_expenses": 2000},
        headers=headers,
        timeout=30,
    )
    if r_fire.status_code == 200:
        fire = r_fire.json()
        fire_start = fire["projected_values"][0]["portfolio_value"]
        fire_currency = fire.get("currency", "EUR")
        print(f"  FIRE start value = {fire_start:.2f}")

        check(
            "S4: FIRE start value == Dashboard total_value",
            abs(fire_start - total_value) < 0.02,
            f"fire={fire_start:.2f}, dashboard={total_value:.2f}",
        )
        check(
            "S4b: FIRE currency matches user preference",
            fire_currency == user_currency,
            f"fire={fire_currency}, user={user_currency}",
        )
    elif r_fire.status_code == 400 and total_value <= 0:
        print("  FIRE skipped (portfolio value is 0)")
        check("S4: FIRE skipped (empty portfolio)", True)
    else:
        print(f"  FIRE error: {r_fire.status_code} {r_fire.text}")
        check("S4: FIRE endpoint accessible", False, f"status={r_fire.status_code}")

    # ── 7. DCA returns currency ──
    print(f"\nFetching DCA from {BASE_URL}/simulations/dca ...")
    r_dca = httpx.post(
        f"{BASE_URL}/simulations/dca",
        json={"total_amount": 1000, "duration_months": 12},
        headers=headers,
        timeout=10,
    )
    r_dca.raise_for_status()
    dca = r_dca.json()
    dca_currency = dca.get("currency", "EUR")
    check(
        "S5: DCA currency matches user preference",
        dca_currency == user_currency,
        f"dca={dca_currency}, user={user_currency}",
    )

    # ── Summary ──
    passed = sum(1 for _, ok in results if ok)
    failed = sum(1 for _, ok in results if not ok)
    print("\n" + "=" * 60)
    print(f"SIMULATION SYNC RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)

    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
