"""
CLI commands for Muninn
"""

import click
from flask.cli import with_appcontext
from app.extensions import db
from app.models import Base, User, Job, JobRun, JobChain
from werkzeug.security import generate_password_hash
from sqlalchemy import text
import json


@click.command('init-db')
@with_appcontext
def init_db_command():
    """Initialize the database."""
    try:
        click.echo('Creating database tables...')
        Base.metadata.create_all(db.engine)
        click.echo('Database tables created successfully!')
    except Exception as e:
        click.echo(f'Error creating database tables: {e}', err=True)
        raise click.Abort()


@click.command('seed-db')
@with_appcontext
def seed_db_command():
    """Seed the database with sample data."""
    try:
        click.echo('Seeding database with sample data...')
        
        # Create sample user
        user = User(
            username='admin',
            email='admin@muninn.local',
            password='admin123456'
        )
        db.session.add(user)
        db.session.flush()  # Get the user ID
        
        # Create sample jobs
        job1 = Job(
            name='Sample Data Processing Job',
            job_type='data_processor',
            config={
                'input_format': 'csv',
                'output_format': 'json',
                'batch_size': 1000
            },
            user_id=user.id
        )
        
        job2 = Job(
            name='Email Notification Job',
            job_type='notifier',
            config={
                'email_template': 'default',
                'recipients': ['user@example.com'],
                'subject': 'Job completed'
            },
            user_id=user.id
        )
        
        db.session.add_all([job1, job2])
        db.session.flush()
        
        # Create sample job runs
        job_run1 = JobRun(
            job_id=job1.id,
            status='completed',
            input_data={'file_path': '/data/input.csv'}
        )
        job_run1.output_data = {'processed_records': 1500, 'file_path': '/data/output.json'}
        job_run1.mark_completed()
        
        job_run2 = JobRun(
            job_id=job2.id,
            status='failed',
            input_data={'job_id': job1.id}
        )
        job_run2.error_message = 'SMTP server unavailable'
        job_run2.mark_failed('SMTP server unavailable')
        
        db.session.add_all([job_run1, job_run2])
        
        # Create sample job chain
        job_chain = JobChain(
            parent_job_id=job1.id,
            child_job_id=job2.id,
            condition_config={
                'trigger_on': 'success',
                'delay_seconds': 30
            }
        )
        db.session.add(job_chain)
        
        db.session.commit()
        click.echo('Database seeded successfully!')
        
    except Exception as e:
        db.session.rollback()
        click.echo(f'Error seeding database: {e}', err=True)
        raise click.Abort()


@click.command('reset-db')
@with_appcontext
def reset_db_command():
    """Reset the database (drop all tables and recreate)."""
    if click.confirm('This will delete ALL data. Are you sure?'):
        try:
            click.echo('Dropping all database tables...')
            Base.metadata.drop_all(db.engine)
            click.echo('Creating fresh database tables...')
            Base.metadata.create_all(db.engine)
            click.echo('Database reset successfully!')
        except Exception as e:
            click.echo(f'Error resetting database: {e}', err=True)
            raise click.Abort()


@click.command('db-status')
@with_appcontext
def db_status_command():
    """Check database connection and table status."""
    try:
        # Test connection
        db.session.execute(text('SELECT 1'))
        click.echo('✓ Database connection: OK')
        
        # Check tables
        inspector = db.inspect(db.engine)
        tables = inspector.get_table_names()
        click.echo(f'✓ Database tables: {len(tables)} found')
        
        for table in tables:
            row_count = db.session.execute(text(f'SELECT COUNT(*) FROM {table}')).scalar()
            click.echo(f'  - {table}: {row_count} rows')
            
    except Exception as e:
        click.echo(f'✗ Database error: {e}', err=True)
        raise click.Abort()


@click.command('create-user')
@click.option('--username', required=True, help='Username for the new user')
@click.option('--email', required=True, help='Email for the new user')
@click.option('--password', required=True, help='Password for the new user')
@with_appcontext
def create_user_command(username, email, password):
    """Create a new user."""
    try:
        # Check if user already exists
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            click.echo(f'User {username} already exists!', err=True)
            return
        
        # Create new user
        user = User(username=username, email=email, password=password)
        db.session.add(user)
        db.session.commit()
        
        click.echo(f'User {username} created successfully!')
        
    except Exception as e:
        db.session.rollback()
        click.echo(f'Error creating user: {e}', err=True)
        raise click.Abort()


@click.command('scheduler-status')
@with_appcontext
def scheduler_status_command():
    """Check scheduler status and list scheduled jobs."""
    try:
        from app.scheduler import scheduler
        
        click.echo('Scheduler Status:')
        click.echo(f'  Running: {scheduler.scheduler.running if scheduler.scheduler else False}')
        
        if scheduler.scheduler and scheduler.scheduler.running:
            jobs = scheduler.get_scheduled_jobs()
            click.echo(f'  Scheduled Jobs: {len(jobs)}')
            
            for job in jobs:
                click.echo(f'    - {job["name"]} (ID: {job["job_id"]})')
                click.echo(f'      Next Run: {job["next_run_time"]}')
                click.echo(f'      Trigger: {job["trigger"]}')
        else:
            click.echo('  Scheduler is not running')
            
    except Exception as e:
        click.echo(f'Error checking scheduler status: {e}', err=True)
        raise click.Abort()


@click.command('scheduler-start')
@with_appcontext
def scheduler_start_command():
    """Start the scheduler."""
    try:
        from app.scheduler import scheduler
        
        if scheduler.scheduler and scheduler.scheduler.running:
            click.echo('Scheduler is already running')
        else:
            scheduler.start()
            click.echo('Scheduler started successfully!')
            
    except Exception as e:
        click.echo(f'Error starting scheduler: {e}', err=True)
        raise click.Abort()


