"""
Pytest configuration and fixtures for Muninn testing
"""

import os
import tempfile
import pytest
from sqlalchemy import text
from app import create_app
from app.extensions import db


def drop_all_with_enums(db_instance):
    """Drop all tables and PostgreSQL ENUMs properly."""
    try:
        # First, close all sessions and expire all objects
        db_instance.session.remove()
        db_instance.session.expire_all()

        # Then, drop all custom ENUM types (PostgreSQL specific)
        # Do this BEFORE dropping tables to avoid constraint issues
        try:
            # Use raw connection without transaction context for DDL
            with db_instance.engine.connect() as connection:
                # Commit any pending transactions first
                try:
                    connection.commit()
                except:
                    pass

                # Execute in AUTOCOMMIT mode for DDL operations
                connection = connection.execution_options(isolation_level="AUTOCOMMIT")

                # Get all custom enum types
                try:
                    result = connection.execute(text("""
                        SELECT t.typname
                        FROM pg_type t
                        JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace
                        WHERE t.typtype = 'e'
                        AND n.nspname = 'public'
                    """))

                    enum_types = [row[0] for row in result.fetchall()]

                    # Drop each enum type with CASCADE
                    for enum_type in enum_types:
                        try:
                            connection.execute(text(f'DROP TYPE IF EXISTS "{enum_type}" CASCADE'))
                        except Exception as e:
                            # If drop fails, just log and continue
                            print(f"Warning: Could not drop enum {enum_type}: {e}")
                except Exception as e:
                    # If we can't query enums (e.g., using SQLite), just continue
                    if 'no such table: pg_type' not in str(e).lower():
                        print(f"Warning: Could not query/drop enums: {e}")
        except Exception as e:
            print(f"Warning: Could not clean up enums: {e}")

        # Drop all tables AFTER dropping enums
        try:
            db_instance.drop_all()
        except Exception as e:
            print(f"Warning: Error dropping tables: {e}")
    except Exception as e:
        print(f"Warning: Error during database cleanup: {e}")


@pytest.fixture
def app():
    """Create and configure a new app instance for each test."""

    # Create the app with testing configuration
    app = create_app('testing')

    # Ensure the app context is available
    with app.app_context():
        # Clean up any leftover data from previous failed tests
        # Always do a thorough cleanup before creating tables
        drop_all_with_enums(db)

        # Create all database tables
        db.create_all()

        yield app

        # Clean up database after each test
        db.session.remove()
        drop_all_with_enums(db)


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
    """Application context for testing.

    This fixture depends on the app fixture to ensure proper database cleanup.
    It simply returns the app which already has its context active.
    """
    # The app fixture already has app_context active, so just return it
    return app


@pytest.fixture
def db_session(app):
    """Database session for testing."""
    with app.app_context():
        # Start with a clean transaction state
        try:
            db.session.rollback()
        except:
            pass

        yield db.session

        # Always clean up after test, even on error
        try:
            db.session.rollback()
        except:
            pass
        finally:
            db.session.remove()


class AuthActions:
    """Helper class for authentication in tests."""

    def __init__(self, client):
        self._client = client

    def login(self, username='testuser', password='password123'):
        """Login helper for tests."""
        return self._client.post(
            '/auth/login',
            data={'username': username, 'password': password},
            follow_redirects=True
        )

    def logout(self):
        """Logout helper for tests."""
        return self._client.get('/auth/logout', follow_redirects=True)


@pytest.fixture
def auth(client):
    """Authentication helper fixture."""
    return AuthActions(client)


@pytest.fixture
def test_job(app, test_user):
    """Create a test job for agent tests"""
    from app.models import Job

    with app.app_context():
        # Create a test job (using agent system)
        job = Job(
            name='Test Agent',
            job_type='rss_agent',  # Use valid agent type
            config={'feed_url': 'https://example.com/feed'},
            user_id=test_user.id
        )
        db.session.add(job)
        db.session.commit()

        yield job

        # Cleanup is handled by app fixture


@pytest.fixture
def test_user(app):
    """Create a test user for authentication tests."""
    from app.models import User

    with app.app_context():
        user = User(username='testuser', email='test@example.com', password='password123')
        db.session.add(user)
        db.session.commit()

        yield user

        # Cleanup is handled by app fixture


@pytest.fixture
def test_user2(app):
    """Create a second test user for multi-user tests."""
    from app.models import User

    with app.app_context():
        user = User(username='testuser2', email='test2@example.com', password='password456')
        db.session.add(user)
        db.session.commit()

        yield user

        # Cleanup is handled by app fixture


@pytest.fixture
def authenticated_client(client, test_user):
    """A test client that's already logged in."""
    # Login the test user
    client.post('/auth/login', data={
        'username': 'testuser',
        'password': 'password123'
    })
    return client


@pytest.fixture
def auth_client(client, test_user):
    """Alias for authenticated_client - a test client logged in as testuser."""
    client.post('/auth/login', data={
        'username': 'testuser',
        'password': 'password123'
    })
    return client


@pytest.fixture
def auth_client2(client, test_user2):
    """A test client logged in as testuser2 (second user)."""
    client.post('/auth/login', data={
        'username': 'testuser2',
        'password': 'password456'
    })
    return client


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