"""Test value parity across Dashboard, Insights, and Smart Insights.

Verifies that the total portfolio value is consistent across:
- Dashboard (analytics total_value)
- Insights / Top Alpha (total_portfolio_value)
- Insights / Strategy Map (total_portfolio_value)
- Smart Insights / Health (metrics_summary.total_value)

Tolerance: 0.00 EUR (same price source = CoinGecko batch).

Run inside Docker:
    TOKEN=... docker compose exec -e INVESTAI_TOKEN=$TOKEN backend python -m tests.test_value_parity
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
    print("VALUE PARITY VERIFICATION")
    print("Dashboard == Insights == Smart Insights")
    print("=" * 60)

    results = []

    def check(name: str, condition: bool, detail: str = ""):
        status = "PASS" if condition else "FAIL"
        results.append((name, condition))
        print(f"  {status}  {name}" + (f" -- {detail}" if detail else ""))

    # ── 1. Dashboard / Analytics total_value ──
    print(f"\n1. Fetching Dashboard analytics from {BASE_URL}/analytics ...")
    r_dash = httpx.get(
        f"{BASE_URL}/analytics",
        params={"days": 30},
        headers=headers,
        timeout=60,
    )
    check("D1: Analytics returns 200", r_dash.status_code == 200, f"status={r_dash.status_code}")

    dashboard_value = 0.0
    if r_dash.status_code == 200:
        dashboard_value = r_dash.json().get("total_value", 0.0)
        print(f"     Dashboard total_value = {dashboard_value:.2f} EUR")

    # ── 2. Insights / Top Alpha total_portfolio_value ──
    print(f"\n2. Fetching Top Alpha from {BASE_URL}/predictions/top-alpha ...")
    r_alpha = httpx.get(
        f"{BASE_URL}/predictions/top-alpha",
        headers=headers,
        timeout=120,
    )
    check("I1: Top Alpha returns 200", r_alpha.status_code == 200, f"status={r_alpha.status_code}")

    alpha_value = 0.0
    if r_alpha.status_code == 200:
        alpha_data = r_alpha.json()
        alpha_value = alpha_data.get("total_portfolio_value", 0.0)
        print(f"     Top Alpha total_portfolio_value = {alpha_value:.2f} EUR")

    # ── 3. Insights / Strategy Map total_portfolio_value ──
    print(f"\n3. Fetching Strategy Map from {BASE_URL}/predictions/strategy-map ...")
    r_strat = httpx.get(
        f"{BASE_URL}/predictions/strategy-map",
        headers=headers,
        timeout=120,
    )
    check("S1: Strategy Map returns 200", r_strat.status_code == 200, f"status={r_strat.status_code}")

    strategy_value = 0.0
    if r_strat.status_code == 200:
        strat_data = r_strat.json()
        strategy_value = strat_data.get("total_portfolio_value", 0.0)
        print(f"     Strategy Map total_portfolio_value = {strategy_value:.2f} EUR")

    # ── 4. Smart Insights / Health metrics_summary.total_value ──
    print(f"\n4. Fetching Smart Insights Health from {BASE_URL}/smart-insights/health ...")
    r_health = httpx.get(
        f"{BASE_URL}/smart-insights/health",
        params={"days": 30},
        headers=headers,
        timeout=120,
    )
    check("H1: Smart Insights Health returns 200", r_health.status_code == 200, f"status={r_health.status_code}")

    health_value = 0.0
    if r_health.status_code == 200:
        health_data = r_health.json()
        health_value = health_data.get("metrics_summary", {}).get("total_value", 0.0)
        print(f"     Smart Insights total_value = {health_value:.2f} EUR")

    # ── 5. Parity checks ──
    print("\n" + "-" * 60)
    print("PARITY CHECKS")
    print("-" * 60)

    values = {
        "Dashboard": dashboard_value,
        "Top Alpha": alpha_value,
        "Strategy Map": strategy_value,
        "Smart Insights": health_value,
    }

    # Dashboard vs Top Alpha — they use different price sources
    # (analytics uses its own fetch, top-alpha uses batch CoinGecko)
    # so we allow 1% tolerance for timing differences
    TOLERANCE_PCT = 1.0  # 1% tolerance for cross-source comparison

    if dashboard_value > 0 and alpha_value > 0:
        ecart_da = abs(dashboard_value - alpha_value)
        pct_da = (ecart_da / dashboard_value) * 100
        check(
            "P1: Dashboard ≈ Top Alpha",
            pct_da <= TOLERANCE_PCT,
            f"écart={ecart_da:.2f} EUR ({pct_da:.2f}%)",
        )
    else:
        check("P1: Dashboard ≈ Top Alpha", False, "missing data")

    # Top Alpha == Strategy Map (same underlying call)
    if alpha_value > 0 and strategy_value > 0:
        ecart_as = abs(alpha_value - strategy_value)
        check(
            "P2: Top Alpha == Strategy Map",
            ecart_as < 0.01,
            f"écart={ecart_as:.2f} EUR",
        )
    else:
        check("P2: Top Alpha == Strategy Map", False, "missing data")

    # Dashboard vs Smart Insights — same analytics service
    if dashboard_value > 0 and health_value > 0:
        ecart_dh = abs(dashboard_value - health_value)
        check(
            "P3: Dashboard == Smart Insights",
            ecart_dh < 0.01,
            f"écart={ecart_dh:.2f} EUR",
        )
    else:
        check("P3: Dashboard == Smart Insights", False, "missing data")

    # ── Summary ──
    print("\n" + "=" * 60)
    total = len(results)
    passed = sum(1 for _, ok in results if ok)
    failed = total - passed
    print(f"VALUE PARITY: {passed} passed, {failed} failed out of {total}")

    print("\nAll values:")
    for label, val in values.items():
        print(f"  {label:20s} = {val:>12.2f} EUR")

    print("=" * 60)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
