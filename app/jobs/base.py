"""
Abstract base job class for the Muninn job framework
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, Optional, List
from .enums import JobStatus


class BaseJob(ABC):
    """Abstract base class for all job types."""
    
    # Job type identifier - must be set by subclasses
    job_type: str = None
    
    # Required configuration fields - must be set by subclasses
    required_config_fields: List[str] = []
    
    # Optional configuration fields - can be set by subclasses
    optional_config_fields: List[str] = []
    
    def __init__(self, job_id: int, config: Dict[str, Any], user_id: int):
        """
        Initialize a new job instance.
        
        Args:
            job_id: Database ID of the job
            config: Job configuration dictionary
            user_id: ID of the user who owns this job
        """
        self.job_id = job_id
        self.config = config or {}
        self.user_id = user_id
        self.status = JobStatus.PENDING
        self.logger = logging.getLogger(f"{self.__class__.__name__}[{job_id}]")
        
        # Validate configuration
        self._validate_config()
    
    def _validate_config(self):
        """Validate job configuration."""
        if not self.job_type:
            raise ValueError(f"Job type not set for {self.__class__.__name__}")
        
        # Check required fields
        missing_fields = []
        for field in self.required_config_fields:
            if field not in self.config:
                missing_fields.append(field)
        
        if missing_fields:
            raise ValueError(f"Missing required configuration fields: {missing_fields}")
        
        # Validate field values
        self._validate_config_values()
    
    def _validate_config_values(self):
        """Validate configuration field values. Override in subclasses."""
        pass
    
    @abstractmethod
    def execute(self, input_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute the job.
        
        Args:
            input_data: Optional input data for the job
            
        Returns:
            Dictionary containing job execution results
        """
        pass
    
    def pre_execute(self, input_data: Optional[Dict[str, Any]] = None) -> None:
        """
        Pre-execution setup. Override in subclasses if needed.
        
        Args:
            input_data: Optional input data for the job
        """
        self.status = JobStatus.RUNNING
        self.logger.info(f"Starting job execution with config: {self.config}")
    
    def post_execute(self, result: Dict[str, Any], success: bool = True) -> None:
        """
        Post-execution cleanup. Override in subclasses if needed.
        
        Args:
            result: Job execution result
            success: Whether the job completed successfully
        """
        if success:
            self.status = JobStatus.COMPLETED
            self.logger.info(f"Job completed successfully: {result}")
        else:
            self.status = JobStatus.FAILED
            self.logger.error(f"Job failed: {result}")
    
    def handle_error(self, error: Exception) -> Dict[str, Any]:
        """
        Handle job execution errors.
        
        Args:
            error: The exception that occurred
            
        Returns:
            Error result dictionary
        """
        self.status = JobStatus.FAILED
        error_result = {
            'error': str(error),
            'error_type': type(error).__name__,
            'timestamp': datetime.utcnow().isoformat()
        }
        self.logger.error(f"Job execution failed: {error_result}")
        return error_result
    
    @classmethod
    def get_config_schema_static(cls) -> Dict[str, Any]:
        """
        Get configuration schema without instantiation.
        Static class method that doesn't require a job instance.

        Returns:
            Dictionary describing the configuration schema
        """
        description = cls.__doc__ or 'No description available'
        # Get first line of docstring
        description = description.strip().split('\n')[0]

        return {
            'job_type': cls.job_type,
            'required_fields': cls.required_config_fields,
            'optional_fields': cls.optional_config_fields,
            'description': description
        }

    def get_config_schema(self) -> Dict[str, Any]:
        """
        Get the configuration schema for this job type.
        Instance method that can be overridden for custom schemas.

        Returns:
            Dictionary describing the configuration schema
        """
        return self.__class__.get_config_schema_static()
    
    def is_valid_for_execution(self) -> bool:
        """
        Check if the job is valid for execution.
        
        Returns:
            True if the job can be executed, False otherwise
        """
        try:
            # Check if status allows execution
            if self.status not in [JobStatus.PENDING, JobStatus.FAILED]:
                return False
            
            # Check if all required fields are present
            for field in self.required_config_fields:
                if field not in self.config:
                    return False
            
            # Check if configuration values are valid
            self._validate_config_values()
            return True
            
        except Exception:
            return False
    
    def __repr__(self):
        return f"<{self.__class__.__name__}(id={self.job_id}, type={self.job_type}, status={self.status.value})>"
