"""
Web Fetch Agent - HTTP GET requests

Single responsibility: ONLY fetch web pages via HTTP GET.
Does NOT parse HTML or extract data (that's HTMLParserAgent's job).
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import requests
from app.agents.base import SourceAgent
from app.agents.registry import register_agent
from app.models import Event


@register_agent
class WebFetchAgent(SourceAgent):
    """
    Fetches web pages via HTTP GET.

    Configuration:
        url (str): URL to fetch
        headers (dict): Optional HTTP headers
        timeout (int): Request timeout in seconds (default: 30)
        verify_ssl (bool): Verify SSL certificates (default: True)
        follow_redirects (bool): Follow HTTP redirects (default: True)
        max_size (int): Maximum response size in bytes (default: 10MB)
    """

    agent_type = 'web_fetch_agent'

    def validate_config(self) -> None:
        """Validate web fetch agent configuration."""
        super().validate_config()

        if 'url' not in self.config:
            raise ValueError("Web fetch agent requires 'url' in config")

        if not isinstance(self.config['url'], str):
            raise ValueError("'url' must be a string")

        if not self.config['url'].startswith(('http://', 'https://')):
            raise ValueError("'url' must be a valid HTTP(S) URL")

        # Validate optional fields
        if 'headers' in self.config:
            if not isinstance(self.config['headers'], dict):
                raise ValueError("'headers' must be a dictionary")

        if 'timeout' in self.config:
            if not isinstance(self.config['timeout'], int) or self.config['timeout'] < 1:
                raise ValueError("'timeout' must be a positive integer")

        if 'verify_ssl' in self.config:
            if not isinstance(self.config['verify_ssl'], bool):
                raise ValueError("'verify_ssl' must be a boolean")

        if 'follow_redirects' in self.config:
            if not isinstance(self.config['follow_redirects'], bool):
                raise ValueError("'follow_redirects' must be a boolean")

        if 'max_size' in self.config:
            if not isinstance(self.config['max_size'], int) or self.config['max_size'] < 1:
                raise ValueError("'max_size' must be a positive integer")

    def fetch(self) -> List[Event]:
        """
        Fetch web page via HTTP GET.

        Returns:
            List containing single Event with response data
        """
        url = self.config['url']
        headers = self.config.get('headers', {})
        timeout = self.config.get('timeout', 30)
        verify_ssl = self.config.get('verify_ssl', True)
        follow_redirects = self.config.get('follow_redirects', True)
        max_size = self.config.get('max_size', 10 * 1024 * 1024)  # 10MB default

        self.log(f'Fetching URL: {url}')

        try:
            # Make HTTP GET request
            response = requests.get(
                url,
                headers=headers,
                timeout=timeout,
                verify=verify_ssl,
                allow_redirects=follow_redirects,
                stream=True  # Stream to check size
            )

            # Check response size
            content_length = response.headers.get('content-length')
            if content_length and int(content_length) > max_size:
                self.log(f'Response too large: {content_length} bytes (max: {max_size})',
                        level='error')
                return []

            # Read response content
            content = b''
            for chunk in response.iter_content(chunk_size=8192):
                content += chunk
                if len(content) > max_size:
                    self.log(f'Response exceeded max size: {max_size} bytes',
                            level='error')
                    return []

            # Decode content
            try:
                text_content = content.decode(response.encoding or 'utf-8')
            except UnicodeDecodeError:
                # Try common encodings
                for encoding in ['utf-8', 'iso-8859-1', 'windows-1252']:
                    try:
                        text_content = content.decode(encoding)
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    # Fall back to binary
                    text_content = content.decode('utf-8', errors='replace')

            # Create event payload
            payload = {
                'url': url,
                'status_code': response.status_code,
                'content': text_content,
                'content_type': response.headers.get('content-type', ''),
                'content_length': len(content),
            }

            # Add metadata
            metadata = {
                'fetched_at': datetime.utcnow().isoformat(),
                'final_url': response.url,  # After redirects
                'headers': dict(response.headers),
                'encoding': response.encoding,
                'elapsed_ms': response.elapsed.total_seconds() * 1000
            }

            # Create event
            event = self.create_event(payload=payload, metadata=metadata)

            self.log(f'Fetched URL successfully', data={
                'url': url,
                'status_code': response.status_code,
                'content_length': len(content),
                'elapsed_ms': metadata['elapsed_ms']
            })

            return [event]

        except requests.exceptions.Timeout:
            self.log(f'Request timeout after {timeout}s', level='error', data={
                'url': url,
                'timeout': timeout
            })
            return []

        except requests.exceptions.SSLError as e:
            self.log(f'SSL error: {e}', level='error', data={
                'url': url,
                'error': str(e)
            })
            return []

        except requests.exceptions.RequestException as e:
            self.log(f'Request error: {e}', level='error', data={
                'url': url,
                'error': str(e)
            })
            return []

        except Exception as e:
            self.log(f'Unexpected error fetching URL: {e}', level='error', data={
                'url': url,
                'error': str(e)
            })
            return []

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """Get configuration schema for web fetch agent."""
        schema = super().get_config_schema()
        schema['required_fields'] = ['url']
        schema['optional_fields'] = [
            {
                'name': 'headers',
                'type': 'object',
                'default': {},
                'description': 'HTTP headers to send with request'
            },
            {
                'name': 'timeout',
                'type': 'integer',
                'default': 30,
                'description': 'Request timeout in seconds'
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
                'description': 'Follow HTTP redirects'
            },
            {
                'name': 'max_size',
                'type': 'integer',
                'default': 10485760,  # 10MB
                'description': 'Maximum response size in bytes'
            }
        ]
        return schema
