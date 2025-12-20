"""Remove old jobs system data

Revision ID: 004
Revises: 003
Create Date: 2025-12-14 00:00:00.000000

Removes data from the old jobs system to prepare for complete removal:
- Deletes jobs with old job_type values (web_scraper, rss_reader, filter, email_sender)
- Deletes associated job_runs for old jobs
- Deletes associated job_chains for old jobs
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None

# Old job types that need to be removed
OLD_JOB_TYPES = ['web_scraper', 'rss_reader', 'filter', 'email_sender']


def upgrade():
    """Delete all data associated with old job types."""
    conn = op.get_bind()

    # First, delete job_runs for old jobs
    conn.execute(
        sa.text("""
            DELETE FROM job_runs
            WHERE job_id IN (
                SELECT id FROM jobs
                WHERE job_type IN :job_types
            )
        """),
        {"job_types": tuple(OLD_JOB_TYPES)}
    )

    # Then delete job_chains for old jobs
    conn.execute(
        sa.text("""
            DELETE FROM job_chains
            WHERE parent_job_id IN (
                SELECT id FROM jobs
                WHERE job_type IN :job_types
            ) OR child_job_id IN (
                SELECT id FROM jobs
                WHERE job_type IN :job_types
            )
        """),
        {"job_types": tuple(OLD_JOB_TYPES)}
    )

    # Finally, delete old jobs
    conn.execute(
        sa.text("""
            DELETE FROM jobs
            WHERE job_type IN :job_types
        """),
        {"job_types": tuple(OLD_JOB_TYPES)}
    )

    # Log the cleanup
    print(f"Removed jobs with types: {', '.join(OLD_JOB_TYPES)}")


def downgrade():
    """
    Cannot restore deleted data.

    Note: This migration is destructive and cannot be reversed.
    The old jobs system data has been permanently removed.
    """
    print("WARNING: Cannot restore deleted old jobs data")
    print("This migration is one-way - downgrade is not supported")
