"""
Database models for Muninn automation platform
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime,
    ForeignKey, JSON, Index, CheckConstraint, Enum
)
from sqlalchemy.orm import relationship, validates
from sqlalchemy.sql import func
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app.extensions import db
from app.constants import (
    VALID_JOB_TYPES, MIN_PASSWORD_LENGTH, MIN_USERNAME_LENGTH,
    MAX_USERNAME_LENGTH, MAX_EMAIL_LENGTH
)


class User(UserMixin, db.Model):
    """User model for authentication and job ownership."""
    
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False, index=True)
    email = Column(String(120), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Relationships
    jobs = relationship('Job', back_populates='user', cascade='all, delete-orphan')
    
    # Constraints
    __table_args__ = (
        CheckConstraint('length(username) >= 3', name='username_min_length'),
        CheckConstraint('length(username) <= 80', name='username_max_length'),
        CheckConstraint('length(email) <= 120', name='email_max_length'),
        Index('idx_users_username_active', 'username', 'is_active'),
        Index('idx_users_email_active', 'email', 'is_active'),
    )
    
    def __init__(self, username, email, password):
        self.username = username
        self.email = email
        self.set_password(password)
    
    def set_password(self, password):
        """Hash and set password."""
        if len(password) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long")
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check if provided password matches hash."""
        return check_password_hash(self.password_hash, password)
    
    @validates('email')
    def validate_email(self, key, email):
        """Validate email format."""
        if '@' not in email or '.' not in email:
            raise ValueError("Invalid email format")
        return email.lower()

    def get_id(self):
        """Return user ID as string for Flask-Login."""
        return str(self.id)

    @property
    def is_authenticated(self):
        """Check if user is authenticated (override to check is_active)."""
        return self.is_active

    def __repr__(self):
        return f'<User {self.username}>'


class Job(db.Model):
    """Job model for automation workflows."""
    
    __tablename__ = 'jobs'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, index=True)
    job_type = Column(Enum('web_scraper', 'rss_reader', 'filter', 'email_sender', name='job_type_enum'), nullable=False, index=True)
    config = Column(JSON, nullable=False, default=dict)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Scheduling fields
    description = Column(Text, nullable=True)
    tags = Column(JSON, nullable=True)
    priority = Column(Integer, default=0, nullable=False)
    schedule_cron = Column(String(100), nullable=True)
    schedule_enabled = Column(Boolean, default=False, nullable=False)
    last_scheduled_run = Column(DateTime, nullable=True)
    next_scheduled_run = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship('User', back_populates='jobs')
    runs = relationship('JobRun', back_populates='job', cascade='all, delete-orphan')
    parent_chains = relationship('JobChain', foreign_keys='JobChain.parent_job_id', back_populates='parent_job')
    child_chains = relationship('JobChain', foreign_keys='JobChain.child_job_id', back_populates='child_job')
    
    # Constraints
    __table_args__ = (
        CheckConstraint('length(name) >= 1', name='job_name_min_length'),
        CheckConstraint('length(name) <= 255', name='job_name_max_length'),
        # Removed length constraints for job_type since it's now an enum
        Index('idx_jobs_user_active', 'user_id', 'is_active'),
        Index('idx_jobs_type_active', 'job_type', 'is_active'),
        Index('idx_jobs_created_active', 'created_at', 'is_active'),
    )
    
    def __init__(self, name, job_type, config, user_id, description=None, tags=None, 
                 priority=0, schedule_cron=None, schedule_enabled=False, 
                 last_scheduled_run=None, next_scheduled_run=None):
        self.name = name
        self.job_type = job_type
        self.config = config or {}
        self.user_id = user_id
        self.description = description
        self.tags = tags
        self.priority = priority
        self.schedule_cron = schedule_cron
        self.schedule_enabled = schedule_enabled
        self.last_scheduled_run = last_scheduled_run
        self.next_scheduled_run = next_scheduled_run
    
    @validates('config')
    def validate_config(self, key, config):
        """Validate config is a dictionary."""
        if not isinstance(config, dict):
            raise ValueError("Config must be a dictionary")
        return config
    
    @validates('job_type')
    def validate_job_type(self, key, job_type):
        """Validate job type is supported."""
        if job_type not in VALID_JOB_TYPES:
            raise ValueError(f"Job type must be one of: {VALID_JOB_TYPES}")
        return job_type
    
    def validate_job_configuration(self):
        """Validate job configuration against job type requirements."""
        from app.jobs import job_registry
        
        if not job_registry.is_registered(self.job_type):
            raise ValueError(f"Unknown job type: {self.job_type}")
        
        try:
            # Create temporary job instance to validate config
            job_class = job_registry.get_job_class(self.job_type)
            temp_job = job_class(job_id=0, config=self.config, user_id=0)
            return True
        except Exception as e:
            raise ValueError(f"Configuration validation failed: {str(e)}")
    
    def can_execute(self):
        """Check if the job can be executed."""
        try:
            self.validate_job_configuration()
            return self.is_active
        except Exception:
            return False
    
    def is_scheduled(self):
        """Check if the job is scheduled."""
        return self.schedule_enabled and self.schedule_cron is not None
    
    def get_next_run_time(self):
        """Get the next scheduled run time."""
        return self.next_scheduled_run
    
    def get_last_run_time(self):
        """Get the last scheduled run time."""
        return self.last_scheduled_run
    
    def update_schedule(self, cron_expression=None, enabled=None):
        """Update job scheduling."""
        if cron_expression is not None:
            self.schedule_cron = cron_expression
        if enabled is not None:
            self.schedule_enabled = enabled
        
        # Update next run time if scheduling is enabled
        if self.schedule_enabled and self.schedule_cron:
            from croniter import croniter
            now = datetime.utcnow()
            cron = croniter(self.schedule_cron, now)
            self.next_scheduled_run = cron.get_next(datetime)
        else:
            self.next_scheduled_run = None
    
    def __repr__(self):
        return f'<Job {self.name} ({self.job_type})>'


