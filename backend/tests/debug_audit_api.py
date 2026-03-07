"""Debug script — simulates an Audit Lab upload and validates the response schema.

Usage:
    python -m tests.debug_audit_api [--base-url http://localhost:8000]

Requires a running backend and a valid JWT token (set via TOKEN env var or .env).
"""

import argparse
import io
import os
import sys

import httpx


def make_test_pdf() -> bytes:
    """Create a minimal PDF with sample crowdfunding data."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        # Fallback: handcraft a minimal valid PDF
        return (
            b"%PDF-1.0\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R"
            b"/Contents 4 0 R>>endobj\n"
            b"4 0 obj<</Length 44>>stream\n"
            b"BT /F1 12 Tf 100 700 Td (Test PDF) Tj ET\nendstream\nendobj\n"
            b"xref\n0 5\n0000000000 65535 f \n"
            b"0000000009 00000 n \n0000000058 00000 n \n"
            b"0000000115 00000 n \n0000000206 00000 n \n"
            b"trailer<</Size 5/Root 1 0 R>>\nstartxref\n300\n%%EOF"
        )

    doc = fitz.open()
    page = doc.new_page()
    text = (
        "Projet : Porticcio - Clos des Orangers\n"
        "Opérateur : SCI Clos des Orangers\n"
        "Localisation : Porticcio, Corse-du-Sud\n"
        "TRI : 11,5%\n"
        "Durée : 18 à 36 mois\n"
        "Montant de la collecte : 800 000 €\n"
        "Chiffre d'affaires prévisionnel : 3 456 789 €\n"
        "Prix de revient : 2 714 321 €\n"
        "LTV : 65%\n"
        "LTC : 72%\n"
        "Pré-commercialisation : 45%\n"
        "Fonds propres : 350 000 €\n"
        "Garantie : Hypothèque de 1er rang\n"
        "PC purgé de tout recours\n"
    )
    page.insert_text((72, 72), text, fontsize=11)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


EXPECTED_FIELDS = {
    "id",
    "project_id",
    "file_names",
    "document_type",
    "project_name",
    "operator",
    "location",
    "tri",
    "duration_min",
    "duration_max",
    "collection_amount",
    "margin_percent",
    "ltv",
    "ltc",
    "pre_sales_percent",
    "equity_contribution",
    "guarantees",
    "admin_status",
    "score_operator",
    "score_location",
    "score_guarantees",
    "score_risk_return",
    "score_admin",
    "risk_score",
    "points_forts",
    "points_vigilance",
    "red_flags",
    "verdict",
    "suggested_investment",
    "diversification_impact",
    "correlation_score",
    "portfolio_concentration",
    "created_at",
}


def get_token(base_url: str) -> str:
    """Get JWT token from env or by logging in."""
    token = os.environ.get("TOKEN")
    if token:
        return token

    email = os.environ.get("TEST_EMAIL", "admin@investai.fr")
    password = os.environ.get("TEST_PASSWORD", "admin123")

    resp = httpx.post(
        f"{base_url}/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    if resp.status_code != 200:
        print(f"Login failed ({resp.status_code}): {resp.text}")
        sys.exit(1)
    return resp.json()["access_token"]


def main():
    parser = argparse.ArgumentParser(description="Debug Audit Lab API")
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    token = get_token(base)
    headers = {"Authorization": f"Bearer {token}"}

    # ── Test 1: GET /audits (should not 422) ──
    print("\n[1] GET /crowdfunding/audits ...")
    resp = httpx.get(f"{base}/api/v1/crowdfunding/audits", headers=headers)
    print(f"    Status: {resp.status_code}")
    if resp.status_code == 200:
        audits = resp.json()
        print(f"    Audits count: {len(audits)}")
        if audits:
            missing = EXPECTED_FIELDS - set(audits[0].keys())
            extra = set(audits[0].keys()) - EXPECTED_FIELDS
            if missing:
                print(f"    MISSING fields: {missing}")
            if extra:
                print(f"    EXTRA fields (ok): {extra}")
            print(f"    First audit verdict: {audits[0].get('verdict')}")
    else:
        print(f"    ERROR: {resp.text[:300]}")

    # ── Test 2: POST /analyze with test PDF ──
    print("\n[2] POST /crowdfunding/analyze ...")
    pdf_bytes = make_test_pdf()
    files = [("files", ("test_porticcio.pdf", io.BytesIO(pdf_bytes), "application/pdf"))]

    resp = httpx.post(
        f"{base}/api/v1/crowdfunding/analyze",
        headers=headers,
        files=files,
        timeout=120.0,
    )
    print(f"    Status: {resp.status_code}")
    if resp.status_code in (200, 201):
        data = resp.json()
        print(f"    Project: {data.get('project_name')}")
        print(f"    TRI: {data.get('tri')}%")
        print(f"    Duration: {data.get('duration_min')}-{data.get('duration_max')} months")
        print(f"    Verdict: {data.get('verdict')}")
        print(f"    Risk Score: {data.get('risk_score')}/10")
        print(f"    Diversification: {data.get('diversification_impact')} (corr={data.get('correlation_score')})")
        print(f"    Suggested: {data.get('suggested_investment')}€")

        missing = EXPECTED_FIELDS - set(data.keys())
        if missing:
            print(f"    MISSING fields: {missing}")
        else:
            print("    All expected fields present")
    elif resp.status_code == 400:
        print(f"    Validation error: {resp.text[:300]}")
    elif resp.status_code == 503:
        print(f"    Service unavailable (no API key): {resp.text[:200]}")
    else:
        print(f"    ERROR: {resp.text[:300]}")

    print("\nDone.")


if __name__ == "__main__":
    main()
