import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def get_env_bool(key: str, default: bool = False) -> bool:
    """Convert environment variable string to boolean."""
    value = os.getenv(key, str(default))
    return value.lower() in ('true', '1', 'yes', 'on')


def get_env_int(key: str, default: int) -> int:
    """Convert environment variable string to integer."""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


class Config:
    """Base configuration class."""

    # Flask configuration
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = False
    TESTING = False

    # Logging configuration
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    # SMTP Configuration (Global)
    SMTP_SERVER = os.getenv('SMTP_SERVER')
    SMTP_PORT = get_env_int('SMTP_PORT', 587)
    SMTP_USE_TLS = get_env_bool('SMTP_USE_TLS', True)
    SMTP_USERNAME = os.getenv('SMTP_USERNAME')
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
    SMTP_FROM_EMAIL = os.getenv('SMTP_FROM_EMAIL')

    # Database configuration
    DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://muninn:muninn_pass@localhost:5432/muninn_dev')
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': get_env_int('DB_POOL_SIZE', 10),
        'pool_timeout': get_env_int('DB_POOL_TIMEOUT', 20),
        'pool_recycle': get_env_int('DB_POOL_RECYCLE', 3600),
        'max_overflow': get_env_int('DB_MAX_OVERFLOW', 20),
    }

    # Security configuration
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # Scheduler configuration (Thundering Herd Prevention)
    SCHEDULER_JITTER_MIN_SECONDS = get_env_int('SCHEDULER_JITTER_MIN', 0)
    SCHEDULER_JITTER_MAX_SECONDS = get_env_int('SCHEDULER_JITTER_MAX', 60)
    SCHEDULER_MAX_STARTS_PER_SECOND = get_env_int('SCHEDULER_MAX_STARTS_PER_SEC', 5)

    # Agent failure reporting window
    AGENT_FAILURE_WINDOW_DAYS = get_env_int('AGENT_FAILURE_WINDOW_DAYS', 7)

    @staticmethod
    def init_app(app):
        """Initialize application with configuration."""
        pass


class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG = True
    LOG_LEVEL = 'DEBUG'

    # Development-specific settings
    SESSION_COOKIE_SECURE = False

    # Development database settings
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 5,
        'pool_timeout': 10,
        'pool_recycle': 1800,
        'max_overflow': 10,
        'echo': False,  # SQL query logging disabled
    }


class TestingConfig(Config):
    """Testing configuration."""

    TESTING = True
    DEBUG = True
    LOG_LEVEL = 'DEBUG'

    # Testing-specific settings
    WTF_CSRF_ENABLED = False
    PRESERVE_CONTEXT_ON_EXCEPTION = False

    # Testing database settings
    DATABASE_URL = os.getenv('TEST_DATABASE_URL', 'postgresql://muninn:muninn_pass@localhost:5432/muninn_test')
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 20,          # Increased for concurrent test execution
        'pool_timeout': 30,       # Increased timeout for concurrent tests
        'pool_recycle': 300,
        'max_overflow': 10,       # Allow more overflow connections
        'pool_pre_ping': True,    # Test connections before using
    }

    # SMTP defaults for testing (override with env vars if needed)
    SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.test.example.com')
    SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
    SMTP_USE_TLS = True
    SMTP_USERNAME = os.getenv('SMTP_USERNAME', 'test@test.example.com')
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', 'test_password')
    SMTP_FROM_EMAIL = os.getenv('SMTP_FROM_EMAIL', 'noreply@test.example.com')


class ProductionConfig(Config):
    """Production configuration."""

    DEBUG = False
    LOG_LEVEL = 'WARNING'

    # Production-specific settings
    SESSION_COOKIE_SECURE = True

    # Production database settings
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': get_env_int('DB_POOL_SIZE', 20),
        'pool_timeout': get_env_int('DB_POOL_TIMEOUT', 30),
        'pool_recycle': get_env_int('DB_POOL_RECYCLE', 3600),
        'max_overflow': get_env_int('DB_MAX_OVERFLOW', 30),
        'pool_pre_ping': True,  # Connection health check
    }

    @classmethod
    def init_app(cls, app):
        """Initialize production application."""
        Config.init_app(app)

        # Production logging
        import logging
        from logging.handlers import RotatingFileHandler

        if not app.debug and not app.testing:
            # File handler
            if not os.path.exists('logs'):
                os.mkdir('logs')
            file_handler = RotatingFileHandler(
                'logs/muninn.log',
                maxBytes=10240000,
                backupCount=10
            )
            file_handler.setFormatter(logging.Formatter(cls.LOG_FORMAT))
            file_handler.setLevel(logging.INFO)
            app.logger.addHandler(file_handler)

            # Console handler
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(logging.Formatter(cls.LOG_FORMAT))
            app.logger.addHandler(console_handler)

            app.logger.setLevel(logging.INFO)
            app.logger.info('Muninn startup')


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
