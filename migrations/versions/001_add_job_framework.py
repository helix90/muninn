"""Add job framework

Revision ID: 001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create job_type enum
    op.execute("CREATE TYPE IF NOT EXISTS job_type_enum AS ENUM ('web_scraper', 'rss_reader', 'filter', 'email_sender')")
    
    # Create users table
    op.create_table('users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(80), nullable=False),
        sa.Column('email', sa.String(120), nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username'),
        sa.UniqueConstraint('email')
    )
    
    # Create jobs table
    op.create_table('jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('job_type', sa.Enum('web_scraper', 'rss_reader', 'filter', 'email_sender', name='job_type_enum'), nullable=False),
        sa.Column('config', postgresql.JSONB(), nullable=False, default={}),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('tags', postgresql.JSONB(), nullable=True),
        sa.Column('priority', sa.Integer(), default=0, nullable=False),
        sa.Column('schedule_cron', sa.String(100), nullable=True),
        sa.Column('schedule_enabled', sa.Boolean(), default=False, nullable=False),
        sa.Column('last_scheduled_run', sa.DateTime(), nullable=True),
        sa.Column('next_scheduled_run', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create job_runs table
    op.create_table('job_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(50), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('output_data', postgresql.JSONB(), nullable=True),
        sa.Column('execution_time', sa.Float(), nullable=True),
        sa.Column('memory_usage', sa.Integer(), nullable=True),
        sa.Column('cpu_usage', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Add constraint for job run status
    op.execute("ALTER TABLE job_runs ADD CONSTRAINT valid_job_run_status CHECK (status IN ('pending', 'running', 'completed', 'failed', 'dead', 'cancelled'))")
    
    # Create job_chains table
    op.create_table('job_chains',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create job_chain_jobs table for many-to-many relationship
    op.create_table('job_chain_jobs',
        sa.Column('chain_id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False),
        sa.Column('order', sa.Integer(), nullable=False),
        sa.Column('condition', sa.String(50), nullable=True),
        sa.ForeignKeyConstraint(['chain_id'], ['job_chains.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('chain_id', 'job_id')
    )
    
    # Add indexes for better performance
    op.create_index('idx_jobs_type_user', 'jobs', ['job_type', 'user_id'])
    op.create_index('idx_job_runs_job_status_time', 'job_runs', ['job_id', 'status', 'started_at'])
    op.create_index('idx_jobs_user_active', 'jobs', ['user_id', 'is_active'])
    op.create_index('idx_job_runs_job_time', 'job_runs', ['job_id', 'started_at'])
    
    # Create job dependencies table
    op.create_table('job_dependencies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False),
        sa.Column('dependency_job_id', sa.Integer(), nullable=False),
        sa.Column('condition_type', sa.String(50), nullable=False),
        sa.Column('condition_config', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['dependency_job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id', 'dependency_job_id', name='uq_job_dependency')
    )
    op.create_index('idx_job_dependencies_job', 'job_dependencies', ['job_id'])
    op.create_index('idx_job_dependencies_dependency', 'job_dependencies', ['dependency_job_id'])
    
    # Create job logs table for detailed execution logging
    op.create_table('job_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_run_id', sa.Integer(), nullable=False),
        sa.Column('level', sa.String(20), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('context', postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(['job_run_id'], ['job_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_job_logs_run_timestamp', 'job_logs', ['job_run_id', 'timestamp'])
    op.create_index('idx_job_logs_level_timestamp', 'job_logs', ['level', 'timestamp'])


def downgrade():
    # Drop job logs table
    op.drop_table('job_logs')
    
    # Drop job dependencies table
    op.drop_table('job_dependencies')
    
    # Drop job chain tables
    op.drop_table('job_chain_jobs')
    op.drop_table('job_chains')
    
    # Drop job runs table
    op.drop_table('job_runs')
    
    # Drop jobs table
    op.drop_table('jobs')
    
    # Drop users table
    op.drop_table('users')
    
    # Drop job_type enum
    op.execute("DROP TYPE IF EXISTS job_type_enum")
