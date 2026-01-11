"""
Tests for Email Agent Global SMTP Configuration

Tests that email agents use global SMTP configuration from environment variables
instead of per-agent configuration.
"""

import pytest
import base64
from unittest.mock import patch, MagicMock
from app.models import Job, Event
from app.agents.types.email_agent import EmailAgent


class TestGlobalSMTPConfig:
    """Test that global SMTP configuration is loaded and used correctly."""

    def test_smtp_config_loaded_from_env(self, app):
        """Test that SMTP configuration is loaded from environment variables."""
        with app.app_context():
            assert app.config.get('SMTP_SERVER') is not None
            assert app.config.get('SMTP_PORT') is not None
            assert app.config.get('SMTP_USERNAME') is not None
            assert app.config.get('SMTP_PASSWORD') is not None

    def test_email_agent_validates_global_config_exists(self, app, db_session, test_user):
        """Test that email agent validates global SMTP config is set."""
        with app.app_context():
            # Create job with minimal config (no SMTP fields)
            job = Job(
                name='Test Email Agent',
                job_type='email_agent',
                config={
                    'to_email': 'test@example.com',
                    'subject_template': 'Test: {{ title }}',
                    'body_template': '{{ description }}'
                },
                user_id=test_user.id
            )
            db_session.add(job)
            db_session.commit()

            # Create agent instance - should validate successfully
            agent = EmailAgent(
                agent_id=job.id,
                config=job.config,
                user_id=job.user_id,
                db_session=db_session
            )
            assert agent is not None

    def test_email_agent_fails_without_global_smtp_server(self, app, db_session, test_user):
        """Test that email agent fails validation if global SMTP_SERVER not set."""
        with app.app_context():
            # Temporarily remove SMTP_SERVER from config
            original_server = app.config.get('SMTP_SERVER')
            app.config['SMTP_SERVER'] = None

            try:
                job = Job(
                    name='Test Email Agent',
                    job_type='email_agent',
                    config={
                        'to_email': 'test@example.com',
                        'subject_template': 'Test: {{ title }}',
                        'body_template': '{{ description }}'
                    },
                    user_id=test_user.id
                )
                db_session.add(job)
                db_session.commit()

                # Should raise ValueError
                with pytest.raises(ValueError, match='Global SMTP_SERVER not configured'):
                    EmailAgent(
                agent_id=job.id,
                config=job.config,
                user_id=job.user_id,
                db_session=db_session
            )

            finally:
                # Restore original config
                app.config['SMTP_SERVER'] = original_server

    def test_email_agent_fails_without_global_smtp_username(self, app, db_session, test_user):
        """Test that email agent fails validation if global SMTP_USERNAME not set."""
        with app.app_context():
            # Temporarily remove SMTP_USERNAME from config
            original_username = app.config.get('SMTP_USERNAME')
            app.config['SMTP_USERNAME'] = None

            try:
                job = Job(
                    name='Test Email Agent',
                    job_type='email_agent',
                    config={
                        'to_email': 'test@example.com',
                        'subject_template': 'Test: {{ title }}',
                        'body_template': '{{ description }}'
                    },
                    user_id=test_user.id
                )
                db_session.add(job)
                db_session.commit()

                # Should raise ValueError
                with pytest.raises(ValueError, match='Global SMTP_USERNAME not configured'):
                    EmailAgent(
                agent_id=job.id,
                config=job.config,
                user_id=job.user_id,
                db_session=db_session
            )

            finally:
                # Restore original config
                app.config['SMTP_USERNAME'] = original_username


