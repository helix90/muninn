"""Add agent system

Revision ID: 003
Revises: 002
Create Date: 2025-12-10 00:00:00.000000

Adds support for the new agent-based architecture:
- Events table for agent-to-agent communication
- AgentMemory table for persistent agent state
- AgentLinks table for agent data flow connections
- Updates to support event-based workflows
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade():
    # Create events table for agent communication
    op.create_table('events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('agent_id', sa.Integer(), nullable=False),
        sa.Column('agent_type', sa.String(50), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('payload', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('metadata', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['agent_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for events table
    op.create_index('idx_events_agent_created', 'events', ['agent_id', 'created_at'])
    op.create_index('idx_events_user_created', 'events', ['user_id', 'created_at'])
    op.create_index('idx_events_type_created', 'events', ['agent_type', 'created_at'])
    op.create_index('idx_events_expires', 'events', ['expires_at'])

    # Create agent_memory table for persistent agent state
    op.create_table('agent_memory',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('agent_id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(255), nullable=False),
        sa.Column('value', postgresql.JSONB(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['agent_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes and unique constraint for agent_memory
    op.create_index('idx_agent_memory_agent_key', 'agent_memory', ['agent_id', 'key'], unique=True)
    op.create_index('idx_agent_memory_expires', 'agent_memory', ['expires_at'])

    # Create agent_links table for agent connections
    op.create_table('agent_links',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_agent_id', sa.Integer(), nullable=False),
        sa.Column('target_agent_id', sa.Integer(), nullable=False),
        sa.Column('config', postgresql.JSONB(), nullable=True, server_default='{}'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.ForeignKeyConstraint(['source_agent_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['target_agent_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('source_agent_id != target_agent_id', name='no_self_link')
    )

    # Create indexes for agent_links
    op.create_index('idx_agent_links_source', 'agent_links', ['source_agent_id'])
    op.create_index('idx_agent_links_target', 'agent_links', ['target_agent_id'])
    op.create_index('idx_agent_links_both', 'agent_links', ['source_agent_id', 'target_agent_id'], unique=True)
    op.create_index('idx_agent_links_active', 'agent_links', ['is_active'])

    # Add input_data column to job_runs if it doesn't exist
    # Check if column exists first to make migration idempotent
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('job_runs')]

    if 'input_data' not in columns:
        op.add_column('job_runs',
            sa.Column('input_data', postgresql.JSONB(), nullable=True, server_default='{}')
        )


def downgrade():
    # Remove input_data column from job_runs if it was added
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('job_runs')]

    if 'input_data' in columns:
        op.drop_column('job_runs', 'input_data')

    # Drop agent_links table
    op.drop_index('idx_agent_links_active', 'agent_links')
    op.drop_index('idx_agent_links_both', 'agent_links')
    op.drop_index('idx_agent_links_target', 'agent_links')
    op.drop_index('idx_agent_links_source', 'agent_links')
    op.drop_table('agent_links')

    # Drop agent_memory table
    op.drop_index('idx_agent_memory_expires', 'agent_memory')
    op.drop_index('idx_agent_memory_agent_key', 'agent_memory')
    op.drop_table('agent_memory')

    # Drop events table
    op.drop_index('idx_events_expires', 'events')
    op.drop_index('idx_events_type_created', 'events')
    op.drop_index('idx_events_user_created', 'events')
    op.drop_index('idx_events_agent_created', 'events')
    op.drop_table('events')
