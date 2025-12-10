"""
Job execution framework for Muninn automation platform
"""

from .base import BaseJob
from .registry import JobRegistry, job_registry
from .enums import JobStatus

# Import and register all job types
from .types.web_scraper import WebScraperJob
from .types.rss_reader import RSSReaderJob
from .types.filter_job import FilterJob
from .types.email_sender import EmailSenderJob

# Register all job types
job_registry.register(WebScraperJob)
job_registry.register(RSSReaderJob)
job_registry.register(FilterJob)
job_registry.register(EmailSenderJob)

__all__ = [
    'BaseJob', 
    'JobRegistry', 
    'job_registry',
    'JobStatus',
    'WebScraperJob',
    'RSSReaderJob',
    'FilterJob',
    'EmailSenderJob'
]
