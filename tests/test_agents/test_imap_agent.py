"""
Tests for IMAP Agent
"""

import pytest
import imaplib
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from app.extensions import db
from app.agents.types.imap_agent import IMAPAgent
from app.agents.registry import agent_registry


@pytest.fixture
def test_job(app, test_user):
    """Create a test job for agent tests"""
    from app.models import Job

    with app.app_context():
        job = Job(
            name='Test IMAP Agent',
            job_type='imap_agent',
            config={
                'host': 'imap.gmail.com',
                'username': 'test@gmail.com',
                'password': 'test_password'
            },
            user_id=test_user.id
        )
        db.session.add(job)
        db.session.commit()

        yield job


class TestIMAPAgentRegistration:
    """Test IMAP agent registration and capabilities"""

    def test_imap_agent_registered(self):
        """Test that IMAP agent is registered in the agent registry"""
        assert agent_registry.is_registered('imap_agent')
        agent_class = agent_registry.get_agent_class('imap_agent')
        assert agent_class == IMAPAgent

    def test_imap_agent_capabilities(self):
        """Test agent capabilities"""
        assert IMAPAgent.can_be_scheduled == True
        assert IMAPAgent.can_receive_events == False
        assert IMAPAgent.can_create_events == True
        assert IMAPAgent.agent_type == 'imap_agent'
        assert IMAPAgent.agent_category == 'source'


class TestIMAPAgentConfig:
    """Test IMAP agent configuration validation"""

    def test_valid_minimal_config(self, test_job):
        """Test agent creation with minimal valid config"""
        config = {
            'host': 'imap.gmail.com',
            'username': 'test@gmail.com',
            'password': 'test_password'
        }
        agent = IMAPAgent(agent_id=test_job.id, config=config, user_id=test_job.user_id, db_session=db.session)
        assert agent.host == 'imap.gmail.com'
        assert agent.username == 'test@gmail.com'
        assert agent.password == 'test_password'
        assert agent.port == 993  # Default SSL port
        assert agent.use_ssl == True

    def test_valid_full_config(self, test_job):
        """Test agent creation with full configuration"""
        config = {
            'host': 'imap.example.com',
            'username': 'user@example.com',
            'password': 'password123',
            'port': 143,
            'use_ssl': False,
            'search_criteria': 'ALL',
            'max_emails': 100,
            'mark_as_read': True,
            'lookback_days': 14
        }
        agent = IMAPAgent(agent_id=test_job.id, config=config, user_id=test_job.user_id, db_session=db.session)
        assert agent.host == 'imap.example.com'
        assert agent.port == 143
        assert agent.use_ssl == False
        assert agent.search_criteria == 'ALL'
        assert agent.max_emails == 100
        assert agent.mark_as_read == True
        assert agent.lookback_days == 14

    def test_missing_host(self):
        """Test validation error when host is missing"""
        config = {
            'username': 'test@gmail.com',
            'password': 'test_password'
        }
        with pytest.raises(ValueError, match='host is required'):
            IMAPAgent(agent_id=1, config=config, user_id=1, db_session=None)

    def test_missing_username(self):
        """Test validation error when username is missing"""
        config = {
            'host': 'imap.gmail.com',
            'password': 'test_password'
        }
        with pytest.raises(ValueError, match='username is required'):
            IMAPAgent(agent_id=1, config=config, user_id=1, db_session=None)

    def test_missing_password(self):
        """Test validation error when password is missing"""
        config = {
            'host': 'imap.gmail.com',
            'username': 'test@gmail.com'
        }
        with pytest.raises(ValueError, match='password is required'):
            IMAPAgent(agent_id=1, config=config, user_id=1, db_session=None)

    def test_invalid_port(self):
        """Test validation error when port is invalid"""
        config = {
            'host': 'imap.gmail.com',
            'username': 'test@gmail.com',
            'password': 'test_password',
            'port': 99999
        }
        with pytest.raises(ValueError, match='port must be between 1 and 65535'):
            IMAPAgent(agent_id=1, config=config, user_id=1, db_session=None)

    def test_invalid_use_ssl(self):
        """Test validation error when use_ssl is not boolean"""
        config = {
            'host': 'imap.gmail.com',
            'username': 'test@gmail.com',
            'password': 'test_password',
            'use_ssl': 'yes'
        }
        with pytest.raises(ValueError, match='use_ssl must be a boolean'):
            IMAPAgent(agent_id=1, config=config, user_id=1, db_session=None)

    def test_invalid_max_emails(self):
        """Test validation error when max_emails is out of range"""
        config = {
            'host': 'imap.gmail.com',
            'username': 'test@gmail.com',
            'password': 'test_password',
            'max_emails': 5000
        }
        with pytest.raises(ValueError, match='max_emails must be between 1 and 1000'):
            IMAPAgent(agent_id=1, config=config, user_id=1, db_session=None)


