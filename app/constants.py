"""
Application constants for Muninn
"""

# Pagination
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# Timeouts (seconds)
DEFAULT_HTTP_TIMEOUT = 30
MIN_HTTP_TIMEOUT = 1
MAX_HTTP_TIMEOUT = 300

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

# Agent failure reporting
AGENT_FAILURE_WINDOW_DAYS = 7  # look-back window for "recent" failed run counts
