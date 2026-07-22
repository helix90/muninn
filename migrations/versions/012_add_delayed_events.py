"""Add delayed_events table for DelayAgent buffering.

Revision ID: 012
Revises: 011
"""

from alembic import op
import sqlalchemy as sa

revision = '012'
down_revision = '011'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'delayed_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('agent_id', sa.Integer(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('metadata', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('release_at', sa.DateTime(), nullable=False),
        sa.Column('released', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['agent_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_delayed_events_release', 'delayed_events', ['agent_id', 'release_at'])
    op.create_index('idx_delayed_events_pending', 'delayed_events', ['released', 'release_at'])


def downgrade():
    op.drop_index('idx_delayed_events_pending', table_name='delayed_events')
    op.drop_index('idx_delayed_events_release', table_name='delayed_events')
    op.drop_table('delayed_events')
