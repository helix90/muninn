"""
Job registry system for managing job types in the Muninn framework
"""

import logging
from typing import Dict, Type, List, Optional, Any
from .base import BaseJob


class JobRegistry:
    """Registry for managing job types and their configurations."""
    
    def __init__(self):
        """Initialize the job registry."""
        self._jobs: Dict[str, Type[BaseJob]] = {}
        self._config_schemas: Dict[str, Dict[str, Any]] = {}
        self.logger = logging.getLogger(__name__)
    
    def register(self, job_class: Type[BaseJob]) -> None:
        """
        Register a job class with the registry.
        
        Args:
            job_class: The job class to register
            
        Raises:
            ValueError: If the job class is invalid or already registered
        """
        if not issubclass(job_class, BaseJob):
            raise ValueError(f"Job class must inherit from BaseJob: {job_class}")
        
        if not job_class.job_type:
            raise ValueError(f"Job class must have a job_type: {job_class}")
        
        if job_class.job_type in self._jobs:
            self.logger.warning(f"Overwriting existing job type: {job_class.job_type}")
        
        self._jobs[job_class.job_type] = job_class

        # Store configuration schema using static class method (no instantiation needed)
        try:
            self._config_schemas[job_class.job_type] = job_class.get_config_schema_static()
        except Exception as e:
            self.logger.error(f"Could not extract config schema for {job_class.job_type}: {e}")
            # Fallback to basic schema from class attributes
            self._config_schemas[job_class.job_type] = {
                'job_type': job_class.job_type,
                'required_fields': getattr(job_class, 'required_config_fields', []),
                'optional_fields': getattr(job_class, 'optional_config_fields', []),
                'description': job_class.__doc__ or 'No description available'
            }

        self.logger.info(f"Registered job type: {job_class.job_type}")
    
    def get_job_class(self, job_type: str) -> Optional[Type[BaseJob]]:
        """
        Get a job class by type.
        
        Args:
            job_type: The type of job to retrieve
            
        Returns:
            The job class if found, None otherwise
        """
        return self._jobs.get(job_type)
    
    def create_job(self, job_type: str, job_id: int, config: Dict[str, Any], user_id: int) -> Optional[BaseJob]:
        """
        Create a job instance of the specified type.
        
        Args:
            job_type: The type of job to create
            job_id: Database ID of the job
            config: Job configuration
            user_id: ID of the user who owns the job
            
        Returns:
            Job instance if successful, None if job type not found
            
        Raises:
            ValueError: If job creation fails
        """
        job_class = self.get_job_class(job_type)
        if not job_class:
            raise ValueError(f"Unknown job type: {job_type}")
        
        try:
            return job_class(job_id=job_id, config=config, user_id=user_id)
        except Exception as e:
            raise ValueError(f"Failed to create job of type {job_type}: {e}")
    
    def get_registered_types(self) -> List[str]:
        """
        Get all registered job types.
        
        Returns:
            List of registered job type names
        """
        return list(self._jobs.keys())
    
    def get_config_schema(self, job_type: str) -> Optional[Dict[str, Any]]:
        """
        Get the configuration schema for a job type.
        
        Args:
            job_type: The type of job
            
        Returns:
            Configuration schema if found, None otherwise
        """
        return self._config_schemas.get(job_type)
    
    def get_all_config_schemas(self) -> Dict[str, Dict[str, Any]]:
        """
        Get configuration schemas for all registered job types.
        
        Returns:
            Dictionary mapping job types to their configuration schemas
        """
        return self._config_schemas.copy()
    
    def is_registered(self, job_type: str) -> bool:
        """
        Check if a job type is registered.
        
        Args:
            job_type: The type of job to check
            
        Returns:
            True if registered, False otherwise
        """
        return job_type in self._jobs
    
    def unregister(self, job_type: str) -> bool:
        """
        Unregister a job type.
        
        Args:
            job_type: The type of job to unregister
            
        Returns:
            True if unregistered, False if not found
        """
        if job_type in self._jobs:
            del self._jobs[job_type]
            if job_type in self._config_schemas:
                del self._config_schemas[job_type]
            self.logger.info(f"Unregistered job type: {job_type}")
            return True
        return False
    
    def clear(self) -> None:
        """Clear all registered job types."""
        self._jobs.clear()
        self._config_schemas.clear()
        self.logger.info("Cleared all registered job types")
    
    def __len__(self) -> int:
        """Get the number of registered job types."""
        return len(self._jobs)
    
    def __contains__(self, job_type: str) -> bool:
        """Check if a job type is registered."""
        return self.is_registered(job_type)


# Global job registry instance
job_registry = JobRegistry()
