# Muninn Job Execution Framework

The Muninn Job Execution Framework provides a robust, extensible system for creating and managing automated workflows. This framework is built on top of the existing authenticated Flask application and includes comprehensive job management, execution tracking, and monitoring capabilities.

## Overview

The job framework consists of several key components:

- **Job Types**: Pre-built job implementations for common automation tasks
- **Job Registry**: Central system for managing and discovering job types
- **Job Service**: Business logic layer for job management operations
- **Job Views**: Web interface for job management and monitoring
- **Database Models**: Enhanced models with job execution tracking

## Architecture

```
app/
├── jobs/                    # Job framework core
│   ├── __init__.py         # Framework initialization and job registration
│   ├── base.py             # Abstract BaseJob class
│   ├── enums.py            # Job status enumerations
│   ├── registry.py         # Job registry system
│   ├── types/              # Job type implementations
│   │   ├── web_scraper.py  # Web scraping jobs
│   │   ├── rss_reader.py   # RSS feed processing
│   │   ├── filter_job.py   # Data filtering and transformation
│   │   └── email_sender.py # Email notification jobs
│   └── views.py            # Job management web interface
├── services/
│   └── job_service.py      # Job business logic service
├── forms.py                # Job configuration forms
└── templates/jobs/         # Job management templates
```

## Job Types

### 1. Web Scraper Job

Extracts data from websites using CSS selectors.

**Configuration:**
- `url`: Target website URL
- `selectors`: Dictionary mapping data names to CSS selectors
- `timeout`: Request timeout in seconds
- `user_agent`: Custom user agent string
- `extract_text`: Whether to extract text content
- `extract_links`: Whether to extract links

**Example:**
```python
config = {
    'url': 'https://example.com',
    'selectors': {
        'title': 'h1',
        'content': '.content p',
        'metadata': '.meta'
    },
    'timeout': 30,
    'extract_text': True
}
```

### 2. RSS Reader Job

Processes RSS feeds with filtering capabilities.

**Configuration:**
- `feed_url`: RSS feed URL
- `max_entries`: Maximum number of entries to process
- `include_content`: Whether to include full content
- `filter_keywords`: Keywords to include
- `exclude_keywords`: Keywords to exclude

**Example:**
```python
config = {
    'feed_url': 'https://example.com/feed.xml',
    'max_entries': 50,
    'filter_keywords': ['python', 'automation'],
    'exclude_keywords': ['spam', 'advertisement']
}
```

### 3. Filter Job

Filters and transforms data based on configurable rules.

**Configuration:**
- `input_data`: Data to filter (dict, list, or string)
- `filters`: List of filter rules
- `output_format`: Output format (original, count, summary)
- `case_sensitive`: Whether filtering is case sensitive
- `regex_enabled`: Whether to enable regex filtering

**Filter Types:**
- `equals`: Exact match
- `contains`: Substring match
- `regex`: Regular expression match
- `greater_than`: Numeric comparison
- `less_than`: Numeric comparison
- `in_list`: List membership
- `not_in_list`: List exclusion

**Example:**
```python
config = {
    'input_data': [
        {'name': 'John', 'age': 30, 'city': 'New York'},
        {'name': 'Jane', 'age': 25, 'city': 'Boston'}
    ],
    'filters': [
        {'type': 'greater_than', 'field': 'age', 'value': 25},
        {'type': 'contains', 'field': 'city', 'value': 'New York'}
    ],
    'output_format': 'summary'
}
```

### 4. Email Sender Job

Sends automated emails with support for attachments.

**Configuration:**
- `smtp_server`: SMTP server address
- `smtp_port`: SMTP server port
- `username`: SMTP username
- `password`: SMTP password
- `to_emails`: List of recipient email addresses
- `subject`: Email subject
- `body`: Plain text email body
- `html_body`: HTML email body
- `cc_emails`: CC recipients
- `bcc_emails`: BCC recipients
- `use_tls`: Whether to use TLS encryption

**Example:**
```python
config = {
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587,
    'username': 'user@gmail.com',
    'password': 'app_password',
    'to_emails': ['recipient@example.com'],
    'subject': 'Automated Report',
    'body': 'Please find attached the daily report.',
    'use_tls': True
}
```

## Creating Custom Job Types

To create a custom job type, inherit from `BaseJob` and implement the required methods:

