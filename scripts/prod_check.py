#!/usr/bin/env python3
"""Smoke test for InvestAI production infrastructure.

Usage:
    python scripts/prod_check.py [BASE_URL]

Default BASE_URL: https://investai-api.onrender.com
"""

import sys
import time

import httpx

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "https://investai-api.onrender.com"

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
WARN = "\033[93m⚠\033[0m"

results = []


def check(name: str, passed: bool, detail: str = ""):
    status = PASS if passed else FAIL
    results.append(passed)
    suffix = f" ({detail})" if detail else ""
    print(f"  {status} {name}{suffix}")


def main():
    print(f"\n{'='*50}")
    print(f"  InvestAI Production Smoke Test")
    print(f"  Target: {BASE_URL}")
    print(f"{'='*50}\n")

    client = httpx.Client(timeout=60, follow_redirects=True)

    # --- 1. Health / Liveness ---
    print("[1/5] Health Check")
    try:
        t0 = time.time()
        r = client.get(f"{BASE_URL}/health")
        dt = (time.time() - t0) * 1000
        data = r.json()
        check("Liveness /health", r.status_code == 200, f"{dt:.0f}ms")
        check("Status = alive", data.get("status") == "alive")
    except Exception as e:
        check("Liveness /health", False, str(e))

    # --- 2. Readiness (DB + Redis) ---
    print("\n[2/5] Readiness Check (DB + Redis)")
    try:
        t0 = time.time()
        r = client.get(f"{BASE_URL}/health/ready")
        dt = (time.time() - t0) * 1000
        data = r.json()
        check("Readiness /health/ready", r.status_code == 200, f"{dt:.0f}ms")
        check("Database = ok", data.get("database") == "ok")
        check("Redis = ok", data.get("redis") == "ok")
        check("DB response < 500ms", dt < 500, f"{dt:.0f}ms")
    except Exception as e:
        check("Readiness /health/ready", False, str(e))

    # --- 3. Auth endpoint ---
    print("\n[3/5] Auth Endpoint")
    try:
        r = client.post(
            f"{BASE_URL}/api/v1/auth/login",
            json={"email": "smoke@test.invalid", "password": "x"},
        )
        # 422 (validation) or 401 (bad creds) both mean the endpoint is alive
        check(
            "POST /api/v1/auth/login responds",
            r.status_code in (401, 422),
            f"HTTP {r.status_code}",
        )
    except Exception as e:
        check("Auth endpoint", False, str(e))

    # --- 4. Crowdfunding endpoint (requires auth) ---
    print("\n[4/5] Crowdfunding Endpoint")
    try:
        r = client.get(f"{BASE_URL}/api/v1/crowdfunding")
        check(
            "GET /api/v1/crowdfunding reachable",
            r.status_code in (401, 200),
            f"HTTP {r.status_code}",
        )
    except Exception as e:
        check("Crowdfunding endpoint", False, str(e))

    # --- 5. CORS headers ---
    print("\n[5/5] CORS Configuration")
    try:
        r = client.options(
            f"{BASE_URL}/api/v1/auth/login",
            headers={
                "Origin": "https://investai-orcin.vercel.app",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization,Content-Type",
            },
        )
        acao = r.headers.get("access-control-allow-origin", "")
        check(
            "CORS allows Vercel origin",
            "investai-orcin.vercel.app" in acao,
            acao or "missing",
        )
        check(
            "CORS allows credentials",
            r.headers.get("access-control-allow-credentials") == "true",
        )
    except Exception as e:
        check("CORS check", False, str(e))

    # --- Summary ---
    passed = sum(results)
    total = len(results)
    all_ok = all(results)
    print(f"\n{'='*50}")
    print(f"  Result: {passed}/{total} checks passed")
    print(f"{'='*50}\n")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
