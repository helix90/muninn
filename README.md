# Muninn - Automation Platform

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/Flask-3.0+-green.svg)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-Passing-brightgreen.svg)](tests/)

Muninn is a modern, intelligent automation platform built with Flask, designed to help you build, deploy, and manage automated workflows with ease. Named after the Norse god of memory and wisdom, Muninn provides a robust foundation for automation projects.

## 🚀 Features

- **Agent-Based Automation**: Huginn-inspired single-responsibility agents with event-driven workflows
- **Composable Workflows**: Build complex automations from simple, reusable agents
- **Source Agents**: Fetch data from RSS feeds, web pages, APIs, and more
- **Transform Agents**: Filter, deduplicate, parse, and transform data
- **Action Agents**: Send emails, HTTP requests, messages, and notifications
- **Event Propagation**: Automatic event flow through agent networks
- **Agent Memory**: Persistent state for deduplication and stateful processing
- **Modern Flask Architecture**: Built with Flask 3.0+ using the application factory pattern
- **Environment-Based Configuration**: Separate configurations for development, testing, and production
- **Comprehensive Testing**: Full test suite with pytest and coverage reporting
- **Production Ready**: Docker support, logging, error handling, and security features
- **Beautiful UI**: Modern, responsive web interface with clean design
- **Health Monitoring**: Built-in health check endpoints for monitoring
- **Extensible**: Blueprint-based architecture for easy feature additions
- **Remote Development Ready**: Configured for remote development with 0.0.0.0 binding
- **Database Support**: PostgreSQL with SQLAlchemy ORM and Alembic migrations
- **CLI Tools**: Database management and sample data seeding commands

## 🏗️ Project Structure

```
muninn/
├── app/                    # Application package
│   ├── __init__.py        # Flask app factory
│   ├── extensions.py      # Database and extension setup
│   ├── models.py          # SQLAlchemy database models
│   ├── cli.py             # CLI commands
│   ├── main/              # Main blueprint
│   │   ├── __init__.py    # Blueprint initialization
│   │   └── views.py       # Route handlers
│   └── templates/         # HTML templates
│       ├── main/          # Main page templates
│       └── errors/        # Error page templates
├── tests/                 # Test suite
│   ├── __init__.py        # Test package
│   ├── conftest.py        # Pytest configuration
│   ├── test_app.py        # App factory tests
│   ├── test_views.py      # View tests
│   └── test_models.py     # Database model tests
├── migrations/             # Database migrations
│   ├── env.py             # Alembic environment
│   └── script.py.mako     # Migration template
├── config.py              # Configuration management
├── run.py                 # Application entry point
├── requirements.txt       # Production dependencies
├── requirements-dev.txt   # Development dependencies
├── pytest.ini            # Pytest configuration
├── alembic.ini           # Alembic configuration
├── init-db.sql           # Database initialization script
├── Dockerfile             # Docker configuration
├── docker-compose.yml     # Docker Compose setup
└── README.md              # This file
```

## 📋 Requirements

- Python 3.8 or higher
- Flask 3.0+
- PostgreSQL 12+
- python-decouple for environment variables
- pytest for testing

## 🛠️ Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd muninn
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
# Install production dependencies
pip install -r requirements.txt

# Install development dependencies (for testing)
pip install -r requirements-dev.txt
```

### 4. Database Setup

#### Option A: Using Docker Compose (Recommended)

```bash
# Start PostgreSQL and Redis services
docker-compose up -d postgres redis

# Wait for services to be healthy, then initialize database
flask init-db
```

#### Option B: Local PostgreSQL Installation

```bash
# Create databases
createdb muninn_dev
createdb muninn_test

# Set environment variables
export DATABASE_URL=postgresql://localhost/muninn_dev
export TEST_DATABASE_URL=postgresql://localhost/muninn_test
```

### 5. Environment Setup

```bash
# Copy environment template
cp env.example .env

# Edit .env file with your configuration
nano .env
```

**Note:** The `.env` file is **automatically loaded** by python-decouple when the application starts. You don't need to manually export environment variables or use scripts to load them.

### 6. Run the Application

```bash
# Development mode (automatically loads .env)
flask run

# Or using Python directly (automatically loads .env)
python run.py

# Or using the convenience script (sets env vars manually - optional)
./start.sh
```

The application will be available at `http://0.0.0.0:5000` (accessible from any network interface)

## 🤖 Agent System

