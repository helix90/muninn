"""Add propagation_id to events and agent_runs for pipeline trace.

Revision ID: 014
Revises: 013
"""

from alembic import op
import sqlalchemy as sa

revision = '014'
down_revision = '013'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('events', sa.Column('propagation_id', sa.String(36), nullable=True))
    op.add_column('agent_runs', sa.Column('propagation_id', sa.String(36), nullable=True))
    op.create_index('idx_events_propagation_id', 'events', ['propagation_id'])
    op.create_index('idx_agent_runs_propagation_id', 'agent_runs', ['propagation_id'])


def downgrade():
    op.drop_index('idx_agent_runs_propagation_id', table_name='agent_runs')
    op.drop_index('idx_events_propagation_id', table_name='events')
    op.drop_column('agent_runs', 'propagation_id')
    op.drop_column('events', 'propagation_id')
