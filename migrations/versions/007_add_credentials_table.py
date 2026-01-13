"""Add credentials table

Revision ID: 007
Revises: 006
Create Date: 2026-01-12 00:00:00.000000

Creates credentials table for secure storage of user credentials with encryption.
Credentials are stored encrypted with per-credential salt for enhanced security.
Agents can reference credentials by name using {{credential:name}} syntax.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade():
    # Create credentials table
    op.create_table(
        'credentials',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.String(500), nullable=True),
        sa.Column('encrypted_value', sa.Text(), nullable=False),
        sa.Column('salt', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
    )

    # Create indexes for performance and uniqueness
    op.create_index('ix_credentials_user_id', 'credentials', ['user_id'])
    op.create_index('ix_credentials_user_name', 'credentials', ['user_id', 'name'], unique=True)


def downgrade():
    # Drop indexes
    op.drop_index('ix_credentials_user_name', 'credentials')
    op.drop_index('ix_credentials_user_id', 'credentials')

    # Drop credentials table
    op.drop_table('credentials')
