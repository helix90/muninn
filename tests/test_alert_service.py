"""Tests for the agent alert service."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, call

from app.models import Job, AgentRun, AlertLog
from app.services.alert_service import (
    check_and_alert, send_alert_email, _is_on_cooldown, _resolve_recipient,
)
from app.services.health_service import HEALTH_CRITICAL, HEALTH_WARNING, HEALTH_HEALTHY


class TestResolveRecipient:
    def test_returns_none_when_alerting_disabled(self, db_session, test_job):
        test_job.alert_enabled = False
        assert _resolve_recipient(test_job) is None

    def test_returns_custom_email_when_set(self, db_session, test_job):
        test_job.alert_enabled = True
        test_job.alert_email = 'custom@example.com'
        assert _resolve_recipient(test_job) == 'custom@example.com'

    def test_falls_back_to_user_email(self, db_session, test_job):
        test_job.alert_enabled = True
        test_job.alert_email = None
        # test_job.user is the test_user whose email is set in conftest
        assert _resolve_recipient(test_job) == test_job.user.email


class TestCooldown:
    def test_no_cooldown_when_never_alerted(self, db_session, test_job):
        test_job.last_alerted_at = None
        assert _is_on_cooldown(test_job) is False

    def test_on_cooldown_within_window(self, db_session, test_job):
        test_job.last_alerted_at = datetime.utcnow() - timedelta(hours=1)
        assert _is_on_cooldown(test_job) is True

    def test_cooldown_expired_after_window(self, db_session, test_job):
        test_job.last_alerted_at = datetime.utcnow() - timedelta(hours=5)
        assert _is_on_cooldown(test_job) is False


class TestCheckAndAlert:
    """Integration tests for check_and_alert."""

    def _configure_agent(self, job, failures=0, status=None,
                         alert_enabled=True, alert_email='test@example.com',
                         last_alerted_at=None):
        job.alert_enabled = alert_enabled
        job.alert_email = alert_email
        job.consecutive_failures = failures
        if status:
            job.health_status = status
        job.last_alerted_at = last_alerted_at

    @patch('app.services.alert_service.send_alert_email', return_value=True)
    def test_sends_failure_alert_for_critical_status(self, mock_send, db_session, test_job):
        """Critical status triggers a failure alert."""
        self._configure_agent(test_job, failures=3)
        result = check_and_alert(test_job, db_session)
        assert result is True
        mock_send.assert_called_once()
        # send_alert_email(recipient, subject, html, text)
        subject = mock_send.call_args[0][1]
        assert 'CRITICAL' in subject

    @patch('app.services.alert_service.send_alert_email', return_value=True)
    def test_sends_warning_alert(self, mock_send, db_session, test_job):
        """Warning status triggers a warning alert."""
        self._configure_agent(test_job, failures=1)
        result = check_and_alert(test_job, db_session)
        assert result is True
        mock_send.assert_called_once()

    @patch('app.services.alert_service.send_alert_email', return_value=True)
    def test_no_alert_when_disabled(self, mock_send, db_session, test_job):
        """No alert sent when alert_enabled is False."""
        self._configure_agent(test_job, failures=5, alert_enabled=False)
        result = check_and_alert(test_job, db_session)
        assert result is False
        mock_send.assert_not_called()

    @patch('app.services.alert_service.send_alert_email', return_value=True)
    def test_no_alert_during_cooldown(self, mock_send, db_session, test_job):
        """No alert sent during cooldown window."""
        self._configure_agent(
            test_job, failures=3,
            last_alerted_at=datetime.utcnow() - timedelta(hours=1),
        )
        result = check_and_alert(test_job, db_session)
        assert result is False
        mock_send.assert_not_called()

    @patch('app.services.alert_service.send_alert_email', return_value=True)
    def test_sends_recovery_alert(self, mock_send, db_session, test_job):
        """Recovery alert sent when agent was previously alerted and is now healthy."""
        self._configure_agent(
            test_job, failures=0,
            last_alerted_at=datetime.utcnow() - timedelta(hours=5),
        )
        # Add a completed run so compute_health resolves to HEALTHY
        run = AgentRun(agent_id=test_job.id, status='completed')
        db_session.add(run)
        db_session.flush()

        result = check_and_alert(test_job, db_session)
        assert result is True
        # send_alert_email(recipient, subject, html, text)
        subject = mock_send.call_args[0][1]
        assert 'RECOVERED' in subject

    @patch('app.services.alert_service.send_alert_email', return_value=True)
    def test_alert_log_recorded(self, mock_send, db_session, test_job):
        """AlertLog row is created after a successful alert."""
        self._configure_agent(test_job, failures=3)
        check_and_alert(test_job, db_session)
        log = db_session.query(AlertLog).filter_by(agent_id=test_job.id).first()
        assert log is not None
        assert log.alert_type == 'failure'

    @patch('app.services.alert_service.send_alert_email', return_value=False)
    def test_no_log_when_send_fails(self, mock_send, db_session, test_job):
        """No AlertLog created when email delivery fails."""
        self._configure_agent(test_job, failures=3)
        result = check_and_alert(test_job, db_session)
        assert result is False
        log = db_session.query(AlertLog).filter_by(agent_id=test_job.id).first()
        assert log is None


class TestSendAlertEmail:
    """Unit tests for send_alert_email SMTP logic."""

    def test_returns_false_when_smtp_not_configured(self, app):
        with app.app_context():
            app.config['SMTP_SERVER'] = None
            result = send_alert_email('r@e.com', 'subj', '<p>hi</p>', 'hi')
            assert result is False

    @patch('app.services.alert_service.smtplib.SMTP')
    def test_sends_via_smtp(self, mock_smtp_cls, app):
        """SMTP connection is used and message is sent."""
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__ = lambda s: mock_server
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        with app.app_context():
            app.config['SMTP_SERVER'] = 'smtp.example.com'
            app.config['SMTP_PORT'] = 587
            app.config['SMTP_USE_TLS'] = True
            app.config['SMTP_USERNAME'] = 'u'
            app.config['SMTP_PASSWORD'] = 'p'
            app.config['SMTP_FROM_EMAIL'] = 'from@example.com'

            result = send_alert_email('to@example.com', 'Test', '<p>body</p>', 'body')
            assert result is True
            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once_with('u', 'p')
            mock_server.sendmail.assert_called_once()
