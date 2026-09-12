"""Tests for SignalScoreAgent."""

from datetime import datetime, timedelta, timezone

import pytest
from app.agents.types.signal_score_agent import SignalScoreAgent
from app.agents.registry import agent_registry
from app.models import Event


@pytest.fixture
def test_user(db_session):
    from app.models import User
    user = User(username='signalscoretest', email='signalscoretest@example.com', password='password123')
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def test_job(db_session, test_user):
    from app.models import Job
    job = Job(
        name='Signal Score Test Agent',
        job_type='signal_score_agent',
        config={},
        user_id=test_user.id,
    )
    db_session.add(job)
    db_session.commit()
    return job


def _make_event(test_job, payload, metadata=None):
    return Event(
        agent_id=test_job.id,
        agent_type='signal_score_agent',
        user_id=test_job.user_id,
        payload=payload,
        metadata=metadata or {},
    )


def _candidate(test_job, topic_key, distinct_sources_48h=2, recurrence_count=3, span_days=12):
    return _make_event(test_job, {
        'topic_key': topic_key,
        'topic_terms': [topic_key],
        'topic_stats': {
            'distinct_sources_48h': distinct_sources_48h,
            'recurrence_count': recurrence_count,
            'span_days': span_days,
        },
    })


class TestSignalScoreAgentRegistration:
    def test_registered(self):
        assert agent_registry.get_agent_class('signal_score_agent') is SignalScoreAgent

    def test_capabilities(self, test_job, db_session):
        agent = SignalScoreAgent(
            agent_id=test_job.id, config={}, user_id=test_job.user_id, db_session=db_session,
        )
        assert agent.can_receive_events is True
        assert agent.can_create_events is True
        assert agent.can_be_scheduled is False


class TestSignalScoreAgentHypeAbsorption:
    def test_hype_snapshot_is_absorbed_and_emits_nothing(self, test_job, db_session):
        agent = SignalScoreAgent(
            agent_id=test_job.id, config={}, user_id=test_job.user_id, db_session=db_session,
        )
        snapshot = _make_event(
            test_job, {'hype_terms': ['ai', 'blockchain']}, metadata={'event_kind': 'hype_snapshot'},
        )
        result = agent.check([snapshot])
        assert result == []
        assert agent.memory.get('hype_terms_state')['terms'] == ['ai', 'blockchain']


class TestSignalScoreAgentCandidateScoring:
    def _make_agent(self, test_job, db_session, config=None):
        return SignalScoreAgent(
            agent_id=test_job.id, config=config or {}, user_id=test_job.user_id, db_session=db_session,
        )

    def test_candidate_passing_all_checks_is_kept(self, test_job, db_session):
        agent = self._make_agent(test_job, db_session)
        candidate = _candidate(test_job, 'supply chain resilience')
        result = agent.check([candidate])
        assert len(result) == 1
        assert 'signal_reason' in result[0].payload

    def test_hype_overlapping_candidate_is_dropped(self, test_job, db_session):
        agent = self._make_agent(test_job, db_session)
        agent.memory.set('hype_terms_state', {
            'terms': ['supply chain resilience'],
            'updated_at': datetime.now(timezone.utc).isoformat(),
        })
        candidate = _candidate(test_job, 'supply chain resilience')
        result = agent.check([candidate])
        assert result == []

    def test_non_persistent_candidate_is_dropped(self, test_job, db_session):
        agent = self._make_agent(test_job, db_session, {'min_recurrences': 2})
        candidate = _candidate(test_job, 'one off story', recurrence_count=1)
        result = agent.check([candidate])
        assert result == []

    def test_too_widely_covered_candidate_is_dropped(self, test_job, db_session):
        agent = self._make_agent(test_job, db_session, {'max_distinct_sources_48h': 4})
        candidate = _candidate(test_job, 'already everywhere', distinct_sources_48h=10)
        result = agent.check([candidate])
        assert result == []

    def test_stale_hype_terms_skip_filtering_instead_of_blocking(self, test_job, db_session):
        agent = self._make_agent(test_job, db_session, {'hype_terms_max_age_hours': 6})
        stale_time = datetime.now(timezone.utc) - timedelta(hours=10)
        agent.memory.set('hype_terms_state', {
            'terms': ['quiet topic'],
            'updated_at': stale_time.isoformat(),
        })
        candidate = _candidate(test_job, 'quiet topic')
        result = agent.check([candidate])
        # Overlaps a cached hype term, but that cache is stale -> not applied.
        assert len(result) == 1

    def test_missing_topic_key_or_stats_is_skipped(self, test_job, db_session):
        agent = self._make_agent(test_job, db_session)
        event = _make_event(test_job, {'topic_terms': ['x']})
        result = agent.check([event])
        assert result == []
