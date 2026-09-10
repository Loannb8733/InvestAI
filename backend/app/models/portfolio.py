"""Portfolio model."""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.sql import func

from app.models import Base

#: Marqueur du portefeuille que l'application gère elle-même pour le
#: crowdfunding. Un portefeuille ordinaire n'en porte aucun.
PORTEFEUILLE_CROWDFUNDING = "crowdfunding"


class Portfolio(Base):
    __tablename__ = "portfolios"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(100), nullable=False)
    description = Column(String(500), nullable=True)
    # Nature du portefeuille, quand elle n'est pas ordinaire.
    #
    # Le portefeuille de crowdfunding était reconnu **à son nom** : le serveur
    # cherchait `name == "Crowdfunding"` à la casse exacte, l'écran l'écartait
    # par `name.toLowerCase() !== 'crowdfunding'`. Deux règles pour une même
    # question, et un geste banal — renommer — dispersait les projets à venir
    # dans un second portefeuille tout en faisant réapparaître les actifs
    # existants dans la page Portefeuille (NEW-68).
    #
    # `None` pour un portefeuille ordinaire ; `"crowdfunding"` pour celui que
    # l'application gère elle-même. Le nom redevient ce qu'il doit être : un
    # libellé que l'utilisateur peut changer.
    kind = Column(String(30), nullable=True, index=True)
    cash_balances = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
