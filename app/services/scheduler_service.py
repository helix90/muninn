"""
Scheduler service for managing job scheduling
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session

from app.extensions import db
from app.models import Job

logger = logging.getLogger(__name__)


class SchedulerService:
    """Service for managing job scheduling operations."""
    
    def __init__(self, db_session: Session):
        self.db = db_session
        # Import scheduler here to avoid circular imports
        from app.scheduler import scheduler
        self.scheduler = scheduler
    
    def schedule_job(self, job_id: int, cron_expression: str, 
                    user_id: int) -> Tuple[bool, Optional[str]]:
        """
        Schedule a job to run based on cron expression.
        
        Args:
            job_id: ID of the job to schedule
            cron_expression: Cron expression (e.g., '0 */6 * * *' for every 6 hours)
            user_id: ID of the user requesting the operation
            
        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Get job and verify ownership
            job = self.db.query(Job).filter(
                Job.id == job_id,
                Job.user_id == user_id
            ).first()
            
            if not job:
                return False, "Job not found or access denied"
            
            # Update job scheduling in database
            job.update_schedule(cron_expression=cron_expression, enabled=True)
            self.db.commit()
            
            # Schedule job in scheduler
            success = self.scheduler.schedule_job(job_id, cron_expression)
            
            if success:
                logger.info(f"Job {job_id} scheduled with cron: {cron_expression}")
                return True, None
            else:
                # Rollback database changes if scheduling failed
                job.schedule_enabled = False
                job.schedule_cron = None
                job.next_scheduled_run = None
                self.db.commit()
                return False, "Failed to schedule job"
                
        except Exception as e:
            logger.error(f"Error scheduling job {job_id}: {e}")
            self.db.rollback()
            return False, f"Error scheduling job: {str(e)}"
    
    def schedule_interval_job(self, job_id: int, interval_minutes: int,
                            user_id: int) -> Tuple[bool, Optional[str]]:
        """
        Schedule a job to run at regular intervals.
        
        Args:
            job_id: ID of the job to schedule
            interval_minutes: Interval in minutes
            user_id: ID of the user requesting the operation
            
        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Get job and verify ownership
            job = self.db.query(Job).filter(
                Job.id == job_id,
                Job.user_id == user_id
            ).first()
            
            if not job:
                return False, "Job not found or access denied"
            
            # Convert interval to cron expression
            cron_expression = f"*/{interval_minutes} * * * *"
            
            # Update job scheduling in database
            job.update_schedule(cron_expression=cron_expression, enabled=True)
            self.db.commit()
            
            # Schedule job in scheduler
            success = self.scheduler.schedule_interval_job(job_id, interval_minutes)
            
            if success:
                logger.info(f"Job {job_id} scheduled with interval: {interval_minutes} minutes")
                return True, None
            else:
                # Rollback database changes if scheduling failed
                job.schedule_enabled = False
                job.schedule_cron = None
                job.next_scheduled_run = None
                self.db.commit()
                return False, "Failed to schedule job"
                
        except Exception as e:
            logger.error(f"Error scheduling interval job {job_id}: {e}")
            self.db.rollback()
            return False, f"Error scheduling job: {str(e)}"
    
    def unschedule_job(self, job_id: int, user_id: int) -> Tuple[bool, Optional[str]]:
        """
        Unschedule a job.
        
        Args:
            job_id: ID of the job to unschedule
            user_id: ID of the user requesting the operation
            
        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Get job and verify ownership
            job = self.db.query(Job).filter(
                Job.id == job_id,
                Job.user_id == user_id
            ).first()
            
            if not job:
                return False, "Job not found or access denied"
            
            # Update job scheduling in database
            job.update_schedule(enabled=False)
            self.db.commit()
            
            # Unschedule job in scheduler
            success = self.scheduler.unschedule_job(job_id)
            
            if success:
                logger.info(f"Job {job_id} unscheduled")
                return True, None
            else:
                return False, "Failed to unschedule job"
                
        except Exception as e:
            logger.error(f"Error unscheduling job {job_id}: {e}")
            self.db.rollback()
            return False, f"Error unscheduling job: {str(e)}"
    
    def get_scheduled_jobs(self, user_id: int) -> List[Dict[str, Any]]:
        """
        Get list of scheduled jobs for a user.
        
        Args:
            user_id: ID of the user
            
        Returns:
            List of scheduled job information
        """
        try:
            # Get user's scheduled jobs from database
            jobs = self.db.query(Job).filter(
                Job.user_id == user_id,
                Job.schedule_enabled == True
            ).all()
            
            scheduled_jobs = []
            for job in jobs:
                # Get scheduler status
                status = self.scheduler.get_job_status(job.id)
                
                job_info = {
                    'id': job.id,
                    'name': job.name,
                    'job_type': job.job_type,
                    'cron_expression': job.schedule_cron,
                    'next_run_time': job.next_scheduled_run,
                    'last_run_time': job.last_scheduled_run,
                    'is_active': job.is_active,
                    'scheduled': status.get('scheduled', False) if status else False
                }
                scheduled_jobs.append(job_info)
            
            return scheduled_jobs
            
        except Exception as e:
            logger.error(f"Error getting scheduled jobs for user {user_id}: {e}")
            return []
    
    def get_job_schedule_status(self, job_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Get schedule status for a specific job.
        
        Args:
            job_id: ID of the job
            user_id: ID of the user
            
        Returns:
            Job schedule status or None if not found
        """
        try:
            # Get job and verify ownership
            job = self.db.query(Job).filter(
                Job.id == job_id,
                Job.user_id == user_id
            ).first()
            
            if not job:
                return None
            
            # Get scheduler status
            status = self.scheduler.get_job_status(job_id)
            
            return {
                'id': job.id,
                'name': job.name,
                'cron_expression': job.schedule_cron,
                'schedule_enabled': job.schedule_enabled,
                'next_run_time': job.next_scheduled_run,
                'last_run_time': job.last_scheduled_run,
                'scheduled': status.get('scheduled', False) if status else False
            }
            
        except Exception as e:
            logger.error(f"Error getting schedule status for job {job_id}: {e}")
            return None
    
    def update_job_schedule(self, job_id: int, cron_expression: str, 
                          enabled: bool, user_id: int) -> Tuple[bool, Optional[str]]:
        """
        Update job scheduling.
        
        Args:
            job_id: ID of the job
            cron_expression: New cron expression
            enabled: Whether scheduling is enabled
            user_id: ID of the user requesting the operation
            
        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Get job and verify ownership
            job = self.db.query(Job).filter(
                Job.id == job_id,
                Job.user_id == user_id
            ).first()
            
            if not job:
                return False, "Job not found or access denied"
            
            if enabled:
                # Schedule the job
                return self.schedule_job(job_id, cron_expression, user_id)
            else:
                # Unschedule the job
                return self.unschedule_job(job_id, user_id)
                
        except Exception as e:
            logger.error(f"Error updating schedule for job {job_id}: {e}")
            return False, f"Error updating schedule: {str(e)}"
    
    def get_scheduler_status(self) -> Dict[str, Any]:
        """
        Get overall scheduler status.
        
        Returns:
            Scheduler status information
        """
        try:
            scheduled_jobs = self.scheduler.get_scheduled_jobs()
            
            return {
                'running': self.scheduler.scheduler.running if self.scheduler.scheduler else False,
                'total_scheduled_jobs': len(scheduled_jobs),
                'scheduled_jobs': scheduled_jobs
            }
            
        except Exception as e:
            logger.error(f"Error getting scheduler status: {e}")
            return {
                'running': False,
                'total_scheduled_jobs': 0,
                'scheduled_jobs': [],
                'error': str(e)
            }
