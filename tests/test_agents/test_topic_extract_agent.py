"""Tests for TopicExtractAgent."""

import pytest
from app.agents.types.topic_extract_agent import TopicExtractAgent
from app.agents.registry import agent_registry
from app.models import Event


@pytest.fixture
def test_user(db_session):
    from app.models import User
    user = User(username='topicextracttest', email='topicextracttest@example.com', password='password123')
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def test_job(db_session, test_user):
    from app.models import Job
    job = Job(
        name='Topic Extract Test Agent',
        job_type='topic_extract_agent',
        config={},
        user_id=test_user.id,
    )
    db_session.add(job)
    db_session.commit()
    return job


def _make_event(test_job, payload):
    return Event(
        agent_id=test_job.id,
        agent_type='topic_extract_agent',
        user_id=test_job.user_id,
        payload=payload,
        metadata={},
    )


class TestTopicExtractAgentRegistration:
    def test_registered(self):
        assert agent_registry.get_agent_class('topic_extract_agent') is TopicExtractAgent

    def test_capabilities(self, test_job, db_session):
        agent = TopicExtractAgent(
            agent_id=test_job.id, config={}, user_id=test_job.user_id, db_session=db_session,
        )
        assert agent.can_receive_events is True
        assert agent.can_create_events is True
        assert agent.can_be_scheduled is False


class TestTopicExtractAgentValidation:
    def test_max_topics_per_item_must_be_positive_int(self, test_job, db_session):
        with pytest.raises(ValueError, match='max_topics_per_item'):
            TopicExtractAgent(
                agent_id=test_job.id, config={'max_topics_per_item': 0},
                user_id=test_job.user_id, db_session=db_session,
            )

    def test_source_fields_must_be_nonempty_list(self, test_job, db_session):
        with pytest.raises(ValueError, match='source_fields'):
            TopicExtractAgent(
                agent_id=test_job.id, config={'source_fields': []},
                user_id=test_job.user_id, db_session=db_session,
            )


class TestTopicExtractAgentExtraction:
    def _make_agent(self, test_job, db_session, config=None):
        return TopicExtractAgent(
            agent_id=test_job.id, config=config or {}, user_id=test_job.user_id, db_session=db_session,
        )

    def test_extracts_topic_terms_and_key(self, test_job, db_session):
        agent = self._make_agent(test_job, db_session)
        event = _make_event(test_job, {
            'title': 'Supply chain resilience grows quietly across regional manufacturers',
            'summary': 'Executives increasingly discuss supply chain resilience as a long-term strategy',
            'link': 'https://example.com/article',
        })
        result = agent.check([event])
        assert len(result) == 1
        payload = result[0].payload
        assert payload['topic_terms'], 'expected at least one extracted term'
        assert payload['topic_key'] == payload['topic_terms'][0]
        assert 'supply chain' in payload['topic_terms']

    def test_source_domain_derived_from_link(self, test_job, db_session):
        agent = self._make_agent(test_job, db_session)
        event = _make_event(test_job, {
            'title': 'Quiet infrastructure investment continues',
            'link': 'https://www.example.com/article/123',
        })
        result = agent.check([event])
        assert result[0].payload['source_domain'] == 'example.com'

    def test_skips_event_with_no_extractable_terms(self, test_job, db_session):
        agent = self._make_agent(test_job, db_session)
        event = _make_event(test_job, {'title': 'to a is of it', 'summary': ''})
        result = agent.check([event])
        assert result == []

    def test_max_topics_per_item_limits_output(self, test_job, db_session):
        agent = self._make_agent(test_job, db_session, {'max_topics_per_item': 2})
        event = _make_event(test_job, {
            'title': 'Alpha bravo charlie delta echo foxtrot golf hotel',
        })
        result = agent.check([event])
        assert len(result[0].payload['topic_terms']) <= 2

    def test_preserves_original_payload_fields(self, test_job, db_session):
        agent = self._make_agent(test_job, db_session)
        event = _make_event(test_job, {
            'title': 'Battery recycling programs expand quietly nationwide',
            'link': 'https://example.com/battery',
            'author': 'Jane Doe',
        })
        result = agent.check([event])
        assert result[0].payload['author'] == 'Jane Doe'
        assert result[0].payload['link'] == 'https://example.com/battery'
