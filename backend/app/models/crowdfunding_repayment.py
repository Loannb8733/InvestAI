"""CrowdfundingRepayment model — individual payments received from projects."""

import enum
import uuid

from sqlalchemy import Column, Date, DateTime, Enum, ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.models import Base


class PaymentType(str, enum.Enum):
    INTEREST = "interest"
    CAPITAL = "capital"
    BOTH = "both"


class CrowdfundingRepayment(Base):
    __tablename__ = "crowdfunding_repayments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("crowdfunding_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    payment_date = Column(Date, nullable=False)
    amount = Column(Numeric(precision=12, scale=2), nullable=False)
    payment_type = Column(Enum(PaymentType), nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
