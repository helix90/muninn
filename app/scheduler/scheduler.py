"""
Job scheduler service for Muninn automation platform
"""

import logging
import atexit
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_JOB_MISSED
from croniter import croniter
from sqlalchemy.orm import Session

from app.extensions import db
from app.services.job_service import JobService
from app.jobs.enums import JobStatus

logger = logging.getLogger(__name__)


class JobScheduler:
    """Robust job scheduler using APScheduler."""
    
    def __init__(self, app=None):
        self.app = app
        self.scheduler = None
        self.job_service = None
        self._setup_scheduler()

        if app:
            self.init_app(app)

    def init_app(self, app):
        """Initialize scheduler with Flask app."""
        self.app = app
        self.job_service = JobService(db.session)

        # Configure PostgreSQL jobstore using app's database URL
        database_url = app.config['SQLALCHEMY_DATABASE_URI']
        jobstore = SQLAlchemyJobStore(url=database_url, tablename='apscheduler_jobs')
        self.scheduler.add_jobstore(jobstore, 'default')

        # Start scheduler in production, but not during testing
        if not app.config.get('TESTING', False):
            self.start()

        # Register cleanup function
        atexit.register(self.shutdown)

    def _setup_scheduler(self):
        """Setup the APScheduler instance."""
        # Configure job stores (will be set in init_app with PostgreSQL)
        jobstores = {
            'default': None  # Will be configured in init_app
        }
        
        # Configure executors
        executors = {
            'default': ThreadPoolExecutor(max_workers=20),
            'high_priority': ThreadPoolExecutor(max_workers=10)
        }
        
        # Configure job defaults
        job_defaults = {
            'coalesce': True,  # Only run the latest version of a job
            'max_instances': 3,  # Maximum 3 instances of a job can run simultaneously
            'misfire_grace_time': 300  # 5 minutes grace time for missed jobs
        }
        
        # Create scheduler
        self.scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone='UTC'
        )
        
        # Add event listeners
        self.scheduler.add_listener(self._job_executed, EVENT_JOB_EXECUTED)
        self.scheduler.add_listener(self._job_error, EVENT_JOB_ERROR)
        self.scheduler.add_listener(self._job_missed, EVENT_JOB_MISSED)
    
    def start(self):
        """Start the scheduler."""
        if self.scheduler and not self.scheduler.running:
            self.scheduler.start()
            logger.info("Job scheduler started")
            
            # Load existing scheduled jobs from database
            self._load_scheduled_jobs()
    
    def stop(self):
        """Stop the scheduler."""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=True)
            logger.info("Job scheduler stopped")
    
    def shutdown(self):
        """Shutdown the scheduler."""
        self.stop()
    
    def _load_scheduled_jobs(self):
        """Load scheduled jobs from the database."""
        if not self.app:
            return
            
        with self.app.app_context():
            try:
                # Get all active jobs with scheduling enabled
                from app.models import Job
                scheduled_jobs = db.session.query(Job).filter(
                    Job.is_active == True,
                    Job.schedule_enabled == True,
                    Job.schedule_cron.isnot(None)
                ).all()
                
                for job in scheduled_jobs:
                    try:
                        self.schedule_job(job.id, job.schedule_cron, replace_existing=True)
                        logger.info(f"Loaded scheduled job: {job.name} (ID: {job.id})")
                    except Exception as e:
                        logger.error(f"Failed to load scheduled job {job.id}: {e}")
                        
            except Exception as e:
                logger.error(f"Failed to load scheduled jobs: {e}")
    
    def schedule_job(self, job_id: int, cron_expression: str, 
                    replace_existing: bool = True) -> bool:
        """
        Schedule a job to run based on cron expression.
        
        Args:
            job_id: ID of the job to schedule
            cron_expression: Cron expression (e.g., '0 */6 * * *' for every 6 hours)
            replace_existing: Whether to replace existing job with same ID
            
        Returns:
            True if scheduled successfully, False otherwise
        """
        try:
            # Validate cron expression
            if not self._validate_cron_expression(cron_expression):
                logger.error(f"Invalid cron expression: {cron_expression}")
                return False
            
            # Get job details
            job = self._get_job(job_id)
            if not job:
                logger.error(f"Job {job_id} not found")
                return False
            
            # Create job function
            job_func = self._create_job_function(job_id)
            
            # Schedule the job
            job_name = f"job_{job_id}"
            trigger = CronTrigger.from_crontab(cron_expression)
            
            self.scheduler.add_job(
                func=job_func,
                trigger=trigger,
                id=job_name,
                name=f"Scheduled: {job.name}",
                replace_existing=replace_existing,
                max_instances=1,
                coalesce=True
            )
            
            # Update job's next scheduled run
            self._update_next_scheduled_run(job_id, cron_expression)
            
            logger.info(f"Scheduled job {job_id} with cron: {cron_expression}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to schedule job {job_id}: {e}")
            return False
    
    def schedule_interval_job(self, job_id: int, interval_minutes: int,
                            replace_existing: bool = True) -> bool:
        """
        Schedule a job to run at regular intervals.
        
        Args:
            job_id: ID of the job to schedule
            interval_minutes: Interval in minutes
            replace_existing: Whether to replace existing job with same ID
            
        Returns:
            True if scheduled successfully, False otherwise
        """
        try:
            # Get job details
            job = self._get_job(job_id)
            if not job:
                logger.error(f"Job {job_id} not found")
                return False
            
            # Create job function
            job_func = self._create_job_function(job_id)
            
            # Schedule the job
            job_name = f"job_{job_id}"
            trigger = IntervalTrigger(minutes=interval_minutes)
            
            self.scheduler.add_job(
                func=job_func,
                trigger=trigger,
                id=job_name,
                name=f"Interval: {job.name}",
                replace_existing=replace_existing,
                max_instances=1,
                coalesce=True
            )
            
            logger.info(f"Scheduled job {job_id} with interval: {interval_minutes} minutes")
            return True
            
        except Exception as e:
            logger.error(f"Failed to schedule interval job {job_id}: {e}")
            return False
    
    def unschedule_job(self, job_id: int) -> bool:
        """
        Unschedule a job.
        
        Args:
            job_id: ID of the job to unschedule
            
        Returns:
            True if unscheduled successfully, False otherwise
        """
        try:
            job_name = f"job_{job_id}"
            self.scheduler.remove_job(job_name)
            
            # Update job's scheduling status
            self._update_job_scheduling_status(job_id, enabled=False)
            
            logger.info(f"Unscheduled job {job_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to unschedule job {job_id}: {e}")
            return False
    
    def get_scheduled_jobs(self) -> List[Dict[str, Any]]:
        """Get list of all scheduled jobs."""
        jobs = []
        for job in self.scheduler.get_jobs():
            job_info = {
                'id': job.id,
                'name': job.name,
                'next_run_time': job.next_run_time,
                'trigger': str(job.trigger),
                'job_id': self._extract_job_id_from_name(job.id)
            }
            jobs.append(job_info)
        return jobs
    
    def get_job_status(self, job_id: int) -> Optional[Dict[str, Any]]:
        """Get status of a scheduled job."""
        job_name = f"job_{job_id}"
        try:
            job = self.scheduler.get_job(job_name)
            if job:
                return {
                    'id': job.id,
                    'name': job.name,
                    'next_run_time': job.next_run_time,
                    'trigger': str(job.trigger),
                    'scheduled': True
                }
            else:
                return {'scheduled': False}
        except Exception as e:
            logger.error(f"Failed to get job status for {job_id}: {e}")
            return None
    
    def _create_job_function(self, job_id: int):
        """Create a job function that executes the job."""
        def execute_scheduled_job():
            try:
                logger.info(f"Executing scheduled job {job_id}")

                # Execute with internal flag to bypass ownership check
                job_run, error = self.job_service.execute_job(
                    job_id,
                    user_id=None,
                    internal=True  # Mark as internal/scheduler execution
                )

                if error:
                    logger.error(f"Scheduled job {job_id} failed: {error}")
                else:
                    logger.info(f"Scheduled job {job_id} completed successfully")

            except Exception as e:
                logger.error(f"Error executing scheduled job {job_id}: {e}")

        return execute_scheduled_job
    
    def _get_job(self, job_id: int):
        """Get job from database."""
        from app.models import Job
        return db.session.query(Job).get(job_id)
    
    def _validate_cron_expression(self, cron_expression: str) -> bool:
        """Validate cron expression."""
        try:
            croniter(cron_expression)
            return True
        except Exception:
            return False
    
    def _update_next_scheduled_run(self, job_id: int, cron_expression: str):
        """Update the next scheduled run time for a job."""
        try:
            from app.models import Job
            job = db.session.query(Job).get(job_id)
            if job:
                # Calculate next run time
                now = datetime.utcnow()
                cron = croniter(cron_expression, now)
                next_run = cron.get_next(datetime)
                
                job.next_scheduled_run = next_run
                job.last_scheduled_run = now
                db.session.commit()
                
        except Exception as e:
            logger.error(f"Failed to update next scheduled run for job {job_id}: {e}")
    
    def _update_job_scheduling_status(self, job_id: int, enabled: bool):
        """Update job scheduling status in database."""
        try:
            from app.models import Job
            job = db.session.query(Job).get(job_id)
            if job:
                job.schedule_enabled = enabled
                if not enabled:
                    job.next_scheduled_run = None
                db.session.commit()
                
        except Exception as e:
            logger.error(f"Failed to update scheduling status for job {job_id}: {e}")
    
    def _extract_job_id_from_name(self, job_name: str) -> Optional[int]:
        """Extract job ID from scheduler job name."""
        try:
            if job_name.startswith('job_'):
                return int(job_name[4:])
        except ValueError:
            pass
        return None
    
    def _job_executed(self, event):
        """Handle job executed event."""
        logger.info(f"Job {event.job_id} executed successfully")
    
    def _job_error(self, event):
        """Handle job error event."""
        logger.error(f"Job {event.job_id} failed: {event.exception}")
    
    def _job_missed(self, event):
        """Handle job missed event."""
        logger.warning(f"Job {event.job_id} missed execution")


# Global scheduler instance
scheduler = JobScheduler()
