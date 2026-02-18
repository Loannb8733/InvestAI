"""Simulation model."""

import enum
import uuid

from sqlalchemy import Column, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.sql import func

from app.models import Base


class SimulationType(str, enum.Enum):
    FIRE = "fire"
    PROJECTION = "projection"
    DCA = "dca"
    WHAT_IF = "what_if"
    REBALANCE = "rebalance"


class Simulation(Base):
    __tablename__ = "simulations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    simulation_type = Column(Enum(SimulationType), nullable=False)
    parameters = Column(JSON, nullable=False, default=dict)
    results = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
