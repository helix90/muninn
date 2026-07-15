"""
API Call Agent - Comprehensive RESTful API calling agent

This agent can make HTTP requests to any RESTful API with support for all HTTP methods
(GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS) and custom headers.
"""

import json
import logging
import requests
from typing import Any, Dict, List, Optional
from jinja2 import Environment, BaseLoader, TemplateError

from app.agents.base import SourceAgent
from app.agents.registry import register_agent
from app.models import Event

logger = logging.getLogger(__name__)


@register_agent
class APICallAgent(SourceAgent):
    """
    Source agent that makes RESTful API calls with full HTTP method support.

    Periodically calls APIs and emits events with the response data.
    Supports all HTTP methods: GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS
    Allows custom headers and credential templating.

    Configuration:
        url (str): API endpoint URL (supports credential templating)
        method (str): HTTP method (GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS)
        headers (dict): Custom HTTP headers (supports credential templating in values)
        payload_template (str): Request body template (for POST, PUT, PATCH)
        query_params (dict): URL query parameters (supports credential templating in values)
        content_type (str): Content-Type header (default: application/json)
        timeout (int): Request timeout in seconds (default: 30)
        verify_ssl (bool): Verify SSL certificates (default: true)
        follow_redirects (bool): Follow HTTP redirects (default: true)
        max_retries (int): Number of retry attempts on failure (default: 0)
    """

    agent_type = 'api_call_agent'
    agent_category = 'source'

    # Supported HTTP methods
    SUPPORTED_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS']

    def __init__(self, agent_id: int, config: Dict[str, Any], user_id: int, db_session=None):
        """Initialize the API call agent."""
        # Set instance variables BEFORE calling super().__init__()
        # because BaseAgent.__init__() calls validate_config() which needs these
        self.url = config.get('url', '')
        self.method = config.get('method', 'GET').upper()
        self.headers = config.get('headers', {})
        self.payload_template = config.get('payload_template', '')
        self.query_params = config.get('query_params', {})
        self.content_type = config.get('content_type', 'application/json')
        self.timeout = int(config.get('timeout', 30))
        self.verify_ssl = config.get('verify_ssl', True)
        self.follow_redirects = config.get('follow_redirects', True)
        self.max_retries = int(config.get('max_retries', 0))

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

        # Check required fields
        if not self.url:
            raise ValueError("URL is required")

        # Validate HTTP method
        if self.method not in self.SUPPORTED_METHODS:
            raise ValueError(f"Invalid HTTP method '{self.method}'. Supported: {', '.join(self.SUPPORTED_METHODS)}")

        # Validate headers is a dict
        if not isinstance(self.headers, dict):
            raise ValueError("Headers must be a dictionary")

        # Validate query_params is a dict
        if not isinstance(self.query_params, dict):
            raise ValueError("Query parameters must be a dictionary")

        # Validate timeout
        if self.timeout <= 0:
            raise ValueError("Timeout must be a positive integer")

        # Validate max_retries
        if self.max_retries < 0:
            raise ValueError("Max retries must be a non-negative integer")

        # Payload template only makes sense for certain methods
        if self.payload_template and self.method in ['GET', 'HEAD', 'OPTIONS']:
            raise ValueError(f"{self.method} requests cannot have a payload")

        # Validate URL template syntax
        try:
            env = Environment(loader=BaseLoader())
            env.from_string(self.url)
        except TemplateError as e:
            raise ValueError(f"Invalid URL template: {str(e)}")

        # Validate payload template syntax if present
        if self.payload_template:
            try:
                env = Environment(loader=BaseLoader())
                env.from_string(self.payload_template)
            except TemplateError as e:
                raise ValueError(f"Invalid payload template: {str(e)}")

    def fetch(self) -> List[Event]:
        """
        Make an API call and return events with the response data.

        Returns:
            List of events containing API response data
        """
        from datetime import datetime

        # Prepare template context (credentials only, no event data for SourceAgents)
        context = {}

        # Render URL with credential templating
        url = self._render_template(self.url, context, "URL")
        if not url:
            return []

        # Render query parameters
        params = {}
        for key, value_template in self.query_params.items():
            rendered_value = self._render_template(str(value_template), context, f"query param '{key}'")
            if rendered_value is not None:
                params[key] = rendered_value

        # Render headers
        headers = {}
        for key, value_template in self.headers.items():
            rendered_value = self._render_template(str(value_template), context, f"header '{key}'")
            if rendered_value is not None:
                headers[key] = rendered_value

        # Add Content-Type header if not already specified and method supports payload
        if self.method in ['POST', 'PUT', 'PATCH'] and 'Content-Type' not in headers:
            headers['Content-Type'] = self.content_type

        # Render payload for methods that support it
        payload = None
        if self.payload_template and self.method in ['POST', 'PUT', 'PATCH']:
            payload_str = self._render_template(self.payload_template, context, "payload")
            if payload_str is None:
                return []

            # Parse payload as JSON if content type is JSON
            if self.content_type == 'application/json':
                try:
                    payload = json.loads(payload_str)
                except json.JSONDecodeError as e:
                    self.log(f'Invalid JSON payload: {e}', level='error')
                    return []
            else:
                payload = payload_str

        # Make the API call with retries
        self.log(f'Making {self.method} request to {url}')
        response = self._send_request_with_retry(url, params, headers, payload)

        if response is None:
            return []

        # Create event payload with response data
        event_payload = {
            'url': url,
            'method': self.method,
            'status_code': response.status_code,
            'headers': dict(response.headers),
        }

        # Include response body if present
        if response.text:
            event_payload['response_body'] = response.text

            # Try to parse as JSON if content-type indicates JSON
            content_type = response.headers.get('content-type', '').lower()
            if 'application/json' in content_type:
                try:
                    event_payload['response_json'] = response.json()
                except json.JSONDecodeError:
                    pass  # Body is not valid JSON

        # Add metadata
        metadata = {
            'called_at': datetime.utcnow().isoformat(),
            'elapsed_ms': response.elapsed.total_seconds() * 1000,
            'final_url': response.url,  # After redirects
        }

        # Create event
        event = self.create_event(payload=event_payload, metadata=metadata)

        self.log(f'{self.method} {url} -> {response.status_code}', data={
            'status_code': response.status_code,
            'elapsed_ms': metadata['elapsed_ms']
        })

        return [event]

    def _send_request_with_retry(
        self,
        url: str,
        params: Dict[str, str],
        headers: Dict[str, str],
        payload: Optional[Any]
    ) -> Optional[requests.Response]:
        """
        Send HTTP request with retry logic.

        Args:
            url: Rendered URL
            params: Query parameters
            headers: HTTP headers
            payload: Request body (for POST, PUT, PATCH)

        Returns:
            Response object if successful, None otherwise
        """
        attempts = 0
        max_attempts = self.max_retries + 1

        while attempts < max_attempts:
            attempts += 1
            try:
                response = self._send_request(url, params, headers, payload)

                self.log(
                    f'{self.method} {url} -> {response.status_code} (attempt {attempts}/{max_attempts})',
                    level='debug'
                )

                # Check if response indicates success (2xx or 3xx)
                if 200 <= response.status_code < 400:
                    return response  # Success, return the response

                # Log non-success status
                self.log(
                    f'Non-success status {response.status_code}: {response.text[:200]}',
                    level='warning'
                )

                # Don't retry on client errors (4xx), but return the response
                if 400 <= response.status_code < 500:
                    return response

            except requests.exceptions.Timeout:
                self.log(
                    f'Request timeout (attempt {attempts}/{max_attempts})',
                    level='warning',
                    data={'url': url, 'timeout': self.timeout}
                )
            except requests.exceptions.ConnectionError as e:
                self.log(
                    f'Connection error (attempt {attempts}/{max_attempts}): {e}',
                    level='warning',
                    data={'url': url}
                )
            except Exception as e:
                self.log(f'Request failed: {e}', level='error', data={'url': url})
                return None  # Don't retry on unexpected errors

            # If we haven't returned yet and have retries left, continue loop
            if attempts < max_attempts:
                self.log('Retrying request...', level='debug')

        # All attempts exhausted
        return None

    def _send_request(
        self,
        url: str,
        params: Dict[str, str],
        headers: Dict[str, str],
        payload: Optional[Any]
    ) -> requests.Response:
        """
        Send HTTP request.

        Args:
            url: Target URL
            params: Query parameters
            headers: HTTP headers
            payload: Request body

        Returns:
            Response object
        """
        # Prepare request kwargs
        kwargs = {
            'params': params,
            'headers': headers,
            'timeout': self.timeout,
            'verify': self.verify_ssl,
            'allow_redirects': self.follow_redirects,
        }

        # Add payload for methods that support it
        if payload is not None and self.method in ['POST', 'PUT', 'PATCH']:
            if isinstance(payload, (dict, list)):
                kwargs['json'] = payload
            else:
                kwargs['data'] = payload

        # Make the request
        response = requests.request(self.method, url, **kwargs)

        return response

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
            return template.render(**context)
        except TemplateError as e:
            logger.error(f"APICallAgent {self.agent_id}: Error rendering {field_name}: {e}")
            return None
        except Exception as e:
            logger.error(f"APICallAgent {self.agent_id}: Unexpected error rendering {field_name}: {e}")
            return None

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """
        Get the configuration schema for this agent's configuration.

        Returns:
            Configuration schema dictionary
        """
        schema = super().get_config_schema()
        schema['required_fields'] = ['url']
        schema['optional_fields'].extend([
            {
                'name': 'method',
                'type': 'select',
                'options': [
                    {'value': 'GET', 'label': 'GET'},
                    {'value': 'POST', 'label': 'POST'},
                    {'value': 'PUT', 'label': 'PUT'},
                    {'value': 'PATCH', 'label': 'PATCH'},
                    {'value': 'DELETE', 'label': 'DELETE'},
                    {'value': 'HEAD', 'label': 'HEAD'},
                    {'value': 'OPTIONS', 'label': 'OPTIONS'}
                ],
                'default': 'GET',
                'description': 'HTTP method for the API request'
            },
            {
                'name': 'headers',
                'type': 'textarea',
                'default': '{}',
                'description': 'Custom HTTP headers as JSON object (values support Jinja2 templating). Example: {"Authorization": "Bearer {{credential:api_token}}"}'
            },
            {
                'name': 'query_params',
                'type': 'textarea',
                'default': '{}',
                'description': 'URL query parameters as JSON object (values support Jinja2 templating). Example: {"api_key": "{{credential:api_key}}", "limit": "10"}'
            },
            {
                'name': 'payload_template',
                'type': 'textarea',
                'default': '',
                'description': 'Request body template for POST/PUT/PATCH (Jinja2). Example: {"token": "{{credential:api_token}}", "data": "value"}'
            },
            {
                'name': 'content_type',
                'type': 'text',
                'default': 'application/json',
                'description': 'Content-Type header for the request'
            },
            {
                'name': 'timeout',
                'type': 'integer',
                'default': 30,
                'description': 'Request timeout in seconds (1-300)'
            },
            {
                'name': 'verify_ssl',
                'type': 'boolean',
                'default': True,
                'description': 'Verify SSL certificates'
            },
            {
                'name': 'follow_redirects',
                'type': 'boolean',
                'default': True,
                'description': 'Follow HTTP redirects automatically'
            },
            {
                'name': 'max_retries',
                'type': 'integer',
                'default': 0,
                'description': 'Number of retry attempts on failure (0-5)'
            }
        ])
        return schema

    def __repr__(self):
        """String representation of the agent."""
        return f'<APICallAgent {self.agent_id}: {self.method} {self.url}>'
