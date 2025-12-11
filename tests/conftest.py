"""
Pytest configuration and fixtures for Muninn testing
"""

import os
import tempfile
import pytest
from app import create_app
from app.extensions import db


@pytest.fixture
def app():
    """Create and configure a new app instance for each test."""

    # Create the app with testing configuration
    app = create_app('testing')

    # Ensure the app context is available
    with app.app_context():
        # Create all database tables
        db.create_all()

        yield app

        # Clean up database after each test
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """A test runner for the app's Click commands."""
    return app.test_cli_runner()


@pytest.fixture
def app_context(app):
    """Application context for testing."""
    with app.app_context():
        yield app


@pytest.fixture
def db_session(app):
    """Database session for testing."""
    with app.app_context():
        yield db.session


class AuthActions:
    """Helper class for authentication in tests."""
    
    def __init__(self, client):
        self._client = client
    
    def login(self, username='test', password='test'):
        """Login helper for tests."""
        # This can be extended when authentication is implemented
        pass
    
    def logout(self):
        """Logout helper for tests."""
        # This can be extended when authentication is implemented
        pass


@pytest.fixture
def auth(client):
    """Authentication helper fixture."""
    return AuthActions(client)


@pytest.fixture
def test_job(app):
    """Create a test job for agent tests"""
    from app.models import Job, User

    with app.app_context():
        # Create a test user first
        user = User(username='testuser', email='test@example.com', password='password123')
        db.session.add(user)
        db.session.flush()

        # Create a test job
        job = Job(
            name='Test Agent',
            job_type='web_scraper',  # Use existing job type
            config={},
            user_id=user.id
        )
        db.session.add(job)
        db.session.commit()

        yield job

        # Cleanup is handled by app fixture


@pytest.fixture
def sample_events(app, test_job):
    """Create sample events for testing"""
    from app.models import Event

    with app.app_context():
        events = [
            Event(
                agent_id=test_job.id,
                agent_type='test_agent',
                user_id=test_job.user_id,
                payload={'title': 'Test Event 1', 'link': 'https://example.com/1'},
                metadata={}
            ),
            Event(
                agent_id=test_job.id,
                agent_type='test_agent',
                user_id=test_job.user_id,
                payload={'title': 'Test Event 2', 'link': 'https://example.com/2'},
                metadata={}
            ),
            Event(
                agent_id=test_job.id,
                agent_type='test_agent',
                user_id=test_job.user_id,
                payload={'title': 'Test Event 3', 'link': 'https://example.com/3'},
                metadata={}
            )
        ]

        for event in events:
            db.session.add(event)
        db.session.commit()

        yield events 