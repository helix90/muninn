"""
Discord Webhook Agent - Send messages to Discord channels via webhooks

This agent sends formatted messages to Discord channels using webhooks. Supports rich embeds,
rate limiting, and Slack-compatible formatting.
"""

import json
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
class DiscordWebhookAgent(ActionAgent):
    """
    Action agent that sends messages to Discord channels via webhooks.

    Supports rich embeds, custom usernames/avatars, rate limiting, and Slack compatibility.
    For Slack-compatible format, append /slack to the webhook URL.

    Configuration:
        webhook_url (str): Discord webhook URL (required)
        content_template (str): Message content template (Jinja2)
        username (str): Override webhook username
        avatar_url (str): Override webhook avatar URL
        embed (dict): Rich embed object with title, description, fields, etc.
        tts (bool): Text-to-speech flag (default: false)
        rate_limit_per_minute (int): Max requests per minute (default: 30)
    """

    agent_type = 'discord_webhook_agent'
    agent_category = 'action'

    # Class-level rate limit tracker: {webhook_url: [timestamp1, timestamp2, ...]}
    _rate_limit_tracker: Dict[str, List[float]] = {}

    def __init__(self, agent_id: int, config: Dict[str, Any], user_id: int, db_session=None):
        """Initialize the Discord webhook agent."""
        # Set instance variables BEFORE calling super().__init__()
        # because BaseAgent.__init__() calls validate_config() which needs these
        self.webhook_url = config.get('webhook_url', '')
        self.content_template = config.get('content_template', '')
        self.username = config.get('username')
        self.avatar_url = config.get('avatar_url')
        self.embed_config = config.get('embed')
        self.tts = config.get('tts', False)
        self.rate_limit_per_minute = int(config.get('rate_limit_per_minute', 30))

        # Now call parent __init__ which will call validate_config()
        super().__init__(agent_id, config, user_id, db_session)

    def validate_config(self) -> None:
        """
        Validate agent configuration.

        Raises:
            ValueError: If configuration is invalid
        """
        # Call parent validation
        super().validate_config()

        # Validate webhook_url is required
        if not self.webhook_url:
            raise ValueError("webhook_url is required")

        # Validate webhook_url format
        if not isinstance(self.webhook_url, str):
            raise ValueError("webhook_url must be a string")

        # Check webhook URL format (Discord or Slack-compatible)
        valid_prefixes = [
            'https://discord.com/api/webhooks/',
            'https://discordapp.com/api/webhooks/'
        ]
        if not any(self.webhook_url.startswith(prefix) for prefix in valid_prefixes):
            raise ValueError(
                "webhook_url must start with https://discord.com/api/webhooks/ "
                "or https://discordapp.com/api/webhooks/"
            )

        # Must have either content_template or embed
        if not self.content_template and not self.embed_config:
            raise ValueError("At least one of content_template or embed is required")

        # Validate content_template syntax if present
        if self.content_template:
            if not isinstance(self.content_template, str):
                raise ValueError("content_template must be a string")
            try:
                env = Environment(loader=BaseLoader())
                env.from_string(self.content_template)
            except TemplateError as e:
                raise ValueError(f"Invalid content_template syntax: {str(e)}")

        # Validate username if present
        if self.username is not None and not isinstance(self.username, str):
            raise ValueError("username must be a string")

        # Validate avatar_url if present
        if self.avatar_url is not None:
            if not isinstance(self.avatar_url, str):
                raise ValueError("avatar_url must be a string")
            if not self.avatar_url.startswith(('http://', 'https://')):
                raise ValueError("avatar_url must be a valid URL")

        # Validate embed if present
        if self.embed_config is not None:
            if not isinstance(self.embed_config, dict):
                raise ValueError("embed must be a dictionary")
            self._validate_embed_config(self.embed_config)

        # Validate tts
        if not isinstance(self.tts, bool):
            raise ValueError("tts must be a boolean")

        # Validate rate_limit_per_minute
        if not isinstance(self.rate_limit_per_minute, int):
            raise ValueError("rate_limit_per_minute must be an integer")
        if not 1 <= self.rate_limit_per_minute <= 30:
            raise ValueError("rate_limit_per_minute must be between 1 and 30")

    def _validate_embed_config(self, embed: Dict[str, Any]) -> None:
        """
        Validate embed configuration structure.

        Args:
            embed: Embed configuration dictionary

        Raises:
            ValueError: If embed configuration is invalid
        """
        # Validate title if present
        if 'title' in embed:
            if not isinstance(embed['title'], str):
                raise ValueError("embed.title must be a string")
            # Validate as Jinja2 template
            try:
                env = Environment(loader=BaseLoader())
                env.from_string(embed['title'])
            except TemplateError as e:
                raise ValueError(f"Invalid embed.title template: {str(e)}")

        # Validate description if present
        if 'description' in embed:
            if not isinstance(embed['description'], str):
                raise ValueError("embed.description must be a string")
            # Validate as Jinja2 template
            try:
                env = Environment(loader=BaseLoader())
                env.from_string(embed['description'])
            except TemplateError as e:
                raise ValueError(f"Invalid embed.description template: {str(e)}")

        # Validate url if present
        if 'url' in embed:
            if not isinstance(embed['url'], str):
                raise ValueError("embed.url must be a string")
            # Validate as Jinja2 template
            try:
                env = Environment(loader=BaseLoader())
                env.from_string(embed['url'])
            except TemplateError as e:
                raise ValueError(f"Invalid embed.url template: {str(e)}")

        # Validate color if present
        if 'color' in embed:
            if not isinstance(embed['color'], int):
                raise ValueError("embed.color must be an integer")
            if not 0 <= embed['color'] <= 16777215:
                raise ValueError("embed.color must be between 0 and 16777215")

        # Validate fields if present
        if 'fields' in embed:
            if not isinstance(embed['fields'], list):
                raise ValueError("embed.fields must be a list")
            for i, field in enumerate(embed['fields']):
                if not isinstance(field, dict):
                    raise ValueError(f"embed.fields[{i}] must be a dictionary")
                if 'name' not in field or 'value' not in field:
                    raise ValueError(f"embed.fields[{i}] must have 'name' and 'value'")
                if not isinstance(field['name'], str):
                    raise ValueError(f"embed.fields[{i}].name must be a string")
                if not isinstance(field['value'], str):
                    raise ValueError(f"embed.fields[{i}].value must be a string")
                if 'inline' in field and not isinstance(field['inline'], bool):
                    raise ValueError(f"embed.fields[{i}].inline must be a boolean")

                # Validate field templates
                try:
                    env = Environment(loader=BaseLoader())
                    env.from_string(field['name'])
                    env.from_string(field['value'])
                except TemplateError as e:
                    raise ValueError(f"Invalid template in embed.fields[{i}]: {str(e)}")

        # Validate thumbnail if present
        if 'thumbnail' in embed:
            if not isinstance(embed['thumbnail'], dict):
                raise ValueError("embed.thumbnail must be a dictionary")
            if 'url' not in embed['thumbnail']:
                raise ValueError("embed.thumbnail must have 'url'")
            if not isinstance(embed['thumbnail']['url'], str):
                raise ValueError("embed.thumbnail.url must be a string")
            # Validate as Jinja2 template
            try:
                env = Environment(loader=BaseLoader())
                env.from_string(embed['thumbnail']['url'])
            except TemplateError as e:
                raise ValueError(f"Invalid embed.thumbnail.url template: {str(e)}")

        # Validate image if present
        if 'image' in embed:
            if not isinstance(embed['image'], dict):
                raise ValueError("embed.image must be a dictionary")
            if 'url' not in embed['image']:
                raise ValueError("embed.image must have 'url'")
            if not isinstance(embed['image']['url'], str):
                raise ValueError("embed.image.url must be a string")
            # Validate as Jinja2 template
            try:
                env = Environment(loader=BaseLoader())
                env.from_string(embed['image']['url'])
            except TemplateError as e:
                raise ValueError(f"Invalid embed.image.url template: {str(e)}")

        # Validate footer if present
        if 'footer' in embed:
            if not isinstance(embed['footer'], dict):
                raise ValueError("embed.footer must be a dictionary")
            if 'text' not in embed['footer']:
                raise ValueError("embed.footer must have 'text'")
            if not isinstance(embed['footer']['text'], str):
                raise ValueError("embed.footer.text must be a string")
            # Validate as Jinja2 template
            try:
                env = Environment(loader=BaseLoader())
                env.from_string(embed['footer']['text'])
            except TemplateError as e:
                raise ValueError(f"Invalid embed.footer.text template: {str(e)}")

            if 'icon_url' in embed['footer']:
                if not isinstance(embed['footer']['icon_url'], str):
                    raise ValueError("embed.footer.icon_url must be a string")
                # Validate as Jinja2 template
                try:
                    env = Environment(loader=BaseLoader())
                    env.from_string(embed['footer']['icon_url'])
                except TemplateError as e:
                    raise ValueError(f"Invalid embed.footer.icon_url template: {str(e)}")

        # Validate timestamp if present
        if 'timestamp' in embed:
            if not isinstance(embed['timestamp'], bool):
                raise ValueError("embed.timestamp must be a boolean")

    def act(self, events: List[Event]) -> None:
        """
        Send Discord webhook messages for each event.

        Args:
            events: List of events to process
        """
        from datetime import datetime

        for event in events:
            try:
                # Prepare template context from event
                context = self._build_template_context(event)

                # Build webhook payload
                payload = self._build_payload(context)

                if not payload:
                    self.log('Skipping event: no content to send', level='warning')
                    continue

                # Wait for rate limit if necessary
                self._wait_for_rate_limit()

                # Send webhook request
                self.log(f'Sending Discord webhook to {self.webhook_url[:50]}...')
                response = self._send_request_with_retry(payload)

                if response is not None:
                    self.log(
                        f'Discord webhook sent successfully: {response.status_code}',
                        level='info'
                    )
                else:
                    self.log('Failed to send Discord webhook', level='error')

            except UndefinedError as e:
                self.log(f'Template rendering failed (missing variable): {e}', level='error')
                continue
            except Exception as e:
                self.log(f'Error processing event: {e}', level='error')
                continue

    def _build_template_context(self, event: Event) -> Dict[str, Any]:
        """
        Build Jinja2 template context from event.

        Args:
            event: Event to process

        Returns:
            Template context dictionary
        """
        context = {}

        # Add event payload fields directly to context
        if event.payload:
            context.update(event.payload)

        # Add event metadata if present
        if event.metadata:
            context['metadata'] = event.metadata

        # Add event ID and created_at
        context['event_id'] = event.id
        context['event_created_at'] = event.created_at.isoformat() if event.created_at else None

        return context

    def _build_payload(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Build Discord webhook payload from template context.

        Args:
            context: Template context dictionary

        Returns:
            Webhook payload dictionary or None if rendering failed
        """
        payload = {}

        # Render content if present
        if self.content_template:
            content = self._render_template(self.content_template, context, 'content')
            if content:
                payload['content'] = content

        # Add username if present
        if self.username:
            payload['username'] = self.username

        # Add avatar_url if present
        if self.avatar_url:
            payload['avatar_url'] = self.avatar_url

        # Add tts flag
        if self.tts:
            payload['tts'] = True

        # Build embed if present
        if self.embed_config:
            embed = self._build_embed(self.embed_config, context)
            if embed:
                payload['embeds'] = [embed]

        # Return None if no content or embeds
        if 'content' not in payload and 'embeds' not in payload:
            return None

        return payload

    def _build_embed(self, embed_config: Dict[str, Any], context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Build Discord embed object from configuration and context.

        Args:
            embed_config: Embed configuration dictionary
            context: Template context dictionary

        Returns:
            Embed dictionary or None if rendering failed
        """
        from datetime import datetime

        embed = {}

        # Render title if present
        if 'title' in embed_config:
            title = self._render_template(embed_config['title'], context, 'embed.title')
            if title:
                embed['title'] = title

        # Render description if present
        if 'description' in embed_config:
            description = self._render_template(embed_config['description'], context, 'embed.description')
            if description:
                embed['description'] = description

        # Render url if present
        if 'url' in embed_config:
            url = self._render_template(embed_config['url'], context, 'embed.url')
            if url:
                embed['url'] = url

        # Add color if present
        if 'color' in embed_config:
            embed['color'] = embed_config['color']

        # Build fields if present
        if 'fields' in embed_config:
            fields = []
            for field_config in embed_config['fields']:
                name = self._render_template(field_config['name'], context, 'field.name')
                value = self._render_template(field_config['value'], context, 'field.value')
                if name and value:
                    field = {'name': name, 'value': value}
                    if 'inline' in field_config:
                        field['inline'] = field_config['inline']
                    fields.append(field)
            if fields:
                embed['fields'] = fields

        # Add thumbnail if present
        if 'thumbnail' in embed_config:
            thumbnail_url = self._render_template(
                embed_config['thumbnail']['url'],
                context,
                'embed.thumbnail.url'
            )
            if thumbnail_url:
                embed['thumbnail'] = {'url': thumbnail_url}

        # Add image if present
        if 'image' in embed_config:
            image_url = self._render_template(
                embed_config['image']['url'],
                context,
                'embed.image.url'
            )
            if image_url:
                embed['image'] = {'url': image_url}

        # Add footer if present
        if 'footer' in embed_config:
            footer_text = self._render_template(
                embed_config['footer']['text'],
                context,
                'embed.footer.text'
            )
            if footer_text:
                footer = {'text': footer_text}
                if 'icon_url' in embed_config['footer']:
                    icon_url = self._render_template(
                        embed_config['footer']['icon_url'],
                        context,
                        'embed.footer.icon_url'
                    )
                    if icon_url:
                        footer['icon_url'] = icon_url
                embed['footer'] = footer

        # Add timestamp if requested
        if embed_config.get('timestamp'):
            embed['timestamp'] = datetime.utcnow().isoformat()

        # Return None if embed is empty
        if not embed:
            return None

        return embed

    def _render_template(self, template_str: str, context: Dict[str, Any], field_name: str) -> Optional[str]:
        """
        Render a Jinja2 template string.

        Args:
            template_str: Template string
            context: Template context
            field_name: Field name for error messages

        Returns:
            Rendered string or None if rendering failed
        """
        try:
            env = Environment(loader=BaseLoader())
            template = env.from_string(template_str)
            rendered = template.render(**context)
            # Return None if rendered string is empty
            return rendered if rendered.strip() else None
        except UndefinedError as e:
            # Re-raise undefined errors so they can be caught by act()
            raise
        except TemplateError as e:
            logger.error(f"DiscordWebhookAgent {self.agent_id}: Error rendering {field_name}: {e}")
            return None
        except Exception as e:
            logger.error(f"DiscordWebhookAgent {self.agent_id}: Unexpected error rendering {field_name}: {e}")
            return None

    def _wait_for_rate_limit(self) -> None:
        """
        Wait if rate limit is reached for this webhook URL.

        Uses token bucket algorithm to track requests per minute.
        """
        current_time = time.time()

        # Initialize tracker for this webhook URL if needed
        if self.webhook_url not in self._rate_limit_tracker:
            self._rate_limit_tracker[self.webhook_url] = []

        # Get request times for this webhook
        request_times = self._rate_limit_tracker[self.webhook_url]

        # Remove timestamps older than 60 seconds
        cutoff = current_time - 60
        request_times[:] = [t for t in request_times if t > cutoff]

        # Wait if at limit
        if len(request_times) >= self.rate_limit_per_minute:
            oldest = request_times[0]
            wait_time = 60 - (current_time - oldest)
            if wait_time > 0:
                self.log(
                    f'Rate limit reached ({self.rate_limit_per_minute} req/min), '
                    f'waiting {wait_time:.1f}s',
                    level='warning'
                )
                time.sleep(wait_time)
                # Update current time after sleeping
                current_time = time.time()

        # Record this request
        request_times.append(current_time)

    def _send_request_with_retry(self, payload: Dict[str, Any]) -> Optional[requests.Response]:
        """
        Send Discord webhook request with retry logic for 429 responses.

        Args:
            payload: Webhook payload dictionary

        Returns:
            Response object if successful, None otherwise
        """
        max_retries = 1
        for attempt in range(max_retries + 1):
            try:
                response = self._send_request(payload)

                # Success (Discord returns 204 No Content)
                if response.status_code == 204:
                    return response

                # Rate limited (429) - retry once
                if response.status_code == 429:
                    if attempt < max_retries:
                        # Try to extract retry_after from response
                        retry_after = 1.0
                        try:
                            error_data = response.json()
                            retry_after = error_data.get('retry_after', 1.0)
                        except Exception:
                            pass

                        self.log(
                            f'Rate limited (429), retrying after {retry_after}s',
                            level='warning'
                        )
                        time.sleep(retry_after)
                        continue
                    else:
                        self.log('Rate limited (429), no retries left', level='error')
                        return None

                # Client error (4xx) - don't retry
                if 400 <= response.status_code < 500:
                    self.log(
                        f'Client error {response.status_code}: {response.text[:200]}',
                        level='error'
                    )
                    return None

                # Server error (5xx) - don't retry (could be Discord issue)
                if 500 <= response.status_code < 600:
                    self.log(
                        f'Server error {response.status_code}: {response.text[:200]}',
                        level='error'
                    )
                    return None

                # Other status codes
                self.log(
                    f'Unexpected status {response.status_code}: {response.text[:200]}',
                    level='warning'
                )
                return response

            except requests.exceptions.Timeout:
                self.log('Request timeout', level='warning')
                return None
            except requests.exceptions.ConnectionError as e:
                self.log(f'Connection error: {e}', level='warning')
                return None
            except Exception as e:
                self.log(f'Request failed: {e}', level='error')
                return None

        return None

    def _send_request(self, payload: Dict[str, Any]) -> requests.Response:
        """
        Send HTTP POST request to Discord webhook.

        Args:
            payload: Webhook payload dictionary

        Returns:
            Response object
        """
        response = requests.post(
            self.webhook_url,
            json=payload,
            timeout=30
        )
        return response

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """
        Get the configuration schema for this agent's configuration.

        Returns:
            Configuration schema dictionary
        """
        schema = super().get_config_schema()
        schema['required_fields'] = ['webhook_url']
        schema['optional_fields'].extend([
            {
                'name': 'content_template',
                'type': 'textarea',
                'default': '',
                'description': 'Message content template (Jinja2). At least one of content_template or embed is required. Example: "New article: {{ title }}"'
            },
            {
                'name': 'username',
                'type': 'text',
                'default': '',
                'description': 'Override webhook username (optional)'
            },
            {
                'name': 'avatar_url',
                'type': 'text',
                'default': '',
                'description': 'Override webhook avatar URL (optional)'
            },
            {
                'name': 'embed',
                'type': 'textarea',
                'default': '{}',
                'description': 'Rich embed object as JSON. Supports title, description, url, color, fields, thumbnail, image, footer, timestamp. Example: {"title": "{{ title }}", "description": "{{ summary }}", "color": 3447003}'
            },
            {
                'name': 'tts',
                'type': 'boolean',
                'default': False,
                'description': 'Enable text-to-speech for message'
            },
            {
                'name': 'rate_limit_per_minute',
                'type': 'integer',
                'default': 30,
                'description': 'Maximum requests per minute (1-30, Discord limit is 30)'
            }
        ])
        return schema

    def __repr__(self):
        """String representation of the agent."""
        return f'<DiscordWebhookAgent {self.agent_id}: {self.webhook_url[:50]}...>'