Muninn uses a Huginn-inspired agent architecture where each agent performs a single, well-defined task. Agents connect together to create powerful automation workflows.

### Agent Types

**Source Agents** - Fetch data from external sources:
- **RSSAgent**: Monitor RSS/Atom feeds
- **WebFetchAgent**: Fetch web pages via HTTP
- **SchedulerAgent**: Generate time-based triggers

**Transform Agents** - Process and transform data:
- **FilterAgent**: Filter events by rules (contains, regex, etc.)
- **DeduplicationAgent**: Remove duplicate events using memory
- **HTMLParserAgent**: Extract data from HTML via CSS selectors
- **JSONExtractAgent**: Extract data from JSON via JSONPath
- **TemplateAgent**: Transform data using Jinja2 templates
- **DigestAgent**: Batch multiple events into summaries

**Action Agents** - Perform terminal actions:
- **EmailAgent**: Send emails via SMTP
- **HTTPPostAgent**: Send HTTP POST/PUT/PATCH requests
- **JabberAgent**: Send XMPP/Jabber messages

### Quick Example: News Monitor

Monitor Hacker News for Python articles and send email notifications:

```python
# 1. RSS Agent - Fetch Hacker News (runs every 30 minutes)
rss_agent = Job(
    name='Hacker News RSS',
    job_type='rss_agent',
    config={'feed_url': 'https://hnrss.org/newest', 'max_entries': 50},
    schedule='*/30 * * * *'
)

# 2. Filter Agent - Keep only Python articles
filter_agent = Job(
    name='Python Filter',
    job_type='filter_agent',
    config={
        'rules': [
            {'field': 'title', 'type': 'contains', 'value': 'Python', 'case_sensitive': False}
        ]
    }
)

# 3. Deduplication Agent - Remove duplicates (7 day window)
dedupe_agent = Job(
    name='Deduplicator',
    job_type='deduplication_agent',
    config={'uniqueness_fields': ['link'], 'lookback_days': 7}
)

# 4. Email Agent - Send notifications
email_agent = Job(
    name='Email Notifier',
    job_type='email_agent',
    config={
        'smtp_server': 'smtp.gmail.com',
        'smtp_port': 587,
        'username': 'alerts@example.com',
        'password': 'app_password',
        'subject_template': 'New Python Article: {{ title }}',
        'body_template': '{{ title }}\n\n{{ link }}\n\n{{ summary }}'
    }
)

# 5. Connect agents: RSS → Filter → Dedupe → Email
AgentLink(source_agent_id=rss_agent.id, target_agent_id=filter_agent.id)
AgentLink(source_agent_id=filter_agent.id, target_agent_id=dedupe_agent.id)
AgentLink(source_agent_id=dedupe_agent.id, target_agent_id=email_agent.id)
```

### How Events Flow

1. **RSS Agent** runs every 30 minutes, creates events for each article
2. **Filter Agent** receives events, filters for Python articles
3. **Deduplication Agent** checks memory, only passes new articles
4. **Email Agent** sends notification email

### Learn More

See [AGENTS_FRAMEWORK.md](AGENTS_FRAMEWORK.md) for:
- Complete agent documentation
- Configuration examples
- Building custom agents
- Advanced workflow patterns
- API reference

## 🌐 Remote Development

Muninn is configured for remote development by default:

- **Default Host**: `0.0.0.0` (binds to all network interfaces)
- **Default Port**: `5000`
- **Access**: Available from any network interface, not just localhost

This makes it ideal for:
- Remote development environments
- Docker containers
- Cloud development setups
- Team development across networks

### Security Note for Remote Development

⚠️ **Warning**: Binding to `0.0.0.0` makes the application accessible from any network interface. For development this is fine, but ensure you have proper firewall rules and authentication in place for production deployments.

## 🗄️ Database Management

### CLI Commands

Muninn provides several CLI commands for database management:

```bash
# Initialize database tables
flask init-db

# Seed database with sample data
flask seed-db

# Reset database (drop all tables and recreate)
flask reset-db

# Check database status and connection
flask db-status

# Create a new user
flask create-user --username admin --email admin@example.com --password securepass123
```

### Database Models

The application includes comprehensive data models:

- **User**: Authentication and agent ownership
- **Job**: Agent definitions (agent_type, config, schedule)
- **JobRun**: Agent execution tracking with input/output events
- **Event**: Event data flowing between agents (payload, metadata)
- **AgentLink**: Connections between agents (source → target)
- **AgentMemory**: Persistent agent state for deduplication and stateful processing

