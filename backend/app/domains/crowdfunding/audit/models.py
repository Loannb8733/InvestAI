import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db.base import Base


class ProjectAudit(Base):
    """Analyse de risque d'un projet tirée de ses PDF ; ``analysis_source`` nomme le fournisseur ou « statique »."""

    __tablename__ = "project_audits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("crowdfunding_projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    file_names: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    document_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    project_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    operator: Mapped[str | None] = mapped_column(String(200), nullable=True)
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    tri: Mapped[Decimal | None] = mapped_column(Numeric(precision=6, scale=3), nullable=True)
    duration_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    collection_amount: Mapped[Decimal | None] = mapped_column(Numeric(precision=14, scale=2), nullable=True)
    margin_percent: Mapped[Decimal | None] = mapped_column(Numeric(precision=6, scale=3), nullable=True)
    ltv: Mapped[Decimal | None] = mapped_column(Numeric(precision=6, scale=3), nullable=True)
    ltc: Mapped[Decimal | None] = mapped_column(Numeric(precision=6, scale=3), nullable=True)
    pre_sales_percent: Mapped[Decimal | None] = mapped_column(Numeric(precision=6, scale=3), nullable=True)
    equity_contribution: Mapped[Decimal | None] = mapped_column(Numeric(precision=14, scale=2), nullable=True)
    guarantees: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, default=list)
    admin_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    score_operator: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_location: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_guarantees: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_risk_return: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_admin: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    points_forts: Mapped[list[str] | None] = mapped_column(JSONB, default=list)
    points_vigilance: Mapped[list[str] | None] = mapped_column(JSONB, default=list)
    red_flags: Mapped[list[str] | None] = mapped_column(JSONB, default=list)
    verdict: Mapped[str | None] = mapped_column(String(20), nullable=True)
    suggested_investment: Mapped[Decimal | None] = mapped_column(Numeric(precision=12, scale=2), nullable=True)
    raw_analysis: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    diversification_impact: Mapped[str | None] = mapped_column(String(20), nullable=True)
    correlation_score: Mapped[Decimal | None] = mapped_column(Numeric(precision=4, scale=2), nullable=True)
    portfolio_concentration: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