class TestIMAPAgentFetch:
    """Test IMAP agent fetch functionality"""

    @patch('app.agents.types.imap_agent.imaplib.IMAP4_SSL')
    def test_first_run_fetches_emails(self, mock_imap_ssl, test_job):
        """Test first run fetches recent emails with lookback filter"""
        # Setup mock IMAP connection
        mock_imap = Mock()
        mock_imap_ssl.return_value = mock_imap
        mock_imap.login.return_value = ('OK', [b'Logged in'])
        mock_imap.select.return_value = ('OK', [b'1'])
        mock_imap.search.return_value = ('OK', [b'1 2'])

        # Mock email fetch
        raw_email = b'From: sender@example.com\r\nTo: test@gmail.com\r\nSubject: Test\r\nMessage-ID: <test123@example.com>\r\nDate: Mon, 15 Feb 2026 10:00:00 +0000\r\n\r\nTest body'
        mock_imap.fetch.return_value = ('OK', [(b'1 (RFC822 {100}', raw_email), b')'])
        mock_imap.logout.return_value = ('BYE', [b'Logging out'])

        config = {
            'host': 'imap.gmail.com',
            'username': 'test@gmail.com',
            'password': 'test_password',
            'lookback_days': 7
        }

        agent = IMAPAgent(agent_id=test_job.id, config=config, user_id=test_job.user_id, db_session=db.session)
        events = agent.fetch()

        # Verify events were created
        assert len(events) > 0

        # Verify search included SINCE criteria for first run
        search_call = mock_imap.search.call_args
        assert search_call is not None
        search_criteria = search_call[0][1]
        assert 'SINCE' in search_criteria

    @patch('app.agents.types.imap_agent.imaplib.IMAP4_SSL')
    def test_subsequent_run_no_lookback(self, mock_imap_ssl, test_job):
        """Test subsequent runs don't apply lookback filter"""
        mock_imap = Mock()
        mock_imap_ssl.return_value = mock_imap
        mock_imap.login.return_value = ('OK', [b'Logged in'])
        mock_imap.select.return_value = ('OK', [b'1'])
        mock_imap.search.return_value = ('OK', [b''])
        mock_imap.logout.return_value = ('BYE', [b'Logging out'])

        config = {
            'host': 'imap.gmail.com',
            'username': 'test@gmail.com',
            'password': 'test_password'
        }

        agent = IMAPAgent(agent_id=test_job.id, config=config, user_id=test_job.user_id, db_session=db.session)

        # Simulate previous run
        agent.memory.set('last_sync_at', datetime.utcnow().isoformat())

        events = agent.fetch()

        # Verify search didn't include SINCE
        search_call = mock_imap.search.call_args
        search_criteria = search_call[0][1]
        assert 'SINCE' not in search_criteria

    @patch('app.agents.types.imap_agent.imaplib.IMAP4_SSL')
    def test_deduplication_by_message_id(self, mock_imap_ssl, test_job):
        """Test that emails are deduplicated by Message-ID"""
        mock_imap = Mock()
        mock_imap_ssl.return_value = mock_imap
        mock_imap.login.return_value = ('OK', [b'Logged in'])
        mock_imap.select.return_value = ('OK', [b'1'])
        mock_imap.search.return_value = ('OK', [b'1 2'])

        raw_email = b'From: sender@example.com\r\nTo: test@gmail.com\r\nSubject: Test\r\nMessage-ID: <duplicate@example.com>\r\nDate: Mon, 15 Feb 2026 10:00:00 +0000\r\n\r\nTest body'
        mock_imap.fetch.return_value = ('OK', [(b'1 (RFC822 {100}', raw_email), b')'])
        mock_imap.logout.return_value = ('BYE', [b'Logging out'])

        config = {
            'host': 'imap.gmail.com',
            'username': 'test@gmail.com',
            'password': 'test_password'
        }

        agent = IMAPAgent(agent_id=test_job.id, config=config, user_id=test_job.user_id, db_session=db.session)

        # First fetch
        events1 = agent.fetch()
        assert len(events1) > 0

        # Reset mock to simulate second run
        mock_imap_ssl.reset_mock()
        mock_imap.reset_mock()
        mock_imap.login.return_value = ('OK', [b'Logged in'])
        mock_imap.select.return_value = ('OK', [b'1'])
        mock_imap.search.return_value = ('OK', [b'1 2'])
        mock_imap.fetch.return_value = ('OK', [(b'1 (RFC822 {100}', raw_email), b')'])
        mock_imap.logout.return_value = ('BYE', [b'Logging out'])

        # Second fetch - should skip duplicate
        events2 = agent.fetch()
        assert len(events2) == 0  # Should be deduplicated

    @patch('app.agents.types.imap_agent.imaplib.IMAP4_SSL')
    def test_no_new_emails_returns_empty(self, mock_imap_ssl, test_job):
        """Test that no new emails returns empty list"""
        mock_imap = Mock()
        mock_imap_ssl.return_value = mock_imap
        mock_imap.login.return_value = ('OK', [b'Logged in'])
        mock_imap.select.return_value = ('OK', [b'1'])
        mock_imap.search.return_value = ('OK', [b''])
        mock_imap.logout.return_value = ('BYE', [b'Logging out'])

        config = {
            'host': 'imap.gmail.com',
            'username': 'test@gmail.com',
            'password': 'test_password'
        }

        agent = IMAPAgent(agent_id=test_job.id, config=config, user_id=test_job.user_id, db_session=db.session)
        events = agent.fetch()

        assert len(events) == 0

    @patch('app.agents.types.imap_agent.imaplib.IMAP4_SSL')
    def test_max_emails_limit(self, mock_imap_ssl, test_job):
        """Test that max_emails limit is respected"""
        mock_imap = Mock()
        mock_imap_ssl.return_value = mock_imap
        mock_imap.login.return_value = ('OK', [b'Logged in'])
        mock_imap.select.return_value = ('OK', [b'1'])

        # Return 100 UIDs
        uids = ' '.join(str(i) for i in range(1, 101))
        mock_imap.search.return_value = ('OK', [uids.encode()])

        raw_email = b'From: sender@example.com\r\nMessage-ID: <test@example.com>\r\n\r\nBody'
        mock_imap.fetch.return_value = ('OK', [(b'1 (RFC822 {100}', raw_email), b')'])
        mock_imap.logout.return_value = ('BYE', [b'Logging out'])

        config = {
            'host': 'imap.gmail.com',
            'username': 'test@gmail.com',
            'password': 'test_password',
            'max_emails': 10
        }

        agent = IMAPAgent(agent_id=test_job.id, config=config, user_id=test_job.user_id, db_session=db.session)
        events = agent.fetch()

        # Should only fetch max_emails
        assert len(events) <= 10


