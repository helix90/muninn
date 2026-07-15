"""
Webhook Agent - Receive HTTP webhooks from external services

This agent provides HTTP endpoints that external services can POST to.
Unlike polling agents, this is push-based - external services send data to Muninn.
Events are created immediately when webhook is received by the Flask route handler.
"""

import secrets
import logging
from typing import Any, Dict, List
from datetime import datetime

from app.agents.base import SourceAgent
from app.agents.registry import register_agent
from app.models import Event

logger = logging.getLogger(__name__)


@register_agent
class WebhookAgent(SourceAgent):
    """
    Source agent that receives HTTP webhooks.

    Provides an HTTP endpoint at /webhooks/<agent_id>/<secret_token>
    that external services can POST to. Creates events immediately when
    webhooks are received.

    Configuration:
        secret_token (str): Auto-generated token for URL authentication
        verify_signature (bool): Enable HMAC signature verification (default: False)
        signature_secret (str): Secret for HMAC verification (GitHub/Stripe style)
        allowed_ips (list): IP whitelist (empty = allow all)
        include_headers (list): HTTP headers to capture in event metadata
        response_status (int): HTTP status code to return (default: 200)
        response_body (dict): JSON response body (default: {"status": "success"})
    """

    agent_type = 'webhook_agent'
    agent_category = 'source'

    # Webhooks are push-based (receive HTTP POST), not pull-based (scheduled polling)
    can_be_scheduled = False

    def __init__(self, agent_id: int, config: Dict[str, Any], user_id: int, db_session=None):
        """Initialize the Webhook agent."""
        # Auto-generate secret token if not provided
        if 'secret_token' not in config or not config['secret_token']:
            config['secret_token'] = secrets.token_urlsafe(32)

        self.secret_token = config.get('secret_token', '')
        self.verify_signature = config.get('verify_signature', False)
        self.signature_secret = config.get('signature_secret', '')
        self.allowed_ips = config.get('allowed_ips', [])
        self.include_headers = config.get('include_headers', [])
        self.response_status = int(config.get('response_status', 200))
        self.response_body = config.get('response_body', {'status': 'success'})

        super().__init__(agent_id, config, user_id, db_session)

    def validate_config(self) -> None:
        """
        Validate agent configuration.

        Raises:
            ValueError: If configuration is invalid
        """
        # Call parent validation
        super().validate_config()

        # Validate secret_token
        if not self.secret_token:
            raise ValueError("secret_token is required")

        if len(self.secret_token) < 16:
            raise ValueError("secret_token must be at least 16 characters")

        # Validate signature settings
        if not isinstance(self.verify_signature, bool):
            raise ValueError("verify_signature must be a boolean")

        if self.verify_signature and not self.signature_secret:
            raise ValueError("signature_secret required when verify_signature is True")

        # Validate allowed_ips
        if not isinstance(self.allowed_ips, list):
            raise ValueError("allowed_ips must be a list")

        # Validate include_headers
        if not isinstance(self.include_headers, list):
            raise ValueError("include_headers must be a list")

        # Validate response_status
        if not 100 <= self.response_status <= 599:
            raise ValueError("response_status must be between 100 and 599")

        # Validate response_body (must be dict or None)
        if self.response_body is not None and not isinstance(self.response_body, dict):
            raise ValueError("response_body must be a dictionary or None")

    def fetch(self) -> List[Event]:
        """
        Webhook agents don't poll - events are created by HTTP endpoint.

        This method exists to satisfy SourceAgent interface but returns empty list.
        The actual event creation happens in /app/webhooks.py route handler.

        Returns:
            Empty list (events created by webhook route handler)
        """
        # Update metrics
        self.memory.set('last_check_at', datetime.utcnow().isoformat())

        # Webhooks are push-based, not poll-based
        # Events are created immediately by the Flask route handler
        return []

    def get_webhook_url(self, base_url: str = None) -> str:
        """
        Get the webhook URL for this agent.

        Args:
            base_url: Base URL (e.g., https://muninn.example.com)
                     If None, uses placeholder

        Returns:
            Full webhook URL
        """
        if not base_url:
            base_url = 'https://your-muninn-instance.com'

        return f'{base_url}/webhooks/{self.agent_id}/{self.secret_token}'

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """
        Get the configuration schema for this agent.

        Returns:
            Configuration schema dictionary
        """
        schema = super().get_config_schema()
        schema['required_fields'] = []  # All fields auto-generated or optional
        schema['optional_fields'].extend([
            {
                'name': 'secret_token',
                'type': 'text',
                'auto_generate': True,
                'description': 'URL authentication token (auto-generated if not provided). Must be at least 16 characters.'
            },
            {
                'name': 'verify_signature',
                'type': 'boolean',
                'default': False,
                'description': 'Enable HMAC-SHA256 signature verification (GitHub/Stripe style). Sender must include X-Hub-Signature-256 header.'
            },
            {
                'name': 'signature_secret',
                'type': 'password',
                'description': 'Secret key for HMAC signature verification (required if verify_signature=True). Must match sender\'s secret.'
            },
            {
                'name': 'allowed_ips',
                'type': 'array',
                'default': [],
                'description': 'IP address whitelist (empty = allow all). Example: ["192.168.1.1", "10.0.0.0/8"]. Checks X-Forwarded-For header if present.'
            },
            {
                'name': 'include_headers',
                'type': 'array',
                'default': [],
                'description': 'HTTP headers to capture in event metadata. Example: ["User-Agent", "X-GitHub-Event", "X-Request-ID"]'
            },
            {
                'name': 'response_status',
                'type': 'integer',
                'default': 200,
                'description': 'HTTP status code to return to webhook sender (100-599). Use 200 for success, 201 for created, etc.'
            },
            {
                'name': 'response_body',
                'type': 'json',
                'default': {'status': 'success'},
                'description': 'JSON response body to return to webhook sender. Will always include "event_id" field.'
            }
        ])
        return schema

    def __repr__(self):
        """String representation of the agent."""
        # Mask the token for security
        masked_token = f'{self.secret_token[:8]}***' if len(self.secret_token) > 8 else '***'
        return f'<WebhookAgent {self.agent_id}: /webhooks/{self.agent_id}/{masked_token}>'
