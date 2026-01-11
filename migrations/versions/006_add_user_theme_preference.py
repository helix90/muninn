"""Add user theme preference

Revision ID: 006
Revises: 005
Create Date: 2026-01-09 00:00:00.000000

Adds theme_preference column to users table for storing user's preferred theme
(light, dark, or system). Used by the dark mode feature in the UI.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade():
    # Add theme_preference column to users table
    op.add_column('users', sa.Column('theme_preference', sa.String(10), nullable=True))


def downgrade():
    # Remove theme_preference column from users table
    op.drop_column('users', 'theme_preference')
