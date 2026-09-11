"""Portfolio snapshot model."""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.models import Base


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    portfolio_id = Column(
        UUID(as_uuid=True),
        ForeignKey("portfolios.id", ondelete="SET NULL"),
        nullable=True,
    )
    snapshot_date = Column(DateTime(timezone=True), nullable=False)
    total_value = Column(Numeric(precision=18, scale=2), nullable=False)
    total_invested = Column(Numeric(precision=18, scale=2), nullable=False)
    total_gain_loss = Column(Numeric(precision=18, scale=2), nullable=False)
    currency = Column(String(10), default="EUR", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Les deux index uniques « un instantané par jour », déclarés ici et non
    # plus seulement dans la migration `n5i6j7k8l9m0`.
    #
    # Absents du modèle, ils manquaient à la base de test, que `create_all`
    # bâtit depuis le modèle. Le test « deux consultations le même jour »
    # passait donc sans jamais éprouver la contrainte, et la course entre deux
    # chargements simultanés — qui faisait tomber le tableau de bord en 500 —
    # restait invisible.
    #
    # Sans effet en production : `create_all` ne touche pas aux tables qui
    # existent déjà, et la migration a posé ces index depuis longtemps.
    __table_args__ = (
        Index(
            "uq_portfolio_snapshots_user_day_global",
            "user_id",
            text("((snapshot_date AT TIME ZONE 'UTC')::date)"),
            unique=True,
            postgresql_where=text("portfolio_id IS NULL"),
        ),
        Index(
            "uq_portfolio_snapshots_user_portfolio_day",
            "user_id",
            "portfolio_id",
            text("((snapshot_date AT TIME ZONE 'UTC')::date)"),
            unique=True,
            postgresql_where=text("portfolio_id IS NOT NULL"),
        ),
    )