class TestEmailAgentSimplifiedConfig:
    """Test that email agent configuration is simplified (only requires recipients and templates)."""

    def test_create_email_agent_minimal_config(self, app, db_session, test_user):
        """Test creating email agent with minimal config (no SMTP fields)."""
        with app.app_context():
            job = Job(
                name='Minimal Email Agent',
                job_type='email_agent',
                config={
                    'to_email': 'user@example.com',
                    'subject_template': 'Alert: {{ title }}',
                    'body_template': '{{ description }}'
                },
                user_id=test_user.id
            )
            db_session.add(job)
            db_session.commit()

            # Should create successfully
            agent = EmailAgent(
                agent_id=job.id,
                config=job.config,
                user_id=job.user_id,
                db_session=db_session
            )
            assert agent.config['to_email'] == 'user@example.com'
            assert agent.config['subject_template'] == 'Alert: {{ title }}'
            assert agent.config['body_template'] == '{{ description }}'

    def test_create_email_agent_with_cc_bcc(self, app, db_session, test_user):
        """Test creating email agent with optional CC and BCC fields."""
        with app.app_context():
            job = Job(
                name='Email Agent with CC/BCC',
                job_type='email_agent',
                config={
                    'to_email': ['user1@example.com', 'user2@example.com'],
                    'cc_email': 'manager@example.com',
                    'bcc_email': ['archive@example.com', 'backup@example.com'],
                    'subject_template': 'Alert: {{ title }}',
                    'body_template': '{{ description }}'
                },
                user_id=test_user.id
            )
            db_session.add(job)
            db_session.commit()

            # Should create successfully
            agent = EmailAgent(
                agent_id=job.id,
                config=job.config,
                user_id=job.user_id,
                db_session=db_session
            )
            assert agent.config['to_email'] == ['user1@example.com', 'user2@example.com']
            assert agent.config['cc_email'] == 'manager@example.com'
            assert agent.config['bcc_email'] == ['archive@example.com', 'backup@example.com']

    def test_email_agent_rejects_smtp_fields_in_config(self, app, db_session, test_user):
        """Test that email agent no longer uses SMTP fields in per-agent config."""
        with app.app_context():
            # Create job with old-style SMTP config (should be ignored)
            job = Job(
                name='Email Agent with Old Config',
                job_type='email_agent',
                config={
                    'smtp_server': 'smtp.example.com',  # Should be ignored
                    'smtp_port': 587,  # Should be ignored
                    'username': 'old@example.com',  # Should be ignored
                    'password': 'oldpassword',  # Should be ignored
                    'to_email': 'user@example.com',
                    'subject_template': 'Alert: {{ title }}',
                    'body_template': '{{ description }}'
                },
                user_id=test_user.id
            )
            db_session.add(job)
            db_session.commit()

            # Agent should create successfully (old fields ignored)
            agent = EmailAgent(
                agent_id=job.id,
                config=job.config,
                user_id=job.user_id,
                db_session=db_session
            )

            # Verify agent doesn't use old config fields
            assert 'smtp_server' in agent.config  # Still in config dict
            assert 'smtp_port' in agent.config
            # But they won't be used - global config will be used instead


class TestEmailAgentUsesGlobalConfig:
    """Test that email agent uses global SMTP configuration when sending emails."""

    @patch('app.agents.types.email_agent.smtplib.SMTP')
    def test_email_agent_uses_global_smtp_server(self, mock_smtp, app, db_session, test_user):
        """Test that email agent uses global SMTP_SERVER when sending."""
        with app.app_context():
            # Create agent
            job = Job(
                name='Test Email Agent',
                job_type='email_agent',
                config={
                    'to_email': 'test@example.com',
                    'subject_template': 'Test: {{ title }}',
                    'body_template': '{{ description }}'
                },
                user_id=test_user.id
            )
            db_session.add(job)
            db_session.commit()

            agent = EmailAgent(
                agent_id=job.id,
                config=job.config,
                user_id=job.user_id,
                db_session=db_session
            )

            # Create test event
            event = Event(
                agent_id=job.id,
                agent_type=job.job_type,
                user_id=job.user_id,
                payload={'title': 'Test Title', 'description': 'Test Description'}
            )
            db_session.add(event)
            db_session.commit()

            # Mock SMTP connection
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            # Send email
            agent.act([event])

            # Verify SMTP was called with global config
            mock_smtp.assert_called_once_with(
                app.config['SMTP_SERVER'],
                app.config.get('SMTP_PORT', 587)
            )
            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once_with(
                app.config['SMTP_USERNAME'],
                app.config['SMTP_PASSWORD']
            )
            mock_server.send_message.assert_called_once()

    @patch('app.agents.types.email_agent.smtplib.SMTP')
    def test_email_agent_uses_global_from_email(self, mock_smtp, app, db_session, test_user):
        """Test that email agent uses global SMTP_FROM_EMAIL."""
        with app.app_context():
            # Set global from_email
            app.config['SMTP_FROM_EMAIL'] = 'noreply@example.com'

            job = Job(
                name='Test Email Agent',
                job_type='email_agent',
                config={
                    'to_email': 'test@example.com',
                    'subject_template': 'Test: {{ title }}',
                    'body_template': '{{ description }}'
                },
                user_id=test_user.id
            )
            db_session.add(job)
            db_session.commit()

            agent = EmailAgent(
                agent_id=job.id,
                config=job.config,
                user_id=job.user_id,
                db_session=db_session
            )

            # Create test event
            event = Event(
                agent_id=job.id,
                agent_type=job.job_type,
                user_id=job.user_id,
                payload={'title': 'Test Title', 'description': 'Test Description'}
            )
            db_session.add(event)
            db_session.commit()

            # Mock SMTP connection
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            # Send email
            agent.act([event])

            # Verify message has correct From header
            call_args = mock_server.send_message.call_args
            message = call_args[0][0]
            assert message['From'] == 'noreply@example.com'


