"""Add scenarios table and scenario_id to jobs

Revision ID: 008
Revises: 007
Create Date: 2026-01-27

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade():
    # Create scenarios table
    op.create_table(
        'scenarios',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('color', sa.String(7), nullable=True),  # Hex color like #3B82F6
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Create indexes
    op.create_index('ix_scenarios_user_id', 'scenarios', ['user_id'])
    op.create_index('ix_scenarios_user_name', 'scenarios', ['user_id', 'name'], unique=True)

    # Add scenario_id to jobs table
    op.add_column('jobs', sa.Column('scenario_id', sa.Integer(), sa.ForeignKey('scenarios.id', ondelete='SET NULL'), nullable=True))
    op.create_index('ix_jobs_scenario_id', 'jobs', ['scenario_id'])


def downgrade():
    # Remove scenario_id from jobs
    op.drop_index('ix_jobs_scenario_id', table_name='jobs')
    op.drop_column('jobs', 'scenario_id')

    # Drop scenarios table and indexes
    op.drop_index('ix_scenarios_user_name', table_name='scenarios')
    op.drop_index('ix_scenarios_user_id', table_name='scenarios')
    op.drop_table('scenarios')
