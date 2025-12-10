"""Add scheduling fields

Revision ID: 002
Revises: 001
Create Date: 2025-09-20 20:50:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade():
    # Add scheduling fields to jobs table
    op.add_column('jobs', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('jobs', sa.Column('tags', postgresql.JSONB(), nullable=True))
    op.add_column('jobs', sa.Column('priority', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('jobs', sa.Column('schedule_cron', sa.String(100), nullable=True))
    op.add_column('jobs', sa.Column('schedule_enabled', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('jobs', sa.Column('last_scheduled_run', sa.DateTime(), nullable=True))
    op.add_column('jobs', sa.Column('next_scheduled_run', sa.DateTime(), nullable=True))
    
    # Add indexes for scheduling fields
    op.create_index('idx_jobs_schedule_enabled', 'jobs', ['schedule_enabled'])
    op.create_index('idx_jobs_next_scheduled_run', 'jobs', ['next_scheduled_run'])
    op.create_index('idx_jobs_priority', 'jobs', ['priority'])


def downgrade():
    # Remove indexes
    op.drop_index('idx_jobs_priority', 'jobs')
    op.drop_index('idx_jobs_next_scheduled_run', 'jobs')
    op.drop_index('idx_jobs_schedule_enabled', 'jobs')
    
    # Remove scheduling fields
    op.drop_column('jobs', 'next_scheduled_run')
    op.drop_column('jobs', 'last_scheduled_run')
    op.drop_column('jobs', 'schedule_enabled')
    op.drop_column('jobs', 'schedule_cron')
    op.drop_column('jobs', 'priority')
    op.drop_column('jobs', 'tags')
    op.drop_column('jobs', 'description')
