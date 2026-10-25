import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, LargeBinary, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db.base import Base


class RepaymentType(enum.StrEnum):
    IN_FINE = "in_fine"
    AMORTIZABLE = "amortizable"


class ProjectStatus(enum.StrEnum):
    FUNDING = "funding"
    ACTIVE = "active"
    COMPLETED = "completed"
    DELAYED = "delayed"
    DEFAULTED = "defaulted"


class PaymentType(enum.StrEnum):
    """Nature d'un versement ; REFERRAL est un bonus de plateforme, ni intérêt ni capital."""

    INTEREST = "interest"
    CAPITAL = "capital"
    BOTH = "both"
    REFERRAL = "referral"


class CrowdfundingProject(Base):
    """Conditions d'un investissement de crowdfunding, rattaché à son actif."""

    __tablename__ = "crowdfunding_projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    platform: Mapped[str] = mapped_column(String(100), nullable=False)
    project_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    invested_amount: Mapped[Decimal] = mapped_column(Numeric(precision=12, scale=2), nullable=False)
    annual_rate: Mapped[Decimal] = mapped_column(Numeric(precision=6, scale=3), nullable=False)
    duration_months: Mapped[Decimal] = mapped_column(Numeric(precision=4, scale=0), nullable=False)
    repayment_type: Mapped[RepaymentType] = mapped_column(
        Enum(RepaymentType), nullable=False, default=RepaymentType.IN_FINE
    )
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    estimated_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(Enum(ProjectStatus), nullable=False, default=ProjectStatus.ACTIVE)
    total_received: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2), default=Decimal("0"), nullable=False
    )
    interest_frequency: Mapped[str | None] = mapped_column(String(20), default="at_maturity", nullable=True)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(precision=5, scale=2), default=Decimal("30.00"), nullable=False)
    delay_months: Mapped[Decimal] = mapped_column(Numeric(precision=4, scale=0), default=Decimal("0"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CrowdfundingRepayment(Base):
    """Versement reçu d'un projet."""

    __tablename__ = "crowdfunding_repayments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("crowdfunding_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(precision=12, scale=2), nullable=False)
    payment_type: Mapped[PaymentType] = mapped_column(Enum(PaymentType), nullable=False)
    interest_amount: Mapped[Decimal | None] = mapped_column(Numeric(precision=12, scale=2), nullable=True)
    capital_amount: Mapped[Decimal | None] = mapped_column(Numeric(precision=12, scale=2), nullable=True)
    tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(precision=12, scale=2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CrowdfundingPaymentSchedule(Base):
    """Échéance contractuelle d'un projet, soldée par le versement qui la rapproche."""

    __tablename__ = "crowdfunding_payment_schedules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("crowdfunding_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_capital: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2), default=Decimal("0"), nullable=False
    )
    expected_interest: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2), default=Decimal("0"), nullable=False
    )
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    repayment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("crowdfunding_repayments.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ProjectDocument(Base):
    """PDF joint à un projet, conservé en base (10 Mo au plus)."""

    __tablename__ = "project_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("crowdfunding_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_name: Mapped[str] = mapped_column(String(300), nullable=False)
    file_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    audit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("project_audits.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
