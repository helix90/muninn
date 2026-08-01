"""Add canvas_position to jobs for pipeline editor node placement.

Revision ID: 015
Revises: 014
"""

from alembic import op
import sqlalchemy as sa

revision = '015'
down_revision = '014'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('jobs', sa.Column('canvas_position', sa.JSON, nullable=True))


def downgrade():
    op.drop_column('jobs', 'canvas_position')