class TestIMAPAgentEmailParsing:
    """Test email parsing functionality"""

    def test_parse_simple_text_email(self, test_job):
        """Test parsing simple text email"""
        config = {
            'host': 'imap.gmail.com',
            'username': 'test@gmail.com',
            'password': 'test_password'
        }
        agent = IMAPAgent(agent_id=test_job.id, config=config, user_id=test_job.user_id, db_session=db.session)

        raw_email = b'From: sender@example.com\r\nTo: recipient@example.com\r\nSubject: Test Subject\r\nMessage-ID: <msg123@example.com>\r\nDate: Mon, 15 Feb 2026 10:00:00 +0000\r\nContent-Type: text/plain\r\n\r\nThis is the email body.'

        parsed = agent._parse_email(raw_email)

        assert parsed['message_id'] == '<msg123@example.com>'
        assert parsed['from'] == 'sender@example.com'
        assert parsed['to'] == 'recipient@example.com'
        assert parsed['subject'] == 'Test Subject'
        assert 'This is the email body' in parsed['body_text']
        assert parsed['body_html'] == ''

    def test_parse_multipart_email(self, test_job):
        """Test parsing multipart email with text and HTML"""
        config = {
            'host': 'imap.gmail.com',
            'username': 'test@gmail.com',
            'password': 'test_password'
        }
        agent = IMAPAgent(agent_id=test_job.id, config=config, user_id=test_job.user_id, db_session=db.session)

        raw_email = b'''From: sender@example.com\r
To: recipient@example.com\r
Subject: Test\r
Message-ID: <msg123@example.com>\r
Date: Mon, 15 Feb 2026 10:00:00 +0000\r
MIME-Version: 1.0\r
Content-Type: multipart/alternative; boundary="boundary"\r
\r
--boundary\r
Content-Type: text/plain; charset="utf-8"\r
\r
Plain text body\r
--boundary\r
Content-Type: text/html; charset="utf-8"\r
\r
<html>HTML body</html>\r
--boundary--\r
'''

        parsed = agent._parse_email(raw_email)

        assert 'Plain text body' in parsed['body_text']
        assert '<html>HTML body</html>' in parsed['body_html']

    def test_parse_email_missing_headers(self, test_job):
        """Test parsing email with missing headers"""
        config = {
            'host': 'imap.gmail.com',
            'username': 'test@gmail.com',
            'password': 'test_password'
        }
        agent = IMAPAgent(agent_id=test_job.id, config=config, user_id=test_job.user_id, db_session=db.session)

        raw_email = b'\r\n\r\nBody only email'

        parsed = agent._parse_email(raw_email)

        # Should handle missing headers gracefully
        assert parsed['message_id'] == ''
        assert parsed['from'] == ''
        assert parsed['to'] == ''
        assert parsed['subject'] == ''


