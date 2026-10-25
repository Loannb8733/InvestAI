import logging
from typing import Any

from app.domains.crowdfunding.audit.financials import MERGED_FIELDS, ExtractedFinancials, extract_financials

logger = logging.getLogger(__name__)

STATIC_SOURCE = "statique"
UNKNOWN_SCORE = 5
NO_GUARANTEE_SCORE = 3


def _merged(file_contents: list[tuple[str, bytes]]) -> ExtractedFinancials:
    extracted = []
    for filename, content in file_contents:
        try:
            extracted.append(extract_financials(content))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Static extraction failed for %s: %s", filename, exc)
    merged = ExtractedFinancials()
    for financials in extracted:
        for name in MERGED_FIELDS:
            if getattr(merged, name) is None and getattr(financials, name) is not None:
                setattr(merged, name, getattr(financials, name))
    return merged


def _risk_return_score(margin: float | None) -> int:
    if margin is not None and margin >= 20:
        return 7
    if margin is not None and margin >= 10:
        return 5
    return 3


def _strengths(merged: ExtractedFinancials) -> list[str]:
    strengths = []
    margin = merged.gross_margin_percent
    if merged.target_rate and merged.target_rate >= 8:
        strengths.append(f"TRI attractif de {merged.target_rate}%")
    if margin and margin >= 20:
        strengths.append(f"Marge promoteur confortable ({margin:.1f}%)")
    if merged.ltv and merged.ltv < 60:
        strengths.append(f"LTV conservateur ({merged.ltv:.1f}%)")
    if merged.equity and merged.equity > 100000:
        strengths.append("Fonds propres significatifs de l'opérateur")
    return strengths


def analyze_statically(file_contents: list[tuple[str, bytes]]) -> dict[str, Any]:
    """Analyse sans modèle de langage : chiffres lus par expressions régulières et scores par défaut."""
    merged = _merged(file_contents)
    scores = {
        "score_operator": UNKNOWN_SCORE,
        "score_location": UNKNOWN_SCORE,
        "score_admin": UNKNOWN_SCORE,
        "score_guarantees": NO_GUARANTEE_SCORE,
        "score_risk_return": _risk_return_score(merged.gross_margin_percent),
    }
    scores["risk_score"] = round(sum(scores.values()) / len(scores))
    return {
        "project_name": "Analyse statique (sans IA)",
        "operator": None,
        "location": None,
        "document_type": "mixed",
        "tri": merged.target_rate,
        "duration_min": merged.duration_min,
        "duration_max": merged.duration_max,
        "collection_amount": merged.raise_amount,
        "margin_percent": merged.gross_margin_percent,
        "ltv": merged.ltv,
        "ltc": merged.ltc,
        "pre_sales_percent": merged.pre_sales or 0,
        "equity_contribution": merged.equity,
        "guarantees": [],
        "admin_status": None,
        "points_forts": _strengths(merged),
        "points_vigilance": ["Analyse statique (regex) — résultats partiels, relecture recommandée"],
        "red_flags": [],
        "verdict": "VIGILANCE",
        **scores,
    }
