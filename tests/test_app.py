"""
Tests for the main Flask application
"""

import os
import pytest
from app import create_app
from config import config


class TestAppFactory:
    """Test the application factory."""
    
    def test_create_app_default_config(self):
        """Test app creation with default configuration."""
        app = create_app()
        assert app.config['DEBUG'] is True
        assert app.config['TESTING'] is False
        assert app.config['SECRET_KEY'] == 'dev-secret-key-change-in-production'
    
    def test_create_app_development_config(self):
        """Test app creation with development configuration."""
        app = create_app('development')
        assert app.config['DEBUG'] is True
        assert app.config['TESTING'] is False
    
    def test_create_app_testing_config(self):
        """Test app creation with testing configuration."""
        app = create_app('testing')
        assert app.config['DEBUG'] is True
        assert app.config['TESTING'] is True
    
    def test_create_app_production_config(self):
        """Test app creation with production configuration."""
        app = create_app('production')
        assert app.config['DEBUG'] is False
        assert app.config['TESTING'] is False
    
    def test_create_app_with_env_var(self, monkeypatch):
        """Test app creation using environment variable."""
        monkeypatch.setenv('FLASK_ENV', 'production')
        app = create_app()
        assert app.config['DEBUG'] is False
    
    def test_app_has_blueprints(self):
        """Test that the app has registered blueprints."""
        app = create_app()
        assert 'main' in app.blueprints
    
    def test_app_logging_setup(self):
        """Test that logging is properly configured."""
        app = create_app()
        assert app.logger is not None
        assert len(app.logger.handlers) > 0


class TestConfiguration:
    """Test configuration classes."""
    
    def test_base_config(self):
        """Test base configuration class."""
        base_config = config['default']
        assert hasattr(base_config, 'SECRET_KEY')
        assert hasattr(base_config, 'DEBUG')
        assert hasattr(base_config, 'TESTING')
        assert hasattr(base_config, 'LOG_LEVEL')
    
    def test_development_config(self):
        """Test development configuration."""
        dev_config = config['development']
        assert dev_config.DEBUG is True
        assert dev_config.LOG_LEVEL == 'DEBUG'
        assert dev_config.SESSION_COOKIE_SECURE is False
    
    def test_testing_config(self):
        """Test testing configuration."""
        test_config = config['testing']
        assert test_config.TESTING is True
        assert test_config.DEBUG is True
        assert test_config.LOG_LEVEL == 'DEBUG'
    
    def test_production_config(self):
        """Test production configuration."""
        prod_config = config['production']
        assert prod_config.DEBUG is False
        assert prod_config.LOG_LEVEL == 'WARNING'
        assert prod_config.SESSION_COOKIE_SECURE is True
    
    def test_config_init_app_method(self):
        """Test configuration init_app method."""
        base_config = config['default']
        assert hasattr(base_config, 'init_app')
        assert callable(base_config.init_app)


class TestAppStructure:
    """Test application structure and components."""
    
    def test_app_instance(self):
        """Test that app is a Flask instance."""
        app = create_app()
        from flask import Flask
        assert isinstance(app, Flask)
    
    def test_app_name(self):
        """Test app name."""
        app = create_app()
        assert app.name == 'app'
    
    def test_app_config_loaded(self):
        """Test that configuration is properly loaded."""
        app = create_app('testing')
        assert app.config['TESTING'] is True
        assert app.config['SECRET_KEY'] is not None
    
    def test_error_handlers_registered(self):
        """Test that error handlers are registered."""
        app = create_app()
        # Check if error handlers are registered
        assert hasattr(app, 'error_handler_spec')
    
    def test_logging_configured(self):
        """Test that logging is configured."""
        app = create_app()
        assert app.logger is not None
        assert app.logger.level > 0


class TestEnvironmentVariables:
    """Test environment variable handling."""
    
    def test_secret_key_from_env(self, monkeypatch):
        """Test SECRET_KEY from environment variable."""
        # Set environment variable before importing config
        test_key = 'test-secret-key-123'
        monkeypatch.setenv('SECRET_KEY', test_key)
        
        # Re-import config to get updated values
        import importlib
        import config as config_module
        importlib.reload(config_module)
        
        # Test that the config class has the updated value
        assert config_module.Config.SECRET_KEY == test_key
    
    def test_log_level_from_env(self, monkeypatch):
        """Test LOG_LEVEL from environment variable."""
        # Set environment variable before importing config
        test_level = 'ERROR'
        monkeypatch.setenv('LOG_LEVEL', test_level)
        
        # Re-import config to get updated values
        import importlib
        import config as config_module
        importlib.reload(config_module)
        
        # Test that the config class has the updated value
        assert config_module.Config.LOG_LEVEL == test_level
    
    def test_database_url_from_env(self, monkeypatch):
        """Test DATABASE_URL from environment variable."""
        # Set environment variable before importing config
        test_db_url = 'postgresql://user:pass@localhost/testdb'
        monkeypatch.setenv('DATABASE_URL', test_db_url)
        
        # Re-import config to get updated values
        import importlib
        import config as config_module
        importlib.reload(config_module)
        
        # Test that the config class has the updated value
        assert config_module.Config.DATABASE_URL == test_db_url


class TestAppInitialization:
    """Test app initialization process."""
    
    def test_app_creation_no_errors(self):
        """Test that app creation doesn't raise errors."""
        try:
            app = create_app()
            assert app is not None
        except Exception as e:
            pytest.fail(f"App creation failed with error: {e}")
    
    def test_app_context_available(self):
        """Test that app context is available after creation."""
        app = create_app()
        with app.app_context():
            assert app.app_context() is not None
    
    def test_blueprint_registration(self):
        """Test that blueprints are properly registered."""
        app = create_app()
        assert 'main' in app.blueprints
        assert app.blueprints['main'].name == 'main' 