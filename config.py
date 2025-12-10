import os
from decouple import config


class Config:
    """Base configuration class."""
    
    # Flask configuration
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = False
    TESTING = False
    
    # Logging configuration
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Database configuration
    DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://muninn:muninn_pass@localhost:5432/muninn_dev')
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': int(os.environ.get('DB_POOL_SIZE', 10)),
        'pool_timeout': int(os.environ.get('DB_POOL_TIMEOUT', 20)),
        'pool_recycle': int(os.environ.get('DB_POOL_RECYCLE', 3600)),
        'max_overflow': int(os.environ.get('DB_MAX_OVERFLOW', 20)),
    }
    
    # Security configuration
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
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
        'echo': True,  # SQL query logging
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
    DATABASE_URL = os.environ.get('TEST_DATABASE_URL', 'postgresql://muninn:muninn_pass@localhost:5432/muninn_test')
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 1,
        'pool_timeout': 5,
        'pool_recycle': 300,
        'max_overflow': 0,
    }


class ProductionConfig(Config):
    """Production configuration."""
    
    DEBUG = False
    LOG_LEVEL = 'WARNING'
    
    # Production-specific settings
    SESSION_COOKIE_SECURE = True
    
    # Production database settings
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': int(os.environ.get('DB_POOL_SIZE', 20)),
        'pool_timeout': int(os.environ.get('DB_POOL_TIMEOUT', 30)),
        'pool_recycle': int(os.environ.get('DB_POOL_RECYCLE', 3600)),
        'max_overflow': int(os.environ.get('DB_MAX_OVERFLOW', 30)),
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