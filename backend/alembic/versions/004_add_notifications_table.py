"""Add notifications table.

Revision ID: 004_add_notifications_table
Revises: 003_add_performance_indexes
Create Date: 2026-01-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = '004_add_notifications_table'
down_revision: Union[str, None] = '003_add_performance_indexes'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create notification type enum
    notification_type = sa.Enum(
        'alert_triggered',
        'price_update',
        'portfolio_milestone',
        'system',
        'dividend',
        'report_ready',
        name='notificationtype'
    )
    notification_type.create(op.get_bind(), checkfirst=True)

    # Create notification priority enum
    notification_priority = sa.Enum(
        'low',
        'normal',
        'high',
        'urgent',
        name='notificationpriority'
    )
    notification_priority.create(op.get_bind(), checkfirst=True)

    # Create notifications table
    op.create_table(
        'notifications',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('type', notification_type, nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('priority', notification_priority, nullable=False, server_default='normal'),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('reference_type', sa.String(50), nullable=True),
        sa.Column('reference_id', UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Create indexes for efficient queries
    op.create_index(
        'ix_notifications_user_id_is_read',
        'notifications',
        ['user_id', 'is_read'],
        unique=False
    )
    op.create_index(
        'ix_notifications_user_id_created_at',
        'notifications',
        ['user_id', 'created_at'],
        unique=False
    )
    op.create_index(
        'ix_notifications_reference',
        'notifications',
        ['reference_type', 'reference_id'],
        unique=False
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_notifications_reference', table_name='notifications')
    op.drop_index('ix_notifications_user_id_created_at', table_name='notifications')
    op.drop_index('ix_notifications_user_id_is_read', table_name='notifications')

    # Drop table
    op.drop_table('notifications')

    # Drop enums
    op.execute('DROP TYPE IF EXISTS notificationpriority')
    op.execute('DROP TYPE IF EXISTS notificationtype')
