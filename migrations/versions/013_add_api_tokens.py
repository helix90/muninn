"""Add api_tokens table for REST API authentication.

Revision ID: 013
Revises: 012
"""

from alembic import op
import sqlalchemy as sa

revision = '013'
down_revision = '012'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'api_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('token_hash', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash'),
    )
    op.create_index('idx_api_tokens_user', 'api_tokens', ['user_id', 'is_active'])
    op.create_index('idx_api_tokens_hash', 'api_tokens', ['token_hash'])


def downgrade():
    op.drop_index('idx_api_tokens_hash', table_name='api_tokens')
    op.drop_index('idx_api_tokens_user', table_name='api_tokens')
    op.drop_table('api_tokens')
