"""
Alert Service - Send health alert emails and enforce cooldowns
"""

import smtplib
import logging
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional
from flask import current_app
from app.extensions import db
from app.models import Job, AlertLog
from app.constants import ALERT_COOLDOWN_HOURS
from app.services.health_service import (
    HEALTH_CRITICAL, HEALTH_WARNING, HEALTH_HEALTHY, compute_health
)

logger = logging.getLogger(__name__)


def _is_on_cooldown(agent: Job) -> bool:
    """Return True if an alert was sent for this agent within the cooldown window."""
    if agent.last_alerted_at is None:
        return False
    return datetime.utcnow() < agent.last_alerted_at + timedelta(hours=ALERT_COOLDOWN_HOURS)


def _resolve_recipient(agent: Job) -> Optional[str]:
    """Return the email address to alert, or None if alerting is disabled."""
    if not agent.alert_enabled:
        return None
    if agent.alert_email:
        return agent.alert_email
    # Fall back to agent owner's email
    if agent.user and agent.user.email:
        return agent.user.email
    return None


def send_alert_email(
    recipient: str,
    subject: str,
    body_html: str,
    body_text: str,
) -> bool:
    """
    Send an alert email via the configured SMTP server.

    Returns True on success, False on failure.
    """
    smtp_server = current_app.config.get('SMTP_SERVER')
    if not smtp_server:
        logger.warning("SMTP_SERVER not configured — alert email not sent")
        return False

    smtp_port = current_app.config.get('SMTP_PORT', 587)
    smtp_use_tls = current_app.config.get('SMTP_USE_TLS', True)
    smtp_user = current_app.config.get('SMTP_USERNAME')
    smtp_password = current_app.config.get('SMTP_PASSWORD')
    from_email = current_app.config.get('SMTP_FROM_EMAIL') or smtp_user

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = from_email
    msg['To'] = recipient
    msg.attach(MIMEText(body_text, 'plain'))
    msg.attach(MIMEText(body_html, 'html'))

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            if smtp_use_tls:
                server.starttls()
            if smtp_user and smtp_password:
                server.login(smtp_user, smtp_password)
            server.sendmail(from_email, [recipient], msg.as_string())
        logger.info(f"Alert email sent to {recipient}: {subject}")
        return True
    except Exception as e:
        logger.error(f"Failed to send alert email to {recipient}: {e}")
        return False


def _build_failure_email(agent: Job) -> tuple[str, str, str]:
    """Return (subject, html, text) for a failure alert."""
    status = agent.health_status.upper()
    subject = f"[Muninn {status}] Agent '{agent.name}' is failing"
    failures = agent.consecutive_failures
    text = (
        f"Agent '{agent.name}' (ID {agent.id}) has failed {failures} consecutive "
        f"time(s) and its health status is {status}.\n\n"
        f"Log in to Muninn to review the agent and its recent runs."
    )
    html = f"""
<html><body>
<h2 style="color:{'#dc2626' if agent.health_status == HEALTH_CRITICAL else '#d97706'}">
  Muninn Agent Alert: {status}
</h2>
<p>Agent <strong>{agent.name}</strong> (ID {agent.id}) has failed
<strong>{failures}</strong> consecutive time(s).</p>
<p>Health status: <strong>{status}</strong></p>
<p>Please log in to Muninn to review the agent and its recent run history.</p>
</body></html>"""
    return subject, html, text


def _build_staleness_email(agent: Job) -> tuple[str, str, str]:
    """Return (subject, html, text) for a staleness alert."""
    subject = f"[Muninn WARNING] Agent '{agent.name}' has not run recently"
    days = agent.expected_receive_period_in_days
    text = (
        f"Agent '{agent.name}' (ID {agent.id}) has not completed a successful run "
        f"within the expected {days}-day window.\n\n"
        f"Log in to Muninn to review the agent."
    )
    html = f"""
<html><body>
<h2 style="color:#d97706">Muninn Agent Alert: STALENESS WARNING</h2>
<p>Agent <strong>{agent.name}</strong> (ID {agent.id}) has not completed a successful
run within the expected <strong>{days}</strong>-day window.</p>
<p>Please log in to Muninn to review the agent.</p>
</body></html>"""
    return subject, html, text


def _build_recovery_email(agent: Job) -> tuple[str, str, str]:
    """Return (subject, html, text) for a recovery notification."""
    subject = f"[Muninn RECOVERED] Agent '{agent.name}' is healthy"
    text = (
        f"Agent '{agent.name}' (ID {agent.id}) has recovered and is now healthy."
    )
    html = f"""
<html><body>
<h2 style="color:#16a34a">Muninn Agent Alert: RECOVERED</h2>
<p>Agent <strong>{agent.name}</strong> (ID {agent.id}) has recovered and is
now <strong>healthy</strong>.</p>
</body></html>"""
    return subject, html, text


def check_and_alert(agent: Job, db_session=None) -> bool:
    """
    Evaluate an agent's health, send an alert if warranted, and record it.

    Called after each agent run completes. Handles:
    - Failure alerts (WARNING / CRITICAL thresholds)
    - Staleness alerts (expected_receive_period_in_days exceeded)
    - Recovery notifications (was alerted, now healthy)

    Returns True if an alert was sent.
    """
    session = db_session or db.session

    # Recompute health to ensure it's current
    status = compute_health(agent, session)

    recipient = _resolve_recipient(agent)
    if not recipient:
        return False

    if _is_on_cooldown(agent):
        return False

    alert_type = None
    if status in (HEALTH_CRITICAL, HEALTH_WARNING):
        # Check staleness vs failure
        if agent.consecutive_failures == 0 and agent.expected_receive_period_in_days:
            alert_type = 'staleness'
            subject, html, text = _build_staleness_email(agent)
        else:
            alert_type = 'failure'
            subject, html, text = _build_failure_email(agent)
    elif status == HEALTH_HEALTHY and agent.last_alerted_at is not None:
        # Send recovery email if we previously alerted and agent is now healthy
        alert_type = 'recovery'
        subject, html, text = _build_recovery_email(agent)

    if alert_type is None:
        return False

    sent = send_alert_email(recipient, subject, html, text)
    if sent:
        agent.last_alerted_at = datetime.utcnow()
        log = AlertLog(
            agent_id=agent.id,
            alert_type=alert_type,
            message=text,
            recipient_email=recipient,
        )
        session.add(log)
        try:
            session.commit()
        except Exception as e:
            logger.error(f"Failed to record alert log: {e}")
            session.rollback()

    return sent