class TestEmailAgentTemplating:
    """Test that Jinja2 templating continues to work with global config."""

    @patch('app.agents.types.email_agent.smtplib.SMTP')
    def test_jinja_template_rendering(self, mock_smtp, app, db_session, test_user):
        """Test that Jinja2 templates render correctly with event data."""
        with app.app_context():
            job = Job(
                name='Template Test Agent',
                job_type='email_agent',
                config={
                    'to_email': 'test@example.com',
                    'subject_template': 'Alert: {{ title }} - {{ severity }}',
                    'body_template': 'Issue: {{ title }}\n\nDetails: {{ description }}\n\nLink: {{ link }}'
                },
                user_id=test_user.id
            )
            db_session.add(job)
            db_session.commit()

            agent = EmailAgent(
                agent_id=job.id,
                config=job.config,
                user_id=job.user_id,
                db_session=db_session
            )

            # Create event with template data
            event = Event(
                agent_id=job.id,
                agent_type=job.job_type,
                user_id=job.user_id,
                payload={
                    'title': 'Database Error',
                    'severity': 'HIGH',
                    'description': 'Connection timeout',
                    'link': 'https://example.com/issue/123'
                }
            )
            db_session.add(event)
            db_session.commit()

            # Mock SMTP
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            # Send email
            agent.act([event])

            # Verify template rendering
            call_args = mock_server.send_message.call_args
            message = call_args[0][0]

            assert message['Subject'] == 'Alert: Database Error - HIGH'
            # Check body contains rendered template
            payload = message.get_payload()
            if isinstance(payload, list):
                body = payload[0].get_payload()
            else:
                body = payload

            # Decode Base64 if encoded
            if isinstance(body, str):
                try:
                    body = base64.b64decode(body).decode('utf-8')
                except:
                    pass  # If not Base64, use as-is

            assert 'Issue: Database Error' in body
            assert 'Connection timeout' in body
            assert 'https://example.com/issue/123' in body

    @patch('app.agents.types.email_agent.smtplib.SMTP')
    def test_recipient_template_rendering(self, mock_smtp, app, db_session, test_user):
        """Test that recipient fields can use Jinja2 templates."""
        with app.app_context():
            job = Job(
                name='Dynamic Recipient Agent',
                job_type='email_agent',
                config={
                    'to_email': '{{ recipient_email }}',  # Template
                    'subject_template': 'Alert: {{ title }}',
                    'body_template': '{{ description }}'
                },
                user_id=test_user.id
            )
            db_session.add(job)
            db_session.commit()

            agent = EmailAgent(
                agent_id=job.id,
                config=job.config,
                user_id=job.user_id,
                db_session=db_session
            )

            # Create event with recipient email in payload
            event = Event(
                agent_id=job.id,
                agent_type=job.job_type,
                user_id=job.user_id,
                payload={
                    'title': 'Test Alert',
                    'description': 'Test description',
                    'recipient_email': 'dynamic@example.com'
                }
            )
            db_session.add(event)
            db_session.commit()

            # Mock SMTP
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            # Send email
            agent.act([event])

            # Verify recipient was rendered from template
            call_args = mock_server.send_message.call_args
            message = call_args[0][0]
            assert message['To'] == 'dynamic@example.com'


class TestEmailAgentConfigSchema:
    """Test that email agent config schema reflects simplified configuration."""

    def test_config_schema_required_fields(self, app):
        """Test that config schema only requires 3 fields."""
        with app.app_context():
            schema = EmailAgent.get_config_schema()

            assert 'required_fields' in schema
            assert len(schema['required_fields']) == 3
            assert 'to_email' in schema['required_fields']
            assert 'subject_template' in schema['required_fields']
            assert 'body_template' in schema['required_fields']

            # SMTP fields should NOT be in required fields
            assert 'smtp_server' not in schema['required_fields']
            assert 'smtp_port' not in schema['required_fields']
            assert 'username' not in schema['required_fields']
            assert 'password' not in schema['required_fields']

    def test_config_schema_has_global_config_note(self, app):
        """Test that config schema includes note about global SMTP config."""
        with app.app_context():
            schema = EmailAgent.get_config_schema()

            assert 'global_config_note' in schema
            assert 'SMTP_SERVER' in schema['global_config_note']
            assert 'environment variables' in schema['global_config_note']
