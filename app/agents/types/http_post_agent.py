"""
HTTP POST Agent - Send HTTP POST requests

Single responsibility: ONLY sends HTTP POST requests.
Does NOT create new events (terminal agent).
"""

from typing import List, Dict, Any, Optional
import requests
import json
from jinja2 import Template, TemplateSyntaxError, UndefinedError
from app.agents.base import ActionAgent
from app.agents.registry import register_agent
from app.models import Event


@register_agent
class HTTPPostAgent(ActionAgent):
    """
    Sends HTTP POST requests with event data.

    Terminal agent: consumes events but does not create new ones.
    Useful for webhooks, APIs, and external integrations.

    Configuration:
        url (str): Target URL, can use Jinja2 template
        method (str): HTTP method (default: 'POST', can be 'POST', 'PUT', 'PATCH')
        headers (dict, optional): HTTP headers, values can use Jinja2 templates
        payload_template (str, optional): Jinja2 template for request body (JSON)
        content_type (str): Content-Type header (default: 'application/json')
        timeout (int): Request timeout in seconds (default: 30)
        verify_ssl (bool): Verify SSL certificates (default: True)
        emit_events (bool): Emit response as events (default: False, DEPRECATED)
    """

    agent_type = 'http_post_agent'

    def validate_config(self) -> None:
        """Validate HTTP POST agent configuration."""
        super().validate_config()

        # Required URL
        if 'url' not in self.config:
            raise ValueError("HTTP POST agent requires 'url' in config")

        if not isinstance(self.config['url'], str):
            raise ValueError("'url' must be a string")

        # Test URL template syntax
        try:
            Template(self.config['url'])
        except TemplateSyntaxError as e:
            raise ValueError(f"Invalid Jinja2 syntax in 'url': {e}")

        # Optional method
        if 'method' in self.config:
            method = self.config['method'].upper()
            if method not in ['POST', 'PUT', 'PATCH', 'DELETE']:
                raise ValueError("'method' must be one of: POST, PUT, PATCH, DELETE")

        # Optional headers
        if 'headers' in self.config:
            if not isinstance(self.config['headers'], dict):
                raise ValueError("'headers' must be a dictionary")

            # Test header value templates
            for key, value in self.config['headers'].items():
                if not isinstance(value, str):
                    raise ValueError(f"Header '{key}' value must be a string")
                try:
                    Template(value)
                except TemplateSyntaxError as e:
                    raise ValueError(f"Invalid Jinja2 syntax in header '{key}': {e}")

        # Optional payload template
        if 'payload_template' in self.config:
            if not isinstance(self.config['payload_template'], str):
                raise ValueError("'payload_template' must be a string")

            # Test payload template syntax
            try:
                Template(self.config['payload_template'])
            except TemplateSyntaxError as e:
                raise ValueError(f"Invalid Jinja2 syntax in 'payload_template': {e}")

        # Optional content_type
        if 'content_type' in self.config:
            if not isinstance(self.config['content_type'], str):
                raise ValueError("'content_type' must be a string")

        # Optional timeout
        if 'timeout' in self.config:
            timeout = self.config['timeout']
            if not isinstance(timeout, (int, float)) or timeout <= 0:
                raise ValueError("'timeout' must be a positive number")

        # Optional verify_ssl
        if 'verify_ssl' in self.config:
            if not isinstance(self.config['verify_ssl'], bool):
                raise ValueError("'verify_ssl' must be a boolean")

    def process(self, events: List[Event]) -> List[Event]:
        """
        Send HTTP POST requests for each event.

        Args:
            events: Events to process

        Returns:
            Empty list (terminal agent does not create events)
        """
        method = self.config.get('method', 'POST').upper()
        content_type = self.config.get('content_type', 'application/json')
        timeout = self.config.get('timeout', 30)
        verify_ssl = self.config.get('verify_ssl', True)

        success_count = 0
        failed_count = 0

        for event in events:
            try:
                # Render URL template
                url = self._render_template(self.config['url'], event.payload)

                # Prepare headers
                headers = {'Content-Type': content_type}
                if 'headers' in self.config:
                    for key, value_template in self.config['headers'].items():
                        rendered_value = self._render_template(value_template, event.payload)
                        headers[key] = rendered_value

                # Prepare payload
                if 'payload_template' in self.config:
                    # Use custom template
                    payload_str = self._render_template(self.config['payload_template'], event.payload)
                    try:
                        payload = json.loads(payload_str)
                    except json.JSONDecodeError as e:
                        self.log(f'Invalid JSON in payload template: {e}', level='error', data={
                            'event_id': event.id,
                            'payload_str': payload_str
                        })
                        failed_count += 1
                        continue
                else:
                    # Use event payload directly
                    payload = event.payload

                # Send request
                response = self._send_request(method, url, headers, payload, timeout, verify_ssl)

                success_count += 1
                self.log(f'{method} request sent successfully', level='info', data={
                    'event_id': event.id,
                    'url': url,
                    'status_code': response.status_code,
                    'response_size': len(response.content)
                })

            except requests.exceptions.Timeout:
                failed_count += 1
                self.log(f'{method} request timed out', level='error', data={
                    'event_id': event.id,
                    'url': url,
                    'timeout': timeout
                })

            except requests.exceptions.RequestException as e:
                failed_count += 1
                self.log(f'{method} request failed: {e}', level='error', data={
                    'event_id': event.id,
                    'url': url,
                    'error': str(e)
                })

            except Exception as e:
                failed_count += 1
                self.log(f'Unexpected error sending {method} request: {e}', level='error', data={
                    'event_id': event.id,
                    'error': str(e)
                })

        self.log(f'Processed {len(events)} events', data={
            'success_count': success_count,
            'failed_count': failed_count,
            'method': method
        })

        # Terminal agent: return empty list
        return []

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

    def _send_request(self, method: str, url: str, headers: Dict[str, str],
                     payload: Any, timeout: int, verify_ssl: bool) -> requests.Response:
        """
        Send HTTP request.

        Args:
            method: HTTP method (POST, PUT, PATCH, DELETE)
            url: Target URL
            headers: HTTP headers
            payload: Request payload
            timeout: Timeout in seconds
            verify_ssl: Verify SSL certificates

        Returns:
            Response object

        Raises:
            requests.exceptions.RequestException on failure
        """
        if method == 'POST':
            response = requests.post(url, json=payload, headers=headers,
                                    timeout=timeout, verify=verify_ssl)
        elif method == 'PUT':
            response = requests.put(url, json=payload, headers=headers,
                                   timeout=timeout, verify=verify_ssl)
        elif method == 'PATCH':
            response = requests.patch(url, json=payload, headers=headers,
                                     timeout=timeout, verify=verify_ssl)
        elif method == 'DELETE':
            response = requests.delete(url, json=payload, headers=headers,
                                      timeout=timeout, verify=verify_ssl)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

        # Raise exception for bad status codes
        response.raise_for_status()

        return response

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """Get configuration schema for HTTP POST agent."""
        schema = super().get_config_schema()
        schema['required_fields'] = ['url']
        schema['optional_fields'] = [
            {
                'name': 'method',
                'type': 'string',
                'default': 'POST',
                'options': ['POST', 'PUT', 'PATCH', 'DELETE'],
                'description': 'HTTP method to use'
            },
            {
                'name': 'headers',
                'type': 'object',
                'description': 'HTTP headers (values can be Jinja2 templates)'
            },
            {
                'name': 'payload_template',
                'type': 'string',
                'description': 'Jinja2 template for request body (must render to valid JSON). If not provided, uses event payload directly.'
            },
            {
                'name': 'content_type',
                'type': 'string',
                'default': 'application/json',
                'description': 'Content-Type header'
            },
            {
                'name': 'timeout',
                'type': 'number',
                'default': 30,
                'description': 'Request timeout in seconds'
            },
            {
                'name': 'verify_ssl',
                'type': 'boolean',
                'default': True,
                'description': 'Verify SSL certificates'
            }
        ]
        schema['template_context'] = {
            'description': 'Templates have access to all event payload fields',
            'example_url': 'https://api.example.com/webhooks/{{ webhook_id }}',
            'example_payload': '{"title": "{{ title }}", "message": "{{ description }}", "priority": {{ priority }}}',
            'example_headers': {'Authorization': 'Bearer {{ api_token }}', 'X-Custom-Header': '{{ custom_value }}'}
        }
        return schema
