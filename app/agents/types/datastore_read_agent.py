"""DataStore Read Agent — emit events from DataStore entries on a schedule."""

import logging
from typing import Any, Dict, List

from app.agents.base import SourceAgent
from app.agents.registry import register_agent
from app.models import Event, DataStore
from app.extensions import db

logger = logging.getLogger(__name__)


@register_agent
class DataStoreReadAgent(SourceAgent):
    """
    Reads key-value data written by DataStoreWriteAgent and emits one event
    per matching entry. Schedule this agent to poll the store periodically.

    Configuration:
        namespace (str): Namespace to read from (required)
        key (str): Exact key to read, or empty to read all keys (optional)
        emit_field (str): Payload field name for the stored value (default: "value")
    """

    agent_type = 'datastore_read_agent'
    agent_category = 'source'

    def __init__(self, agent_id: int, config: Dict[str, Any], user_id: int, db_session=None):
        self.namespace = config.get('namespace', '').strip()
        self.key = config.get('key', '').strip()
        self.emit_field = config.get('emit_field', 'value').strip() or 'value'
        super().__init__(agent_id, config, user_id, db_session)

    def validate_config(self) -> None:
        super().validate_config()
        if not self.namespace:
            raise ValueError("namespace is required")
        if len(self.namespace) > 100:
            raise ValueError("namespace must be 100 characters or fewer")

    def fetch(self) -> List[Event]:
        session = self.db_session or db.session

        query = session.query(DataStore).filter(
            DataStore.user_id == self.user_id,
            DataStore.namespace == self.namespace,
        )
        if self.key:
            query = query.filter(DataStore.key == self.key)

        entries = query.order_by(DataStore.key).all()

        if not entries:
            self.log(f'No entries found in {self.namespace}/{self.key or "*"}')
            return []

        events = []
        for entry in entries:
            payload = {
                'namespace': entry.namespace,
                'key': entry.key,
                self.emit_field: entry.value,
                'updated_at': entry.updated_at.isoformat() if entry.updated_at else None,
            }
            event = self.create_event(payload=payload, metadata={'source': 'datastore'})
            events.append(event)

        self.log(f'Emitted {len(events)} events from {self.namespace}')
        return events

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        schema = super().get_config_schema()
        schema['required_fields'] = ['namespace']
        schema['optional_fields'].extend([
            {
                'name': 'key',
                'type': 'text',
                'default': '',
                'description': 'Specific key to read; leave empty to read all keys in the namespace',
            },
            {
                'name': 'emit_field',
                'type': 'text',
                'default': 'value',
                'description': "Event payload field name for the stored value (default: 'value')",
            },
        ])
        return schema
