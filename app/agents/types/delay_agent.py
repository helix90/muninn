"""Delay Agent — buffer events and release them after a configurable delay."""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

from app.agents.base import TransformAgent
from app.agents.registry import register_agent
from app.models import Event, DelayedEvent
from app.extensions import db

logger = logging.getLogger(__name__)


@register_agent
class DelayAgent(TransformAgent):
    """
    Buffers incoming events and releases them after a fixed delay.
    Schedule this agent periodically (e.g. every 5 minutes) so it can
    flush events whose delay has elapsed.

    When events arrive via the pipeline, they are stored instead of
    propagated. On each scheduled run (incoming_events=[]), buffered events
    whose release time has passed are emitted downstream.

    Configuration:
        delay_minutes (int): Minutes to hold each event before releasing (required, ≥1)
    """

    agent_type = 'delay_agent'
    agent_category = 'transform'

    # Override: this agent is also schedulable so it can flush buffered events
    can_be_scheduled = True

    def __init__(self, agent_id: int, config: Dict[str, Any], user_id: int, db_session=None):
        raw = config.get('delay_minutes', 0)
        try:
            self.delay_minutes = int(raw)
        except (TypeError, ValueError):
            self.delay_minutes = 0  # validate_config will raise the user-friendly message
        super().__init__(agent_id, config, user_id, db_session)

    def validate_config(self) -> None:
        super().validate_config()
        raw = self.config.get('delay_minutes')
        if raw is None:
            raise ValueError("delay_minutes is required")
        try:
            minutes = int(raw)
        except (TypeError, ValueError):
            raise ValueError("delay_minutes must be an integer")
        if minutes < 1:
            raise ValueError("delay_minutes must be at least 1")

    def check(self, incoming_events: List[Event]) -> List[Event]:
        """Override to handle both receive (store) and schedule (release) modes."""
        self._cleanup_old_events()

        if incoming_events:
            self._store_events(incoming_events)
            return []

        return self._release_ready_events()

    # Required by TransformAgent ABC but never reached via check() above
    def process(self, events: List[Event]) -> List[Event]:
        self._store_events(events)
        return []

    def _store_events(self, events: List[Event]) -> None:
        session = self.db_session or db.session
        release_at = datetime.utcnow() + timedelta(minutes=self.delay_minutes)

        for event in events:
            delayed = DelayedEvent(
                agent_id=self.agent_id,
                payload=event.payload or {},
                metadata_=event.event_metadata or {},
                release_at=release_at,
                released=False,
            )
            session.add(delayed)

        try:
            session.commit()
            self.log(f'Buffered {len(events)} event(s), releasing at {release_at.isoformat()}')
        except Exception as e:
            session.rollback()
            logger.error(f'DelayAgent {self.agent_id}: failed to buffer events: {e}')

    def _release_ready_events(self) -> List[Event]:
        session = self.db_session or db.session
        now = datetime.utcnow()

        pending = (
            session.query(DelayedEvent)
            .filter(
                DelayedEvent.agent_id == self.agent_id,
                DelayedEvent.release_at <= now,
                DelayedEvent.released == False,
            )
            .with_for_update(skip_locked=True)
            .all()
        )

        if not pending:
            return []

        events: List[Event] = []
        for delayed in pending:
            event = self.create_event(
                payload=delayed.payload or {},
                metadata=delayed.metadata_ or {},
            )
            events.append(event)
            delayed.released = True

        try:
            session.commit()
            self.log(f'Released {len(events)} delayed event(s)')
        except Exception as e:
            session.rollback()
            logger.error(f'DelayAgent {self.agent_id}: failed to release events: {e}')
            return []

        return events

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        schema = super().get_config_schema()
        schema['required_fields'] = ['delay_minutes']
        schema['optional_fields'].extend([])
        return schema
