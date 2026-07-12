"""Add REFERRAL to paymenttype enum (bonus de parrainage crowdfunding)

Ajoute la valeur ``REFERRAL`` à l'enum PG ``paymenttype`` : les bonus de
parrainage/plateforme (ex Tokimo « commission filleul ») sont encaissés en
cash mais ne sont ni un intérêt ni un remboursement de capital — comptabilisés
dans une poche à part, exclus du P&L d'intérêts, du XIRR et du rapport fiscal.

Revision ID: r9m0n1o2p3q4
Revises: q8l9m0n1o2p3
Create Date: 2026-07-12

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "r9m0n1o2p3q4"
down_revision: Union[str, None] = "q8l9m0n1o2p3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLAlchemy stocke le .name (majuscules) de l'Enum dans PostgreSQL.
    op.execute("ALTER TYPE paymenttype ADD VALUE IF NOT EXISTS 'REFERRAL'")


def downgrade() -> None:
    # PostgreSQL ne supporte pas la suppression de valeurs d'enum.
    pass
