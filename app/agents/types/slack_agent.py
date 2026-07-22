"""Slack Agent — send messages to Slack channels via Incoming Webhooks."""

import logging
import time
import requests
from typing import Any, Dict, List, Optional
from jinja2 import Environment, BaseLoader, TemplateError, UndefinedError

from app.agents.base import ActionAgent
from app.agents.registry import register_agent
from app.models import Event

logger = logging.getLogger(__name__)


@register_agent
class SlackAgent(ActionAgent):
    """
    Action agent that sends messages to Slack channels via Incoming Webhooks.

    Configuration:
        webhook_url (str): Slack Incoming Webhook URL (required)
        message_template (str): Jinja2 message text (required)
        username (str): Override bot username (optional)
        icon_emoji (str): Override bot emoji e.g. ':robot_face:' (optional)
        icon_url (str): Override bot icon URL (optional)
        channel (str): Override channel e.g. '#alerts' (optional)
    """

    agent_type = 'slack_agent'
    agent_category = 'action'

    def __init__(self, agent_id: int, config: Dict[str, Any], user_id: int, db_session=None):
        self.webhook_url = config.get('webhook_url', '')
        self.message_template = config.get('message_template', '')
        self.username = config.get('username')
        self.icon_emoji = config.get('icon_emoji')
        self.icon_url = config.get('icon_url')
        self.channel = config.get('channel')
        super().__init__(agent_id, config, user_id, db_session)

    def validate_config(self) -> None:
        super().validate_config()
        if not self.webhook_url:
            raise ValueError("webhook_url is required")
        if not self.webhook_url.startswith('https://hooks.slack.com/'):
            raise ValueError(
                "webhook_url must be a Slack Incoming Webhook URL "
                "(https://hooks.slack.com/...)"
            )
        if not self.message_template:
            raise ValueError("message_template is required")
        try:
            Environment(loader=BaseLoader()).from_string(self.message_template)
        except TemplateError as e:
            raise ValueError(f"Invalid message_template syntax: {e}")

    def act(self, events: List[Event]) -> None:
        for event in events:
            try:
                context = self._build_context(event)
                text = self._render(self.message_template, context)
                if not text:
                    self.log('Skipping event: rendered message is empty', level='warning')
                    continue

                payload: Dict[str, Any] = {'text': text}
                if self.username:
                    payload['username'] = self.username
                if self.icon_emoji:
                    payload['icon_emoji'] = self.icon_emoji
                if self.icon_url:
                    payload['icon_url'] = self.icon_url
                if self.channel:
                    payload['channel'] = self.channel

                self.log(f'Sending Slack message to {self.webhook_url[:60]}...')
                response = requests.post(self.webhook_url, json=payload, timeout=30)

                if response.status_code == 200:
                    self.log('Slack message sent successfully')
                elif response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 1))
                    self.log(f'Rate limited — retrying after {retry_after}s', level='warning')
                    time.sleep(retry_after)
                    response = requests.post(self.webhook_url, json=payload, timeout=30)
                    if response.status_code == 200:
                        self.log('Slack message sent on retry')
                    else:
                        self.log(f'Slack retry failed: {response.status_code}', level='error')
                else:
                    self.log(
                        f'Slack webhook error {response.status_code}: {response.text[:200]}',
                        level='error'
                    )

            except UndefinedError as e:
                self.log(f'Template variable missing: {e}', level='error')
            except Exception as e:
                self.log(f'Error sending Slack message: {e}', level='error')

    def _build_context(self, event: Event) -> Dict[str, Any]:
        ctx: Dict[str, Any] = {}
        if event.payload:
            ctx.update(event.payload)
        if event.metadata:
            ctx['metadata'] = event.metadata
        ctx['event_id'] = event.id
        ctx['event_created_at'] = event.created_at.isoformat() if event.created_at else None
        return ctx

    def _render(self, template_str: str, context: Dict[str, Any]) -> Optional[str]:
        try:
            rendered = Environment(loader=BaseLoader()).from_string(template_str).render(**context)
            return rendered if rendered.strip() else None
        except UndefinedError:
            raise
        except TemplateError as e:
            logger.error(f'SlackAgent {self.agent_id}: template error: {e}')
            return None

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        schema = super().get_config_schema()
        schema['required_fields'] = ['webhook_url', 'message_template']
        schema['optional_fields'].extend([
            {
                'name': 'username',
                'type': 'text',
                'default': '',
                'description': 'Override the bot display name (optional)',
            },
            {
                'name': 'icon_emoji',
                'type': 'text',
                'default': '',
                'description': "Emoji for the bot icon e.g. ':bell:' (optional)",
            },
            {
                'name': 'icon_url',
                'type': 'text',
                'default': '',
                'description': 'URL for the bot icon image (optional)',
            },
            {
                'name': 'channel',
                'type': 'text',
                'default': '',
                'description': "Override destination channel e.g. '#alerts' (optional)",
            },
        ])
        return schema
