"""Add agent health and alerting fields

Revision ID: 010
Revises: 009
Create Date: 2026-07-14 00:00:00.000000

Adds health tracking and alert configuration columns to the jobs table,
and creates the alert_logs table for recording sent alerts.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '010'
down_revision = '009'
branch_labels = None
depends_on = None


def upgrade():
    # Health & alerting columns on jobs
    op.add_column('jobs', sa.Column('alert_enabled', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('jobs', sa.Column('alert_email', sa.String(120), nullable=True))
    op.add_column('jobs', sa.Column('consecutive_failures', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('jobs', sa.Column('last_alerted_at', sa.DateTime(), nullable=True))
    op.add_column('jobs', sa.Column('expected_receive_period_in_days', sa.Integer(), nullable=True))
    op.add_column('jobs', sa.Column('health_status', sa.String(20), nullable=False, server_default='unknown'))
    op.add_column('jobs', sa.Column('health_checked_at', sa.DateTime(), nullable=True))

    # alert_logs table
    op.create_table(
        'alert_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('agent_id', sa.Integer(), sa.ForeignKey('jobs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('alert_type', sa.String(50), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('sent_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('recipient_email', sa.String(120), nullable=False),
    )
    op.create_index('idx_alert_logs_agent_sent', 'alert_logs', ['agent_id', 'sent_at'])


def downgrade():
    op.drop_index('idx_alert_logs_agent_sent', table_name='alert_logs')
    op.drop_table('alert_logs')

    op.drop_column('jobs', 'health_checked_at')
    op.drop_column('jobs', 'health_status')
    op.drop_column('jobs', 'expected_receive_period_in_days')
    op.drop_column('jobs', 'last_alerted_at')
    op.drop_column('jobs', 'consecutive_failures')
    op.drop_column('jobs', 'alert_email')
    op.drop_column('jobs', 'alert_enabled')
