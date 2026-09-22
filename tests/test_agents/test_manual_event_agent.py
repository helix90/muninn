"""Tests for ManualEventAgent."""

import pytest
from app.agents.registry import agent_registry
from app.agents.types.manual_event_agent import ManualEventAgent


@pytest.fixture
def test_user(db_session):
    from app.models import User
    user = User(username='manualtest', email='manualtest@example.com', password='password123')
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def test_job(db_session, test_user):
    from app.models import Job
    job = Job(
        name='Manual Event Agent',
        job_type='manual_event_agent',
        config={'payload': {'title': 'test', 'value': 42}},
        user_id=test_user.id,
    )
    db_session.add(job)
    db_session.commit()
    return job


def _make_agent(job, db_session, config=None):
    cfg = config if config is not None else job.config
    return ManualEventAgent(
        agent_id=job.id, config=cfg, user_id=job.user_id, db_session=db_session,
    )


class TestManualEventAgentRegistration:
    def test_registered(self):
        assert agent_registry.get_agent_class('manual_event_agent') is ManualEventAgent

    def test_capabilities(self, test_job, db_session):
        agent = _make_agent(test_job, db_session)
        assert agent.can_be_scheduled is True
        assert agent.can_create_events is True
        assert agent.can_receive_events is False


class TestManualEventAgentValidation:
    def test_missing_payload_raises(self, test_job, db_session):
        with pytest.raises(ValueError, match='payload'):
            _make_agent(test_job, db_session, config={})

    def test_non_dict_payload_raises(self, test_job, db_session):
        with pytest.raises(ValueError, match='payload'):
            _make_agent(test_job, db_session, config={'payload': ['a', 'b']})

    def test_string_payload_raises(self, test_job, db_session):
        with pytest.raises(ValueError, match='payload'):
            _make_agent(test_job, db_session, config={'payload': 'hello'})

    def test_empty_dict_payload_is_valid(self, test_job, db_session):
        agent = _make_agent(test_job, db_session, config={'payload': {}})
        assert agent is not None


class TestManualEventAgentFetch:
    def test_emits_exactly_one_event(self, test_job, db_session):
        agent = _make_agent(test_job, db_session)
        events = agent.fetch()
        assert len(events) == 1

    def test_event_payload_matches_config(self, test_job, db_session):
        agent = _make_agent(test_job, db_session)
        events = agent.fetch()
        assert events[0].payload == {'title': 'test', 'value': 42}

    def test_payload_is_a_copy_not_a_reference(self, test_job, db_session):
        agent = _make_agent(test_job, db_session)
        events = agent.fetch()
        events[0].payload['injected'] = True
        assert 'injected' not in agent.config['payload']

    def test_arbitrary_keys_are_preserved(self, test_job, db_session):
        agent = _make_agent(test_job, db_session, config={
            'payload': {'nested': {'a': 1}, 'list': [1, 2, 3], 'flag': True}
        })
        events = agent.fetch()
        assert events[0].payload['nested'] == {'a': 1}
        assert events[0].payload['list'] == [1, 2, 3]
        assert events[0].payload['flag'] is True

    def test_each_run_emits_one_event(self, test_job, db_session):
        agent = _make_agent(test_job, db_session)
        for _ in range(3):
            events = agent.fetch()
            assert len(events) == 1

    def test_empty_payload_emits_empty_event(self, test_job, db_session):
        agent = _make_agent(test_job, db_session, config={'payload': {}})
        events = agent.fetch()
        assert len(events) == 1
        assert events[0].payload == {}
