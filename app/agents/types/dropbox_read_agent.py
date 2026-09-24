"""
Dropbox Read Agent — monitor a Dropbox folder for new or modified files.

Single responsibility: ONLY detects new/modified files in a configured Dropbox
folder and emits one event per file. Does not write anything.

Authentication uses a Dropbox API access token stored via the credential vault:
    "access_token": "{{credential:dropbox_token}}"
"""

import json
from typing import List, Optional

import requests

from app.agents.base import SourceAgent
from app.agents.registry import register_agent
from app.models import Event


@register_agent
class DropboxReadAgent(SourceAgent):
    """
    Monitors a Dropbox folder for new or modified files and emits one event per
    file. Uses agent memory (keyed by file path + revision) to avoid re-emitting
    the same file revision on subsequent runs.

    Configuration:
        access_token (str): Dropbox API access token.
            Use {{credential:dropbox_token}} to pull from the credential vault.
        folder_path (str): Dropbox folder to monitor (e.g. "/reports").
            Use "" (empty string) for the root folder.
        read_content (bool): If True, download each file and include its text
            content in the event payload. Default: False.
        file_filter (str, optional): Only emit events for files whose names
            contain this substring (case-insensitive).
        max_files (int): Maximum number of new files to emit per run. Default: 50.
    """

    agent_type = 'dropbox_read_agent'
    agent_category = 'source'

    def validate_config(self) -> None:
        super().validate_config()
        if not self.config.get('access_token'):
            raise ValueError(
                "'access_token' is required. Use {{credential:dropbox_token}} "
                "to reference a stored credential."
            )
        if 'folder_path' not in self.config:
            raise ValueError(
                "'folder_path' is required (e.g. '/reports'). "
                "Use \"\" for the Dropbox root."
            )
        if 'read_content' in self.config and not isinstance(self.config['read_content'], bool):
            raise ValueError("'read_content' must be a boolean")
        if 'max_files' in self.config:
            v = self.config['max_files']
            if not isinstance(v, int) or v < 1:
                raise ValueError("'max_files' must be a positive integer")

    def fetch(self) -> List[Event]:
        access_token = self.config['access_token']
        folder_path = self.config['folder_path']
        read_content = self.config.get('read_content', False)
        file_filter = self.config.get('file_filter', '').lower()
        max_files = self.config.get('max_files', 50)

        auth_header = {'Authorization': f'Bearer {access_token}'}
        entries = self._list_folder(folder_path, auth_header)

        events = []
        for entry in entries:
            if entry.get('.tag') != 'file':
                continue

            name = entry.get('name', '')
            if file_filter and file_filter not in name.lower():
                continue

            path = entry.get('path_lower', '')
            rev = entry.get('rev', '')
            if self.memory.get(f'rev:{path}') == rev:
                continue  # already emitted this revision

            payload = {
                'name': name,
                'path': entry.get('path_display', path),
                'size': entry.get('size', 0),
                'server_modified': entry.get('server_modified', ''),
                'client_modified': entry.get('client_modified', ''),
                'rev': rev,
                'id': entry.get('id', ''),
            }

            if read_content:
                content = self._download_file(path, auth_header)
                if content is not None:
                    payload['content'] = content

            self.memory.set(f'rev:{path}', rev)
            events.append(self.create_event(payload=payload))

            if len(events) >= max_files:
                break

        self.log(f'Emitting {len(events)} new/modified file(s) from {folder_path!r}')
        return events

    def _list_folder(self, folder_path: str, auth_header: dict) -> List[dict]:
        """List all file entries in folder_path, handling Dropbox pagination."""
        json_header = {**auth_header, 'Content-Type': 'application/json'}
        resp = requests.post(
            'https://api.dropboxapi.com/2/files/list_folder',
            headers=json_header,
            json={'path': folder_path, 'recursive': False, 'limit': 200},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        entries = list(data.get('entries', []))

        while data.get('has_more'):
            resp = requests.post(
                'https://api.dropboxapi.com/2/files/list_folder/continue',
                headers=json_header,
                json={'cursor': data['cursor']},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            entries.extend(data.get('entries', []))

        return entries

    def _download_file(self, path: str, auth_header: dict) -> Optional[str]:
        """Download a file from Dropbox and return its decoded text content."""
        resp = requests.post(
            'https://content.dropboxapi.com/2/files/download',
            headers={
                **auth_header,
                'Dropbox-API-Arg': json.dumps({'path': path}),
            },
            timeout=60,
        )
        if resp.status_code == 200:
            return resp.text
        self.log(
            f'Could not download {path!r}: HTTP {resp.status_code}',
            level='warning',
        )
        return None

    @classmethod
    def get_config_schema(cls):
        schema = super().get_config_schema()
        schema['required_fields'] = ['access_token', 'folder_path']
        schema['optional_fields'] = [
            {
                'name': 'read_content',
                'type': 'checkbox',
                'default': False,
                'description': 'Download and include file text content in the event payload.',
            },
            {
                'name': 'file_filter',
                'type': 'text',
                'description': 'Only emit events for files whose names contain this substring (case-insensitive), e.g. ".csv".',
            },
            {
                'name': 'max_files',
                'type': 'number',
                'default': 50,
                'description': 'Maximum number of new files to emit per run.',
            },
        ] + schema['optional_fields']
        return schema
