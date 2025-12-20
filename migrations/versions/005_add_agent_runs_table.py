"""Add agent_runs table

Revision ID: 005
Revises: 004
Create Date: 2025-12-16 00:00:00.000000

Creates the agent_runs table for tracking individual agent executions.
This table is used by the AgentService to track agent run statistics and history.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade():
    # Create agent_runs table for tracking agent executions
    op.create_table('agent_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('agent_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(50), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('manual', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('input_event_ids', postgresql.JSONB(), nullable=True, server_default='[]'),
        sa.Column('output_event_ids', postgresql.JSONB(), nullable=True, server_default='[]'),
        sa.ForeignKeyConstraint(['agent_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name='valid_agent_run_status'
        )
    )

    # Create indexes for agent_runs table
    op.create_index('idx_agent_runs_agent_status', 'agent_runs', ['agent_id', 'status'])
    op.create_index('idx_agent_runs_started_at', 'agent_runs', ['started_at'])


def downgrade():
    # Drop indexes
    op.drop_index('idx_agent_runs_started_at', 'agent_runs')
    op.drop_index('idx_agent_runs_agent_status', 'agent_runs')

    # Drop table
    op.drop_table('agent_runs')
