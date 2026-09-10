"""Provenance de l'analyse d'audit (NEW-41).

Ajoute `project_audits.analysis_source` : le nom du fournisseur ayant produit
l'analyse ("Groq", "Gemini", "Anthropic", "Ollama") ou "statique" quand aucun
n'a répondu et que les chiffres viennent de l'extraction par expressions
régulières.

Écrite à la main. `alembic revision --autogenerate` proposait ici de
**supprimer la table `price_history`** et une vingtaine d'index : la base porte
des objets que les modèles ne déclarent pas — l'hypertable TimescaleDB et ses
index, notamment. Sa sortie ne doit pas être reprise telle quelle sur ce
projet.

Revision ID: cc8154d9307f
Revises: s0n1o2p3q4r5
Create Date: 2026-09-08
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "cc8154d9307f"
down_revision: Union[str, None] = "s0n1o2p3q4r5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "project_audits",
        sa.Column("analysis_source", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("project_audits", "analysis_source")