### Migrations

Database schema changes are managed with Alembic:

```bash
# Create a new migration
flask db revision --autogenerate -m "Description of changes"

# Apply migrations
flask db upgrade

# Rollback migrations
flask db downgrade
```

## 🧪 Testing

### Run All Tests

```bash
pytest
```

### Run Tests with Coverage

```bash
pytest --cov=app --cov-report=html
```

### Run Specific Test Files

```bash
pytest tests/test_views.py
pytest tests/test_app.py
pytest tests/test_models.py
```

### Run Tests with Verbose Output

```bash
pytest -v
```

### Database Testing

Tests use a separate test database and automatically clean up after each test:

```bash
# Set test database URL
export TEST_DATABASE_URL=postgresql://localhost/muninn_test

# Run tests
pytest
```

## 🐳 Docker

### Build and Run with Docker

```bash
# Build the image
docker build -t muninn .

# Run the container
docker run -p 5000:5000 muninn
```

### Using Docker Compose

```bash
# Start all services (including PostgreSQL and Redis)
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Docker Services

- **muninn**: Main Flask application
- **postgres**: PostgreSQL 15 database
- **redis**: Redis 7 for caching and sessions

## 🔧 Configuration

Muninn uses **python-decouple** for configuration management, which automatically loads `.env` files. Simply create a `.env` file in the project root (copy from `env.example`) and your settings will be loaded automatically.

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `FLASK_ENV` | Flask environment | `development` |
| `FLASK_DEBUG` | Debug mode | `True` |
| `FLASK_HOST` | Host to bind to | `0.0.0.0` |
| `FLASK_PORT` | Port to bind to | `5000` |
| `SECRET_KEY` | Flask secret key | `dev-secret-key-change-in-production` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `DATABASE_URL` | Main database URL | `postgresql://localhost/muninn_dev` |
| `TEST_DATABASE_URL` | Test database URL | `postgresql://localhost/muninn_test` |
| `DB_POOL_SIZE` | Database connection pool size | `10` |
| `DB_POOL_TIMEOUT` | Database connection timeout | `20` |
| `DB_POOL_RECYCLE` | Database connection recycle time | `3600` |
| `DB_MAX_OVERFLOW` | Database max overflow connections | `20` |

### Configuration Classes

- **DevelopmentConfig**: Debug enabled, detailed logging, SQL query logging
- **TestingConfig**: Testing environment, debug enabled, minimal connection pool
- **ProductionConfig**: Production optimized, security enabled, connection health checks

## 📡 API Endpoints

### Health Check

```
GET /health
```

Returns application health status including database connectivity:

```json
{
  "status": "healthy",
  "service": "Muninn",
  "version": "1.0.0",
  "environment": "development",
  "database": "healthy",
  "timestamp": "2024-01-01T00:00:00"
}
```

### Home Page

```
GET /
```

Returns the main application interface.

## 🚀 Development

### Adding New Routes

1. Create a new blueprint in `app/` directory
2. Register the blueprint in `app/__init__.py`
3. Add tests in `tests/` directory

### Adding New Database Models

1. Create model in `app/models.py`
2. Add validation and relationships
3. Create and run migrations: `flask db revision --autogenerate -m "Add new model"`
4. Add comprehensive tests in `tests/test_models.py`

### Adding New Features

1. Follow Flask best practices
2. Add comprehensive tests
3. Update documentation
4. Follow PEP 8 style guidelines

### Code Quality

```bash
# Format code with black
black .

# Lint with flake8
flake8 .

# Type checking with mypy
mypy .
```

## 📊 Monitoring

### Health Checks

The application includes a health check endpoint at `/health` that returns:

- Application status
- Service name and version
- Current environment
- Database connectivity status
- Response time metrics

### Logging

- Console logging for development
- File logging for production
- Configurable log levels
- Structured log format
- SQL query logging in development

## 🔒 Security

- Environment-based configuration
- Secure session cookies
- CSRF protection ready
- Non-root Docker user
- Input validation and sanitization
- Password hashing with Werkzeug
- Database connection pooling with health checks

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a pull request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Flask team for the excellent web framework
- pytest team for the testing framework
- SQLAlchemy team for the ORM
- The open-source community for inspiration and tools

## 📞 Support

For support and questions:

- Create an issue in the repository
- Check the documentation
- Review the test examples

---

**Muninn** - Building the future of automation, one workflow at a time. 🚀 