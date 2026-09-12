"""Tests for HypeTermAgent."""

import pytest
from app.agents.types.hype_term_agent import HypeTermAgent
from app.agents.registry import agent_registry
from app.models import Event


@pytest.fixture
def test_user(db_session):
    from app.models import User
    user = User(username='hypetermtest', email='hypetermtest@example.com', password='password123')
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def test_job(db_session, test_user):
    from app.models import Job
    job = Job(
        name='Hype Term Test Agent',
        job_type='hype_term_agent',
        config={},
        user_id=test_user.id,
    )
    db_session.add(job)
    db_session.commit()
    return job


def _make_event(test_job, payload):
    return Event(
        agent_id=test_job.id,
        agent_type='hype_term_agent',
        user_id=test_job.user_id,
        payload=payload,
        metadata={},
    )


class TestHypeTermAgentRegistration:
    def test_registered(self):
        assert agent_registry.get_agent_class('hype_term_agent') is HypeTermAgent

    def test_capabilities(self, test_job, db_session):
        agent = HypeTermAgent(
            agent_id=test_job.id, config={}, user_id=test_job.user_id, db_session=db_session,
        )
        assert agent.can_receive_events is True
        assert agent.can_create_events is True
        assert agent.can_be_scheduled is False


class TestHypeTermAgentSnapshot:
    def _make_agent(self, test_job, db_session, config=None):
        return HypeTermAgent(
            agent_id=test_job.id, config=config or {}, user_id=test_job.user_id, db_session=db_session,
        )

    def test_emits_single_tagged_snapshot_event(self, test_job, db_session):
        agent = self._make_agent(test_job, db_session)
        events = [
            _make_event(test_job, {'title': 'Quarterly earnings beat expectations'}),
            _make_event(test_job, {'title': 'Startup raises massive funding round'}),
            _make_event(test_job, {'title': 'New smartphone launch draws crowds'}),
        ]
        result = agent.check(events)
        assert len(result) == 1
        assert result[0].event_metadata['event_kind'] == 'hype_snapshot'
        assert result[0].payload['item_count'] == 3
        assert 'hype_terms' in result[0].payload
        assert 'generated_at' in result[0].payload

    def test_document_frequency_beats_raw_repetition(self, test_job, db_session):
        agent = self._make_agent(test_job, db_session)
        events = [
            # 'quantum' repeated 3x within ONE document -> document frequency 1
            _make_event(test_job, {'title': 'quantum quantum quantum breakthrough'}),
            # 'signal' appears once each in THREE distinct documents -> document frequency 3
            _make_event(test_job, {'title': 'signal update alpha'}),
            _make_event(test_job, {'title': 'signal update beta'}),
            _make_event(test_job, {'title': 'signal update gamma'}),
        ]
        result = agent.check(events)
        hype_terms = result[0].payload['hype_terms']
        assert hype_terms.index('signal') < hype_terms.index('quantum')

    def test_top_n_terms_limits_output(self, test_job, db_session):
        agent = self._make_agent(test_job, db_session, {'top_n_terms': 2})
        events = [
            _make_event(test_job, {'title': 'alpha bravo charlie delta echo'}),
        ]
        result = agent.check(events)
        assert len(result[0].payload['hype_terms']) <= 2

    def test_empty_events_returns_empty_list(self, test_job, db_session):
        agent = self._make_agent(test_job, db_session)
        result = agent.check([])
        assert result == []
