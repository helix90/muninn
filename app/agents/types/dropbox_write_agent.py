"""
Dropbox Write Agent — upload event payload content to Dropbox.

Single responsibility: ONLY writes files to Dropbox. Does not read.

Authentication uses a Dropbox API access token stored via the credential vault:
    "access_token": "{{credential:dropbox_token}}"
"""

import json
from typing import List

import requests
from jinja2 import Template, TemplateSyntaxError, UndefinedError

from app.agents.base import ActionAgent
from app.agents.registry import register_agent
from app.models import Event


@register_agent
class DropboxWriteAgent(ActionAgent):
    """
    For each incoming event, renders the configured path and content templates
    and uploads the result as a file to Dropbox.

    Configuration:
        access_token (str): Dropbox API access token.
            Use {{credential:dropbox_token}} to pull from the credential vault.
        path_template (str): Jinja2 template for the destination path,
            e.g. "/reports/{{name}}.txt" or "/backup/{{server_modified}}.json".
        content_template (str): Jinja2 template for the file content.
        mode (str): How to handle an existing file at the destination.
            "overwrite" replaces it; "add" creates a new auto-renamed file.
            Default: "overwrite".
    """

    agent_type = 'dropbox_write_agent'
    agent_category = 'action'

    def validate_config(self) -> None:
        super().validate_config()
        if not self.config.get('access_token'):
            raise ValueError(
                "'access_token' is required. Use {{credential:dropbox_token}} "
                "to reference a stored credential."
            )
        if not self.config.get('path_template'):
            raise ValueError(
                "'path_template' is required (e.g. '/reports/{{name}}.txt')"
            )
        if not self.config.get('content_template'):
            raise ValueError("'content_template' is required")
        if 'mode' in self.config and self.config['mode'] not in ('overwrite', 'add'):
            raise ValueError("'mode' must be 'overwrite' or 'add'")
        for field in ('path_template', 'content_template'):
            try:
                Template(self.config[field])
            except TemplateSyntaxError as e:
                raise ValueError(f"Invalid Jinja2 syntax in '{field}': {e}")

    def act(self, events: List[Event]) -> None:
        access_token = self.config['access_token']
        mode = self.config.get('mode', 'overwrite')

        for event in events:
            try:
                data = event.payload or {}
                path = self._render(self.config['path_template'], data)
                content = self._render(self.config['content_template'], data)

                resp = requests.post(
                    'https://content.dropboxapi.com/2/files/upload',
                    headers={
                        'Authorization': f'Bearer {access_token}',
                        'Content-Type': 'application/octet-stream',
                        'Dropbox-API-Arg': json.dumps({
                            'path': path,
                            'mode': mode,
                            'autorename': False,
                            'mute': False,
                        }),
                    },
                    data=content.encode('utf-8'),
                    timeout=60,
                )
                resp.raise_for_status()
                result = resp.json()
                self.log(
                    f"Uploaded {result.get('path_display', path)!r}",
                    level='info',
                    data={
                        'path': result.get('path_display'),
                        'size': result.get('size'),
                        'rev': result.get('rev'),
                    },
                )

            except Exception as e:
                self.log(
                    f'Failed to write to Dropbox: {e}',
                    level='error',
                    data={'event_id': event.id, 'error': str(e)},
                )
                if hasattr(self, '_test_mode_errors'):
                    self._test_mode_errors.append(str(e))

    def _render(self, template_str: str, data: dict) -> str:
        try:
            return Template(template_str).render(**data)
        except UndefinedError as e:
            return f'[Template Error: {e}]'
