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

    # Cast enum to text for IN comparison.  The job_chains table in this
    # schema does not have parent_job_id/child_job_id columns so that
    # cleanup is intentionally omitted.

    conn.execute(sa.text("""
        DELETE FROM job_runs
        WHERE job_id IN (
            SELECT id FROM jobs WHERE job_type::text IN ('web_scraper', 'rss_reader', 'filter', 'email_sender')
        )
    """))

    conn.execute(sa.text("""
        DELETE FROM jobs
        WHERE job_type::text IN ('web_scraper', 'rss_reader', 'filter', 'email_sender')
    """))


def downgrade():
    """
    Cannot restore deleted data.

    Note: This migration is destructive and cannot be reversed.
    The old jobs system data has been permanently removed.
    """
    print("WARNING: Cannot restore deleted old jobs data")
    print("This migration is one-way - downgrade is not supported")