class TestIMAPAgentConnection:
    """Test IMAP connection functionality"""

    @patch('app.agents.types.imap_agent.imaplib.IMAP4_SSL')
    def test_ssl_connection(self, mock_imap_ssl, test_job):
        """Test SSL connection is used by default"""
        mock_imap = Mock()
        mock_imap_ssl.return_value = mock_imap
        mock_imap.login.return_value = ('OK', [b'Logged in'])
        mock_imap.select.return_value = ('OK', [b'1'])
        mock_imap.search.return_value = ('OK', [b''])
        mock_imap.logout.return_value = ('BYE', [b'Logging out'])

        config = {
            'host': 'imap.gmail.com',
            'username': 'test@gmail.com',
            'password': 'test_password',
            'use_ssl': True
        }

        agent = IMAPAgent(agent_id=test_job.id, config=config, user_id=test_job.user_id, db_session=db.session)
        agent.fetch()

        # Verify SSL connection was created
        mock_imap_ssl.assert_called_once_with('imap.gmail.com', 993)

    @patch('app.agents.types.imap_agent.imaplib.IMAP4')
    def test_non_ssl_connection(self, mock_imap, test_job):
        """Test non-SSL connection when use_ssl is False"""
        mock_conn = Mock()
        mock_imap.return_value = mock_conn
        mock_conn.login.return_value = ('OK', [b'Logged in'])
        mock_conn.select.return_value = ('OK', [b'1'])
        mock_conn.search.return_value = ('OK', [b''])
        mock_conn.logout.return_value = ('BYE', [b'Logging out'])

        config = {
            'host': 'imap.example.com',
            'username': 'test@example.com',
            'password': 'test_password',
            'port': 143,
            'use_ssl': False
        }

        agent = IMAPAgent(agent_id=test_job.id, config=config, user_id=test_job.user_id, db_session=db.session)
        agent.fetch()

        # Verify non-SSL connection was created
        mock_imap.assert_called_once_with('imap.example.com', 143)

    @patch('app.agents.types.imap_agent.imaplib.IMAP4_SSL')
    def test_mark_as_read_flag(self, mock_imap_ssl, test_job):
        """Test mark_as_read flag marks emails as read"""
        mock_imap = Mock()
        mock_imap_ssl.return_value = mock_imap
        mock_imap.login.return_value = ('OK', [b'Logged in'])
        mock_imap.select.return_value = ('OK', [b'1'])
        mock_imap.search.return_value = ('OK', [b'1'])

        raw_email = b'From: sender@example.com\r\nMessage-ID: <test@example.com>\r\n\r\nBody'
        mock_imap.fetch.return_value = ('OK', [(b'1 (RFC822 {100}', raw_email), b')'])
        mock_imap.store.return_value = ('OK', [b''])
        mock_imap.logout.return_value = ('BYE', [b'Logging out'])

        config = {
            'host': 'imap.gmail.com',
            'username': 'test@gmail.com',
            'password': 'test_password',
            'mark_as_read': True
        }

        agent = IMAPAgent(agent_id=test_job.id, config=config, user_id=test_job.user_id, db_session=db.session)
        agent.fetch()

        # Verify email was marked as read
        mock_imap.store.assert_called()


