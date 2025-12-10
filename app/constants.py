"""
Application constants for Muninn
"""

# Job Types - these should match the job_type attributes in job classes
JOB_TYPE_WEB_SCRAPER = 'web_scraper'
JOB_TYPE_RSS_READER = 'rss_reader'
JOB_TYPE_FILTER = 'filter'
JOB_TYPE_EMAIL_SENDER = 'email_sender'

# All valid job types
VALID_JOB_TYPES = [
    JOB_TYPE_WEB_SCRAPER,
    JOB_TYPE_RSS_READER,
    JOB_TYPE_FILTER,
    JOB_TYPE_EMAIL_SENDER
]

# Job type display names
JOB_TYPE_NAMES = {
    JOB_TYPE_WEB_SCRAPER: 'Web Scraper',
    JOB_TYPE_RSS_READER: 'RSS Reader',
    JOB_TYPE_FILTER: 'Data Filter',
    JOB_TYPE_EMAIL_SENDER: 'Email Sender'
}

# Pagination
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# Timeouts (seconds)
DEFAULT_HTTP_TIMEOUT = 30
MIN_HTTP_TIMEOUT = 1
MAX_HTTP_TIMEOUT = 300

# Job execution
MAX_CONCURRENT_JOBS = 3
DEFAULT_JOB_PRIORITY = 0

# Database
DEFAULT_POOL_SIZE = 10
MAX_POOL_OVERFLOW = 20
POOL_RECYCLE_TIME = 3600  # 1 hour

# Scheduler
SCHEDULER_MAX_WORKERS = 20
SCHEDULER_MISFIRE_GRACE_TIME = 300  # 5 minutes

# Logging
DEFAULT_LOG_LEVEL = 'INFO'
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# Password
MIN_PASSWORD_LENGTH = 8

# Username
MIN_USERNAME_LENGTH = 3
MAX_USERNAME_LENGTH = 80

# Email
MAX_EMAIL_LENGTH = 120
