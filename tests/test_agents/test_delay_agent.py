"""Tests for DelayAgent."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

from app.agents.types.delay_agent import DelayAgent
from app.agents.registry import agent_registry
from app.models import Event, DelayedEvent
from app.extensions import db


@pytest.fixture
def test_user(db_session):
    from app.models import User
    user = User(username='delaytest', email='delaytest@example.com', password='password123')
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def test_job(db_session, test_user):
    from app.models import Job
    job = Job(
        name='Delay Test Agent',
        job_type='delay_agent',
        config={'delay_minutes': 30},
        user_id=test_user.id,
    )
    db_session.add(job)
    db_session.commit()
    return job


def _event(test_job, payload=None):
    return Event(
        agent_id=test_job.id,
        agent_type='delay_agent',
        user_id=test_job.user_id,
        payload=payload or {'title': 'test'},
        metadata={},
    )


class TestDelayAgentRegistration:
    def test_registered(self):
        assert agent_registry.get_agent_class('delay_agent') is DelayAgent

    def test_capabilities(self, test_job, db_session):
        agent = DelayAgent(
            agent_id=test_job.id,
            config={'delay_minutes': 10},
            user_id=test_job.user_id,
            db_session=db_session,
        )
        assert agent.can_receive_events is True
        assert agent.can_create_events is True
        assert agent.can_be_scheduled is True


class TestDelayAgentValidation:
    def test_delay_minutes_required(self, test_job, db_session):
        with pytest.raises(ValueError, match='delay_minutes is required'):
            DelayAgent(
                agent_id=test_job.id, config={},
                user_id=test_job.user_id, db_session=db_session,
            )

    def test_delay_minutes_must_be_positive(self, test_job, db_session):
        with pytest.raises(ValueError, match='at least 1'):
            DelayAgent(
                agent_id=test_job.id, config={'delay_minutes': 0},
                user_id=test_job.user_id, db_session=db_session,
            )

    def test_delay_minutes_non_integer(self, test_job, db_session):
        with pytest.raises(ValueError, match='integer'):
            DelayAgent(
                agent_id=test_job.id, config={'delay_minutes': 'ten'},
                user_id=test_job.user_id, db_session=db_session,
            )

    def test_valid_config(self, test_job, db_session):
        agent = DelayAgent(
            agent_id=test_job.id, config={'delay_minutes': 60},
            user_id=test_job.user_id, db_session=db_session,
        )
        assert agent.delay_minutes == 60


class TestDelayAgentBuffering:
    def test_incoming_events_are_stored(self, test_job, db_session):
        agent = DelayAgent(
            agent_id=test_job.id, config={'delay_minutes': 30},
            user_id=test_job.user_id, db_session=db_session,
        )
        result = agent.check([_event(test_job, {'msg': 'hello'})])
        assert result == []  # nothing propagates immediately

        stored = db_session.query(DelayedEvent).filter_by(agent_id=test_job.id).all()
        assert len(stored) == 1
        assert stored[0].payload == {'msg': 'hello'}
        assert stored[0].released is False

    def test_release_at_is_in_the_future(self, test_job, db_session):
        before = datetime.utcnow()
        agent = DelayAgent(
            agent_id=test_job.id, config={'delay_minutes': 15},
            user_id=test_job.user_id, db_session=db_session,
        )
        agent.check([_event(test_job)])
        stored = db_session.query(DelayedEvent).filter_by(agent_id=test_job.id).first()
        assert stored.release_at >= before + timedelta(minutes=14)

    def test_multiple_events_stored(self, test_job, db_session):
        agent = DelayAgent(
            agent_id=test_job.id, config={'delay_minutes': 5},
            user_id=test_job.user_id, db_session=db_session,
        )
        events = [_event(test_job, {'n': i}) for i in range(4)]
        result = agent.check(events)
        assert result == []
        count = db_session.query(DelayedEvent).filter_by(agent_id=test_job.id).count()
        assert count == 4


class TestDelayAgentRelease:
    def _seed_delayed(self, db_session, agent_id, payload, release_at, released=False):
        row = DelayedEvent(
            agent_id=agent_id,
            payload=payload,
            metadata_={},
            release_at=release_at,
            released=released,
        )
        db_session.add(row)
        db_session.commit()
        return row

    def test_scheduled_run_releases_ready_events(self, test_job, db_session):
        past = datetime.utcnow() - timedelta(minutes=5)
        self._seed_delayed(db_session, test_job.id, {'msg': 'ready'}, past)

        agent = DelayAgent(
            agent_id=test_job.id, config={'delay_minutes': 30},
            user_id=test_job.user_id, db_session=db_session,
        )
        events = agent.check([])  # scheduled run
        assert len(events) == 1
        assert events[0].payload == {'msg': 'ready'}

    def test_not_yet_ready_events_not_released(self, test_job, db_session):
        future = datetime.utcnow() + timedelta(hours=1)
        self._seed_delayed(db_session, test_job.id, {'msg': 'not yet'}, future)

        agent = DelayAgent(
            agent_id=test_job.id, config={'delay_minutes': 30},
            user_id=test_job.user_id, db_session=db_session,
        )
        events = agent.check([])
        assert events == []

    def test_already_released_not_emitted_again(self, test_job, db_session):
        past = datetime.utcnow() - timedelta(minutes=10)
        self._seed_delayed(db_session, test_job.id, {'msg': 'done'}, past, released=True)

        agent = DelayAgent(
            agent_id=test_job.id, config={'delay_minutes': 30},
            user_id=test_job.user_id, db_session=db_session,
        )
        events = agent.check([])
        assert events == []

    def test_released_flag_set_after_release(self, test_job, db_session):
        past = datetime.utcnow() - timedelta(minutes=5)
        row = self._seed_delayed(db_session, test_job.id, {'x': 1}, past)

        agent = DelayAgent(
            agent_id=test_job.id, config={'delay_minutes': 30},
            user_id=test_job.user_id, db_session=db_session,
        )
        agent.check([])
        db_session.refresh(row)
        assert row.released is True

    def test_no_events_in_empty_buffer(self, test_job, db_session):
        agent = DelayAgent(
            agent_id=test_job.id, config={'delay_minutes': 30},
            user_id=test_job.user_id, db_session=db_session,
        )
        events = agent.check([])
        assert events == []

    def test_store_then_release_roundtrip(self, test_job, db_session):
        agent = DelayAgent(
            agent_id=test_job.id, config={'delay_minutes': 30},
            user_id=test_job.user_id, db_session=db_session,
        )
        # Store
        agent.check([_event(test_job, {'value': 42})])
        # Force release time to the past
        row = db_session.query(DelayedEvent).filter_by(agent_id=test_job.id).first()
        row.release_at = datetime.utcnow() - timedelta(seconds=1)
        db_session.commit()

        # Release
        events = agent.check([])
        assert len(events) == 1
        assert events[0].payload == {'value': 42}
