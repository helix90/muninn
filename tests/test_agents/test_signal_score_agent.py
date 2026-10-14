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


class TestSignalScoreAgentHypeMerging:
    def _make_agent(self, test_job, db_session, config=None):
        return SignalScoreAgent(
            agent_id=test_job.id, config=config or {}, user_id=test_job.user_id, db_session=db_session,
        )

    def _snapshot(self, test_job, terms):
        return _make_event(test_job, {'hype_terms': terms}, metadata={'event_kind': 'hype_snapshot'})

    def test_snapshots_from_multiple_feeds_are_merged(self, test_job, db_session):
        agent = self._make_agent(test_job, db_session)
        agent.check([self._snapshot(test_job, ['quantum computing'])])
        agent.check([self._snapshot(test_job, ['battery recycling'])])
        assert agent.check([_candidate(test_job, 'quantum computing')]) == []
        assert agent.check([_candidate(test_job, 'battery recycling')]) == []

    def test_terms_expire_individually(self, test_job, db_session):
        agent = self._make_agent(test_job, db_session, {'hype_terms_max_age_hours': 6})
        old = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat()
        agent.memory.set('hype_terms_state', {
            'terms': ['old story'], 'term_seen': {'old story': old}, 'updated_at': old,
        })
        agent.check([self._snapshot(test_job, ['fresh story'])])
        assert agent.memory.get('hype_terms_state')['terms'] == ['fresh story']
        assert len(agent.check([_candidate(test_job, 'old story')])) == 1
        assert agent.check([_candidate(test_job, 'fresh story')]) == []


class TestSignalScoreAgentHypeMatching:
    def _agent_with_hype(self, test_job, db_session, terms, config=None):
        agent = SignalScoreAgent(
            agent_id=test_job.id, config=config or {}, user_id=test_job.user_id, db_session=db_session,
        )
        agent.memory.set('hype_terms_state', {
            'terms': terms, 'updated_at': datetime.now(timezone.utc).isoformat(),
        })
        return agent

    def _with_terms(self, test_job, terms):
        event = _candidate(test_job, terms[0])
        event.payload = {**event.payload, 'topic_terms': terms}
        return event

    def test_phrase_built_from_hype_words_is_hype(self, test_job, db_session):
        agent = self._agent_with_hype(test_job, db_session, ['openai', 'model'])
        assert agent.check([_candidate(test_job, 'openai model')]) == []

    def test_single_incidental_overlap_does_not_drop(self, test_job, db_session):
        agent = self._agent_with_hype(test_job, db_session, ['open source'])
        event = self._with_terms(test_job, [
            'water utilities', 'leak detection', 'open source', 'acoustic sensors',
        ])
        assert len(agent.check([event])) == 1

    def test_majority_overlap_drops(self, test_job, db_session):
        agent = self._agent_with_hype(test_job, db_session, ['open source', 'rust compiler'])
        event = self._with_terms(test_job, ['leak detection', 'open source', 'rust compiler'])
        assert agent.check([event]) == []

    def test_strict_overlap_threshold(self, test_job, db_session):
        agent = self._agent_with_hype(test_job, db_session, ['open source'], {'max_hype_overlap': 0.25})
        event = self._with_terms(test_job, [
            'water utilities', 'leak detection', 'open source', 'acoustic sensors',
        ])
        assert agent.check([event]) == []

    def test_invalid_overlap_rejected(self, test_job, db_session):
        with pytest.raises(ValueError, match='max_hype_overlap'):
            SignalScoreAgent(agent_id=test_job.id, config={'max_hype_overlap': 0},
                             user_id=test_job.user_id, db_session=db_session)


class TestSignalScoreAgentHypeLanguageAndCooldown:
    def _make_agent(self, test_job, db_session, config=None):
        return SignalScoreAgent(
            agent_id=test_job.id, config=config or {}, user_id=test_job.user_id, db_session=db_session,
        )

    def test_oversold_item_dropped(self, test_job, db_session):
        agent = self._make_agent(test_job, db_session)
        event = _candidate(test_job, 'battery chemistry')
        event.payload = {**event.payload, 'hype_language': ['revolutionary', 'game-changing']}
        assert agent.check([event]) == []

    def test_single_hype_word_tolerated_by_default(self, test_job, db_session):
        agent = self._make_agent(test_job, db_session)
        event = _candidate(test_job, 'battery chemistry')
        event.payload = {**event.payload, 'hype_language': ['breakthrough']}
        assert len(agent.check([event])) == 1

    def test_cooldown_suppresses_same_cluster(self, test_job, db_session):
        agent = self._make_agent(test_job, db_session, {'resurface_cooldown_days': 7})
        first = _candidate(test_job, 'leak detection')
        first.payload = {**first.payload, 'topic_cluster_terms': ['leak detection', 'water utilities', 'water']}
        second = _candidate(test_job, 'water utilities')
        second.payload = {**second.payload, 'topic_cluster_terms': ['water utilities', 'water']}
        unrelated = _candidate(test_job, 'water rights')
        unrelated.payload = {**unrelated.payload, 'topic_cluster_terms': ['water rights', 'water']}
        result = agent.check([first, second, unrelated])
        assert [e.payload['topic_key'] for e in result] == ['leak detection', 'water rights']

    def test_no_cooldown_by_default(self, test_job, db_session):
        agent = self._make_agent(test_job, db_session)
        result = agent.check([_candidate(test_job, 'leak detection'), _candidate(test_job, 'leak detection')])
        assert len(result) == 2
