"""
Job type implementations for the Muninn framework
"""

from .web_scraper import WebScraperJob
from .rss_reader import RSSReaderJob
from .filter_job import FilterJob
from .email_sender import EmailSenderJob

__all__ = [
    'WebScraperJob',
    'RSSReaderJob', 
    'FilterJob',
    'EmailSenderJob'
]