class JobRun(db.Model):
    """JobRun model for tracking job execution."""
    
    __tablename__ = 'job_runs'
    
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey('jobs.id'), nullable=False, index=True)
    status = Column(String(50), nullable=False, index=True)
    input_data = Column(JSON, nullable=True, default=dict)
    output_data = Column(JSON, nullable=True, default=dict)
    started_at = Column(DateTime, default=func.now(), nullable=False)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Relationships
    job = relationship('Job', back_populates='runs')
    
    # Constraints
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'dead', 'cancelled')",
            name='valid_job_run_status'
        ),
        CheckConstraint('length(status) <= 50', name='status_max_length'),
        Index('idx_job_runs_job_status', 'job_id', 'status'),
        Index('idx_job_runs_status_created', 'status', 'started_at'),
        Index('idx_job_runs_started_at', 'started_at'),
    )
    
    def __init__(self, job_id, status='pending', input_data=None):
        self.job_id = job_id
        self.status = status
        self.input_data = input_data or {}
    
    @validates('status')
    def validate_status(self, key, status):
        """Validate job run status."""
        valid_statuses = ['pending', 'running', 'completed', 'failed', 'dead', 'cancelled']
        if status not in valid_statuses:
            raise ValueError(f"Status must be one of: {valid_statuses}")
        return status
    
    @validates('input_data', 'output_data')
    def validate_json_data(self, key, data):
        """Validate JSON data is a dictionary."""
        if data is not None and not isinstance(data, dict):
            raise ValueError(f"{key} must be a dictionary or None")
        return data or {}
    
    def mark_completed(self, output_data=None):
        """Mark job run as completed."""
        self.status = 'completed'
        self.completed_at = datetime.utcnow()
        if output_data is not None:
            self.output_data = output_data
    
    def mark_failed(self, error_message):
        """Mark job run as failed."""
        self.status = 'failed'
        self.completed_at = datetime.utcnow()
        self.error_message = error_message
    
    def get_duration(self):
        """Get job run duration in seconds."""
        if self.completed_at and self.started_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
    
    def __repr__(self):
        job_name = self.job.name if self.job else f"Job({self.job_id})"
        return f'<JobRun {self.id} - {job_name} ({self.status})>'


class JobChain(db.Model):
    """JobChain model for defining job dependencies and workflows."""
    
    __tablename__ = 'job_chains'
    
    id = Column(Integer, primary_key=True)
    parent_job_id = Column(Integer, ForeignKey('jobs.id'), nullable=False, index=True)
    child_job_id = Column(Integer, ForeignKey('jobs.id'), nullable=False, index=True)
    condition_config = Column(JSON, nullable=True, default=dict)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    
    # Relationships
    parent_job = relationship('Job', foreign_keys=[parent_job_id], back_populates='parent_chains')
    child_job = relationship('Job', foreign_keys=[child_job_id], back_populates='child_chains')
    
    # Constraints
    __table_args__ = (
        CheckConstraint('parent_job_id != child_job_id', name='no_self_reference'),
        Index('idx_job_chains_parent', 'parent_job_id'),
        Index('idx_job_chains_child', 'child_job_id'),
        Index('idx_job_chains_both', 'parent_job_id', 'child_job_id', unique=True),
    )
    
    def __init__(self, parent_job_id, child_job_id, condition_config=None):
        if parent_job_id == child_job_id:
            raise ValueError("Parent and child job cannot be the same")
        self.parent_job_id = parent_job_id
        self.child_job_id = child_job_id
        self.condition_config = condition_config or {}
    
    @validates('condition_config')
    def validate_condition_config(self, key, config):
        """Validate condition config is a dictionary."""
        if not isinstance(config, dict):
            raise ValueError("Condition config must be a dictionary")
        return config
    
    def __repr__(self):
        return f'<JobChain {self.parent_job_id} -> {self.child_job_id}>' 