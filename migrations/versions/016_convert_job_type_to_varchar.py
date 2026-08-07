"""Convert job_type column from PostgreSQL enum to VARCHAR.

Revision ID: 016
Revises: 015

Migration 001 created job_type as a PostgreSQL ENUM (job_type_enum) containing
only the four original agent types.  Every new agent type added since then
works on fresh instances (where the column was always VARCHAR), but fails on
instances that ran migrations from scratch because the enum never had new
values added to it.

This migration converts the column to VARCHAR(100) so the application-level
registry check (Job.validate_job_type) is the sole constraint on valid values.

The conversion is guarded with a DO block: if the enum type does not exist
the block is a no-op, so this migration is safe on all instances regardless
of whether they have the old schema.
"""
from alembic import op

revision = '016'
down_revision = '015'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'job_type_enum') THEN
                ALTER TABLE jobs
                    ALTER COLUMN job_type TYPE VARCHAR(100)
                    USING job_type::text;
                DROP TYPE job_type_enum;
            END IF;
        END $$;
    """)


def downgrade():
    # Recreate the original enum.  Any rows whose job_type value is not in
    # the list will cause the downgrade to fail, which is the correct guard.
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'job_type_enum') THEN
                CREATE TYPE job_type_enum AS ENUM (
                    'web_scraper', 'rss_reader', 'filter', 'email_sender'
                );
                ALTER TABLE jobs
                    ALTER COLUMN job_type TYPE job_type_enum
                    USING job_type::job_type_enum;
            END IF;
        END $$;
    """)
