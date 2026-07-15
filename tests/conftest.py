"""
Pytest configuration and fixtures for Muninn testing
"""

import pytest
from sqlalchemy import text
from flask import g
from app import create_app
from app.extensions import db


def _drop_all_with_enums():
    """Drop all tables, types, and other objects in the public schema."""
    try:
        db.session.remove()
        db.engine.dispose()

        with db.engine.connect() as conn:
            conn = conn.execution_options(isolation_level="AUTOCOMMIT")
            # Terminate all other connections that might hold locks
            conn.execute(text("""
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = current_database()
                  AND pid <> pg_backend_pid()
            """))
            # Drop and recreate the schema — clears all tables, types, sequences
            conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
            conn.execute(text("GRANT ALL ON SCHEMA public TO public"))

    except Exception as e:
        print(f"Warning: Error during database cleanup: {e}")


def _truncate_all_tables():
    """Delete all rows and reset sequences — much faster than TRUNCATE CASCADE on this system."""
    try:
        with db.engine.connect() as conn:
            conn = conn.execution_options(isolation_level="AUTOCOMMIT")
            # Delete in FK dependency order (children before parents)
            conn.execute(text("""
                DELETE FROM agent_links;
                DELETE FROM agent_memory;
                DELETE FROM agent_runs;
                DELETE FROM events;
                DELETE FROM job_chains;
                DELETE FROM job_runs;
                DELETE FROM jobs;
                DELETE FROM credentials;
                DELETE FROM scenarios;
                DELETE FROM users;
                ALTER SEQUENCE agent_links_id_seq RESTART WITH 1;
                ALTER SEQUENCE agent_memory_id_seq RESTART WITH 1;
                ALTER SEQUENCE agent_runs_id_seq RESTART WITH 1;
                ALTER SEQUENCE events_id_seq RESTART WITH 1;
                ALTER SEQUENCE job_chains_id_seq RESTART WITH 1;
                ALTER SEQUENCE job_runs_id_seq RESTART WITH 1;
                ALTER SEQUENCE jobs_id_seq RESTART WITH 1;
                ALTER SEQUENCE credentials_id_seq RESTART WITH 1;
                ALTER SEQUENCE scenarios_id_seq RESTART WITH 1;
                ALTER SEQUENCE users_id_seq RESTART WITH 1;
            """))
    except Exception as e:
        print(f"Warning: Error clearing tables: {e}")


@pytest.fixture(scope='session')
def app():
    """Create the app once for the entire test session."""
    app = create_app('testing')

    with app.app_context():
        # Clean start: drop everything and recreate schema once
        _drop_all_with_enums()
        db.create_all()

        yield app

        # Final cleanup at end of session
        db.session.remove()
        _drop_all_with_enums()


@pytest.fixture(autouse=True)
def clean_tables(app):
    """Truncate all tables before each test for clean isolation.

    Uses the session-scoped app context directly — no nested context push,
    which prevents the outer session from holding locks that block TRUNCATE.
    """
    db.session.remove()
    _truncate_all_tables()
    # Clear Flask-Login's cached current_user from g — it's bound to the persistent
    # session-scoped app context, so it survives between test requests otherwise.
    if hasattr(g, '_login_user'):
        del g._login_user
    # Reset class-level state that accumulates across tests
    try:
        from app.agents.types.discord_webhook_agent import DiscordWebhookAgent
        DiscordWebhookAgent._rate_limit_tracker.clear()
    except ImportError:
        pass
    yield
    db.session.remove()


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

    Returns the session-scoped app whose context is already active.
    """
    return app


@pytest.fixture
def db_session(app):
    """Database session for testing."""
    with app.app_context():
        try:
            db.session.rollback()
        except Exception:
            pass

        yield db.session

        try:
            db.session.rollback()
        except Exception:
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
        job = Job(
            name='Test Agent',
            job_type='rss_agent',
            config={'feed_url': 'https://example.com/feed'},
            user_id=test_user.id
        )
        db.session.add(job)
        db.session.commit()

        yield job


@pytest.fixture
def test_user(app):
    """Create a test user for authentication tests."""
    from app.models import User

    with app.app_context():
        user = User(username='testuser', email='test@example.com', password='password123')
        db.session.add(user)
        db.session.commit()

        yield user


@pytest.fixture
def test_user2(app):
    """Create a second test user for multi-user tests."""
    from app.models import User

    with app.app_context():
        user = User(username='testuser2', email='test2@example.com', password='password456')
        db.session.add(user)
        db.session.commit()

        yield user


@pytest.fixture
def authenticated_client(client, test_user):
    """A test client that's already logged in."""
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
def auth_client2(app, test_user2):
    """A test client logged in as testuser2 (second user)."""
    client = app.test_client()
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
