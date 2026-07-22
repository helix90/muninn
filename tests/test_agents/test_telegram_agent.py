"""Tests for TelegramAgent."""

import pytest
from unittest.mock import patch, Mock

from app.agents.types.telegram_agent import TelegramAgent
from app.agents.registry import agent_registry
from app.models import Event
from app.extensions import db


@pytest.fixture
def test_user(db_session):
    from app.models import User
    user = User(username='teletest', email='teletest@example.com', password='password123')
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def test_job(db_session, test_user):
    from app.models import Job
    job = Job(
        name='Telegram Test Agent',
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
        payload={'title': 'Breaking news', 'body': 'Something happened'},
        metadata={},
    )


BASE_CONFIG = {
    'bot_token': '123456:ABCdef',
    'chat_id': '-100123456',
    'message_template': '{{ title }}',
}


class TestTelegramAgentRegistration:
    def test_registered(self):
        assert agent_registry.get_agent_class('telegram_agent') is TelegramAgent

    def test_capabilities(self, test_job, db_session):
        agent = TelegramAgent(
            agent_id=test_job.id,
            config=BASE_CONFIG,
            user_id=test_job.user_id,
            db_session=db_session,
        )
        assert agent.can_receive_events is True
        assert agent.can_be_scheduled is False
        assert agent.can_create_events is False


class TestTelegramAgentValidation:
    def test_bot_token_required(self, test_job, db_session):
        with pytest.raises(ValueError, match='bot_token is required'):
            TelegramAgent(
                agent_id=test_job.id,
                config={'chat_id': '123', 'message_template': 'hi'},
                user_id=test_job.user_id,
                db_session=db_session,
            )

    def test_chat_id_required(self, test_job, db_session):
        with pytest.raises(ValueError, match='chat_id is required'):
            TelegramAgent(
                agent_id=test_job.id,
                config={'bot_token': 'abc', 'message_template': 'hi'},
                user_id=test_job.user_id,
                db_session=db_session,
            )

    def test_message_template_required(self, test_job, db_session):
        with pytest.raises(ValueError, match='message_template is required'):
            TelegramAgent(
                agent_id=test_job.id,
                config={'bot_token': 'abc', 'chat_id': '123'},
                user_id=test_job.user_id,
                db_session=db_session,
            )

    def test_invalid_parse_mode(self, test_job, db_session):
        with pytest.raises(ValueError, match='parse_mode must be one of'):
            TelegramAgent(
                agent_id=test_job.id,
                config={**BASE_CONFIG, 'parse_mode': 'BBCode'},
                user_id=test_job.user_id,
                db_session=db_session,
            )

    def test_valid_parse_modes(self, test_job, db_session):
        for mode in ('Markdown', 'MarkdownV2', 'HTML'):
            agent = TelegramAgent(
                agent_id=test_job.id,
                config={**BASE_CONFIG, 'parse_mode': mode},
                user_id=test_job.user_id,
                db_session=db_session,
            )
            assert agent.parse_mode == mode

    def test_invalid_jinja2_syntax(self, test_job, db_session):
        with pytest.raises(ValueError, match='Invalid message_template syntax'):
            TelegramAgent(
                agent_id=test_job.id,
                config={**BASE_CONFIG, 'message_template': '{{ bad'},
                user_id=test_job.user_id,
                db_session=db_session,
            )


class TestTelegramAgentSend:
    @patch('app.agents.types.telegram_agent.requests.post')
    def test_sends_message(self, mock_post, test_job, db_session, sample_event):
        mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={'ok': True, 'result': {'message_id': 1}}),
        )
        agent = TelegramAgent(
            agent_id=test_job.id,
            config=BASE_CONFIG,
            user_id=test_job.user_id,
            db_session=db_session,
        )
        result = agent.check([sample_event])
        assert result == []
        assert mock_post.called
        payload = mock_post.call_args.kwargs.get('json') or mock_post.call_args[1].get('json')
        assert payload['chat_id'] == '-100123456'
        assert payload['text'] == 'Breaking news'

    @patch('app.agents.types.telegram_agent.requests.post')
    def test_optional_flags(self, mock_post, test_job, db_session, sample_event):
        mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={'ok': True}),
        )
        agent = TelegramAgent(
            agent_id=test_job.id,
            config={
                **BASE_CONFIG,
                'parse_mode': 'Markdown',
                'disable_web_page_preview': True,
                'disable_notification': True,
            },
            user_id=test_job.user_id,
            db_session=db_session,
        )
        agent.check([sample_event])
        payload = mock_post.call_args.kwargs.get('json') or mock_post.call_args[1].get('json')
        assert payload['parse_mode'] == 'Markdown'
        assert payload['disable_web_page_preview'] is True
        assert payload['disable_notification'] is True

    @patch('app.agents.types.telegram_agent.requests.post')
    def test_api_error_logged(self, mock_post, test_job, db_session, sample_event):
        mock_post.return_value = Mock(
            status_code=400,
            json=Mock(return_value={'ok': False, 'description': 'Bad Request: chat not found'}),
        )
        agent = TelegramAgent(
            agent_id=test_job.id,
            config=BASE_CONFIG,
            user_id=test_job.user_id,
            db_session=db_session,
        )
        result = agent.check([sample_event])
        assert result == []  # no exception

    @patch('app.agents.types.telegram_agent.requests.post')
    def test_skips_empty_render(self, mock_post, test_job, db_session):
        event = Event(
            agent_id=test_job.id,
            agent_type='rss_agent',
            user_id=test_job.user_id,
            payload={},
            metadata={},
        )
        agent = TelegramAgent(
            agent_id=test_job.id,
            config={**BASE_CONFIG, 'message_template': '   '},
            user_id=test_job.user_id,
            db_session=db_session,
        )
        agent.check([event])
        assert not mock_post.called
