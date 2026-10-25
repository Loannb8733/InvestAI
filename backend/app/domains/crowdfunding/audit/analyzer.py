import json
import logging
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.crowdfunding.audit import providers
from app.domains.crowdfunding.audit.models import ProjectAudit
from app.domains.crowdfunding.audit.pdf_text import extract_text
from app.domains.crowdfunding.audit.prompt import build_messages, parse_answer
from app.domains.crowdfunding.audit.scoring import add_red_flags, diversification, suggest_investment
from app.domains.crowdfunding.audit.static import STATIC_SOURCE, analyze_statically

logger = logging.getLogger(__name__)

DECIMAL_FIELDS = (
    "tri",
    "collection_amount",
    "margin_percent",
    "ltv",
    "ltc",
    "pre_sales_percent",
    "equity_contribution",
    "correlation_score",
)
PLAIN_FIELDS = (
    "document_type",
    "project_name",
    "operator",
    "location",
    "duration_min",
    "duration_max",
    "admin_status",
    "score_operator",
    "score_location",
    "score_guarantees",
    "score_risk_return",
    "score_admin",
    "risk_score",
    "diversification_impact",
)


def _texts(file_contents: list[tuple[str, bytes]]) -> list[str]:
    texts = []
    for filename, content in file_contents:
        try:
            text = extract_text(content)
        except Exception as exc:
            logger.error("Failed to extract text from %s: %s", filename, exc)
            raise ValueError(f"Impossible de lire le PDF '{filename}' — fichier corrompu ou protégé") from exc
        if text.strip():
            texts.append(text)
    if not texts:
        raise ValueError("Aucun texte extractible des PDFs fournis")
    return texts


async def _ask_models(messages: list[dict[str, str]]) -> tuple[Any, str | None, str | None]:
    for name, provider in providers.configured_providers():
        try:
            raw_text = await provider(messages)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Provider %s failed: %s", name, exc)
            continue
        data = parse_answer(raw_text)
        if data is None:
            logger.warning("LLM returned non-JSON, falling back to static: %s", raw_text[:100])
        return data, raw_text, name
    return None, None, None


def _audit(data: dict[str, Any], **fields: Any) -> ProjectAudit:
    return ProjectAudit(
        id=uuid.uuid4(),
        **fields,
        **{name: data.get(name) for name in PLAIN_FIELDS},
        **{name: Decimal(str(data[name])) if data.get(name) is not None else None for name in DECIMAL_FIELDS},
        guarantees=data.get("guarantees", []),
        points_forts=data.get("points_forts", []),
        points_vigilance=data.get("points_vigilance", []),
        red_flags=data.get("red_flags", []),
        verdict=data.get("verdict", "VIGILANCE"),
        suggested_investment=Decimal(str(data.get("suggested_investment", 0))),
        portfolio_concentration=data.get("portfolio_concentration", {}),
    )


async def analyze_documents(
    db: AsyncSession,
    file_contents: list[tuple[str, bytes]],
    user_id: uuid.UUID,
    project_id: uuid.UUID | None = None,
    cash: float = 0.0,
    total_capital: float = 0.0,
) -> ProjectAudit:
    """Analyse les PDF par le premier fournisseur qui répond, sinon par expressions régulières, et enregistre l'audit.

    ``ValueError`` quand aucun PDF ne contient de texte lisible.
    """
    messages = build_messages(_texts(file_contents), cash, total_capital)
    data, raw_text, source = await _ask_models(messages)
    if data is None:
        logger.info("All LLM providers failed or unavailable — using static analysis")
        data = analyze_statically(file_contents)
        raw_text = json.dumps(data, ensure_ascii=False)
        source = STATIC_SOURCE
    data = add_red_flags(data)
    data.update(await diversification(db, user_id, data))
    data = suggest_investment(data, total_capital, cash)
    audit = _audit(
        data,
        user_id=user_id,
        project_id=project_id,
        file_names=[filename for filename, _ in file_contents],
        raw_analysis=raw_text,
        analysis_source=source,
    )
    db.add(audit)
    await db.flush()
    logger.info(
        "Audit saved: %s — verdict=%s, risk_score=%s, source=%s", audit.id, audit.verdict, audit.risk_score, source
    )
    return audit
