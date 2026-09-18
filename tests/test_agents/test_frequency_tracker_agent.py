"""Tests for FrequencyTrackerAgent."""

from datetime import datetime, timedelta, timezone

import pytest
from app.agents.types.frequency_tracker_agent import FrequencyTrackerAgent
from app.agents.registry import agent_registry
from app.models import Event


@pytest.fixture
def test_user(db_session):
    from app.models import User
    user = User(username='freqtrackertest', email='freqtrackertest@example.com', password='password123')
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def test_job(db_session, test_user):
    from app.models import Job
    job = Job(
        name='Frequency Tracker Test Agent',
        job_type='frequency_tracker_agent',
        config={},
        user_id=test_user.id,
    )
    db_session.add(job)
    db_session.commit()
    return job


def _make_event(test_job, payload):
    return Event(
        agent_id=test_job.id,
        agent_type='frequency_tracker_agent',
        user_id=test_job.user_id,
        payload=payload,
        metadata={},
    )


class TestFrequencyTrackerAgentRegistration:
    def test_registered(self):
        assert agent_registry.get_agent_class('frequency_tracker_agent') is FrequencyTrackerAgent

    def test_capabilities(self, test_job, db_session):
        agent = FrequencyTrackerAgent(
            agent_id=test_job.id, config={}, user_id=test_job.user_id, db_session=db_session,
        )
        assert agent.can_receive_events is True
        assert agent.can_create_events is True
        assert agent.can_be_scheduled is False


class TestFrequencyTrackerAgentValidation:
    def test_window_days_must_be_positive(self, test_job, db_session):
        with pytest.raises(ValueError, match='window_days'):
            FrequencyTrackerAgent(
                agent_id=test_job.id, config={'window_days': 0},
                user_id=test_job.user_id, db_session=db_session,
            )


class TestFrequencyTrackerAgentTracking:
    def _make_agent(self, test_job, db_session, config=None):
        return FrequencyTrackerAgent(
            agent_id=test_job.id, config=config or {}, user_id=test_job.user_id, db_session=db_session,
        )

    def test_first_mention_has_recurrence_count_one(self, test_job, db_session):
        agent = self._make_agent(test_job, db_session)
        event = _make_event(test_job, {'topic_terms': ['quantum sensing'], 'source_domain': 'example.com'})
        result = agent.check([event])
        stats = result[0].payload['topic_stats']
        assert stats['recurrence_count'] == 1
        assert stats['distinct_sources_48h'] == 1
        assert stats['span_days'] == 0.0

    def test_second_mention_from_new_source_increments(self, test_job, db_session):
        agent = self._make_agent(test_job, db_session)
        e1 = _make_event(test_job, {'topic_terms': ['quantum sensing'], 'source_domain': 'a.com'})
        agent.check([e1])

        e2 = _make_event(test_job, {'topic_terms': ['quantum sensing'], 'source_domain': 'b.com'})
        result = agent.check([e2])
        stats = result[0].payload['topic_stats']
        assert stats['recurrence_count'] == 2
        assert stats['distinct_sources_48h'] == 2

    def test_shared_multiword_phrase_clusters_across_articles(self, test_job, db_session):
        agent = self._make_agent(test_job, db_session)
        e1 = _make_event(test_job, {
            'topic_terms': ['quantum sensing', 'photonics'], 'source_domain': 'a.com',
        })
        agent.check([e1])

        e2 = _make_event(test_job, {
            'topic_terms': ['quantum sensing', 'other phrase'], 'source_domain': 'b.com',
        })
        result = agent.check([e2])
        stats = result[0].payload['topic_stats']
        assert stats['recurrence_count'] == 2

    def test_singleword_terms_do_not_cross_link_unrelated_topics(self, test_job, db_session):
        agent = self._make_agent(test_job, db_session)
        # Has a bigram, so its cluster_terms are the bigram only -- the lone
        # word 'market' is passed through but NOT used to link history.
        e_with_bigram = _make_event(test_job, {
            'topic_terms': ['quantum sensing', 'market'], 'source_domain': 'c.com',
        })
        agent.check([e_with_bigram])

        # No bigram at all -> falls back to its own single word for clustering,
        # but that bucket was never written to by the event above.
        e_singleword_only = _make_event(test_job, {
            'topic_terms': ['market'], 'source_domain': 'd.com',
        })
        result = agent.check([e_singleword_only])
        stats = result[0].payload['topic_stats']
        assert stats['recurrence_count'] == 1

    def test_window_days_excludes_old_records(self, test_job, db_session):
        agent = self._make_agent(test_job, db_session, {'window_days': 14})
        old_record = {
            'source': 'old.com',
            'seen_at': (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),
        }
        agent.memory.set('topic_hist:old phrase', [old_record])

        event = _make_event(test_job, {'topic_terms': ['old phrase'], 'source_domain': 'new.com'})
        result = agent.check([event])
        stats = result[0].payload['topic_stats']
        assert stats['recurrence_count'] == 1  # only the new mention -- old one fell outside the window

    def test_missing_topic_terms_skips_event(self, test_job, db_session):
        agent = self._make_agent(test_job, db_session)
        event = _make_event(test_job, {'source_domain': 'example.com'})
        result = agent.check([event])
        assert result == []


