"""Test analytics edge cases and interpretation logic.

Verifies that:
- Analytics endpoint returns 200 with interpretations
- Sharpe/Sortino/Calmar have contextual interpretations
- Short history (<20 days) shows warning interpretation
- XIRR endpoint returns 200 (regression)
- All ratios are finite numbers (no NaN/Inf)

Run inside Docker:
    TOKEN=... docker compose exec -e INVESTAI_TOKEN=$TOKEN backend python -m tests.test_analytics_edge_cases
"""

import math
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
    print("ANALYTICS EDGE CASES VERIFICATION")
    print("=" * 60)

    results = []

    def check(name: str, condition: bool, detail: str = ""):
        status = "PASS" if condition else "FAIL"
        results.append((name, condition))
        print(f"  {status}  {name}" + (f" -- {detail}" if detail else ""))

    # ── 1. Analytics endpoint with 60 days (default) ──
    print(f"\nFetching analytics (60d) from {BASE_URL}/analytics ...")
    r = httpx.get(f"{BASE_URL}/analytics", params={"days": 60}, headers=headers, timeout=30)
    check("A1: Analytics 60d returns 200", r.status_code == 200, f"status={r.status_code}")

    if r.status_code != 200:
        print(f"  Response: {r.text[:500]}")
        print("\n" + "=" * 60)
        print("ANALYTICS EDGE CASES: 0 passed, 1 failed")
        print("=" * 60)
        sys.exit(1)

    data = r.json()
    sharpe = data.get("sharpe_ratio", 0)
    sortino = data.get("sortino_ratio", 0)
    calmar = data.get("calmar_ratio", 0)
    interp = data.get("interpretations", {})

    print(f"  Sharpe={sharpe}, Sortino={sortino}, Calmar={calmar}")
    print(f"  Interpretations keys: {list(interp.keys())}")

    # ── 2. Ratios are finite numbers ──
    check(
        "A2: Sharpe is finite",
        isinstance(sharpe, (int, float)) and math.isfinite(sharpe),
        f"sharpe={sharpe}",
    )
    check(
        "A3: Sortino is finite",
        isinstance(sortino, (int, float)) and math.isfinite(sortino),
        f"sortino={sortino}",
    )
    check(
        "A4: Calmar is finite",
        isinstance(calmar, (int, float)) and math.isfinite(calmar),
        f"calmar={calmar}",
    )

    # ── 3. Interpretations present for 60d ──
    check(
        "A5: interpretations field present",
        "interpretations" in data,
    )
    if data.get("asset_count", 0) > 0:
        check(
            "A6: sharpe interpretation present (60d)",
            "sharpe" in interp,
            f"keys={list(interp.keys())}",
        )
        check(
            "A7: sortino interpretation present (60d)",
            "sortino" in interp,
            f"keys={list(interp.keys())}",
        )
        check(
            "A8: calmar interpretation present (60d)",
            "calmar" in interp,
            f"keys={list(interp.keys())}",
        )
    else:
        print("  SKIP: empty portfolio — no interpretations expected")
        check("A6: empty portfolio skip", True)
        check("A7: empty portfolio skip", True)
        check("A8: empty portfolio skip", True)

    # ── 4. Short history (1 day) → should have "global" warning ──
    print(f"\nFetching analytics (1d) from {BASE_URL}/analytics ...")
    r_short = httpx.get(f"{BASE_URL}/analytics", params={"days": 1}, headers=headers, timeout=30)
    check("A9: Analytics 1d returns 200", r_short.status_code == 200, f"status={r_short.status_code}")

    if r_short.status_code == 200:
        short_data = r_short.json()
        short_interp = short_data.get("interpretations", {})
        print(f"  1d interpretations keys: {list(short_interp.keys())}")

        if short_data.get("asset_count", 0) > 0:
            check(
                "A10: Short history has 'global' warning",
                "global" in short_interp,
                f"keys={list(short_interp.keys())}",
            )
        else:
            check("A10: empty portfolio skip", True)
    else:
        check("A10: Short history test skipped", True)

    # ── 5. XIRR still works (regression) ──
    print(f"\nFetching XIRR from {BASE_URL}/analytics/xirr ...")
    r_xirr = httpx.get(f"{BASE_URL}/analytics/xirr", headers=headers, timeout=30)
    check(
        "A11: XIRR returns 200 (no 500)",
        r_xirr.status_code == 200,
        f"status={r_xirr.status_code}",
    )

    if r_xirr.status_code == 200:
        xirr_data = r_xirr.json()
        xirr_val = xirr_data.get("xirr")
        if xirr_val is not None:
            check(
                "A12: XIRR is finite",
                isinstance(xirr_val, (int, float)) and math.isfinite(xirr_val),
                f"xirr={xirr_val}",
            )
        else:
            check("A12: XIRR is None (acceptable)", True)
    else:
        check("A12: XIRR skipped", False)

    # ── 6. Volatility zero edge case (all ratios should be 0) ──
    vol = data.get("portfolio_volatility", 0)
    if vol == 0 and data.get("asset_count", 0) > 0:
        check(
            "A13: Zero vol → Sharpe == 0",
            sharpe == 0,
            f"sharpe={sharpe}",
        )
    else:
        check("A13: Non-zero vol (skip zero-vol check)", True, f"vol={vol}")

    # ── Summary ──
    passed = sum(1 for _, ok in results if ok)
    failed = sum(1 for _, ok in results if not ok)
    print("\n" + "=" * 60)
    print(f"ANALYTICS EDGE CASES: {passed} passed, {failed} failed")
    print("=" * 60)

    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
