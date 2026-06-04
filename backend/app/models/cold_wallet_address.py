"""Cold wallet address → label mapping.

Lets the scheduled exchange sync route a withdrawal to the right named cold
wallet (Tangem, Ledger, …) based on its destination address, instead of always
defaulting to a single hardcoded wallet. Unknown addresses fall back to the
default ``COLD_WALLET_DESTINATION``.
"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.models import Base


class ColdWalletAddress(Base):
    __tablename__ = "cold_wallet_addresses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Destination address as reported by the exchange. Stored raw; matched
    # case-insensitively (some chains are case-sensitive, but a same-address
    # case collision is not realistic in practice).
    address = Column(String(255), nullable=False)
    # Human-friendly wallet name used as the destination asset's `exchange`.
    label = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "address", name="uq_cold_wallet_user_address"),)
