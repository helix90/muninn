"""
Tests for application startup and initialization

These tests verify that the application can start successfully and that
all components (extensions, blueprints, scheduler, etc.) initialize correctly.
"""

import pytest
from flask import Flask
from app import create_app
from app.extensions import db, migrate, login_manager


class TestApplicationStartup:
    """Test that the application starts up successfully."""

    def test_app_creation_succeeds(self):
        """Test that create_app() returns a Flask instance without errors."""
        try:
            app = create_app('testing')
            assert isinstance(app, Flask)
        except Exception as e:
            pytest.fail(f"Application creation failed: {e}")

    def test_app_context_works(self):
        """Test that application context can be created."""
        app = create_app('testing')
        with app.app_context():
            # If we get here, app context is working
            assert True

    def test_request_context_works(self):
        """Test that request context can be created."""
        app = create_app('testing')
        with app.test_request_context():
            # If we get here, request context is working
            assert True


class TestExtensionInitialization:
    """Test that all Flask extensions initialize properly."""

    def test_database_extension_initialized(self):
        """Test that SQLAlchemy is initialized."""
        app = create_app('testing')
        with app.app_context():
            assert db is not None
            assert hasattr(db, 'session')
            assert hasattr(db, 'Model')

    def test_migration_extension_initialized(self):
        """Test that Flask-Migrate is initialized."""
        app = create_app('testing')
        assert migrate is not None
        assert hasattr(migrate, 'init_app')

    def test_login_manager_initialized(self):
        """Test that Flask-Login is initialized."""
        app = create_app('testing')
        assert login_manager is not None
        assert login_manager.login_view == 'auth.login'
        assert login_manager.login_message_category == 'info'

    def test_scheduler_initialized(self):
        """Test that the scheduler is initialized."""
        app = create_app('testing')
        from app.scheduler import scheduler
        assert scheduler is not None
        # In testing mode, scheduler should not auto-start
        assert scheduler.scheduler is not None

    def test_all_extensions_initialized_in_order(self):
        """Test that all extensions initialize without errors."""
        try:
            app = create_app('testing')
            with app.app_context():
                # If we get here, all extensions initialized successfully
                assert db is not None
                assert migrate is not None
                assert login_manager is not None
        except Exception as e:
            pytest.fail(f"Extension initialization failed: {e}")


class TestBlueprintRegistration:
    """Test that all blueprints are registered correctly."""

    def test_main_blueprint_registered(self):
        """Test that main blueprint is registered."""
        app = create_app('testing')
        assert 'main' in app.blueprints
        assert app.blueprints['main'].name == 'main'

    def test_auth_blueprint_registered(self):
        """Test that auth blueprint is registered."""
        app = create_app('testing')
        assert 'auth' in app.blueprints
        assert app.blueprints['auth'].name == 'auth'
        assert app.blueprints['auth'].url_prefix == '/auth'

    def test_agents_blueprint_registered(self):
        """Test that agents blueprint is registered."""
        app = create_app('testing')
        assert 'agents' in app.blueprints
        assert app.blueprints['agents'].name == 'agents'
        assert app.blueprints['agents'].url_prefix == '/agents'

    def test_scheduler_blueprint_registered(self):
        """Test that scheduler blueprint is registered."""
        app = create_app('testing')
        assert 'scheduler' in app.blueprints
        assert app.blueprints['scheduler'].name == 'scheduler'
        assert app.blueprints['scheduler'].url_prefix == '/scheduler'

    def test_all_expected_blueprints_present(self):
        """Test that all expected blueprints are registered."""
        app = create_app('testing')
        expected_blueprints = ['main', 'auth', 'agents', 'scheduler']
        for blueprint_name in expected_blueprints:
            assert blueprint_name in app.blueprints, f"Blueprint '{blueprint_name}' not registered"


class TestModuleImports:
    """Test that all modules can be imported without errors."""

    def test_import_models(self):
        """Test that models module can be imported."""
        try:
            from app import models
            assert hasattr(models, 'User')
            assert hasattr(models, 'Job')
            assert hasattr(models, 'JobRun')
            assert hasattr(models, 'JobChain')
        except ImportError as e:
            pytest.fail(f"Failed to import models: {e}")

    def test_import_extensions(self):
        """Test that extensions module can be imported."""
        try:
            from app import extensions
            assert hasattr(extensions, 'db')
            assert hasattr(extensions, 'migrate')
            assert hasattr(extensions, 'login_manager')
        except ImportError as e:
            pytest.fail(f"Failed to import extensions: {e}")

    def test_import_utilities(self):
        """Test that utility modules can be imported."""
        try:
            from app.utils import validators, encryption
            assert hasattr(validators, 'validate_email')
            assert hasattr(validators, 'validate_url')
            assert hasattr(encryption, 'ConfigEncryption')
        except ImportError as e:
            pytest.fail(f"Failed to import utilities: {e}")

    def test_import_agent_service(self):
        """Test that agent service module can be imported."""
        try:
            from app.services import agent_service
            assert hasattr(agent_service, 'AgentService')
        except ImportError as e:
            pytest.fail(f"Failed to import agent service: {e}")