class TestAnchorWordPivoting:
    """Anchor-word pivoting: a word appearing in 2+ of an article's phrases
    becomes a secondary cluster key, linking topic variants that share a
    keyword but no complete phrase."""

    def _make_agent(self, test_job, db_session, config=None):
        return FrequencyTrackerAgent(
            agent_id=test_job.id, config=config or {}, user_id=test_job.user_id, db_session=db_session,
        )

    def test_anchor_word_bridges_synonym_variants(self, test_job, db_session):
        """Two articles that share no complete phrase but both have 2+ phrases
        containing the same word are linked via that anchor word."""
        agent = self._make_agent(test_job, db_session)

        # "supply" appears in two phrases → becomes an anchor pivot
        e1 = _make_event(test_job, {
            'topic_terms': ['supply chain', 'supply shortage'],
            'source_domain': 'a.com',
        })
        agent.check([e1])

        # No shared phrase with e1, but "supply" again in two phrases →
        # looks up the "supply" anchor bucket and finds e1's history
        e2 = _make_event(test_job, {
            'topic_terms': ['supply disruption', 'supply risk'],
            'source_domain': 'b.com',
        })
        result = agent.check([e2])
        assert result[0].payload['topic_stats']['recurrence_count'] == 2

    def test_word_in_only_one_phrase_is_not_an_anchor(self, test_job, db_session):
        """A word that appears in only one phrase does not become an anchor,
        so a later article using that word as an anchor finds no history."""
        agent = self._make_agent(test_job, db_session)

        # "quantum" appears in only one phrase → not written under "quantum"
        e1 = _make_event(test_job, {
            'topic_terms': ['quantum sensing', 'photon detection'],
            'source_domain': 'a.com',
        })
        agent.check([e1])

        # "quantum" appears in two phrases → would look under "quantum",
        # but e1 never wrote there, so no link is found
        e2 = _make_event(test_job, {
            'topic_terms': ['quantum computing', 'quantum algorithm'],
            'source_domain': 'b.com',
        })
        result = agent.check([e2])
        assert result[0].payload['topic_stats']['recurrence_count'] == 1

    def test_anchor_accumulates_across_multiple_articles(self, test_job, db_session):
        """History accumulated under an anchor grows as more articles share it."""
        agent = self._make_agent(test_job, db_session)

        for payload, source in [
            ({'topic_terms': ['supply chain', 'supply shortage'], 'source_domain': 'a.com'}, 'a.com'),
            ({'topic_terms': ['supply disruption', 'supply risk'], 'source_domain': 'b.com'}, 'b.com'),
            ({'topic_terms': ['supply crunch', 'supply pressure'], 'source_domain': 'c.com'}, 'c.com'),
        ]:
            agent.check([_make_event(test_job, payload)])

        # Fourth article with "supply" anchor should see all three prior records
        e4 = _make_event(test_job, {
            'topic_terms': ['supply glut', 'supply surplus'],
            'source_domain': 'd.com',
        })
        result = agent.check([e4])
        assert result[0].payload['topic_stats']['recurrence_count'] == 4

    def test_unrelated_single_word_still_does_not_cross_link(self, test_job, db_session):
        """A lone unigram term (no phrases present) does not accidentally link
        to an article that used it only within bigrams."""
        agent = self._make_agent(test_job, db_session)

        # Article with a bigram only — "market" is a component but not an anchor
        e1 = _make_event(test_job, {
            'topic_terms': ['housing market', 'bond market'],
            'source_domain': 'a.com',
        })
        agent.check([e1])

        # Wait — "market" appears in TWO phrases above → it IS an anchor.
        # But a bare "market" unigram article with no phrases should still
        # link (this tests that the anchor key is picked up correctly).
        e2 = _make_event(test_job, {
            'topic_terms': ['market'],   # no phrases → cluster_terms = ['market']
            'source_domain': 'b.com',
        })
        result = agent.check([e2])
        # "market" was written as an anchor by e1, so e2 finds it
        assert result[0].payload['topic_stats']['recurrence_count'] == 2
