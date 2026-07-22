"""
Database models for Muninn automation platform
"""

from datetime import datetime, timedelta
import hashlib
import secrets
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime,
    ForeignKey, JSON, Index, CheckConstraint
)
from sqlalchemy.orm import relationship, validates
from sqlalchemy.sql import func
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app.extensions import db
from app.constants import (
    MIN_PASSWORD_LENGTH, MIN_USERNAME_LENGTH,
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
    theme_preference = Column(String(10), nullable=True)  # 'light', 'dark', 'system', or NULL
    reset_token = Column(String(64), nullable=True, index=True)
    reset_token_expiry = Column(DateTime, nullable=True)

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

    def generate_reset_token(self):
        """Generate a secure password reset token valid for 1 hour."""
        self.reset_token = secrets.token_urlsafe(48)
        self.reset_token_expiry = datetime.utcnow() + timedelta(hours=1)
        return self.reset_token

    @classmethod
    def verify_reset_token(cls, token):
        """Return user if token is valid and not expired, else None."""
        user = cls.query.filter_by(reset_token=token).first()
        if user is None or user.reset_token_expiry is None:
            return None
        if datetime.utcnow() > user.reset_token_expiry:
            return None
        return user

    def clear_reset_token(self):
        """Invalidate the reset token after use."""
        self.reset_token = None
        self.reset_token_expiry = None

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
    job_type = Column(String(50), nullable=False, index=True)  # Changed from ENUM to String for agent system flexibility
    config = Column(JSON, nullable=False, default=dict)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    scenario_id = Column(Integer, ForeignKey('scenarios.id', ondelete='SET NULL'), nullable=True)
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

    # Health & alerting fields
    alert_enabled = Column(Boolean, default=False, nullable=False)
    alert_email = Column(String(120), nullable=True)
    consecutive_failures = Column(Integer, default=0, nullable=False)
    last_alerted_at = Column(DateTime, nullable=True)
    expected_receive_period_in_days = Column(Integer, nullable=True)
    health_status = Column(String(20), default='unknown', nullable=False)
    health_checked_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship('User', back_populates='jobs')
    runs = relationship('JobRun', back_populates='job', cascade='all, delete-orphan')
    agent_runs = relationship('AgentRun', back_populates='agent', cascade='all, delete-orphan')
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
                 last_scheduled_run=None, next_scheduled_run=None, scenario_id=None, is_active=True,
                 alert_enabled=False, alert_email=None, expected_receive_period_in_days=None):
        self.name = name
        self.job_type = job_type
        self.config = config or {}
        self.user_id = user_id
        self.scenario_id = scenario_id
        self.description = description
        self.tags = tags
        self.priority = priority
        self.schedule_cron = schedule_cron
        self.schedule_enabled = schedule_enabled
        self.last_scheduled_run = last_scheduled_run
        self.next_scheduled_run = next_scheduled_run
        self.is_active = is_active
        self.alert_enabled = alert_enabled
        self.alert_email = alert_email
        self.consecutive_failures = 0
        self.health_status = 'unknown'
        self.expected_receive_period_in_days = expected_receive_period_in_days
    
    @validates('config')
    def validate_config(self, key, config):
        """Validate config is a dictionary."""
        if not isinstance(config, dict):
            raise ValueError("Config must be a dictionary")
        return config
    
    @validates('job_type')
    def validate_job_type(self, key, job_type):
        """Validate job type is supported (only for new records)."""
        from sqlalchemy import inspect as sa_inspect

        # Only validate for new records, not when loading from database
        # This allows legacy job types to exist in the database without causing errors
        state = sa_inspect(self)
        if not state.persistent and not state.deleted:
            # Check against registered agent types
            from app.agents.registry import agent_registry
            if not agent_registry.is_registered(job_type):
                raise ValueError(f"Job type '{job_type}' is not registered. Register it in the agent registry.")

        return job_type
    
    def validate_job_configuration(self):
        """Validate job configuration against agent type requirements."""
        from app.agents.registry import agent_registry

        if not agent_registry.is_registered(self.job_type):
            raise ValueError(f"Unknown agent type: {self.job_type}")

        try:
            # Validate configuration using agent registry
            agent_registry.validate_agent_config(self.job_type, self.config)
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


class Scenario(db.Model):
    """Groups of agents that work together on specific tasks"""
    __tablename__ = 'scenarios'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    color = Column(String(7), nullable=True)  # Hex color for UI display
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship('User', backref='scenarios')
    agents = relationship('Job', backref='scenario', lazy='dynamic')

    # Constraints
    __table_args__ = (
        db.Index('ix_scenarios_user_name', 'user_id', 'name', unique=True),
    )

    def __repr__(self):
        return f'<Scenario {self.name} (user {self.user_id})>'

    @property
    def agent_count(self):
        """Get count of agents in this scenario"""
        return self.agents.filter(Job.is_active == True).count()


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


