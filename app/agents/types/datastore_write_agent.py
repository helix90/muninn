"""DataStore Write Agent — persist key-value data from event payloads."""

import logging
from typing import Any, Dict, List, Optional
from jinja2 import Environment, BaseLoader, TemplateError, UndefinedError

from app.agents.base import ActionAgent
from app.agents.registry import register_agent
from app.models import Event, DataStore
from app.extensions import db

logger = logging.getLogger(__name__)


@register_agent
class DataStoreWriteAgent(ActionAgent):
    """
    Writes key-value data to the shared DataStore on each incoming event.
    Other agents (DataStoreReadAgent) can read this data later.

    Configuration:
        namespace (str): Logical grouping for the data (required), e.g. "prices"
        key_template (str): Jinja2 template for the key (required),
                            e.g. "{{ ticker }}" or "latest_price"
        value_template (str): Jinja2 template for the value (required),
                              e.g. "{{ price }}" or "{{ payload | tojson }}"
    """

    agent_type = 'datastore_write_agent'
    agent_category = 'action'

    def __init__(self, agent_id: int, config: Dict[str, Any], user_id: int, db_session=None):
        self.namespace = config.get('namespace', '').strip()
        self.key_template = config.get('key_template', '')
        self.value_template = config.get('value_template', '')
        super().__init__(agent_id, config, user_id, db_session)

    def validate_config(self) -> None:
        super().validate_config()
        if not self.namespace:
            raise ValueError("namespace is required")
        if len(self.namespace) > 100:
            raise ValueError("namespace must be 100 characters or fewer")
        if not self.key_template:
            raise ValueError("key_template is required")
        if not self.value_template:
            raise ValueError("value_template is required")
        for field, tmpl in [('key_template', self.key_template),
                             ('value_template', self.value_template)]:
            try:
                Environment(loader=BaseLoader()).from_string(tmpl)
            except TemplateError as e:
                raise ValueError(f"Invalid {field} syntax: {e}")

    def act(self, events: List[Event]) -> None:
        session = self.db_session or db.session

        for event in events:
            try:
                context = self._build_context(event)
                key = self._render(self.key_template, context)
                if not key:
                    self.log('Skipping event: key_template rendered empty', level='warning')
                    continue

                raw_value = self._render(self.value_template, context)
                if raw_value is None:
                    self.log('Skipping event: value_template rendered empty', level='warning')
                    continue

                # Only parse as JSON for objects/arrays; store plain strings as-is
                import json
                stripped_raw = raw_value.strip()
                if stripped_raw.startswith(('{', '[')):
                    try:
                        value = json.loads(stripped_raw)
                    except (json.JSONDecodeError, TypeError):
                        value = raw_value
                else:
                    value = raw_value

                self._upsert(session, key, value)
                self.log(f"Stored {self.namespace}/{key}")

            except UndefinedError as e:
                self.log(f'Template variable missing: {e}', level='error')
            except Exception as e:
                self.log(f'Error writing to DataStore: {e}', level='error')

    def _upsert(self, session, key: str, value: Any) -> None:
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from datetime import datetime

        stmt = (
            pg_insert(DataStore)
            .values(
                user_id=self.user_id,
                namespace=self.namespace,
                key=key,
                value=value,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            .on_conflict_do_update(
                index_elements=['user_id', 'namespace', 'key'],
                set_={'value': value, 'updated_at': datetime.utcnow()},
            )
        )
        session.execute(stmt)
        session.commit()

    def _build_context(self, event: Event) -> Dict[str, Any]:
        ctx: Dict[str, Any] = {}
        if event.payload:
            ctx.update(event.payload)
        if event.event_metadata:
            ctx['metadata'] = event.event_metadata
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
            logger.error(f'DataStoreWriteAgent {self.agent_id}: template error: {e}')
            return None

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        schema = super().get_config_schema()
        schema['required_fields'] = ['namespace', 'key_template', 'value_template']
        schema['optional_fields'].extend([])
        return schema