class TestIMAPAgentErrors:
    """Test error handling"""

    @patch('app.agents.types.imap_agent.imaplib.IMAP4_SSL')
    def test_imap_protocol_error(self, mock_imap_ssl, test_job):
        """Test handling of IMAP protocol errors"""
        mock_imap_ssl.side_effect = imaplib.IMAP4.error('IMAP error')

        config = {
            'host': 'imap.gmail.com',
            'username': 'test@gmail.com',
            'password': 'test_password'
        }

        agent = IMAPAgent(agent_id=test_job.id, config=config, user_id=test_job.user_id, db_session=db.session)
        events = agent.fetch()

        # Should return empty list on error
        assert events == []

    @patch('app.agents.types.imap_agent.imaplib.IMAP4_SSL')
    def test_connection_refused_error(self, mock_imap_ssl, test_job):
        """Test handling of connection refused errors"""
        mock_imap_ssl.side_effect = ConnectionRefusedError('Connection refused')

        config = {
            'host': 'imap.gmail.com',
            'username': 'test@gmail.com',
            'password': 'test_password'
        }

        agent = IMAPAgent(agent_id=test_job.id, config=config, user_id=test_job.user_id, db_session=db.session)
        events = agent.fetch()

        # Should return empty list on error
        assert events == []

    @patch('app.agents.types.imap_agent.imaplib.IMAP4_SSL')
    def test_timeout_error(self, mock_imap_ssl, test_job):
        """Test handling of timeout errors"""
        import socket
        mock_imap_ssl.side_effect = socket.timeout('Connection timed out')

        config = {
            'host': 'imap.gmail.com',
            'username': 'test@gmail.com',
            'password': 'test_password'
        }

        agent = IMAPAgent(agent_id=test_job.id, config=config, user_id=test_job.user_id, db_session=db.session)
        events = agent.fetch()

        # Should return empty list on error
        assert events == []

    @patch('app.agents.types.imap_agent.imaplib.IMAP4_SSL')
    def test_search_failure(self, mock_imap_ssl, test_job):
        """Test handling of search failures"""
        mock_imap = Mock()
        mock_imap_ssl.return_value = mock_imap
        mock_imap.login.return_value = ('OK', [b'Logged in'])
        mock_imap.select.return_value = ('OK', [b'1'])
        mock_imap.search.return_value = ('NO', [b'Search failed'])
        mock_imap.logout.return_value = ('BYE', [b'Logging out'])

        config = {
            'host': 'imap.gmail.com',
            'username': 'test@gmail.com',
            'password': 'test_password'
        }

        agent = IMAPAgent(agent_id=test_job.id, config=config, user_id=test_job.user_id, db_session=db.session)
        events = agent.fetch()

        # Should return empty list when search fails
        assert events == []


class TestIMAPAgentConfigSchema:
    """Test configuration schema"""

    def test_config_schema(self):
        """Test configuration schema structure"""
        schema = IMAPAgent.get_config_schema()

        assert 'required_fields' in schema
        assert 'host' in schema['required_fields']
        assert 'username' in schema['required_fields']
        assert 'password' in schema['required_fields']

        assert 'optional_fields' in schema

        # Verify optional fields contain expected configuration options
        field_names = [field['name'] for field in schema['optional_fields']]
        assert 'port' in field_names
        assert 'use_ssl' in field_names
        assert 'search_criteria' in field_names
        assert 'max_emails' in field_names
        assert 'mark_as_read' in field_names
        assert 'lookback_days' in field_names
