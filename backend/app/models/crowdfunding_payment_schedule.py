"""CrowdfundingPaymentSchedule model — contractual payment schedule entries."""

import uuid
from decimal import Decimal

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.models import Base


class CrowdfundingPaymentSchedule(Base):
    __tablename__ = "crowdfunding_payment_schedules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("crowdfunding_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    due_date = Column(Date, nullable=False)
    expected_capital = Column(Numeric(precision=12, scale=2), default=Decimal("0"), nullable=False)
    expected_interest = Column(Numeric(precision=12, scale=2), default=Decimal("0"), nullable=False)
    is_completed = Column(Boolean, default=False, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    repayment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("crowdfunding_repayments.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
