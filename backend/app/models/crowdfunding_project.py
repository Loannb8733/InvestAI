"""CrowdfundingProject model — extended metadata for crowdfunding assets."""

import enum
import uuid
from decimal import Decimal

from sqlalchemy import Column, Date, DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.models import Base


class RepaymentType(str, enum.Enum):
    IN_FINE = "in_fine"
    AMORTIZABLE = "amortizable"


class ProjectStatus(str, enum.Enum):
    FUNDING = "funding"
    ACTIVE = "active"
    COMPLETED = "completed"
    DELAYED = "delayed"
    DEFAULTED = "defaulted"


class CrowdfundingProject(Base):
    __tablename__ = "crowdfunding_projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id = Column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Platform info
    platform = Column(String(100), nullable=False)
    project_name = Column(String(300), nullable=True)
    description = Column(Text, nullable=True)
    project_url = Column(String(500), nullable=True)

    # Financial terms
    invested_amount = Column(Numeric(precision=12, scale=2), nullable=False)
    annual_rate = Column(Numeric(precision=6, scale=3), nullable=False)
    duration_months = Column(Numeric(precision=4, scale=0), nullable=False)
    repayment_type = Column(Enum(RepaymentType), nullable=False, default=RepaymentType.IN_FINE)

    # Timeline
    start_date = Column(Date, nullable=True)
    estimated_end_date = Column(Date, nullable=True)
    actual_end_date = Column(Date, nullable=True)

    # Status
    status = Column(Enum(ProjectStatus), nullable=False, default=ProjectStatus.ACTIVE)

    # Tracking
    total_received = Column(Numeric(precision=12, scale=2), default=Decimal("0"), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