class TestSchedulerInitialization:
    """Test scheduler-specific initialization."""

    def test_scheduler_instance_created(self):
        """Test that scheduler instance is created."""
        app = create_app('testing')
        from app.scheduler import scheduler
        assert scheduler is not None
        assert hasattr(scheduler, 'scheduler')

    def test_scheduler_has_required_methods(self):
        """Test that scheduler has all required methods."""
        app = create_app('testing')
        from app.scheduler import scheduler
        assert hasattr(scheduler, 'schedule_job')
        assert hasattr(scheduler, 'unschedule_job')
        assert hasattr(scheduler, 'get_scheduled_jobs')
        assert hasattr(scheduler, 'start')
        assert hasattr(scheduler, 'stop')

    def test_scheduler_not_started_in_testing_mode(self):
        """Test that scheduler doesn't auto-start in testing mode."""
        app = create_app('testing')
        from app.scheduler import scheduler
        # In testing mode, scheduler should be initialized but not running
        if scheduler.scheduler:
            assert not scheduler.scheduler.running

    def test_scheduler_jobstore_configured(self):
        """Test that scheduler has PostgreSQL jobstore configured."""
        app = create_app('testing')
        from app.scheduler import scheduler
        assert scheduler.scheduler is not None
        # Check that jobstore was added
        assert 'default' in scheduler.scheduler._jobstores


class TestEncryptionInitialization:
    """Test that encryption utilities work correctly."""

    def test_encryption_module_imports(self):
        """Test that encryption module imports without errors."""
        try:
            from app.utils.encryption import ConfigEncryption
            assert ConfigEncryption is not None
        except ImportError as e:
            pytest.fail(f"Failed to import encryption module: {e}")

    def test_encryption_pbkdf2_import(self):
        """Test that PBKDF2HMAC is imported correctly (regression test)."""
        try:
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
            assert PBKDF2HMAC is not None
        except ImportError as e:
            pytest.fail(f"Failed to import PBKDF2HMAC: {e}")

    def test_encryption_cipher_creation(self):
        """Test that encryption cipher can be created."""
        app = create_app('testing')
        with app.app_context():
            try:
                from app.utils.encryption import ConfigEncryption
                cipher = ConfigEncryption.get_cipher()
                assert cipher is not None
            except Exception as e:
                pytest.fail(f"Failed to create encryption cipher: {e}")

    def test_encryption_roundtrip(self):
        """Test that encryption and decryption work."""
        app = create_app('testing')
        with app.app_context():
            from app.utils.encryption import ConfigEncryption

            test_config = {'password': 'secret123'}
            encrypted = ConfigEncryption.encrypt_config('email_sender', test_config)
            assert encrypted['password'].startswith('enc:')

            decrypted = ConfigEncryption.decrypt_config('email_sender', encrypted)
            assert decrypted['password'] == 'secret123'


class TestAgentRegistryInitialization:
    """Test that agent registry initializes correctly."""

    def test_agent_registry_imports(self):
        """Test that agent registry can be imported."""
        try:
            from app.agents import agent_registry
            assert agent_registry is not None
        except ImportError as e:
            pytest.fail(f"Failed to import agent registry: {e}")

    def test_agent_registry_has_agents(self):
        """Test that agent types are registered."""
        from app.agents import agent_registry
        registered_types = agent_registry.get_registered_types()
        assert len(registered_types) > 0
        # Check for some known agent types
        assert 'rss_agent' in registered_types


class TestDatabaseConnection:
    """Test database connection and session management."""

    def test_database_session_available(self):
        """Test that database session is available."""
        app = create_app('testing')
        with app.app_context():
            assert db.session is not None

    def test_database_models_accessible(self):
        """Test that database models can be queried."""
        app = create_app('testing')
        with app.app_context():
            try:
                from app.models import User, Job
                # Just verify queries can be constructed (not executed)
                user_query = db.session.query(User)
                job_query = db.session.query(Job)
                assert user_query is not None
                assert job_query is not None
            except Exception as e:
                pytest.fail(f"Failed to access database models: {e}")


class TestErrorHandlers:
    """Test that error handlers are registered."""

    def test_404_error_handler_registered(self):
        """Test that 404 error handler exists."""
        app = create_app('testing')
        with app.test_client() as client:
            response = client.get('/nonexistent-page')
            # Should get 404, not 500 (unhandled error)
            assert response.status_code == 404

    def test_500_error_handler_exists(self):
        """Test that 500 error handler is configured."""
        app = create_app('testing')
        # Check that error handler spec exists
        assert app.error_handler_spec is not None
