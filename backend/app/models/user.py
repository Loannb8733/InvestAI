"""User model."""

import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, Enum, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.models import Base


class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    role = Column(Enum(UserRole), default=UserRole.USER, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    mfa_enabled = Column(Boolean, default=False, nullable=False)
    mfa_secret = Column(String(255), nullable=True)
    mfa_backup_codes = Column(Text, nullable=True)  # JSON array of hashed backup codes
    preferred_currency = Column(String(10), default="EUR", nullable=False)
    telegram_chat_id = Column(String(100), nullable=True)
    telegram_enabled = Column(Boolean, default=False, nullable=False)
    # Allocation cible par classe crypto (ex: {"L1": 0.5, "Stable": 0.2, ...},
    # fractions sommant à 1.0). Clé de voûte du pilotage : widget d'écart sur
    # le dashboard + rapport de rebalancing. NULL = pas encore définie.
    target_allocations = Column(JSONB, nullable=True)
    # --- Profil investisseur (paramètres financiers de pilotage) ---------
    # Tranche marginale d'imposition (0, 0.11, 0.30, 0.41, 0.45). Consommée
    # par l'estimation d'impôt au barème progressif (dashboard, rapports).
    # NULL = non renseignée → l'UI affiche le plancher PS 17,2 % seul.
    tmi_rate = Column(Numeric(4, 3), nullable=True)
    # Profil de risque : "conservative" / "moderate" / "aggressive".
    # Consommé par les suggestions de déploiement de capital.
    risk_profile = Column(String(20), nullable=True)
    # Montant investi en DCA chaque mois (EUR). Pré-remplit les simulateurs.
    monthly_dca_eur = Column(Numeric(10, 2), nullable=True)
    email_verified = Column(Boolean, default=False, nullable=False)
    email_verification_token = Column(String(255), nullable=True)
    email_verification_expires = Column(DateTime(timezone=True), nullable=True)
    password_reset_token = Column(String(255), nullable=True)
    password_reset_expires = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
