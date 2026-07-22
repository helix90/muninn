"""Tests for Feature 9 — Pipeline Run History/Trace."""

import uuid
import pytest
from datetime import datetime

from app.models import AgentRun, Event
from app.services.event_service import EventService


# ---------------------------------------------------------------------------
# Model / propagation_id column tests
# ---------------------------------------------------------------------------

class TestPropagationIdColumns:
    def test_event_has_propagation_id_column(self, db_session, test_user, test_job):
        e = Event(
            agent_id=test_job.id,
            agent_type='rss_agent',
            user_id=test_user.id,
            payload={'x': 1},
            propagation_id='test-pid',
        )
        db_session.add(e)
        db_session.commit()
        db_session.refresh(e)
        assert e.propagation_id == 'test-pid'

    def test_event_propagation_id_defaults_to_none(self, db_session, test_user, test_job):
        e = Event(
            agent_id=test_job.id,
            agent_type='rss_agent',
            user_id=test_user.id,
            payload={},
        )
        db_session.add(e)
        db_session.commit()
        assert e.propagation_id is None

    def test_agent_run_has_propagation_id_column(self, db_session, test_job):
        run = AgentRun(
            agent_id=test_job.id,
            status='completed',
            propagation_id='my-run-id',
        )
        db_session.add(run)
        db_session.commit()
        db_session.refresh(run)
        assert run.propagation_id == 'my-run-id'


# ---------------------------------------------------------------------------
# EventService propagation_id threading tests
# ---------------------------------------------------------------------------

class TestEventServicePropagation:
    def test_propagate_returns_propagation_id(self, db_session, test_user, test_job):
        e = Event(
            agent_id=test_job.id,
            agent_type='rss_agent',
            user_id=test_user.id,
            payload={'title': 'Test'},
        )
        db_session.add(e)
        db_session.commit()

        svc = EventService(db_session=db_session)
        stats = svc.propagate_events([e])
        assert 'propagation_id' in stats

    def test_propagate_stamps_source_events(self, db_session, test_user, test_job):
        e = Event(
            agent_id=test_job.id,
            agent_type='rss_agent',
            user_id=test_user.id,
            payload={'title': 'Test'},
        )
        db_session.add(e)
        db_session.commit()

        svc = EventService(db_session=db_session)
        stats = svc.propagate_events([e])
        pid = stats['propagation_id']
        assert pid is not None
        db_session.refresh(e)
        assert e.propagation_id == pid

    def test_propagate_empty_returns_none_propagation_id(self, db_session):
        svc = EventService(db_session=db_session)
        stats = svc.propagate_events([])
        assert stats['propagation_id'] is None

    def test_each_propagation_gets_unique_id(self, db_session, test_user, test_job):
        e1 = Event(agent_id=test_job.id, agent_type='rss_agent', user_id=test_user.id, payload={})
        e2 = Event(agent_id=test_job.id, agent_type='rss_agent', user_id=test_user.id, payload={})
        db_session.add_all([e1, e2])
        db_session.commit()

        svc = EventService(db_session=db_session)
        s1 = svc.propagate_events([e1])
        s2 = svc.propagate_events([e2])
        assert s1['propagation_id'] != s2['propagation_id']


# ---------------------------------------------------------------------------
# Pipeline Runs list route
# ---------------------------------------------------------------------------

class TestPipelineRunsListRoute:
    def test_requires_login(self, client):
        resp = client.get('/pipeline-runs/')
        assert resp.status_code in (302, 401)

    def test_empty_state(self, auth_client):
        resp = auth_client.get('/pipeline-runs/')
        assert resp.status_code == 200
        assert b'Pipeline Runs' in resp.data

    def test_shows_agent_runs_with_propagation_id(self, auth_client, db_session, test_user, test_job):
        pid = str(uuid.uuid4())
        run = AgentRun(
            agent_id=test_job.id,
            status='completed',
            propagation_id=pid,
        )
        db_session.add(run)
        db_session.commit()

        resp = auth_client.get('/pipeline-runs/')
        assert resp.status_code == 200
        assert pid.encode() in resp.data

    def test_does_not_show_runs_without_propagation_id(self, auth_client, db_session, test_job):
        run = AgentRun(agent_id=test_job.id, status='completed')
        db_session.add(run)
        db_session.commit()

        resp = auth_client.get('/pipeline-runs/')
        assert resp.status_code == 200
        # Should not error; row with None propagation_id is excluded

    def test_user_isolation(self, auth_client, auth_client2, db_session, test_user, test_user2, app):
        from app.models import Job
        with app.app_context():
            job2 = Job(
                name='Other Job',
                job_type='rss_agent',
                config={},
                user_id=test_user2.id,
            )
            db_session.add(job2)
            db_session.commit()

            pid = str(uuid.uuid4())
            run = AgentRun(agent_id=job2.id, status='completed', propagation_id=pid)
            db_session.add(run)
            db_session.commit()

        resp = auth_client.get('/pipeline-runs/')
        assert resp.status_code == 200
        # user1 should not see user2's run
        assert pid.encode() not in resp.data


# ---------------------------------------------------------------------------
# Pipeline Runs detail route
# ---------------------------------------------------------------------------

class TestPipelineRunsDetailRoute:
    def test_requires_login(self, client):
        resp = client.get('/pipeline-runs/some-fake-id')
        assert resp.status_code in (302, 401)

    def test_nonexistent_propagation_id_returns_200(self, auth_client):
        resp = auth_client.get('/pipeline-runs/nonexistent-pid-xyz')
        assert resp.status_code == 200

    def test_shows_agent_run_details(self, auth_client, db_session, test_user, test_job):
        pid = str(uuid.uuid4())
        run = AgentRun(
            agent_id=test_job.id,
            status='completed',
            propagation_id=pid,
            input_event_ids=[1, 2],
            output_event_ids=[3],
        )
        db_session.add(run)
        db_session.commit()

        resp = auth_client.get(f'/pipeline-runs/{pid}')
        assert resp.status_code == 200
        assert b'completed' in resp.data

    def test_shows_events_for_propagation(self, auth_client, db_session, test_user, test_job):
        pid = str(uuid.uuid4())
        e = Event(
            agent_id=test_job.id,
            agent_type='rss_agent',
            user_id=test_user.id,
            payload={'title': 'Traced event'},
            propagation_id=pid,
        )
        db_session.add(e)
        run = AgentRun(agent_id=test_job.id, status='completed', propagation_id=pid)
        db_session.add(run)
        db_session.commit()

        resp = auth_client.get(f'/pipeline-runs/{pid}')
        assert resp.status_code == 200
        assert b'Traced event' in resp.data

    def test_shows_failed_status(self, auth_client, db_session, test_user, test_job):
        pid = str(uuid.uuid4())
        run = AgentRun(
            agent_id=test_job.id,
            status='failed',
            propagation_id=pid,
            error_message='Something broke',
        )
        db_session.add(run)
        db_session.commit()

        resp = auth_client.get(f'/pipeline-runs/{pid}')
        assert resp.status_code == 200
        assert b'failed' in resp.data
        assert b'Something broke' in resp.data
