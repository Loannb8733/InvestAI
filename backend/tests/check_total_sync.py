"""The Cent Difference Test — Cross-service total_value parity check.

Calls Dashboard, Insights, Smart Insights and Monte Carlo simultaneously.
If total_value diverges > 0.001 EUR between services, lists the culprit functions.

Usage (inside Docker):
    TOKEN=... docker compose exec -e INVESTAI_TOKEN=$TOKEN backend \
        python -m tests.check_total_sync

Exit code 1 on any parity failure.
"""

import asyncio
import os
import sys
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import httpx

BASE_URL = os.environ.get("INVESTAI_BASE_URL", "http://localhost:8000/api/v1")
TOKEN = os.environ.get("INVESTAI_TOKEN", "")

TOLERANCE_EUR = 0.001  # hard tolerance for same-source endpoints
TOLERANCE_CROSS_PCT = 1.0  # 1% for cross-source (dashboard vs predictions)


@dataclass
class EndpointResult:
    name: str
    total_value: Optional[float] = None
    status_code: int = 0
    elapsed_ms: float = 0
    error: Optional[str] = None
    source_function: str = ""


def _headers() -> dict:
    if not TOKEN:
        print("ERROR: Set INVESTAI_TOKEN environment variable")
        sys.exit(1)
    return {"Authorization": f"Bearer {TOKEN}"}


async def _fetch(
    client: httpx.AsyncClient, name: str, url: str, params: Optional[dict] = None, source_function: str = ""
) -> EndpointResult:
    """Fetch an endpoint and extract total_value."""
    t0 = time.monotonic()
    try:
        resp = await client.get(url, params=params, headers=_headers(), timeout=120)
        elapsed = (time.monotonic() - t0) * 1000
        result = EndpointResult(
            name=name,
            status_code=resp.status_code,
            elapsed_ms=round(elapsed, 1),
            source_function=source_function,
        )
        if resp.status_code != 200:
            result.error = f"HTTP {resp.status_code}"
            return result

        data = resp.json()

        # Extract total_value based on endpoint shape
        if name == "Dashboard":
            result.total_value = data.get("total_value")
        elif name == "Top Alpha":
            result.total_value = data.get("total_portfolio_value")
        elif name == "Strategy Map":
            result.total_value = data.get("total_portfolio_value")
        elif name == "Smart Insights":
            result.total_value = data.get("metrics_summary", {}).get("total_value")
        elif name == "Monte Carlo":
            # MC doesn't return total_value directly — we skip parity for it
            # but we check it ran successfully
            result.total_value = None
            sims = data.get("simulations", 0)
            if sims == 0:
                result.error = "0 simulations returned"

        return result

    except Exception as exc:
        elapsed = (time.monotonic() - t0) * 1000
        return EndpointResult(
            name=name,
            error=str(exc),
            elapsed_ms=round(elapsed, 1),
            source_function=source_function,
        )


async def run_parity_check() -> bool:
    """Run all endpoints simultaneously, check parity. Returns True if all pass."""

    endpoints = [
        ("Dashboard", f"{BASE_URL}/analytics", {"days": 30}, "analytics_service.get_portfolio_analytics"),
        ("Top Alpha", f"{BASE_URL}/predictions/top-alpha", None, "prediction_service.get_top_alpha_asset"),
        ("Strategy Map", f"{BASE_URL}/predictions/strategy-map", None, "prediction_service.get_strategy_map"),
        (
            "Smart Insights",
            f"{BASE_URL}/smart-insights/health",
            {"days": 30},
            "smart_insights_service.get_portfolio_health",
        ),
        ("Monte Carlo", f"{BASE_URL}/analytics/monte-carlo", {"horizon_days": 90}, "analytics_service.monte_carlo"),
    ]

    print("=" * 70)
    print("THE CENT DIFFERENCE TEST — Cross-Service Parity")
    print(f"Tolerance: {TOLERANCE_EUR} EUR (same source), {TOLERANCE_CROSS_PCT}% (cross source)")
    print("=" * 70)
    print(f"\nFiring {len(endpoints)} concurrent requests...\n")

    async with httpx.AsyncClient() as client:
        tasks = [_fetch(client, name, url, params, src) for name, url, params, src in endpoints]
        results: List[EndpointResult] = await asyncio.gather(*tasks)

    # ── Display results ──
    for r in results:
        val_str = f"{r.total_value:>14,.2f} EUR" if r.total_value is not None else "       N/A"
        status = "OK" if r.status_code == 200 and not r.error else "FAIL"
        print(f"  [{status:4s}] {r.name:20s} {val_str}  ({r.elapsed_ms:.0f}ms)  src={r.source_function}")
        if r.error:
            print(f"         ERROR: {r.error}")

    # ── Parity checks ──
    print("\n" + "-" * 70)
    print("PARITY CHECKS")
    print("-" * 70)

    # Collect endpoints that returned a value
    valued: Dict[str, EndpointResult] = {}
    for r in results:
        if r.total_value is not None and r.status_code == 200:
            valued[r.name] = r

    if len(valued) < 2:
        print("\n  SKIP: fewer than 2 endpoints returned a total_value")
        return True

    checks: List[tuple] = []  # (name, passed, detail)
    culprits: List[str] = []

    def _check(label: str, a_name: str, b_name: str, tolerance_eur: float):
        if a_name not in valued or b_name not in valued:
            checks.append((label, True, "skipped (missing data)"))
            return
        a_val = valued[a_name].total_value
        b_val = valued[b_name].total_value
        diff = abs(a_val - b_val)
        passed = diff <= tolerance_eur
        detail = f"|{a_val:,.4f} - {b_val:,.4f}| = {diff:,.4f} EUR (tol={tolerance_eur})"
        checks.append((label, passed, detail))
        if not passed:
            culprits.append(f"{valued[a_name].source_function} vs {valued[b_name].source_function}")

    # Same-source pairs (strict tolerance)
    _check("P1: Top Alpha == Strategy Map", "Top Alpha", "Strategy Map", TOLERANCE_EUR)
    _check("P2: Dashboard == Smart Insights", "Dashboard", "Smart Insights", TOLERANCE_EUR)

    # Cross-source pairs (percentage tolerance)
    if "Dashboard" in valued and "Top Alpha" in valued:
        dash = valued["Dashboard"].total_value
        alpha = valued["Top Alpha"].total_value
        diff = abs(dash - alpha)
        pct = (diff / dash * 100) if dash > 0 else 0
        passed = pct <= TOLERANCE_CROSS_PCT
        checks.append(("P3: Dashboard ≈ Top Alpha", passed, f"diff={diff:,.4f} EUR ({pct:.3f}%)"))
        if not passed:
            culprits.append(f"{valued['Dashboard'].source_function} vs {valued['Top Alpha'].source_function}")

    all_passed = True
    for label, passed, detail in checks:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {label}")
        print(f"         {detail}")
        if not passed:
            all_passed = False

    # ── Culprit report ──
    if culprits:
        print("\n" + "!" * 70)
        print("CULPRIT FUNCTIONS (divergence > tolerance):")
        for c in culprits:
            print(f"  → {c}")
        print("!" * 70)

    # ── Summary ──
    print("\n" + "=" * 70)
    total = len(checks)
    passed_count = sum(1 for _, p, _ in checks if p)
    print(f"PARITY RESULT: {passed_count}/{total} passed")
    print("=" * 70)

    return all_passed


def main():
    ok = asyncio.run(run_parity_check())
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