```python
from app.jobs.base import BaseJob

class CustomJob(BaseJob):
    job_type = 'custom_job'
    required_config_fields = ['required_field']
    optional_config_fields = ['optional_field']
    
    def execute(self, input_data=None):
        """Implement job execution logic."""
        # Your job logic here
        result = self._process_data(input_data)
        return result
    
    def _validate_config_values(self):
        """Validate configuration field values."""
        # Custom validation logic
        if self.config.get('required_field') == 'invalid':
            raise ValueError("Invalid required_field value")
```

Then register your job type:

```python
from app.jobs import job_registry
from app.jobs.types.custom_job import CustomJob

job_registry.register(CustomJob)
```

## Job Management

### Creating Jobs

Jobs can be created through the web interface or programmatically:

```python
from app.services.job_service import JobService

service = JobService(db_session)
job, error = service.create_job(
    name='Daily Report',
    job_type='web_scraper',
    config={'url': 'https://example.com', 'selectors': {'title': 'h1'}},
    user_id=1
)
```

### Executing Jobs

Jobs can be executed manually or scheduled:

```python
job_run, error = service.execute_job(job_id=1, user_id=1)
```

### Job Monitoring

Track job execution status and history:

```python
# Get job runs
runs = service.get_job_runs(job_id=1, user_id=1)

# Get job statistics
stats = service.get_job_statistics(user_id=1)
```

## Scheduler Thundering Herd Prevention

The Muninn scheduler implements automatic protection against the "Thundering Herd" problem, where many jobs with identical cron schedules fire simultaneously and overwhelm the system.

### Automatic Jitter

Every cron-scheduled job gets an automatic random delay (jitter) of 0-60 seconds before execution:

- **Deterministic**: The same job always gets the same offset within each hour (based on `hash((job_id, current_hour))`)
- **Transparent**: Users don't need to configure anything - jitter is applied automatically
- **Spread Load**: 100 jobs scheduled at "0 * * * *" will execute gradually between HH:00:00 and HH:01:00, not all at once

**Example Impact:**
```
Without jitter: 100 jobs at 12:00:00 → System overload
With jitter:    100 jobs spread across 12:00:00 - 12:01:00 → Smooth load
```

### Global Rate Limiting

The scheduler enforces a global rate limit on job starts to prevent system overload:

- **Default Limit**: 5 job starts per second (configurable)
- **Token Bucket Algorithm**: Smooth rate limiting with automatic token refill
- **Thread-Safe**: Concurrent job starts are safely coordinated
- **Queuing**: Jobs wait for available slots rather than failing

**How It Works:**
1. APScheduler triggers job at scheduled time
2. Job waits for jitter delay (0-60 seconds, deterministic)
3. Job acquires rate limit token (may wait if limit reached)
4. Job executes

### Configuration

Configure Thundering Herd prevention behavior via environment variables or `config.py`:

```python
# Jitter configuration
SCHEDULER_JITTER_MIN_SECONDS = 0      # Minimum jitter delay (default: 0)
SCHEDULER_JITTER_MAX_SECONDS = 60     # Maximum jitter delay (default: 60)

# Rate limiting
SCHEDULER_MAX_STARTS_PER_SECOND = 5   # Max job starts per second (default: 5)
```

**Environment Variables:**
```bash
SCHEDULER_JITTER_MIN=0
SCHEDULER_JITTER_MAX=60
SCHEDULER_MAX_STARTS_PER_SEC=5
```

### Benefits

- **System Stability**: Prevents thread pool saturation during scheduled peaks
- **Predictable Performance**: Smooth resource utilization instead of spiky loads
- **Automatic Protection**: No user action required - works for all cron jobs
- **Scalable**: Handles hundreds of synchronized schedules without degradation

### Implementation Details

The Thundering Herd prevention is implemented in `app/scheduler/scheduler.py:execute_scheduled_job()`:

```python
# STEP 1: Apply jitter (0-60 seconds, deterministic per job+hour)
current_hour = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
seed_value = hash((job_id, current_hour))
random.seed(seed_value)
jitter_seconds = random.uniform(jitter_min, jitter_max)
time.sleep(jitter_seconds)

# STEP 2: Acquire rate limit token
_rate_limiter.acquire()  # Blocks until token available

# STEP 3: Execute job
result = agent_service.run_agent(...)
```

### Testing

