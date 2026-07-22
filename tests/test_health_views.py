"""Tests for the health dashboard views."""
import pytest
from unittest.mock import patch
from app.models import Job, AgentRun
from app.services.health_service import HEALTH_CRITICAL, HEALTH_WARNING, HEALTH_HEALTHY


class TestHealthDashboard:
    """Tests for /health/ route."""

    def test_dashboard_requires_login(self, client):
        """Unauthenticated request redirects to login."""
        resp = client.get('/health/')
        assert resp.status_code == 302
        assert '/auth/login' in resp.headers['Location']

    def test_dashboard_loads_for_authenticated_user(self, client, test_user, db_session):
        """Authenticated user can access the health dashboard."""
        client.post('/auth/login', data={
            'username': test_user.username,
            'password': 'password123',
        }, follow_redirects=True)
        resp = client.get('/health/')
        assert resp.status_code == 200
        assert b'Health Dashboard' in resp.data

    def test_dashboard_shows_all_status_labels(self, client, test_user, test_job, db_session):
        """Summary section renders correctly."""
        client.post('/auth/login', data={
            'username': test_user.username,
            'password': 'password123',
        }, follow_redirects=True)
        test_job.health_status = HEALTH_CRITICAL
        db_session.commit()
        resp = client.get('/health/')
        assert resp.status_code == 200
        assert b'Critical' in resp.data

    def test_dashboard_shows_agent_names(self, client, test_user, test_job, db_session):
        """Agent names appear in the table."""
        client.post('/auth/login', data={
            'username': test_user.username,
            'password': 'password123',
        }, follow_redirects=True)
        resp = client.get('/health/')
        assert resp.status_code == 200
        assert test_job.name.encode() in resp.data


class TestHealthApiSummary:
    """Tests for /health/api/summary."""

    def test_api_summary_requires_login(self, client):
        resp = client.get('/health/api/summary')
        assert resp.status_code == 302

    def test_api_summary_returns_json(self, client, test_user, test_job, db_session):
        """API endpoint returns valid JSON fleet summary."""
        client.post('/auth/login', data={
            'username': test_user.username,
            'password': 'password123',
        }, follow_redirects=True)
        resp = client.get('/health/api/summary')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'total' in data
        assert 'healthy' in data
        assert 'critical' in data
        assert 'has_critical' in data
        assert data['total'] >= 1

    def test_api_summary_reflects_critical_status(self, client, test_user, db_session):
        """has_critical is True when a critical agent exists."""
        # Create the job directly in db_session so we can set health_status
        from app.models import Job
        job = Job(
            name='Critical Agent', job_type='rss_agent',
            config={'feed_url': 'https://example.com/feed'}, user_id=test_user.id,
        )
        job.health_status = HEALTH_CRITICAL
        job.consecutive_failures = 3
        db_session.add(job)
        db_session.commit()

        client.post('/auth/login', data={
            'username': test_user.username,
            'password': 'password123',
        }, follow_redirects=True)
        resp = client.get('/health/api/summary')
        data = resp.get_json()
        assert data['has_critical'] is True


class TestHealthApiAgentDetail:
    """Tests for /health/api/agent/<id>."""

    def test_returns_agent_health(self, client, test_user, test_job, db_session):
        """Endpoint returns health detail for a specific agent."""
        client.post('/auth/login', data={
            'username': test_user.username,
            'password': 'password123',
        }, follow_redirects=True)
        resp = client.get(f'/health/api/agent/{test_job.id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['id'] == test_job.id
        assert 'health_status' in data
        assert 'consecutive_failures' in data

    def test_returns_404_for_other_users_agent(self, client, test_user, test_job, db_session):
        """Cannot view another user's agent health."""
        from app.models import User
        other = User(username='other99', email='other99@example.com', password='password123')
        db_session.add(other)
        db_session.flush()

        from app.models import Job
        from app.agents.registry import agent_registry
        agent_type = agent_registry.get_registered_types()[0]
        other_job = Job(
            name='Other Job', job_type=agent_type,
            config={}, user_id=other.id
        )
        db_session.add(other_job)
        db_session.commit()

        client.post('/auth/login', data={
            'username': test_user.username,
            'password': 'password123',
        }, follow_redirects=True)
        resp = client.get(f'/health/api/agent/{other_job.id}')
        assert resp.status_code == 404
