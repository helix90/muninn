"""Telegram Agent — send messages via the Telegram Bot API."""

import logging
import requests
from typing import Any, Dict, List, Optional
from jinja2 import Environment, BaseLoader, TemplateError, UndefinedError

from app.agents.base import ActionAgent
from app.agents.registry import register_agent
from app.models import Event

logger = logging.getLogger(__name__)

_TELEGRAM_API = 'https://api.telegram.org/bot'
_VALID_PARSE_MODES = ('Markdown', 'MarkdownV2', 'HTML')


@register_agent
class TelegramAgent(ActionAgent):
    """
    Action agent that sends messages to Telegram chats via the Bot API.

    Configuration:
        bot_token (str): Telegram Bot API token (required)
        chat_id (str): Target chat ID or @channel_username (required)
        message_template (str): Jinja2 message text (required)
        parse_mode (str): 'Markdown', 'MarkdownV2', or 'HTML' (optional)
        disable_web_page_preview (bool): Suppress link previews (default: false)
        disable_notification (bool): Send silently (default: false)
    """

    agent_type = 'telegram_agent'
    agent_category = 'action'

    def __init__(self, agent_id: int, config: Dict[str, Any], user_id: int, db_session=None):
        self.bot_token = config.get('bot_token', '')
        self.chat_id = str(config.get('chat_id', ''))
        self.message_template = config.get('message_template', '')
        self.parse_mode = config.get('parse_mode')
        self.disable_web_page_preview = bool(config.get('disable_web_page_preview', False))
        self.disable_notification = bool(config.get('disable_notification', False))
        super().__init__(agent_id, config, user_id, db_session)

    def validate_config(self) -> None:
        super().validate_config()
        if not self.bot_token:
            raise ValueError("bot_token is required")
        if not self.chat_id:
            raise ValueError("chat_id is required")
        if not self.message_template:
            raise ValueError("message_template is required")
        if self.parse_mode and self.parse_mode not in _VALID_PARSE_MODES:
            raise ValueError(
                f"parse_mode must be one of: {', '.join(_VALID_PARSE_MODES)}"
            )
        try:
            Environment(loader=BaseLoader()).from_string(self.message_template)
        except TemplateError as e:
            raise ValueError(f"Invalid message_template syntax: {e}")

    def act(self, events: List[Event]) -> None:
        url = f'{_TELEGRAM_API}{self.bot_token}/sendMessage'

        for event in events:
            try:
                context = self._build_context(event)
                text = self._render(self.message_template, context)
                if not text:
                    self.log('Skipping event: rendered message is empty', level='warning')
                    continue

                payload: Dict[str, Any] = {
                    'chat_id': self.chat_id,
                    'text': text,
                }
                if self.parse_mode:
                    payload['parse_mode'] = self.parse_mode
                if self.disable_web_page_preview:
                    payload['disable_web_page_preview'] = True
                if self.disable_notification:
                    payload['disable_notification'] = True

                self.log(f'Sending Telegram message to chat {self.chat_id}')
                response = requests.post(url, json=payload, timeout=30)
                data = response.json()

                if response.status_code == 200 and data.get('ok'):
                    self.log('Telegram message sent successfully')
                else:
                    error_desc = data.get('description', response.text[:200])
                    self.log(
                        f'Telegram API error {response.status_code}: {error_desc}',
                        level='error'
                    )

            except UndefinedError as e:
                self.log(f'Template variable missing: {e}', level='error')
            except Exception as e:
                self.log(f'Error sending Telegram message: {e}', level='error')

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
            logger.error(f'TelegramAgent {self.agent_id}: template error: {e}')
            return None

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        schema = super().get_config_schema()
        schema['required_fields'] = ['bot_token', 'chat_id', 'message_template']
        schema['optional_fields'].extend([
            {
                'name': 'parse_mode',
                'type': 'text',
                'default': '',
                'description': "Message formatting: 'Markdown', 'MarkdownV2', or 'HTML' (optional)",
            },
            {
                'name': 'disable_web_page_preview',
                'type': 'boolean',
                'default': False,
                'description': 'Disable link previews in the message',
            },
            {
                'name': 'disable_notification',
                'type': 'boolean',
                'default': False,
                'description': 'Send message silently (no notification sound)',
            },
        ])
        return schema