class AgentRun(db.Model):
    """AgentRun model for tracking agent execution."""

    __tablename__ = 'agent_runs'

    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, ForeignKey('jobs.id'), nullable=False, index=True)
    status = Column(String(50), nullable=False, index=True, default='pending')
    started_at = Column(DateTime, default=func.now(), nullable=False)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    manual = Column(Boolean, default=False, nullable=False)
    input_event_ids = Column(JSON, nullable=True, default=list)
    output_event_ids = Column(JSON, nullable=True, default=list)
    propagation_id = Column(String(36), nullable=True, index=True)

    # Relationships
    agent = relationship('Job', foreign_keys=[agent_id], back_populates='agent_runs')

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name='valid_agent_run_status'
        ),
        Index('idx_agent_runs_agent_status', 'agent_id', 'status'),
        Index('idx_agent_runs_started_at', 'started_at'),
        Index('idx_agent_runs_propagation_id', 'propagation_id'),
    )

    def __repr__(self):
        agent_name = self.agent.name if self.agent else f"Agent({self.agent_id})"
        return f'<AgentRun {self.id} - {agent_name} ({self.status})>'


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


class Event(db.Model):
    """Event model for agent-to-agent communication."""

    __tablename__ = 'events'

    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, ForeignKey('jobs.id'), nullable=False, index=True)
    agent_type = Column(String(50), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    payload = Column(JSON, nullable=False, default=dict)
    event_metadata = Column('metadata', JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    expires_at = Column(DateTime, nullable=True)
    propagation_id = Column(String(36), nullable=True, index=True)

    # Relationships
    user = relationship('User')
    agent = relationship('Job', foreign_keys=[agent_id])

    # Constraints
    __table_args__ = (
        Index('idx_events_agent_created', 'agent_id', 'created_at'),
        Index('idx_events_user_created', 'user_id', 'created_at'),
        Index('idx_events_type_created', 'agent_type', 'created_at'),
        Index('idx_events_expires', 'expires_at'),
        Index('idx_events_propagation_id', 'propagation_id'),
    )

    def __init__(self, agent_id, agent_type, user_id, payload, metadata=None, expires_at=None,
                 propagation_id=None):
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.user_id = user_id
        self.payload = payload or {}
        self.event_metadata = metadata or {}
        self.expires_at = expires_at
        self.propagation_id = propagation_id

    @validates('payload', 'event_metadata')
    def validate_json_data(self, key, data):
        """Validate JSON data is a dictionary."""
        if not isinstance(data, dict):
            raise ValueError(f"{key} must be a dictionary")
        return data

    def to_dict(self):
        """Convert event to dictionary."""
        return {
            'id': self.id,
            'agent_id': self.agent_id,
            'agent_type': self.agent_type,
            'user_id': self.user_id,
            'payload': self.payload,
            'metadata': self.event_metadata,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None
        }

    def get_payload_field(self, field_path, default=None):
        """Get a field from payload using dot notation (e.g., 'user.name')."""
        try:
            value = self.payload
            for key in field_path.split('.'):
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default

    def is_expired(self):
        """Check if event has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    def __repr__(self):
        return f'<Event {self.id} from Agent {self.agent_id} ({self.agent_type})>'


class AgentMemory(db.Model):
    """AgentMemory model for persistent agent state storage."""

    __tablename__ = 'agent_memory'

    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, ForeignKey('jobs.id'), nullable=False, index=True)
    key = Column(String(255), nullable=False)
    value = Column(JSON, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    agent = relationship('Job', foreign_keys=[agent_id])

    # Constraints
    __table_args__ = (
        Index('idx_agent_memory_agent_key', 'agent_id', 'key', unique=True),
        Index('idx_agent_memory_expires', 'expires_at'),
    )

    def __init__(self, agent_id, key, value, expires_at=None):
        self.agent_id = agent_id
        self.key = key
        self.value = value
        self.expires_at = expires_at

    @validates('key')
    def validate_key(self, key_name, key_value):
        """Validate key is not empty."""
        if not key_value or len(key_value) == 0:
            raise ValueError("Key cannot be empty")
        if len(key_value) > 255:
            raise ValueError("Key cannot be longer than 255 characters")
        return key_value

    @validates('value')
    def validate_value(self, key, value):
        """Validate value is JSON-serializable."""
        import json
        try:
            json.dumps(value)
            return value
        except (TypeError, ValueError) as e:
            raise ValueError(f"Value must be JSON-serializable: {e}")

    def is_expired(self):
        """Check if memory has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    def __repr__(self):
        return f'<AgentMemory {self.agent_id}:{self.key}>'


class AgentLink(db.Model):
    """AgentLink model for defining agent connections and data flow."""

    __tablename__ = 'agent_links'

    id = Column(Integer, primary_key=True)
    source_agent_id = Column(Integer, ForeignKey('jobs.id'), nullable=False, index=True)
    target_agent_id = Column(Integer, ForeignKey('jobs.id'), nullable=False, index=True)
    config = Column(JSON, nullable=True, default=dict)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    source_agent = relationship('Job', foreign_keys=[source_agent_id])
    target_agent = relationship('Job', foreign_keys=[target_agent_id])

    # Constraints
    __table_args__ = (
        CheckConstraint('source_agent_id != target_agent_id', name='no_self_link'),
        Index('idx_agent_links_source', 'source_agent_id'),
        Index('idx_agent_links_target', 'target_agent_id'),
        Index('idx_agent_links_both', 'source_agent_id', 'target_agent_id', unique=True),
        Index('idx_agent_links_active', 'is_active'),
    )

    def __init__(self, source_agent_id, target_agent_id, config=None):
        if source_agent_id == target_agent_id:
            raise ValueError("Source and target agent cannot be the same")
        self.source_agent_id = source_agent_id
        self.target_agent_id = target_agent_id
        self.config = config or {}

    @validates('config')
    def validate_config(self, key, config):
        """Validate config is a dictionary."""
        if not isinstance(config, dict):
            raise ValueError("Config must be a dictionary")
        return config

    def __repr__(self):
        return f'<AgentLink {self.source_agent_id} -> {self.target_agent_id}>'


class Credential(db.Model):
    """User credentials stored securely with encryption

    Credentials are stored encrypted with per-credential salt for enhanced security.
    Agents can reference credentials by name using {{credential:name}} syntax.
    """
    __tablename__ = 'credentials'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(String(500), nullable=True)
    encrypted_value = Column(Text, nullable=False)
    salt = Column(String(100), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    last_used_at = Column(DateTime, nullable=True)

    # Relationships
    user = db.relationship('User', backref='credentials')

    # Constraints
    __table_args__ = (
        Index('ix_credentials_user_name', 'user_id', 'name', unique=True),
    )

    def __repr__(self):
        return f'<Credential {self.name} for user {self.user_id}>'


class AlertLog(db.Model):
    """Records alerts sent for agent health issues."""

    __tablename__ = 'alert_logs'

    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, ForeignKey('jobs.id', ondelete='CASCADE'), nullable=False, index=True)
    alert_type = Column(String(50), nullable=False)   # 'failure', 'recovery', 'staleness'
    message = Column(Text, nullable=False)
    sent_at = Column(DateTime, default=func.now(), nullable=False)
    recipient_email = Column(String(120), nullable=False)

    # Relationships
    agent = relationship('Job', foreign_keys=[agent_id])

    # Constraints
    __table_args__ = (
        Index('idx_alert_logs_agent_sent', 'agent_id', 'sent_at'),
    )

    def __init__(self, agent_id, alert_type, message, recipient_email):
        self.agent_id = agent_id
        self.alert_type = alert_type
        self.message = message
        self.recipient_email = recipient_email

    def __repr__(self):
        return f'<AlertLog agent={self.agent_id} type={self.alert_type} sent={self.sent_at}>'


class DataStore(db.Model):
    """User-scoped key-value store for cross-pipeline data sharing."""

    __tablename__ = 'data_store'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    namespace = Column(String(100), nullable=False)
    key = Column(String(255), nullable=False)
    value = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship('User', foreign_keys=[user_id])

    __table_args__ = (
        Index('idx_data_store_user_ns', 'user_id', 'namespace'),
        Index('idx_data_store_lookup', 'user_id', 'namespace', 'key', unique=True),
    )

    def __repr__(self):
        return f'<DataStore {self.namespace}/{self.key}>'


class DelayedEvent(db.Model):
    """Buffered events waiting to be released by a DelayAgent."""

    __tablename__ = 'delayed_events'

    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, ForeignKey('jobs.id', ondelete='CASCADE'), nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    metadata_ = Column('metadata', JSON, nullable=False, default=dict)
    release_at = Column(DateTime, nullable=False)
    released = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    agent = relationship('Job', foreign_keys=[agent_id])

    __table_args__ = (
        Index('idx_delayed_events_release', 'agent_id', 'release_at'),
        Index('idx_delayed_events_pending', 'released', 'release_at'),
    )


class ApiToken(db.Model):
    """API token for programmatic access to the REST API.

    The raw token is shown to the user once on creation; only its SHA-256
    hash is persisted so the database never holds a usable secret.
    """

    __tablename__ = 'api_tokens'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    name = Column(String(100), nullable=False)
    token_hash = Column(String(64), nullable=False, unique=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    user = relationship('User', backref='api_tokens')

    __table_args__ = (
        Index('idx_api_tokens_user', 'user_id', 'is_active'),
        Index('idx_api_tokens_hash', 'token_hash'),
    )

    @staticmethod
    def generate() -> str:
        """Return a new random 40-char hex token (caller must store the hash)."""
        return secrets.token_hex(20)

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode()).hexdigest()

    @classmethod
    def verify(cls, raw_token: str):
        """Return the active ApiToken for *raw_token*, or None."""
        h = cls.hash_token(raw_token)
        return cls.query.filter_by(token_hash=h, is_active=True).first()

    def touch(self):
        """Update last_used_at to now."""
        self.last_used_at = datetime.utcnow()

    def __repr__(self):
        return f'<ApiToken {self.name} user={self.user_id}>'