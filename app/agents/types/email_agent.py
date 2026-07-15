"""
Email Agent - Send emails via SMTP

Single responsibility: ONLY sends emails via SMTP.
Does NOT create new events (terminal agent).
"""

from typing import List, Dict, Any
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jinja2 import Template, TemplateSyntaxError, UndefinedError
from app.agents.base import ActionAgent
from app.agents.registry import register_agent
from app.models import Event


@register_agent
class EmailAgent(ActionAgent):
    """
    Sends emails via SMTP.

    Terminal agent: consumes events but does not create new ones.
    Uses Jinja2 templates for subject and body.

    Configuration:
        smtp_server (str): SMTP server hostname
        smtp_port (int): SMTP server port (default: 587 for TLS)
        use_tls (bool): Use TLS encryption (default: True)
        username (str): SMTP authentication username
        password (str): SMTP authentication password
        from_email (str): Sender email address
        to_email (str or list): Recipient email(s), can use Jinja2 template
        subject_template (str): Jinja2 template for email subject
        body_template (str): Jinja2 template for email body
        cc_email (str or list, optional): CC recipients
        bcc_email (str or list, optional): BCC recipients
        html (bool): Send as HTML email (default: False)
    """

    agent_type = 'email_agent'

    def validate_config(self) -> None:
        """Validate email agent configuration."""
        super().validate_config()

        # Check global SMTP configuration is set
        from flask import current_app
        if not current_app.config.get('SMTP_SERVER'):
            raise ValueError("Global SMTP_SERVER not configured. Set SMTP_SERVER environment variable.")
        if not current_app.config.get('SMTP_USERNAME'):
            raise ValueError("Global SMTP_USERNAME not configured. Set SMTP_USERNAME environment variable.")
        if not current_app.config.get('SMTP_PASSWORD'):
            raise ValueError("Global SMTP_PASSWORD not configured. Set SMTP_PASSWORD environment variable.")

        # Recipient validation (to_email required)
        if 'to_email' not in self.config:
            raise ValueError("Email agent requires 'to_email' in config")

        # to_email can be string or list
        to_email = self.config['to_email']
        if not isinstance(to_email, (str, list)):
            raise ValueError("'to_email' must be a string or list of strings")

        if isinstance(to_email, list):
            if not all(isinstance(email, str) for email in to_email):
                raise ValueError("All 'to_email' entries must be strings")

        # Templates
        if 'subject_template' not in self.config:
            raise ValueError("Email agent requires 'subject_template' in config")

        if not isinstance(self.config['subject_template'], str):
            raise ValueError("'subject_template' must be a string")

        # Test subject template syntax
        try:
            Template(self.config['subject_template'])
        except TemplateSyntaxError as e:
            raise ValueError(f"Invalid Jinja2 syntax in 'subject_template': {e}")

        if 'body_template' not in self.config:
            raise ValueError("Email agent requires 'body_template' in config")

        if not isinstance(self.config['body_template'], str):
            raise ValueError("'body_template' must be a string")

        # Test body template syntax
        try:
            Template(self.config['body_template'])
        except TemplateSyntaxError as e:
            raise ValueError(f"Invalid Jinja2 syntax in 'body_template': {e}")

        # Optional CC/BCC
        for field in ['cc_email', 'bcc_email']:
            if field in self.config:
                value = self.config[field]
                if not isinstance(value, (str, list)):
                    raise ValueError(f"'{field}' must be a string or list of strings")
                if isinstance(value, list):
                    if not all(isinstance(email, str) for email in value):
                        raise ValueError(f"All '{field}' entries must be strings")

        # Optional HTML flag
        if 'html' in self.config:
            if not isinstance(self.config['html'], bool):
                raise ValueError("'html' must be a boolean")

    def act(self, events: List[Event]) -> None:
        """
        Send emails for each event.

        Args:
            events: Events to process
        """
        from flask import current_app

        # Get SMTP settings from global config
        smtp_server = current_app.config['SMTP_SERVER']
        smtp_port = current_app.config.get('SMTP_PORT', 587)
        use_tls = current_app.config.get('SMTP_USE_TLS', True)
        username = current_app.config['SMTP_USERNAME']
        password = current_app.config['SMTP_PASSWORD']
        from_email = current_app.config.get('SMTP_FROM_EMAIL', username)

        # Get per-agent settings
        html = self.config.get('html', False)

        sent_count = 0
        failed_count = 0

        for event in events:
            try:
                # Render templates with event data
                subject = self._render_template(self.config['subject_template'], event.payload)
                body = self._render_template(self.config['body_template'], event.payload)

                # Render to_email (can be a template)
                to_email = self._resolve_recipients(self.config['to_email'], event.payload)
                cc_email = self._resolve_recipients(self.config.get('cc_email'), event.payload) if 'cc_email' in self.config else []
                bcc_email = self._resolve_recipients(self.config.get('bcc_email'), event.payload) if 'bcc_email' in self.config else []

                # Create email message
                msg = MIMEMultipart('alternative') if html else MIMEText(body, 'plain', 'utf-8')

                if html:
                    # Add both plain text and HTML versions
                    msg.attach(MIMEText(body, 'plain', 'utf-8'))
                    msg.attach(MIMEText(body, 'html', 'utf-8'))

                msg['Subject'] = subject
                msg['From'] = from_email
                msg['To'] = ', '.join(to_email) if isinstance(to_email, list) else to_email

                if cc_email:
                    msg['Cc'] = ', '.join(cc_email) if isinstance(cc_email, list) else cc_email

                # Combine all recipients
                all_recipients = []
                if isinstance(to_email, list):
                    all_recipients.extend(to_email)
                else:
                    all_recipients.append(to_email)

                if cc_email:
                    if isinstance(cc_email, list):
                        all_recipients.extend(cc_email)
                    else:
                        all_recipients.append(cc_email)

                if bcc_email:
                    if isinstance(bcc_email, list):
                        all_recipients.extend(bcc_email)
                    else:
                        all_recipients.append(bcc_email)

                # Send email
                self._send_email(smtp_server, smtp_port, use_tls, username, password,
                                from_email, all_recipients, msg)

                sent_count += 1
                self.log(f'Email sent successfully', level='info', data={
                    'event_id': event.id,
                    'to': to_email,
                    'subject': subject
                })

            except Exception as e:
                failed_count += 1
                self.log(f'Failed to send email: {e}', level='error', data={
                    'event_id': event.id,
                    'error': str(e)
                })

        self.log(f'Processed {len(events)} events', data={
            'sent_count': sent_count,
            'failed_count': failed_count
        })

    def _render_template(self, template_str: str, data: Dict[str, Any]) -> str:
        """
        Render Jinja2 template with event data.

        Args:
            template_str: Template string
            data: Event payload data

        Returns:
            Rendered string
        """
        try:
            template = Template(template_str)
            return template.render(**data)
        except UndefinedError as e:
            self.log(f'Undefined variable in template: {e}', level='warning')
            return f'[Template Error: {e}]'
        except Exception as e:
            self.log(f'Template rendering error: {e}', level='error')
            return f'[Render Error: {e}]'

    def _resolve_recipients(self, recipients: Any, data: Dict[str, Any]) -> List[str]:
        """
        Resolve recipient email addresses (can be templates or lists).

        Args:
            recipients: String, template, or list of emails
            data: Event payload data for template rendering

        Returns:
            List of email addresses
        """
        if recipients is None:
            return []

        if isinstance(recipients, list):
            # Each item in list can be a template
            return [self._render_template(str(r), data) for r in recipients]
        else:
            # Single recipient (can be a template)
            rendered = self._render_template(str(recipients), data)
            return [rendered]

    def _send_email(self, smtp_server: str, smtp_port: int, use_tls: bool,
                   username: str, password: str, from_email: str,
                   recipients: List[str], message: Any) -> None:
        """
        Send email via SMTP.

        Args:
            smtp_server: SMTP server hostname
            smtp_port: SMTP server port
            use_tls: Use TLS encryption
            username: SMTP username
            password: SMTP password
            from_email: Sender address
            recipients: List of recipient addresses
            message: Email message object
        """
        if use_tls:
            # Use STARTTLS
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(username, password)
                server.send_message(message)
        else:
            # Plain connection or SSL
            if smtp_port == 465:
                # Use SSL
                with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
                    server.login(username, password)
                    server.send_message(message)
            else:
                # Plain connection
                with smtplib.SMTP(smtp_server, smtp_port) as server:
                    server.login(username, password)
                    server.send_message(message)

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """Get configuration schema for email agent."""
        schema = super().get_config_schema()
        schema['required_fields'] = [
            'to_email',
            'subject_template',
            'body_template'
        ]
        schema['optional_fields'] = [
            {
                'name': 'cc_email',
                'type': 'string or list',
                'description': 'CC recipient(s), can use Jinja2 templates'
            },
            {
                'name': 'bcc_email',
                'type': 'string or list',
                'description': 'BCC recipient(s), can use Jinja2 templates'
            },
            {
                'name': 'html',
                'type': 'boolean',
                'default': False,
                'description': 'Send email as HTML (includes both plain text and HTML versions)'
            }
        ]
        schema['global_config_note'] = (
            'SMTP server configuration is managed globally via environment variables: '
            'SMTP_SERVER, SMTP_PORT, SMTP_USE_TLS, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM_EMAIL'
        )
        schema['template_context'] = {
            'description': 'Templates have access to all event payload fields',
            'example_subject': 'New alert: {{ title }}',
            'example_body': 'Alert: {{ title }}\\n\\nDetails: {{ description }}\\n\\nLink: {{ link }}'
        }
        return schema
