"""
Job status enumerations for the Muninn job framework
"""

from enum import Enum


class JobStatus(Enum):
    """Job execution status enumeration."""
    
    PENDING = 'pending'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'
    DEAD = 'dead'
    CANCELLED = 'cancelled'
    
    @classmethod
    def is_valid(cls, status):
        """Check if a status string is valid."""
        return status in [s.value for s in cls]
    
    @classmethod
    def get_all(cls):
        """Get all status values as a list."""
        return [s.value for s in cls]
    
    @classmethod
    def get_active_statuses(cls):
        """Get statuses that indicate active job execution."""
        return [cls.PENDING.value, cls.RUNNING.value]
    
    @classmethod
    def get_final_statuses(cls):
        """Get statuses that indicate job completion."""
        return [cls.COMPLETED.value, cls.FAILED.value, cls.DEAD.value, cls.CANCELLED.value]