@click.command('scheduler-stop')
@with_appcontext
def scheduler_stop_command():
    """Stop the scheduler."""
    try:
        from app.scheduler import scheduler
        
        if not scheduler.scheduler or not scheduler.scheduler.running:
            click.echo('Scheduler is not running')
        else:
            scheduler.stop()
            click.echo('Scheduler stopped successfully!')
            
    except Exception as e:
        click.echo(f'Error stopping scheduler: {e}', err=True)
        raise click.Abort()


@click.command('migrate-scheduler-jobs')
@with_appcontext
def migrate_scheduler_jobs_command():
    """Migrate scheduled jobs from SQLite (jobs.db) to PostgreSQL."""
    import os
    import sqlite3
    try:
        # Check if old jobs.db exists
        if not os.path.exists('jobs.db'):
            click.echo('No jobs.db file found. Nothing to migrate.')
            return

        # Backup the file first
        import shutil
        backup_file = 'jobs.db.backup'
        shutil.copy2('jobs.db', backup_file)
        click.echo(f'Created backup: {backup_file}')

        # Connect to SQLite database
        conn = sqlite3.connect('jobs.db')
        cursor = conn.cursor()

        # Check if apscheduler_jobs table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='apscheduler_jobs'")
        if not cursor.fetchone():
            click.echo('No apscheduler_jobs table found in jobs.db')
            conn.close()
            return

        # Get all scheduled jobs
        cursor.execute('SELECT id, next_run_time, job_state FROM apscheduler_jobs')
        jobs = cursor.fetchall()
        conn.close()

        if not jobs:
            click.echo('No scheduled jobs found in jobs.db')
            return

        click.echo(f'Found {len(jobs)} scheduled job(s) in SQLite database')

        # Parse job IDs from scheduler job names (format: "job_<id>")
        from app.scheduler import scheduler
        from app.models import Job

        migrated = 0
        failed = 0

        for job_id_str, next_run, job_state in jobs:
            try:
                # Extract Muninn job ID from scheduler job ID (format: "job_<id>")
                if job_id_str.startswith('job_'):
                    muninn_job_id = int(job_id_str[4:])

                    # Get job from database
                    job = db.session.query(Job).get(muninn_job_id)
                    if job and job.schedule_enabled and job.schedule_cron:
                        # Re-schedule the job using the scheduler
                        success = scheduler.schedule_job(
                            muninn_job_id,
                            job.schedule_cron,
                            replace_existing=True
                        )
                        if success:
                            click.echo(f'  ✓ Migrated job {muninn_job_id}: {job.name}')
                            migrated += 1
                        else:
                            click.echo(f'  ✗ Failed to migrate job {muninn_job_id}: {job.name}')
                            failed += 1
                    else:
                        click.echo(f'  - Skipped job {muninn_job_id} (not found or not enabled)')
                else:
                    click.echo(f'  - Skipped scheduler job {job_id_str} (unknown format)')
            except Exception as e:
                click.echo(f'  ✗ Error migrating {job_id_str}: {e}')
                failed += 1

        click.echo(f'\nMigration complete:')
        click.echo(f'  Migrated: {migrated}')
        click.echo(f'  Failed: {failed}')
        click.echo(f'\nBackup saved to: {backup_file}')
        click.echo(f'Original jobs.db can be safely deleted after verification.')

    except Exception as e:
        click.echo(f'Error during migration: {e}', err=True)
        raise click.Abort()


@click.command('encrypt-credentials')
@with_appcontext
def encrypt_credentials_command():
    """Encrypt existing plain-text credentials in job configurations."""
    try:
        from app.models import Job
        from app.utils.encryption import ConfigEncryption

        click.echo('Encrypting credentials in job configurations...')

        jobs = db.session.query(Job).all()
        encrypted_count = 0
        skipped_count = 0

        for job in jobs:
            # Get sensitive fields for this job type
            sensitive_fields = ConfigEncryption.SENSITIVE_FIELDS.get(job.job_type, [])

            if not sensitive_fields:
                skipped_count += 1
                continue

            # Check if any sensitive fields need encryption
            needs_encryption = False
            for field in sensitive_fields:
                if field in job.config and job.config[field]:
                    if not ConfigEncryption.is_encrypted(job.config[field]):
                        needs_encryption = True
                        break

            if needs_encryption:
                # Encrypt the config
                job.config = ConfigEncryption.encrypt_config(job.job_type, job.config)
                encrypted_count += 1
                click.echo(f'  ✓ Encrypted job {job.id}: {job.name} ({job.job_type})')
            else:
                skipped_count += 1

        # Commit changes
        db.session.commit()

        click.echo(f'\nEncryption complete:')
        click.echo(f'  Encrypted: {encrypted_count} job(s)')
        click.echo(f'  Skipped: {skipped_count} job(s) (no sensitive fields or already encrypted)')
        click.echo(f'  Total: {len(jobs)} job(s)')

    except Exception as e:
        db.session.rollback()
        click.echo(f'Error encrypting credentials: {e}', err=True)
        raise click.Abort()


def register_commands(app):
    """Register CLI commands with the Flask app."""
    app.cli.add_command(init_db_command)
    app.cli.add_command(seed_db_command)
    app.cli.add_command(reset_db_command)
    app.cli.add_command(db_status_command)
    app.cli.add_command(create_user_command)
    app.cli.add_command(scheduler_status_command)
    app.cli.add_command(scheduler_start_command)
    app.cli.add_command(scheduler_stop_command)
    app.cli.add_command(migrate_scheduler_jobs_command)
    app.cli.add_command(encrypt_credentials_command) 