"""ProjectAudit model — stores AI analysis results for crowdfunding projects."""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.sql import func

from app.models import Base


class ProjectAudit(Base):
    __tablename__ = "project_audits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("crowdfunding_projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Input
    file_names = Column(ARRAY(Text), nullable=False)
    document_type = Column(String(50), nullable=True)

    # Extracted data
    project_name = Column(String(300), nullable=True)
    operator = Column(String(200), nullable=True)
    location = Column(String(300), nullable=True)
    tri = Column(Numeric(precision=6, scale=3), nullable=True)
    duration_min = Column(Integer, nullable=True)
    duration_max = Column(Integer, nullable=True)
    collection_amount = Column(Numeric(precision=14, scale=2), nullable=True)
    margin_percent = Column(Numeric(precision=6, scale=3), nullable=True)
    ltv = Column(Numeric(precision=6, scale=3), nullable=True)
    ltc = Column(Numeric(precision=6, scale=3), nullable=True)
    pre_sales_percent = Column(Numeric(precision=6, scale=3), nullable=True)
    equity_contribution = Column(Numeric(precision=14, scale=2), nullable=True)

    # Guarantees & admin
    guarantees = Column(JSONB, default=list)
    admin_status = Column(String(100), nullable=True)

    # Scoring (1-10)
    score_operator = Column(Integer, nullable=True)
    score_location = Column(Integer, nullable=True)
    score_guarantees = Column(Integer, nullable=True)
    score_risk_return = Column(Integer, nullable=True)
    score_admin = Column(Integer, nullable=True)
    risk_score = Column(Integer, nullable=True)

    # Analysis
    points_forts = Column(JSONB, default=list)
    points_vigilance = Column(JSONB, default=list)
    red_flags = Column(JSONB, default=list)
    verdict = Column(String(20), nullable=True)
    suggested_investment = Column(Numeric(precision=12, scale=2), nullable=True)
    raw_analysis = Column(Text, nullable=True)

    # Diversification analysis
    diversification_impact = Column(String(20), nullable=True)  # "ameliore" / "degrade" / "neutre"
    correlation_score = Column(Numeric(precision=4, scale=2), nullable=True)  # 0.00 - 1.00
    portfolio_concentration = Column(JSONB, default=dict)  # {geo, asset_type, risk_return}

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
