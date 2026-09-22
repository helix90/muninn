"""
Manual Event Agent — inject a custom event payload on demand.

Single responsibility: emit exactly one event containing a user-defined JSON
payload each time the agent is run. No schedule required; trigger it with the
"Run Now" button on the agent detail page.

Useful for injecting test data into a pipeline without waiting for a real
source, or for one-off manual triggers during development and debugging.
"""

from typing import List

from app.agents.base import SourceAgent
from app.agents.registry import register_agent
from app.models import Event


@register_agent
class ManualEventAgent(SourceAgent):
    """
    Emits a single event whose payload is defined in the agent config.

    Run it on demand via the "Run Now" button on the agent detail page.
    Each invocation emits exactly one event, which then propagates to any
    connected downstream agents as normal.

    Configuration:
        payload (dict): The JSON object to emit as the event payload. Any
            key-value pairs are allowed. Required.
    """

    agent_type = 'manual_event_agent'
    agent_category = 'source'

    def validate_config(self) -> None:
        super().validate_config()
        if 'payload' not in self.config:
            raise ValueError("'payload' is required — provide the JSON object to emit")
        if not isinstance(self.config['payload'], dict):
            raise ValueError("'payload' must be a JSON object (dict)")

    def fetch(self) -> List[Event]:
        payload = dict(self.config['payload'])
        self.log('Emitting manual event', data={'payload_keys': list(payload.keys())})
        return [self.create_event(payload=payload)]
