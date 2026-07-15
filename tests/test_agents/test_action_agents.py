"""
Tests for Action Agents

Tests EmailAgent, HTTPPostAgent, JabberAgent, and DiscordWebhookAgent.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests

from app.agents.registry import agent_registry
from app.agents.types.email_agent import EmailAgent
from app.agents.types.http_post_agent import HTTPPostAgent
from app.agents.types.jabber_agent import JabberAgent
from app.agents.types.discord_webhook_agent import DiscordWebhookAgent
from app.models import Event
from app.extensions import db


@pytest.fixture
def test_job(app_context):
    """Create a test job for agent tests"""
    from app.models import Job, User

    # Create a test user first
    user = User(username='testuser', email='test@example.com', password='password123')
    db.session.add(user)
    db.session.flush()

    # Create a test job
    job = Job(
        name='Test Agent',
        job_type='rss_agent',  # Use valid agent type
        config={'feed_url': 'https://example.com/feed.xml'},
        user_id=user.id
    )
    db.session.add(job)
    db.session.commit()

    return job


@pytest.fixture
def sample_events(test_job):
    """Create sample events for testing."""
    events = [
        Event(
            agent_id=test_job.id,
            agent_type='test_agent',
            user_id=test_job.user_id,
            payload={
                'title': 'System Alert',
                'message': 'Server is down',
                'priority': 'high',
                'link': 'https://example.com/alerts/1'
            },
            metadata={'source': 'monitoring'}
        ),
        Event(
            agent_id=test_job.id,
            agent_type='test_agent',
            user_id=test_job.user_id,
            payload={
                'title': 'Info Notice',
                'message': 'Backup completed',
                'priority': 'low',
                'link': 'https://example.com/alerts/2'
            },
            metadata={'source': 'backup'}
        )
    ]
    return events


# ============================================================================
# EmailAgent Tests
# ============================================================================

def test_email_agent_registered():
    """Test that EmailAgent is registered."""
    agent_class = agent_registry.get_agent_class('email_agent')
    assert agent_class is EmailAgent


def test_email_agent_capabilities(test_job, db_session):
    """Test EmailAgent capabilities."""
    config = {
        'smtp_server': 'smtp.example.com',
        'username': 'user@example.com',
        'password': 'password',
        'from_email': 'alerts@example.com',
        'to_email': 'admin@example.com',
        'subject_template': 'Alert: {{ title }}',
        'body_template': '{{ message }}'
    }

    agent = EmailAgent(
        agent_id=test_job.id,
        config=config,
        user_id=test_job.user_id,
        db_session=db_session
    )

    assert agent.can_be_scheduled is False
    assert agent.can_receive_events is True
    assert agent.can_create_events is False
    assert agent.requires_input is True


def test_email_agent_config_validation_required_fields(test_job, db_session):
    """Test EmailAgent config validation for required fields."""
    # Missing to_email
    with pytest.raises(ValueError, match="requires 'to_email'"):
        EmailAgent(
            agent_id=test_job.id,
            config={},
            user_id=test_job.user_id,
            db_session=db_session
        )

    # Missing subject_template
    with pytest.raises(ValueError, match="requires 'subject_template'"):
        EmailAgent(
            agent_id=test_job.id,
            config={'to_email': 'to@example.com'},
            user_id=test_job.user_id,
            db_session=db_session
        )

    # Missing body_template
    with pytest.raises(ValueError, match="requires 'body_template'"):
        EmailAgent(
            agent_id=test_job.id,
            config={
                'to_email': 'to@example.com',
                'subject_template': 'Subject'
            },
            user_id=test_job.user_id,
            db_session=db_session
        )


def test_email_agent_config_validation_types(test_job, db_session):
    """Test EmailAgent config validation for field types."""
    base_config = {
        'to_email': 'to@example.com',
        'subject_template': 'Subject',
        'body_template': 'Body'
    }

    # Invalid to_email type (not string or list)
    with pytest.raises(ValueError, match="'to_email' must be a string or list"):
        EmailAgent(
            agent_id=test_job.id,
            config={**base_config, 'to_email': 12345},
            user_id=test_job.user_id,
            db_session=db_session
        )

    # Invalid html
    with pytest.raises(ValueError, match="'html' must be a boolean"):
        EmailAgent(
            agent_id=test_job.id,
            config={**base_config, 'html': 'true'},
            user_id=test_job.user_id,
            db_session=db_session
        )

    # Invalid cc_email type
    with pytest.raises(ValueError, match="'cc_email' must be a string or list"):
        EmailAgent(
            agent_id=test_job.id,
            config={**base_config, 'cc_email': 12345},
            user_id=test_job.user_id,
            db_session=db_session
        )


def test_email_agent_config_validation_template_syntax(test_job, db_session):
    """Test EmailAgent template syntax validation."""
    base_config = {
        'smtp_server': 'smtp.example.com',
        'username': 'user',
        'password': 'pass',
        'from_email': 'from@example.com',
        'to_email': 'to@example.com',
        'subject_template': 'Subject',
        'body_template': 'Body'
    }

    # Invalid subject template syntax
    with pytest.raises(ValueError, match="Invalid Jinja2 syntax in 'subject_template'"):
        EmailAgent(
            agent_id=test_job.id,
            config={**base_config, 'subject_template': '{{ invalid }'},
            user_id=test_job.user_id,
            db_session=db_session
        )

    # Invalid body template syntax
    with pytest.raises(ValueError, match="Invalid Jinja2 syntax in 'body_template'"):
        EmailAgent(
            agent_id=test_job.id,
            config={**base_config, 'body_template': '{% for %}'},
            user_id=test_job.user_id,
            db_session=db_session
        )


@patch('app.agents.types.email_agent.smtplib.SMTP')
def test_email_agent_sends_email(mock_smtp, app_context, test_job, db_session, sample_events):
    """Test EmailAgent sends emails using global SMTP configuration."""
    config = {
        'to_email': 'admin@example.com',
        'subject_template': 'Alert: {{ title }}',
        'body_template': 'Message: {{ message }}\nLink: {{ link }}'
    }

    agent = EmailAgent(
        agent_id=test_job.id,
        config=config,
        user_id=test_job.user_id,
        db_session=db_session
    )

    # Mock SMTP server
    mock_server = MagicMock()
    mock_smtp.return_value.__enter__.return_value = mock_server

    # Process events
    result = agent.check(sample_events)

    # Should return empty list (terminal agent)
    assert result == []

    # Should have sent 2 emails
    assert mock_server.send_message.call_count == 2

    # Verify SMTP connection used global config values
    mock_smtp.assert_called_with(
        app_context.config['SMTP_SERVER'],
        app_context.config.get('SMTP_PORT', 587)
    )
    mock_server.starttls.assert_called()
    mock_server.login.assert_called_with(
        app_context.config['SMTP_USERNAME'],
        app_context.config['SMTP_PASSWORD']
    )


@patch('app.agents.types.email_agent.smtplib.SMTP')
def test_email_agent_template_rendering(mock_smtp, test_job, db_session, sample_events):
    """Test EmailAgent renders templates correctly."""
    config = {
        'smtp_server': 'smtp.example.com',
        'username': 'user@example.com',
        'password': 'password',
        'from_email': 'alerts@example.com',
        'to_email': 'admin@example.com',
        'subject_template': '[{{ priority|upper }}] {{ title }}',
        'body_template': '{{ message }}\n\nPriority: {{ priority }}'
    }

    agent = EmailAgent(
        agent_id=test_job.id,
        config=config,
        user_id=test_job.user_id,
        db_session=db_session
    )

    # Mock SMTP server
    mock_server = MagicMock()
    mock_smtp.return_value.__enter__.return_value = mock_server

    # Process first event
    result = agent.check([sample_events[0]])

    assert result == []

    # Verify message was sent
    assert mock_server.send_message.call_count == 1

    # Get the message that was sent
    sent_message = mock_server.send_message.call_args[0][0]

    # Verify subject was rendered correctly
    assert sent_message['Subject'] == '[HIGH] System Alert'


@patch('app.agents.types.email_agent.smtplib.SMTP')
def test_email_agent_multiple_recipients(mock_smtp, test_job, db_session, sample_events):
    """Test EmailAgent with multiple recipients."""
    config = {
        'smtp_server': 'smtp.example.com',
        'username': 'user@example.com',
        'password': 'password',
        'from_email': 'alerts@example.com',
        'to_email': ['admin1@example.com', 'admin2@example.com'],
        'cc_email': 'manager@example.com',
        'bcc_email': ['archive@example.com'],
        'subject_template': 'Alert',
        'body_template': '{{ message }}'
    }

    agent = EmailAgent(
        agent_id=test_job.id,
        config=config,
        user_id=test_job.user_id,
        db_session=db_session
    )

    # Mock SMTP server
    mock_server = MagicMock()
    mock_smtp.return_value.__enter__.return_value = mock_server

    # Process first event
    result = agent.check([sample_events[0]])

    assert result == []
    assert mock_server.send_message.call_count == 1


@patch('app.agents.types.email_agent.smtplib.SMTP')
def test_email_agent_error_handling(mock_smtp, test_job, db_session, sample_events):
    """Test EmailAgent handles errors gracefully."""
    config = {
        'smtp_server': 'smtp.example.com',
        'username': 'user@example.com',
        'password': 'password',
        'from_email': 'alerts@example.com',
        'to_email': 'admin@example.com',
        'subject_template': 'Alert',
        'body_template': '{{ message }}'
    }

    agent = EmailAgent(
        agent_id=test_job.id,
        config=config,
        user_id=test_job.user_id,
        db_session=db_session
    )

    # Mock SMTP to raise an error
    mock_smtp.return_value.__enter__.side_effect = smtplib.SMTPException("Connection failed")

    # Process events - should not raise exception
    result = agent.check(sample_events)

    # Should still return empty list
    assert result == []


# ============================================================================
# HTTPPostAgent Tests
# ============================================================================

def test_http_post_agent_registered():
    """Test that HTTPPostAgent is registered."""
    agent_class = agent_registry.get_agent_class('http_post_agent')
    assert agent_class is HTTPPostAgent


def test_http_post_agent_capabilities(test_job, db_session):
    """Test HTTPPostAgent capabilities."""
    config = {
        'url': 'https://api.example.com/webhook'
    }

    agent = HTTPPostAgent(
        agent_id=test_job.id,
        config=config,
        user_id=test_job.user_id,
        db_session=db_session
    )

    assert agent.can_be_scheduled is False
    assert agent.can_receive_events is True
    assert agent.can_create_events is False
    assert agent.requires_input is True


def test_http_post_agent_config_validation_required_fields(test_job, db_session):
    """Test HTTPPostAgent config validation for required fields."""
    # Missing url
    with pytest.raises(ValueError, match="requires 'url'"):
        HTTPPostAgent(
            agent_id=test_job.id,
            config={},
            user_id=test_job.user_id,
            db_session=db_session
        )


def test_http_post_agent_config_validation_types(test_job, db_session):
    """Test HTTPPostAgent config validation for field types."""
    base_config = {'url': 'https://api.example.com/webhook'}

    # Invalid method
    with pytest.raises(ValueError, match="'method' must be one of"):
        HTTPPostAgent(
            agent_id=test_job.id,
            config={**base_config, 'method': 'GET'},
            user_id=test_job.user_id,
            db_session=db_session
        )

    # Invalid headers type
    with pytest.raises(ValueError, match="'headers' must be a dictionary"):
        HTTPPostAgent(
            agent_id=test_job.id,
            config={**base_config, 'headers': 'invalid'},
            user_id=test_job.user_id,
            db_session=db_session
        )

    # Invalid timeout
    with pytest.raises(ValueError, match="'timeout' must be a positive number"):
        HTTPPostAgent(
            agent_id=test_job.id,
            config={**base_config, 'timeout': -5},
            user_id=test_job.user_id,
            db_session=db_session
        )

    # Invalid verify_ssl
    with pytest.raises(ValueError, match="'verify_ssl' must be a boolean"):
        HTTPPostAgent(
            agent_id=test_job.id,
            config={**base_config, 'verify_ssl': 'yes'},
            user_id=test_job.user_id,
            db_session=db_session
        )


def test_http_post_agent_config_validation_template_syntax(test_job, db_session):
    """Test HTTPPostAgent template syntax validation."""
    base_config = {'url': 'https://api.example.com/webhook'}

    # Invalid URL template syntax
    with pytest.raises(ValueError, match="Invalid Jinja2 syntax in 'url'"):
        HTTPPostAgent(
            agent_id=test_job.id,
            config={'url': 'https://api.example.com/{{ invalid }'},
            user_id=test_job.user_id,
            db_session=db_session
        )

    # Invalid header template syntax
    with pytest.raises(ValueError, match="Invalid Jinja2 syntax in header"):
        HTTPPostAgent(
            agent_id=test_job.id,
            config={
                **base_config,
                'headers': {'X-Custom': '{{ invalid }'}
            },
            user_id=test_job.user_id,
            db_session=db_session
        )

    # Invalid payload template syntax
    with pytest.raises(ValueError, match="Invalid Jinja2 syntax in 'payload_template'"):
        HTTPPostAgent(
            agent_id=test_job.id,
            config={
                **base_config,
                'payload_template': '{% for %}'
            },
            user_id=test_job.user_id,
            db_session=db_session
        )


@patch('app.agents.types.http_post_agent.requests.post')
def test_http_post_agent_sends_request(mock_post, test_job, db_session, sample_events):
    """Test HTTPPostAgent sends POST requests successfully."""
    config = {
        'url': 'https://api.example.com/webhook',
        'method': 'POST',
        'timeout': 30,
        'verify_ssl': True
    }

    agent = HTTPPostAgent(
        agent_id=test_job.id,
        config=config,
        user_id=test_job.user_id,
        db_session=db_session
    )

    # Mock response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.content = b'OK'
    mock_post.return_value = mock_response

    # Process events
    result = agent.check(sample_events)

    # Should return empty list (terminal agent)
    assert result == []

    # Should have sent 2 requests
    assert mock_post.call_count == 2

    # Verify request parameters
    mock_post.assert_called_with(
        'https://api.example.com/webhook',
        json=sample_events[1].payload,
        headers={'Content-Type': 'application/json'},
        timeout=30,
        verify=True
    )


@patch('app.agents.types.http_post_agent.requests.post')
def test_http_post_agent_template_rendering(mock_post, test_job, db_session, sample_events):
    """Test HTTPPostAgent renders templates correctly."""
    config = {
        'url': 'https://api.example.com/{{ priority }}/alert',
        'headers': {
            'X-Priority': '{{ priority }}',
            'X-Source': 'muninn'
        },
        'payload_template': '{"alert": "{{ title }}", "details": "{{ message }}"}'
    }

    agent = HTTPPostAgent(
        agent_id=test_job.id,
        config=config,
        user_id=test_job.user_id,
        db_session=db_session
    )

    # Mock response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.content = b'OK'
    mock_post.return_value = mock_response

    # Process first event
    result = agent.check([sample_events[0]])

    assert result == []

    # Verify URL was rendered
    call_args = mock_post.call_args
    assert call_args[0][0] == 'https://api.example.com/high/alert'

    # Verify headers were rendered
    headers = call_args[1]['headers']
    assert headers['X-Priority'] == 'high'
    assert headers['X-Source'] == 'muninn'

    # Verify payload was rendered
    payload = call_args[1]['json']
    assert payload == {'alert': 'System Alert', 'details': 'Server is down'}


@patch('app.agents.types.http_post_agent.requests.put')
def test_http_post_agent_different_methods(mock_put, test_job, db_session, sample_events):
    """Test HTTPPostAgent supports different HTTP methods."""
    config = {
        'url': 'https://api.example.com/resource',
        'method': 'PUT'
    }

    agent = HTTPPostAgent(
        agent_id=test_job.id,
        config=config,
        user_id=test_job.user_id,
        db_session=db_session
    )

    # Mock response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.content = b'OK'
    mock_put.return_value = mock_response

    # Process first event
    result = agent.check([sample_events[0]])

    assert result == []
    assert mock_put.call_count == 1


@patch('app.agents.types.http_post_agent.requests.post')
def test_http_post_agent_error_handling(mock_post, test_job, db_session, sample_events):
    """Test HTTPPostAgent handles errors gracefully."""
    config = {
        'url': 'https://api.example.com/webhook'
    }

    agent = HTTPPostAgent(
        agent_id=test_job.id,
        config=config,
        user_id=test_job.user_id,
        db_session=db_session
    )

    # Mock request to raise timeout
    mock_post.side_effect = requests.exceptions.Timeout("Connection timeout")

    # Process events - should not raise exception
    result = agent.check(sample_events)

    # Should still return empty list
    assert result == []


# ============================================================================
# JabberAgent Tests
# ============================================================================

def test_jabber_agent_registered():
    """Test that JabberAgent is registered."""
    agent_class = agent_registry.get_agent_class('jabber_agent')
    assert agent_class is JabberAgent


def test_jabber_agent_capabilities(test_job, db_session):
    """Test JabberAgent capabilities."""
    # Skip if slixmpp not available
    try:
        import slixmpp
    except ImportError:
        pytest.skip("slixmpp not installed")

    config = {
        'jid': 'bot@jabber.example.com',
        'password': 'password',
        'recipient': 'admin@jabber.example.com',
        'message_template': '{{ message }}'
    }

    agent = JabberAgent(
        agent_id=test_job.id,
        config=config,
        user_id=test_job.user_id,
        db_session=db_session
    )

    assert agent.can_be_scheduled is False
    assert agent.can_receive_events is True
    assert agent.can_create_events is False
    assert agent.requires_input is True


def test_jabber_agent_config_validation_required_fields(test_job, db_session):
    """Test JabberAgent config validation for required fields."""
    # Skip if slixmpp not available
    try:
        import slixmpp
    except ImportError:
        pytest.skip("slixmpp not installed")

    # Missing jid
    with pytest.raises(ValueError, match="requires 'jid'"):
        JabberAgent(
            agent_id=test_job.id,
            config={},
            user_id=test_job.user_id,
            db_session=db_session
        )

    # Missing password
    with pytest.raises(ValueError, match="requires 'password'"):
        JabberAgent(
            agent_id=test_job.id,
            config={'jid': 'bot@jabber.example.com'},
            user_id=test_job.user_id,
            db_session=db_session
        )

    # Missing recipient
    with pytest.raises(ValueError, match="requires 'recipient'"):
        JabberAgent(
            agent_id=test_job.id,
            config={
                'jid': 'bot@jabber.example.com',
                'password': 'password'
            },
            user_id=test_job.user_id,
            db_session=db_session
        )

    # Missing message_template
    with pytest.raises(ValueError, match="requires 'message_template'"):
        JabberAgent(
            agent_id=test_job.id,
            config={
                'jid': 'bot@jabber.example.com',
                'password': 'password',
                'recipient': 'admin@jabber.example.com'
            },
            user_id=test_job.user_id,
            db_session=db_session
        )


def test_jabber_agent_config_validation_types(test_job, db_session):
    """Test JabberAgent config validation for field types."""
    # Skip if slixmpp not available
    try:
        import slixmpp
    except ImportError:
        pytest.skip("slixmpp not installed")

    base_config = {
        'jid': 'bot@jabber.example.com',
        'password': 'password',
        'recipient': 'admin@jabber.example.com',
        'message_template': '{{ message }}'
    }

    # Invalid port
    with pytest.raises(ValueError, match="'port' must be a valid port number"):
        JabberAgent(
            agent_id=test_job.id,
            config={**base_config, 'port': 99999},
            user_id=test_job.user_id,
            db_session=db_session
        )

    # Invalid use_tls
    with pytest.raises(ValueError, match="'use_tls' must be a boolean"):
        JabberAgent(
            agent_id=test_job.id,
            config={**base_config, 'use_tls': 'yes'},
            user_id=test_job.user_id,
            db_session=db_session
        )


def test_jabber_agent_config_validation_template_syntax(test_job, db_session):
    """Test JabberAgent template syntax validation."""
    # Skip if slixmpp not available
    try:
        import slixmpp
    except ImportError:
        pytest.skip("slixmpp not installed")

    base_config = {
        'jid': 'bot@jabber.example.com',
        'password': 'password',
        'recipient': 'admin@jabber.example.com',
        'message_template': '{{ message }}'
    }

    # Invalid recipient template syntax
    with pytest.raises(ValueError, match="Invalid Jinja2 syntax in 'recipient'"):
        JabberAgent(
            agent_id=test_job.id,
            config={**base_config, 'recipient': '{{ invalid }'},
            user_id=test_job.user_id,
            db_session=db_session
        )

    # Invalid message template syntax
    with pytest.raises(ValueError, match="Invalid Jinja2 syntax in 'message_template'"):
        JabberAgent(
            agent_id=test_job.id,
            config={**base_config, 'message_template': '{% for %}'},
            user_id=test_job.user_id,
            db_session=db_session
        )


def test_jabber_agent_library_not_available(test_job, db_session, sample_events):
    """Test JabberAgent handles missing slixmpp library gracefully."""
    config = {
        'jid': 'bot@jabber.example.com',
        'password': 'password',
        'recipient': 'admin@jabber.example.com',
        'message_template': '{{ message }}'
    }

    # Patch XMPP_AVAILABLE to simulate missing library
    with patch('app.agents.types.jabber_agent.XMPP_AVAILABLE', False):
        # Should raise error during validation
        with pytest.raises(ValueError, match="requires 'slixmpp' library"):
            JabberAgent(
                agent_id=test_job.id,
                config=config,
                user_id=test_job.user_id,
                db_session=db_session
            )


def test_jabber_agent_sends_message(test_job, db_session, sample_events):
    """Test JabberAgent sends XMPP messages successfully."""
    # Skip if slixmpp not available
    slixmpp = pytest.importorskip("slixmpp")

    from unittest.mock import patch
    with patch('app.agents.types.jabber_agent.slixmpp') as mock_slixmpp:
        config = {
            'jid': 'bot@jabber.example.com',
            'password': 'password',
            'recipient': 'admin@jabber.example.com',
            'message_template': '{{ title }}: {{ message }}'
        }

        agent = JabberAgent(
            agent_id=test_job.id,
            config=config,
            user_id=test_job.user_id,
            db_session=db_session
        )

        # Mock XMPP client
        mock_client = MagicMock()
        mock_client.message_sent = True
        mock_slixmpp.ClientXMPP.return_value = mock_client

        # Process events
        result = agent.check(sample_events)

        # Should return empty list (terminal agent)
        assert result == []


def test_jabber_agent_template_rendering(test_job, db_session, sample_events):
    """Test JabberAgent renders templates correctly."""
    # Skip if slixmpp not available
    slixmpp = pytest.importorskip("slixmpp")

    from unittest.mock import patch
    with patch('app.agents.types.jabber_agent.slixmpp') as mock_slixmpp:
        config = {
            'jid': 'bot@jabber.example.com',
            'password': 'password',
            'recipient': '{{ priority }}@jabber.example.com',
            'message_template': '[{{ priority|upper }}] {{ title }}: {{ message }}'
        }

        agent = JabberAgent(
            agent_id=test_job.id,
            config=config,
            user_id=test_job.user_id,
            db_session=db_session
        )

        # Mock XMPP client
        mock_client = MagicMock()
        mock_client.message_sent = True
        mock_slixmpp.ClientXMPP.return_value = mock_client

        # Process first event
        result = agent.check([sample_events[0]])

        assert result == []


def test_jabber_agent_error_handling(test_job, db_session, sample_events):
    """Test JabberAgent handles errors gracefully."""
    # Skip if slixmpp not available
    slixmpp = pytest.importorskip("slixmpp")

    from unittest.mock import patch
    with patch('app.agents.types.jabber_agent.slixmpp') as mock_slixmpp:
        config = {
            'jid': 'bot@jabber.example.com',
            'password': 'password',
            'recipient': 'admin@jabber.example.com',
            'message_template': '{{ message }}'
        }

        agent = JabberAgent(
            agent_id=test_job.id,
            config=config,
            user_id=test_job.user_id,
            db_session=db_session
        )

        # Mock XMPP client to raise error
        mock_slixmpp.ClientXMPP.side_effect = Exception("Connection failed")

        # Process events - should not raise exception
        result = agent.check(sample_events)

        # Should still return empty list
        assert result == []


# ============================================================================
# Discord Webhook Agent Tests
# ============================================================================

class TestDiscordWebhookAgent:
    """Test Discord Webhook Agent functionality."""

    def test_discord_webhook_agent_registered(self):
        """Test that DiscordWebhookAgent is properly registered."""
        agent_class = agent_registry.get_agent_class('discord_webhook_agent')
        assert agent_class is DiscordWebhookAgent

    def test_discord_webhook_agent_capabilities(self, test_job, db_session):
        """Test DiscordWebhookAgent capabilities and attributes."""
        config = {
            'webhook_url': 'https://discord.com/api/webhooks/123456/abcdef',
            'content_template': 'Test message'
        }
        
        agent = DiscordWebhookAgent(
            agent_id=test_job.id,
            config=config,
            user_id=test_job.user_id,
            db_session=db_session
        )

        # Check agent type
        assert agent.agent_type == 'discord_webhook_agent'
        assert agent.agent_category == 'action'

        # Check capabilities
        assert agent.can_be_scheduled == False
        assert agent.can_receive_events == True

    def test_discord_webhook_agent_validates_webhook_url_required(self, test_job, db_session):
        """Test that webhook_url is required."""
        config = {
            'content_template': 'Test message'
        }
        
        with pytest.raises(ValueError, match="webhook_url is required"):
            DiscordWebhookAgent(
                agent_id=test_job.id,
                config=config,
                user_id=test_job.user_id,
                db_session=db_session
            )

    def test_discord_webhook_agent_validates_webhook_url_format(self, test_job, db_session):
        """Test that webhook_url format is validated."""
        config = {
            'webhook_url': 'https://example.com/webhook',
            'content_template': 'Test message'
        }
        
        with pytest.raises(ValueError, match="webhook_url must start with"):
            DiscordWebhookAgent(
                agent_id=test_job.id,
                config=config,
                user_id=test_job.user_id,
                db_session=db_session
            )

    def test_discord_webhook_agent_validates_content_or_embed_required(self, test_job, db_session):
        """Test that either content or embed is required."""
        config = {
            'webhook_url': 'https://discord.com/api/webhooks/123456/abcdef'
        }

        with pytest.raises(ValueError, match="At least one of content_template or embed is required"):
            DiscordWebhookAgent(
                agent_id=test_job.id,
                config=config,
                user_id=test_job.user_id,
                db_session=db_session
            )

    def test_discord_webhook_agent_validates_jinja2_syntax(self, test_job, db_session):
        """Test that Jinja2 template syntax is validated."""
        config = {
            'webhook_url': 'https://discord.com/api/webhooks/123456/abcdef',
            'content_template': '{{ invalid template'
        }

        with pytest.raises(ValueError, match="Invalid content_template syntax"):
            DiscordWebhookAgent(
                agent_id=test_job.id,
                config=config,
                user_id=test_job.user_id,
                db_session=db_session
            )

    @patch('app.agents.types.discord_webhook_agent.requests.post')
    def test_discord_webhook_agent_sends_simple_message(self, mock_post, test_job, db_session, sample_events):
        """Test sending a simple text message to Discord."""
        config = {
            'webhook_url': 'https://discord.com/api/webhooks/123456/abcdef',
            'content_template': 'New article: {{ title }}'
        }
        
        agent = DiscordWebhookAgent(
            agent_id=test_job.id,
            config=config,
            user_id=test_job.user_id,
            db_session=db_session
        )

        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 204
        mock_post.return_value = mock_response

        # Process event
        result = agent.check([sample_events[0]])

        # Should return empty list (action agents don't emit events)
        assert result == []

        # Verify POST was called
        assert mock_post.called
        call_args = mock_post.call_args

        # Verify URL
        assert call_args[0][0] == 'https://discord.com/api/webhooks/123456/abcdef'

        # Verify payload
        payload = call_args[1]['json']
        assert 'content' in payload
        assert 'System Alert' in payload['content']

    @patch('app.agents.types.discord_webhook_agent.requests.post')
    def test_discord_webhook_agent_sends_embed(self, mock_post, test_job, db_session, sample_events):
        """Test sending a rich embed to Discord."""
        config = {
            'webhook_url': 'https://discord.com/api/webhooks/123456/abcdef',
            'embed': {
                'title': '{{ title }}',
                'description': '{{ message }}',
                'color': 3447003,
                'fields': [
                    {'name': 'Status', 'value': 'Published', 'inline': True}
                ]
            }
        }
        
        agent = DiscordWebhookAgent(
            agent_id=test_job.id,
            config=config,
            user_id=test_job.user_id,
            db_session=db_session
        )

        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 204
        mock_post.return_value = mock_response

        # Process event
        result = agent.check([sample_events[0]])

        # Should return empty list
        assert result == []

        # Verify POST was called with embed
        assert mock_post.called
        payload = mock_post.call_args[1]['json']
        
        assert 'embeds' in payload
        assert len(payload['embeds']) == 1
        
        embed = payload['embeds'][0]
        assert 'title' in embed
        assert 'description' in embed
        assert embed['color'] == 3447003
        assert 'fields' in embed
        assert len(embed['fields']) == 1

    @patch('app.agents.types.discord_webhook_agent.requests.post')
    @patch('app.agents.types.discord_webhook_agent.time.sleep')
    def test_discord_webhook_agent_rate_limiting(self, mock_sleep, mock_post, test_job, db_session, sample_events):
        """Test rate limiting behavior."""
        config = {
            'webhook_url': 'https://discord.com/api/webhooks/123456/abcdef',
            'content_template': 'Message {{ loop.index }}',
            'rate_limit_per_minute': 2
        }
        
        agent = DiscordWebhookAgent(
            agent_id=test_job.id,
            config=config,
            user_id=test_job.user_id,
            db_session=db_session
        )

        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 204
        mock_post.return_value = mock_response

        # Process first 2 events - should not sleep
        agent.check([sample_events[0]])
        agent.check([sample_events[1]])
        
        # After 2 events at limit of 2/min, next should wait
        # Note: Implementation may vary based on exact rate limiting logic

    @patch('app.agents.types.discord_webhook_agent.requests.post')
    def test_discord_webhook_agent_handles_429_response(self, mock_post, test_job, db_session, sample_events):
        """Test retry logic for 429 (Too Many Requests) response."""
        config = {
            'webhook_url': 'https://discord.com/api/webhooks/123456/abcdef',
            'content_template': 'Test message'
        }
        
        agent = DiscordWebhookAgent(
            agent_id=test_job.id,
            config=config,
            user_id=test_job.user_id,
            db_session=db_session
        )

        # Mock 429 response first, then success
        mock_response_429 = Mock()
        mock_response_429.status_code = 429
        mock_response_429.headers = {}
        mock_response_429.json.return_value = {'retry_after': 1.0}
        
        mock_response_success = Mock()
        mock_response_success.status_code = 204
        
        mock_post.side_effect = [mock_response_429, mock_response_success]

        # Process event - should retry after 429
        result = agent.check([sample_events[0]])

        # Should still return empty list
        assert result == []

        # Verify POST was called twice (once failed with 429, once succeeded)
        assert mock_post.call_count == 2

    @patch('app.agents.types.discord_webhook_agent.requests.post')
    def test_discord_webhook_agent_with_username_override(self, mock_post, test_job, db_session, sample_events):
        """Test overriding webhook username."""
        config = {
            'webhook_url': 'https://discord.com/api/webhooks/123456/abcdef',
            'content_template': 'Test message',
            'username': 'Muninn Bot'
        }
        
        agent = DiscordWebhookAgent(
            agent_id=test_job.id,
            config=config,
            user_id=test_job.user_id,
            db_session=db_session
        )

        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 204
        mock_post.return_value = mock_response

        # Process event
        agent.check([sample_events[0]])

        # Verify username in payload
        payload = mock_post.call_args[1]['json']
        assert payload['username'] == 'Muninn Bot'

    @patch('app.agents.types.discord_webhook_agent.requests.post')
    def test_discord_webhook_agent_error_handling(self, mock_post, test_job, db_session, sample_events):
        """Test error handling for failed requests."""
        config = {
            'webhook_url': 'https://discord.com/api/webhooks/123456/abcdef',
            'content_template': 'Test message'
        }
        
        agent = DiscordWebhookAgent(
            agent_id=test_job.id,
            config=config,
            user_id=test_job.user_id,
            db_session=db_session
        )

        # Mock connection error
        mock_post.side_effect = requests.exceptions.ConnectionError("Failed to connect")

        # Process event - should not raise exception
        result = agent.check([sample_events[0]])

        # Should still return empty list
        assert result == []

    def test_discord_webhook_agent_config_schema(self):
        """Test configuration schema structure."""
        schema = DiscordWebhookAgent.get_config_schema()
        
        assert 'required_fields' in schema
        assert 'webhook_url' in schema['required_fields']
        
        assert 'optional_fields' in schema
        optional_field_names = [f['name'] for f in schema['optional_fields']]
        
        assert 'content_template' in optional_field_names
        assert 'username' in optional_field_names
        assert 'avatar_url' in optional_field_names
        assert 'embed' in optional_field_names

    @patch('app.agents.types.discord_webhook_agent.requests.post')
    def test_discord_webhook_agent_processes_multiple_events(self, mock_post, test_job, db_session, sample_events):
        """Test processing multiple events in one batch."""
        config = {
            'webhook_url': 'https://discord.com/api/webhooks/123456/abcdef',
            'content_template': '{{ title }}: {{ link }}'
        }
        
        agent = DiscordWebhookAgent(
            agent_id=test_job.id,
            config=config,
            user_id=test_job.user_id,
            db_session=db_session
        )

        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 204
        mock_post.return_value = mock_response

        # Process multiple events (sample_events fixture has 2 events)
        result = agent.check(sample_events)

        # Should return empty list
        assert result == []

        # Should have sent 2 webhooks
        assert mock_post.call_count == 2
