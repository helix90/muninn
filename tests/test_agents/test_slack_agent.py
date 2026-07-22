"""Tests for SlackAgent."""

import pytest
from unittest.mock import patch, Mock

from app.agents.types.slack_agent import SlackAgent
from app.agents.registry import agent_registry
from app.models import Event
from app.extensions import db


@pytest.fixture
def test_user(db_session):
    from app.models import User
    user = User(username='slacktest', email='slacktest@example.com', password='password123')
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def test_job(db_session, test_user):
    from app.models import Job
    job = Job(
        name='Slack Test Agent',
        job_type='rss_agent',
        config={'feed_url': 'https://example.com/feed'},
        user_id=test_user.id,
    )
    db_session.add(job)
    db_session.commit()
    return job


@pytest.fixture
def sample_event(test_job):
    return Event(
        agent_id=test_job.id,
        agent_type='rss_agent',
        user_id=test_job.user_id,
        payload={'title': 'Alert fired', 'severity': 'high', 'link': 'https://example.com'},
        metadata={},
    )


WEBHOOK_URL = 'https://hooks.slack.com/services/T000/B000/xxxx'


class TestSlackAgentRegistration:
    def test_registered(self):
        assert agent_registry.get_agent_class('slack_agent') is SlackAgent

    def test_capabilities(self, test_job, db_session):
        agent = SlackAgent(
            agent_id=test_job.id,
            config={'webhook_url': WEBHOOK_URL, 'message_template': 'hello'},
            user_id=test_job.user_id,
            db_session=db_session,
        )
        assert agent.can_receive_events is True
        assert agent.can_be_scheduled is False
        assert agent.can_create_events is False


class TestSlackAgentValidation:
    def test_webhook_url_required(self, test_job, db_session):
        with pytest.raises(ValueError, match='webhook_url is required'):
            SlackAgent(
                agent_id=test_job.id,
                config={'message_template': 'hi'},
                user_id=test_job.user_id,
                db_session=db_session,
            )

    def test_webhook_url_must_be_slack(self, test_job, db_session):
        with pytest.raises(ValueError, match='hooks.slack.com'):
            SlackAgent(
                agent_id=test_job.id,
                config={'webhook_url': 'https://discord.com/api/webhooks/123', 'message_template': 'hi'},
                user_id=test_job.user_id,
                db_session=db_session,
            )

    def test_message_template_required(self, test_job, db_session):
        with pytest.raises(ValueError, match='message_template is required'):
            SlackAgent(
                agent_id=test_job.id,
                config={'webhook_url': WEBHOOK_URL},
                user_id=test_job.user_id,
                db_session=db_session,
            )

    def test_invalid_jinja2_syntax(self, test_job, db_session):
        with pytest.raises(ValueError, match='Invalid message_template syntax'):
            SlackAgent(
                agent_id=test_job.id,
                config={'webhook_url': WEBHOOK_URL, 'message_template': '{{ unclosed'},
                user_id=test_job.user_id,
                db_session=db_session,
            )

    def test_valid_config(self, test_job, db_session):
        agent = SlackAgent(
            agent_id=test_job.id,
            config={'webhook_url': WEBHOOK_URL, 'message_template': 'Alert: {{ title }}'},
            user_id=test_job.user_id,
            db_session=db_session,
        )
        assert agent.webhook_url == WEBHOOK_URL


class TestSlackAgentSend:
    @patch('app.agents.types.slack_agent.requests.post')
    def test_sends_message(self, mock_post, test_job, db_session, sample_event):
        mock_post.return_value = Mock(status_code=200)
        agent = SlackAgent(
            agent_id=test_job.id,
            config={'webhook_url': WEBHOOK_URL, 'message_template': 'Alert: {{ title }}'},
            user_id=test_job.user_id,
            db_session=db_session,
        )
        result = agent.check([sample_event])
        assert result == []
        assert mock_post.called
        payload = mock_post.call_args.kwargs.get('json') or mock_post.call_args[1].get('json')
        assert payload['text'] == 'Alert: Alert fired'

    @patch('app.agents.types.slack_agent.requests.post')
    def test_optional_fields_sent(self, mock_post, test_job, db_session, sample_event):
        mock_post.return_value = Mock(status_code=200)
        agent = SlackAgent(
            agent_id=test_job.id,
            config={
                'webhook_url': WEBHOOK_URL,
                'message_template': 'hi',
                'username': 'Muninn Bot',
                'icon_emoji': ':bell:',
                'channel': '#alerts',
            },
            user_id=test_job.user_id,
            db_session=db_session,
        )
        agent.check([sample_event])
        payload = mock_post.call_args.kwargs.get('json') or mock_post.call_args[1].get('json')
        assert payload['username'] == 'Muninn Bot'
        assert payload['icon_emoji'] == ':bell:'
        assert payload['channel'] == '#alerts'

    @patch('app.agents.types.slack_agent.requests.post')
    def test_skips_empty_render(self, mock_post, test_job, db_session):
        event = Event(
            agent_id=test_job.id,
            agent_type='rss_agent',
            user_id=test_job.user_id,
            payload={},
            metadata={},
        )
        agent = SlackAgent(
            agent_id=test_job.id,
            config={'webhook_url': WEBHOOK_URL, 'message_template': '   '},
            user_id=test_job.user_id,
            db_session=db_session,
        )
        agent.check([event])
        assert not mock_post.called

    @patch('app.agents.types.slack_agent.time.sleep')
    @patch('app.agents.types.slack_agent.requests.post')
    def test_retries_on_429(self, mock_post, mock_sleep, test_job, db_session, sample_event):
        rate_limit_resp = Mock(status_code=429, headers={'Retry-After': '1'})
        ok_resp = Mock(status_code=200)
        mock_post.side_effect = [rate_limit_resp, ok_resp]
        agent = SlackAgent(
            agent_id=test_job.id,
            config={'webhook_url': WEBHOOK_URL, 'message_template': 'hi'},
            user_id=test_job.user_id,
            db_session=db_session,
        )
        agent.check([sample_event])
        assert mock_post.call_count == 2
        mock_sleep.assert_called_once_with(1)

    @patch('app.agents.types.slack_agent.requests.post')
    def test_handles_error_response(self, mock_post, test_job, db_session, sample_event):
        mock_post.return_value = Mock(status_code=400, text='invalid_payload')
        agent = SlackAgent(
            agent_id=test_job.id,
            config={'webhook_url': WEBHOOK_URL, 'message_template': 'hi'},
            user_id=test_job.user_id,
            db_session=db_session,
        )
        result = agent.check([sample_event])
        assert result == []  # no exception raised
