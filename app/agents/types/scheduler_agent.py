"""
Scheduler Agent - Time-based triggers

Single responsibility: Create events based on time triggers.
Useful for starting workflows at specific times or intervals.
"""

from typing import List, Dict, Any
from datetime import datetime
from app.agents.base import SourceAgent
from app.agents.registry import register_agent
from app.models import Event


@register_agent
class SchedulerAgent(SourceAgent):
    """
    Creates events based on time triggers.

    This agent creates an event each time it runs (based on its schedule).
    Useful for triggering workflows at specific times.

    Configuration:
        message (str): Message to include in event payload (optional)
        data (dict): Additional data to include in payload (optional)
        expected_receive_period_in_days (int): Alert if not run within N days (optional)
    """

    agent_type = 'scheduler_agent'

    def validate_config(self) -> None:
        """Validate scheduler agent configuration."""
        super().validate_config()

        # Validate optional fields
        if 'message' in self.config:
            if not isinstance(self.config['message'], str):
                raise ValueError("'message' must be a string")

        if 'data' in self.config:
            if not isinstance(self.config['data'], dict):
                raise ValueError("'data' must be a dictionary")

        if 'expected_receive_period_in_days' in self.config:
            if not isinstance(self.config['expected_receive_period_in_days'], (int, float)):
                raise ValueError("'expected_receive_period_in_days' must be a number")
            if self.config['expected_receive_period_in_days'] <= 0:
                raise ValueError("'expected_receive_period_in_days' must be positive")

    def fetch(self) -> List[Event]:
        """
        Create a scheduled event.

        Returns:
            List containing single Event with trigger information
        """
        message = self.config.get('message', 'Scheduled trigger')
        data = self.config.get('data', {})
        expected_period = self.config.get('expected_receive_period_in_days')

        # Check if we're overdue (if expected period is set)
        if expected_period:
            last_run = self.memory.get('last_run_at')
            if last_run:
                last_run_dt = datetime.fromisoformat(last_run)
                days_since_last = (datetime.utcnow() - last_run_dt).total_seconds() / 86400

                if days_since_last > expected_period:
                    self.log(f'Agent overdue: {days_since_last:.1f} days since last run '
                            f'(expected: {expected_period})',
                            level='warning',
                            data={
                                'days_since_last': days_since_last,
                                'expected_period': expected_period
                            })

        # Update last run time in memory
        self.memory.set('last_run_at', datetime.utcnow().isoformat())

        # Create event payload
        payload = {
            'message': message,
            'triggered_at': datetime.utcnow().isoformat(),
        }

        # Add any custom data
        if data:
            payload.update(data)

        # Add metadata
        metadata = {
            'agent_type': self.agent_type,
            'trigger_type': 'scheduled'
        }

        # Create event
        event = self.create_event(payload=payload, metadata=metadata)

        self.log('Created scheduled event', data={
            'message': message,
            'has_custom_data': bool(data)
        })

        return [event]

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """Get configuration schema for scheduler agent."""
        schema = super().get_config_schema()
        schema['required_fields'] = []
        schema['optional_fields'] = [
            {
                'name': 'message',
                'type': 'string',
                'default': 'Scheduled trigger',
                'description': 'Message to include in event payload'
            },
            {
                'name': 'data',
                'type': 'object',
                'default': {},
                'description': 'Additional data to include in payload'
            },
            {
                'name': 'expected_receive_period_in_days',
                'type': 'number',
                'description': 'Alert if not run within N days (monitoring)'
            }
        ]
        return schema