Comprehensive tests verify Thundering Herd prevention:

```bash
# Run scheduler jitter tests
pytest tests/test_scheduler_jitter.py -v
```

Test coverage includes:
- Rate limiter token bucket algorithm
- Token refill and rate enforcement
- Thread safety under concurrent access
- Jitter application and determinism
- Configuration respect
- Integration scenarios

## Web Interface

The job framework provides a comprehensive web interface:

- **Job List**: View all jobs with status indicators
- **Job Creation**: Dynamic forms for each job type
- **Job Details**: View configuration and execution history
- **Job Execution**: Manual job execution with real-time status
- **Job Management**: Edit, delete, and monitor jobs

### Navigation

- Dashboard: `/` - Overview and quick actions
- Job List: `/jobs/` - All user jobs
- Create Job: `/jobs/create` - Job creation form
- Job Details: `/jobs/<id>` - Job information and history
- Edit Job: `/jobs/<id>/edit` - Job editing form

## Database Schema

The job framework extends the existing database with:

### Jobs Table
- `id`: Primary key
- `name`: Job name
- `job_type`: Job type enum
- `config`: JSON configuration
- `user_id`: Owner user ID
- `created_at`: Creation timestamp
- `updated_at`: Last update timestamp
- `is_active`: Whether job is active
- `description`: Job description
- `tags`: JSON tags
- `priority`: Execution priority
- `schedule_cron`: Cron schedule expression
- `schedule_enabled`: Whether scheduling is enabled

### Job Runs Table
- `id`: Primary key
- `job_id`: Associated job ID
- `status`: Execution status
- `input_data`: Input data JSON
- `output_data`: Output data JSON
- `started_at`: Execution start time
- `completed_at`: Execution completion time
- `error_message`: Error message if failed
- `execution_time`: Execution duration
- `memory_usage`: Memory usage
- `cpu_usage`: CPU usage

### Job Dependencies Table
- `id`: Primary key
- `job_id`: Job ID
- `dependency_job_id`: Dependent job ID
- `condition_type`: Dependency condition type
- `condition_config`: Condition configuration JSON

### Job Logs Table
- `id`: Primary key
- `job_run_id`: Associated job run ID
- `level`: Log level
- `message`: Log message
- `timestamp`: Log timestamp
- `context`: Additional context JSON

## Security and Authentication

All job management operations require authentication:

- Job views are protected with `@login_required` decorator
- Users can only access their own jobs
- Job execution is restricted to job owners
- Configuration validation prevents malicious input

## Testing

The job framework includes comprehensive tests:

```bash
# Run all tests
pytest

# Run job framework tests specifically
pytest tests/test_jobs.py

# Run with coverage
pytest --cov=app/jobs --cov=app/services
```

Test coverage includes:
- Job type implementations
- Job registry functionality
- Job service operations
- Configuration validation
- Error handling
- Integration scenarios

## Configuration

### Environment Variables

```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost/muninn

# Logging
LOG_LEVEL=INFO

# Security
SECRET_KEY=your-secret-key
```

### Dependencies

The job framework requires additional packages:

```
Flask-WTF==1.2.1
WTForms==3.1.1
requests==2.31.0
beautifulsoup4==4.12.2
feedparser==6.0.10
```

## Deployment

### Database Migration

Apply the job framework database changes:

```bash
# Create migration
flask db migrate -m "Add job framework"

# Apply migration
flask db upgrade
```

### Production Considerations

- Use environment variables for sensitive configuration
- Implement proper logging and monitoring
- Set up database connection pooling
- Configure job execution timeouts
- Implement job queue management for high-volume scenarios

## Troubleshooting

### Common Issues

1. **Job Type Not Found**: Ensure job types are properly registered
2. **Configuration Validation Errors**: Check required fields and data types
3. **Database Connection Issues**: Verify database configuration and connectivity
4. **Permission Errors**: Ensure user authentication and job ownership

### Debug Mode

Enable debug logging for troubleshooting:

```python
import logging
logging.getLogger('app.jobs').setLevel(logging.DEBUG)
```

## Contributing

To extend the job framework:

1. Create new job types in `app/jobs/types/`
2. Add corresponding tests in `tests/test_jobs.py`
3. Update database schema if needed
4. Add web interface components
5. Update documentation

## License

This job framework is part of the Muninn automation platform and follows the same licensing terms.
