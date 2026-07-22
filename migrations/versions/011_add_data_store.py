"""Add data_store table for cross-pipeline key-value storage.

Revision ID: 011
Revises: 010
"""

from alembic import op
import sqlalchemy as sa

revision = '011'
down_revision = '010'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'data_store',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('namespace', sa.String(100), nullable=False),
        sa.Column('key', sa.String(255), nullable=False),
        sa.Column('value', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_data_store_user_ns', 'data_store', ['user_id', 'namespace'])
    op.create_index(
        'idx_data_store_lookup', 'data_store',
        ['user_id', 'namespace', 'key'],
        unique=True
    )


def downgrade():
    op.drop_index('idx_data_store_lookup', table_name='data_store')
    op.drop_index('idx_data_store_user_ns', table_name='data_store')
    op.drop_table('data_store')
