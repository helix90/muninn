"""
Job management service for the Muninn application
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, desc, func

from app.models import Job, JobRun, User
from app.jobs import job_registry, JobStatus
from app.jobs.base import BaseJob
from app.utils.encryption import ConfigEncryption
from app.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE


class JobService:
    """Service for managing jobs and their execution."""
    
    def __init__(self, db_session: Session):
        """
        Initialize the job service.
        
        Args:
            db_session: Database session for database operations
        """
        self.db = db_session
        self.logger = logging.getLogger(__name__)
    
    def create_job(self, name: str, job_type: str, config: Dict[str, Any], 
                   user_id: int) -> Tuple[Job, Optional[str]]:
        """
        Create a new job.
        
        Args:
            name: Job name
            job_type: Type of job to create
            config: Job configuration
            user_id: ID of the user creating the job
            
        Returns:
            Tuple of (Job instance, error message if any)
        """
        try:
            # Validate job type
            if not job_registry.is_registered(job_type):
                return None, f"Unknown job type: {job_type}"
            
            # Validate configuration
            validation_error = self._validate_job_config(job_type, config)
            if validation_error:
                return None, validation_error

            # Encrypt sensitive fields in config
            encrypted_config = ConfigEncryption.encrypt_config(job_type, config)

            # Create job instance
            job = Job(
                name=name,
                job_type=job_type,
                config=encrypted_config,
                user_id=user_id
            )
            
            # Save to database
            self.db.add(job)
            self.db.commit()
            self.db.refresh(job)
            
            self.logger.info(f"Created job {job.id} of type {job_type} for user {user_id}")
            return job, None
            
        except Exception as e:
            self.db.rollback()
            error_msg = f"Failed to create job: {str(e)}"
            self.logger.error(error_msg)
            return None, error_msg
    
    def update_job(self, job_id: int, user_id: int, **kwargs) -> Tuple[Optional[Job], Optional[str]]:
        """
        Update an existing job.
        
        Args:
            job_id: ID of the job to update
            user_id: ID of the user updating the job
            **kwargs: Fields to update
            
        Returns:
            Tuple of (updated Job instance, error message if any)
        """
        try:
            # Get job and verify ownership
            job = self.get_job_by_id(job_id, user_id)
            if not job:
                return None, "Job not found or access denied"
            
            # Validate configuration if it's being updated
            if 'config' in kwargs and 'job_type' in kwargs:
                validation_error = self._validate_job_config(kwargs['job_type'], kwargs['config'])
                if validation_error:
                    return None, validation_error
            elif 'config' in kwargs:
                validation_error = self._validate_job_config(job.job_type, kwargs['config'])
                if validation_error:
                    return None, validation_error
            
            # Update fields
            for field, value in kwargs.items():
                if hasattr(job, field):
                    setattr(job, field, value)
            
            job.updated_at = datetime.utcnow()
            
            # Save changes
            self.db.commit()
            self.db.refresh(job)
            
            self.logger.info(f"Updated job {job_id} for user {user_id}")
            return job, None
            
        except Exception as e:
            self.db.rollback()
            error_msg = f"Failed to update job: {str(e)}"
            self.logger.error(error_msg)
            return None, error_msg
    
    def delete_job(self, job_id: int, user_id: int) -> Tuple[bool, Optional[str]]:
        """
        Delete a job.
        
        Args:
            job_id: ID of the job to delete
            user_id: ID of the user deleting the job
            
        Returns:
            Tuple of (success boolean, error message if any)
        """
        try:
            # Get job and verify ownership
            job = self.get_job_by_id(job_id, user_id)
            if not job:
                return False, "Job not found or access denied"
            
            # Check if job has active runs
            active_runs = self.db.query(JobRun).filter(
                and_(
                    JobRun.job_id == job_id,
                    JobRun.status.in_(JobStatus.get_active_statuses())
                )
            ).count()
            
            if active_runs > 0:
                return False, f"Cannot delete job with {active_runs} active runs"
            
            # Delete job (cascade will handle related records)
            self.db.delete(job)
            self.db.commit()
            
            self.logger.info(f"Deleted job {job_id} for user {user_id}")
            return True, None
            
        except Exception as e:
            self.db.rollback()
            error_msg = f"Failed to delete job: {str(e)}"
            self.logger.error(error_msg)
            return False, error_msg
    
    def get_job_by_id(self, job_id: int, user_id: int = None, internal: bool = False) -> Optional[Job]:
        """
        Get a job by ID, ensuring user has access.

        Args:
            job_id: ID of the job
            user_id: ID of the user requesting the job (None for internal/scheduler)
            internal: If True, bypass ownership checks (for scheduler/system execution)

        Returns:
            Job instance if found and accessible, None otherwise
        """
        query = self.db.query(Job).filter(Job.id == job_id, Job.is_active == True)

        if not internal:
            # User access: verify ownership
            if user_id is None:
                return None
            query = query.filter(Job.user_id == user_id)

        job = query.first()
        if job:
            # Decrypt config for use
            job.config = ConfigEncryption.decrypt_config(job.job_type, job.config)

        return job
    
    def get_user_jobs(self, user_id: int, page: int = 1, per_page: int = DEFAULT_PAGE_SIZE) -> Dict[str, Any]:
        """
        Get all jobs for a user with pagination.

        Args:
            user_id: ID of the user
            page: Page number (1-indexed)
            per_page: Number of jobs per page

        Returns:
            Dictionary with jobs, pagination info
        """
        # Validate pagination parameters
        page = max(1, page)
        per_page = min(max(1, per_page), MAX_PAGE_SIZE)
        offset = (page - 1) * per_page

        query = self.db.query(Job).filter(
            and_(
                Job.user_id == user_id,
                Job.is_active == True
            )
        ).order_by(desc(Job.created_at))

        # Get total count
        total = query.count()

        # Get page of results
        jobs = query.limit(per_page).offset(offset).all()

        # Calculate pagination info
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1

        return {
            'jobs': jobs,
            'page': page,
            'per_page': per_page,
            'total': total,
            'total_pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages
        }
    
    def get_jobs_by_type(self, user_id: int, job_type: str, limit: int = 100) -> List[Job]:
        """
        Get jobs of a specific type for a user.
        
        Args:
            user_id: ID of the user
            job_type: Type of jobs to retrieve
            limit: Maximum number of jobs to return
            
        Returns:
            List of job instances
        """
        return self.db.query(Job).filter(
            and_(
                Job.user_id == user_id,
                Job.job_type == job_type,
                Job.is_active == True
            )
        ).order_by(desc(Job.created_at)).limit(limit).all()
    
    def execute_job(self, job_id: int, user_id: int = None,
                   input_data: Optional[Dict[str, Any]] = None,
                   internal: bool = False) -> Tuple[Optional[JobRun], Optional[str]]:
        """
        Execute a job.

        Args:
            job_id: ID of the job to execute
            user_id: ID of the user executing the job (None for scheduler)
            input_data: Optional input data for the job
            internal: If True, bypass ownership checks (for scheduler/system execution)

        Returns:
            Tuple of (JobRun instance, error message if any)
        """
        try:
            # Get job with appropriate access control
            job = self.get_job_by_id(job_id, user_id, internal=internal)
            if not job:
                return None, "Job not found or access denied"

            # Log execution type
            if internal:
                self.logger.info(f"Internal/scheduler execution of job {job_id}")
            else:
                self.logger.info(f"User {user_id} executing job {job_id}")

            # Use job's owner ID for execution context
            execution_user_id = job.user_id
            
            # Create job run record
            job_run = JobRun(
                job_id=job_id,
                status=JobStatus.PENDING.value,
                input_data=input_data or {}
            )
            
            self.db.add(job_run)
            self.db.commit()
            self.db.refresh(job_run)
            
            # Create and execute job instance
            try:
                # Config is already decrypted by get_job_by_id
                job_instance = job_registry.create_job(
                    job_type=job.job_type,
                    job_id=job.id,
                    config=job.config,  # Already decrypted
                    user_id=execution_user_id
                )
                
                # Update status to running
                job_run.status = JobStatus.RUNNING.value
                self.db.commit()
                
                # Execute job
                result = job_instance.execute(input_data)
                
                # Update job run with results
                if job_instance.status == JobStatus.COMPLETED:
                    job_run.status = JobStatus.COMPLETED.value
                    job_run.output_data = result
                    job_run.completed_at = datetime.utcnow()
                else:
                    job_run.status = JobStatus.FAILED.value
                    job_run.error_message = result.get('error', 'Unknown error')
                    job_run.completed_at = datetime.utcnow()
                
                self.db.commit()
                self.db.refresh(job_run)
                
                self.logger.info(f"Executed job {job_id}, run {job_run.id}, status: {job_run.status}")
                return job_run, None
                
            except Exception as e:
                # Update job run with error
                job_run.status = JobStatus.FAILED.value
                job_run.error_message = str(e)
                job_run.completed_at = datetime.utcnow()
                self.db.commit()
                
                error_msg = f"Job execution failed: {str(e)}"
                self.logger.error(error_msg)
                return job_run, error_msg
                
        except Exception as e:
            self.db.rollback()
            error_msg = f"Failed to execute job: {str(e)}"
            self.logger.error(error_msg)
            return None, error_msg
    
    def get_job_runs(self, job_id: int, user_id: int, limit: int = 100) -> List[JobRun]:
        """
        Get execution history for a job.
        
        Args:
            job_id: ID of the job
            user_id: ID of the user requesting the runs
            limit: Maximum number of runs to return
            
        Returns:
            List of job run instances
        """
        # Verify job ownership
        job = self.get_job_by_id(job_id, user_id)
        if not job:
            return []
        
        return self.db.query(JobRun).filter(
            JobRun.job_id == job_id
        ).order_by(desc(JobRun.started_at)).limit(limit).all()
    
    def get_job_statistics(self, user_id: int) -> Dict[str, Any]:
        """
        Get job statistics for a user.
        
        Args:
            user_id: ID of the user
            
        Returns:
            Dictionary containing job statistics
        """
        try:
            # Total jobs
            total_jobs = self.db.query(Job).filter(
                and_(
                    Job.user_id == user_id,
                    Job.is_active == True
                )
            ).count()
            
            # Jobs by type
            jobs_by_type = self.db.query(Job.job_type, func.count(Job.id)).filter(
                and_(
                    Job.user_id == user_id,
                    Job.is_active == True
                )
            ).group_by(Job.job_type).all()
            
            # Recent runs with eager loading to avoid N+1 queries
            recent_runs = self.db.query(JobRun).join(Job).filter(
                and_(
                    Job.user_id == user_id,
                    Job.is_active == True
                )
            ).options(joinedload(JobRun.job)).order_by(desc(JobRun.started_at)).limit(10).all()
            
            # Run statistics
            run_stats = self.db.query(JobRun.status, func.count(JobRun.id)).join(Job).filter(
                and_(
                    Job.user_id == user_id,
                    Job.is_active == True
                )
            ).group_by(JobRun.status).all()
            
            return {
                'total_jobs': total_jobs,
                'jobs_by_type': dict(jobs_by_type),
                'recent_runs': [
                    {
                        'id': run.id,
                        'job_name': run.job.name,
                        'status': run.status,
                        'started_at': run.started_at.isoformat() if run.started_at else None,
                        'completed_at': run.completed_at.isoformat() if run.completed_at else None
                    }
                    for run in recent_runs
                ],
                'run_statistics': dict(run_stats)
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get job statistics: {e}")
            return {}
    
    def _validate_job_config(self, job_type: str, config: Dict[str, Any]) -> Optional[str]:
        """
        Validate job configuration.
        
        Args:
            job_type: Type of job
            config: Configuration to validate
            
        Returns:
            Error message if validation fails, None if valid
        """
        try:
            # Get job class
            job_class = job_registry.get_job_class(job_type)
            if not job_class:
                return f"Unknown job type: {job_type}"
            
            # Create temporary job instance to validate config
            temp_job = job_class(job_id=0, config=config, user_id=0)
            return None
            
        except Exception as e:
            return f"Configuration validation failed: {str(e)}"
    
    def get_available_job_types(self) -> List[Dict[str, Any]]:
        """
        Get all available job types with their schemas.
        
        Returns:
            List of job type information dictionaries
        """
        # Job type display names
        job_type_names = {
            'web_scraper': 'Web Scraper',
            'rss_reader': 'RSS Reader',
            'filter': 'Data Filter',
            'email_sender': 'Email Sender'
        }
        
        return [
            {
                'type': job_type,
                'name': job_type_names.get(job_type, job_type.replace('_', ' ').title()),
                'schema': schema
            }
            for job_type, schema in job_registry.get_all_config_schemas().items()
        ]
