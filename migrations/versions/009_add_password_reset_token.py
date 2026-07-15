"""Add password reset token fields to users

Revision ID: 009
Revises: 008
Create Date: 2026-04-05 00:00:00.000000

Adds reset_token and reset_token_expiry columns to the users table to support
the forgot-password flow.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('reset_token', sa.String(64), nullable=True))
    op.add_column('users', sa.Column('reset_token_expiry', sa.DateTime(), nullable=True))
    op.create_index('ix_users_reset_token', 'users', ['reset_token'])


def downgrade():
    op.drop_index('ix_users_reset_token', table_name='users')
    op.drop_column('users', 'reset_token_expiry')
    op.drop_column('users', 'reset_token')
