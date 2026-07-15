"""
Aggregation Agent - Collect events into time/count-based windows and emit aggregates

This transform agent accumulates events into tumbling windows that close based on either:
- Event count threshold (window_size)
- Time duration threshold (window_duration_seconds)
Whichever condition is met first triggers window closure and aggregation emission.

Supports four aggregation modes:
1. Simple: Count events only
2. Collect All: Bundle all event payloads
3. Statistics: Calculate sum/avg/min/max/count on numeric fields
4. Group By: Group events by field value with optional per-group statistics

Use cases:
- Reduce API calls by batching requests
- Create digest emails from multiple events
- Generate periodic summaries
- Bulk process events for efficiency
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta

from app.agents.base import TransformAgent
from app.agents.registry import register_agent
from app.models import Event

logger = logging.getLogger(__name__)


@register_agent
class AggregationAgent(TransformAgent):
    """
    Transform agent that aggregates events into time/count-based windows.

    Configuration Examples:

    Simple mode (just count):
        {
            "window_size": 10,
            "window_duration_seconds": 300,
            "aggregation_mode": "simple"
        }

    Collect all mode (bulk processing):
        {
            "window_size": 20,
            "window_duration_seconds": 600,
            "aggregation_mode": "collect_all"
        }

    Statistics mode:
        {
            "window_size": 100,
            "window_duration_seconds": 3600,
            "aggregation_mode": "statistics",
            "statistics_config": {
                "fields": ["price", "quantity"],
                "operations": ["sum", "avg", "min", "max", "count"]
            }
        }

    Group by mode:
        {
            "window_size": 50,
            "window_duration_seconds": 1800,
            "aggregation_mode": "group_by",
            "group_by_field": "category",
            "statistics_config": {
                "fields": ["price"],
                "operations": ["sum", "avg"]
            }
        }

    Configuration:
        window_size (int): Maximum events before closing window (required)
        window_duration_seconds (int): Maximum seconds before closing window (required)
        aggregation_mode (str): Mode - 'simple', 'collect_all', 'statistics', 'group_by' (required)
        statistics_config (dict): For statistics/group_by modes (mode-dependent)
            fields (list): Field names to aggregate
            operations (list): Operations - 'sum', 'avg', 'min', 'max', 'count'
        group_by_field (str): Field path for grouping (for group_by mode)
        max_window_size (int): Safety limit with FIFO eviction (default: 1000)
        include_metadata (bool): Include event metadata in output (default: False)
        emit_partial_on_reset (bool): Emit partial window on agent restart (default: True)
    """

    agent_type = 'aggregation_agent'
    agent_category = 'transform'

    def __init__(self, agent_id: int, config: Dict[str, Any], user_id: int, db_session=None):
        """Initialize the aggregation agent."""
        # Extract config values before calling super().__init__()
        self.aggregation_mode = config.get('aggregation_mode')
        self.max_window_size = config.get('max_window_size', 1000)
        self.include_metadata = config.get('include_metadata', False)
        self.emit_partial_on_reset = config.get('emit_partial_on_reset', True)

        # Call parent __init__ which will call validate_config()
        super().__init__(agent_id, config, user_id, db_session)

    def validate_config(self) -> None:
        """
        Validate aggregation agent configuration.

        Raises:
            ValueError: If configuration is invalid
        """
        # Call parent validation
        super().validate_config()

        # Validate required fields
        if 'window_size' not in self.config:
            raise ValueError("'window_size' is required")

        if not isinstance(self.config['window_size'], int):
            raise ValueError("'window_size' must be an integer")

        if self.config['window_size'] <= 0:
            raise ValueError("'window_size' must be greater than 0")

        if 'window_duration_seconds' not in self.config:
            raise ValueError("'window_duration_seconds' is required")

        if not isinstance(self.config['window_duration_seconds'], (int, float)):
            raise ValueError("'window_duration_seconds' must be a number")

        if self.config['window_duration_seconds'] <= 0:
            raise ValueError("'window_duration_seconds' must be greater than 0")

        if 'aggregation_mode' not in self.config:
            raise ValueError("'aggregation_mode' is required")

        mode = self.config['aggregation_mode']
        valid_modes = ['simple', 'collect_all', 'statistics', 'group_by']
        if mode not in valid_modes:
            raise ValueError(f"'aggregation_mode' must be one of: {', '.join(valid_modes)}")

        # Mode-specific validation
        if mode == 'statistics':
            if 'statistics_config' not in self.config:
                raise ValueError("'statistics_config' is required for statistics mode")
            self._validate_statistics_config(self.config['statistics_config'])

        if mode == 'group_by':
            if 'group_by_field' not in self.config:
                raise ValueError("'group_by_field' is required for group_by mode")

            if not isinstance(self.config['group_by_field'], str):
                raise ValueError("'group_by_field' must be a string")

            if not self.config['group_by_field'].strip():
                raise ValueError("'group_by_field' cannot be empty")

            # Optional statistics for group_by mode
            if 'statistics_config' in self.config:
                self._validate_statistics_config(self.config['statistics_config'])

        # Validate optional fields
        if 'max_window_size' in self.config:
            if not isinstance(self.config['max_window_size'], int):
                raise ValueError("'max_window_size' must be an integer")
            if self.config['max_window_size'] <= 0:
                raise ValueError("'max_window_size' must be greater than 0")
            # Note: max_window_size can be < window_size for testing/edge cases
            # This allows FIFO eviction to kick in before window closure

        if 'include_metadata' in self.config:
            if not isinstance(self.config['include_metadata'], bool):
                raise ValueError("'include_metadata' must be a boolean")

        if 'emit_partial_on_reset' in self.config:
            if not isinstance(self.config['emit_partial_on_reset'], bool):
                raise ValueError("'emit_partial_on_reset' must be a boolean")

    def _validate_statistics_config(self, stats_config: Any) -> None:
        """
        Validate statistics configuration.

        Args:
            stats_config: Statistics configuration to validate

        Raises:
            ValueError: If configuration is invalid
        """
        if not isinstance(stats_config, dict):
            raise ValueError("'statistics_config' must be a dictionary")

        if 'fields' not in stats_config:
            raise ValueError("'statistics_config' must contain 'fields'")

        if not isinstance(stats_config['fields'], list):
            raise ValueError("'statistics_config.fields' must be a list")

        if len(stats_config['fields']) == 0:
            raise ValueError("'statistics_config.fields' must contain at least one field")

        for field in stats_config['fields']:
            if not isinstance(field, str):
                raise ValueError(f"Field names must be strings, got: {type(field).__name__}")

        if 'operations' not in stats_config:
            raise ValueError("'statistics_config' must contain 'operations'")

        if not isinstance(stats_config['operations'], list):
            raise ValueError("'statistics_config.operations' must be a list")

        if len(stats_config['operations']) == 0:
            raise ValueError("'statistics_config.operations' must contain at least one operation")

        valid_operations = ['sum', 'avg', 'min', 'max', 'count']
        for op in stats_config['operations']:
            if op not in valid_operations:
                raise ValueError(f"Invalid operation '{op}'. Valid operations: {', '.join(valid_operations)}")

    def process(self, events: List[Event]) -> List[Event]:
        """
        Process events and aggregate into windows.

        Args:
            events: List of events to process

        Returns:
            List with single aggregated event if window closes, empty list otherwise
        """
        # Handle empty input
        if not events:
            return []

        # Get or initialize window state
        window_state = self._get_window_state()

        # Check if window should close DUE TO TIME (before adding new events)
        # This ensures time-based closures don't include the triggering events
        window_start = datetime.fromisoformat(window_state['window_start_time'])
        elapsed_seconds = (datetime.utcnow() - window_start).total_seconds()
        time_expired = elapsed_seconds >= self.config['window_duration_seconds']

        if time_expired and window_state['event_count'] > 0:
            # Time threshold reached - emit current window WITHOUT new events
            reason = f"time_threshold_{self.config['window_duration_seconds']}s"
            aggregated_event = self._aggregate_and_emit(window_state, reason)

            # Reset window for new events
            self._reset_window()

            # Add new events to fresh window
            new_window_state = self._get_window_state()
            new_window_state = self._add_events_to_window(new_window_state, events)
            self._save_window_state(new_window_state)

            return [aggregated_event] if aggregated_event else []

        # Add incoming events to window
        window_state = self._add_events_to_window(window_state, events)

        # Check if window should close (count threshold)
        should_close, reason = self._should_close_window(window_state)

        if should_close:
            # Skip empty windows
            if window_state['event_count'] == 0:
                self.log('Window closed but empty, skipping emission', level='debug', data={
                    'reason': reason
                })
                return []

            # Aggregate and emit
            aggregated_event = self._aggregate_and_emit(window_state, reason)

            # Reset window
            self._reset_window()

            return [aggregated_event] if aggregated_event else []
        else:
            # Save updated state and return empty
            self._save_window_state(window_state)
            return []

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """
        Get the configuration schema for this agent.

        Returns:
            Configuration schema dictionary
        """
        schema = super().get_config_schema()
        schema['required_fields'] = ['window_size', 'window_duration_seconds', 'aggregation_mode']
        schema['optional_fields'] = [
            {
                'name': 'window_size',
                'type': 'integer',
                'description': 'Maximum number of events before closing window. Window closes when this count is reached OR duration expires (whichever first).'
            },
            {
                'name': 'window_duration_seconds',
                'type': 'number',
                'description': 'Maximum time in seconds before closing window. Window closes when this duration expires OR event count is reached (whichever first).'
            },
            {
                'name': 'aggregation_mode',
                'type': 'select',
                'options': ['simple', 'collect_all', 'statistics', 'group_by'],
                'description': 'Aggregation strategy. "simple": count only, "collect_all": bundle all events, "statistics": calculate metrics on fields, "group_by": group by field with optional statistics.'
            },
            {
                'name': 'statistics_config',
                'type': 'json',
                'description': 'Required for statistics/group_by modes. Format: {"fields": ["price", "quantity"], "operations": ["sum", "avg", "min", "max", "count"]}'
            },
            {
                'name': 'group_by_field',
                'type': 'text',
                'description': 'Required for group_by mode. Field path to group by (supports dot notation like "user.id"). Events with missing field go to "__null__" group.'
            },
            {
                'name': 'max_window_size',
                'type': 'integer',
                'default': 1000,
                'description': 'Safety limit for maximum events in window. If exceeded, oldest events are removed (FIFO). Should be >= window_size.'
            },
            {
                'name': 'include_metadata',
                'type': 'boolean',
                'default': False,
                'description': 'Include original event metadata in aggregated output. Useful for preserving event context.'
            },
            {
                'name': 'emit_partial_on_reset',
                'type': 'boolean',
                'default': True,
                'description': 'Emit partial window contents if agent restarts mid-window. If False, partial windows are discarded on restart.'
            }
        ]
        return schema

    def __repr__(self):
        """String representation of the agent."""
        mode = self.config.get('aggregation_mode', 'unknown')
        window_size = self.config.get('window_size', '?')
        window_duration = self.config.get('window_duration_seconds', '?')
        return f'<AggregationAgent {self.agent_id}: mode={mode}, size={window_size}, duration={window_duration}s>'

    # ========== PHASE 2: State Management ==========

    def _initialize_window(self) -> Dict[str, Any]:
        """
        Initialize a new empty window.

        Returns:
            New window state dictionary
        """
        return {
            'window_start_time': datetime.utcnow().isoformat(),
            'event_count': 0,
            'events': [],
            'metadata_list': [] if self.include_metadata else None,
            'group_state': {} if self.aggregation_mode == 'group_by' else None
        }

    def _get_window_state(self) -> Dict[str, Any]:
        """
        Get current window state from memory or initialize new window.

        Returns:
            Window state dictionary
        """
        state = self.memory.get('window_state')

        if state is None:
            # No existing window - initialize new one
            state = self._initialize_window()
            self.log('Initialized new window', level='debug', data={
                'window_start': state['window_start_time']
            })
        else:
            # Existing window found
            self.log('Resumed existing window', level='debug', data={
                'window_start': state['window_start_time'],
                'event_count': state['event_count']
            })

        return state

    def _save_window_state(self, state: Dict[str, Any]) -> None:
        """
        Save window state to memory with TTL.

        Args:
            state: Window state to save
        """
        # TTL is 10x window duration so state survives slow environments (e.g. full test suite)
        # without being stored forever. Window closure is driven by window_start_time, not TTL.
        ttl_seconds = max(int(self.config['window_duration_seconds'] * 10), 60)

        self.memory.set('window_state', state, ttl=ttl_seconds)

        self.log('Saved window state', level='debug', data={
            'event_count': state['event_count'],
            'ttl_seconds': ttl_seconds
        })

    def _reset_window(self) -> None:
        """Reset window state (delete from memory)."""
        self.memory.delete('window_state')
        self.log('Reset window state', level='debug')

    def _add_events_to_window(self, state: Dict[str, Any], events: List[Event]) -> Dict[str, Any]:
        """
        Add events to window with FIFO eviction if max size exceeded.

        Args:
            state: Current window state
            events: Events to add

        Returns:
            Updated window state
        """
        for event in events:
            # Handle group_by mode
            if self.aggregation_mode == 'group_by':
                group_field = self.config['group_by_field']
                group_value = self._get_field_value(event.payload, group_field)

                # Use "__null__" for missing values
                if group_value is None:
                    group_value = '__null__'
                else:
                    group_value = str(group_value)

                # Initialize group if not exists
                if group_value not in state['group_state']:
                    state['group_state'][group_value] = []

                state['group_state'][group_value].append(event.payload)
            else:
                # Regular mode - add to events list
                state['events'].append(event.payload)

            # Track metadata if configured
            if self.include_metadata and state['metadata_list'] is not None:
                # Use event_metadata attribute (not metadata which is SQLAlchemy MetaData)
                state['metadata_list'].append(dict(event.event_metadata) if event.event_metadata else {})

            state['event_count'] += 1

        # Enforce max window size with FIFO eviction
        if state['event_count'] > self.max_window_size:
            events_to_remove = state['event_count'] - self.max_window_size

            self.log(f'Window exceeded max size, removing {events_to_remove} oldest events', level='warning', data={
                'current_count': state['event_count'],
                'max_size': self.max_window_size
            })

            if self.aggregation_mode == 'group_by':
                # FIFO eviction across all groups
                removed = 0
                for group_value in list(state['group_state'].keys()):
                    group_events = state['group_state'][group_value]
                    if removed >= events_to_remove:
                        break

                    to_remove = min(len(group_events), events_to_remove - removed)
                    state['group_state'][group_value] = group_events[to_remove:]
                    removed += to_remove

                    # Remove empty groups
                    if len(state['group_state'][group_value]) == 0:
                        del state['group_state'][group_value]
            else:
                # Regular mode - remove from front of list
                state['events'] = state['events'][events_to_remove:]

            if state['metadata_list'] is not None:
                state['metadata_list'] = state['metadata_list'][events_to_remove:]

            # Note: event_count tracks total events added, not array length after FIFO
            # DO NOT reset event_count here - it should remain accurate

        return state

    # ========== PHASE 3: Window Logic ==========

    def _should_close_window(self, state: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Check if window should close based on count or time thresholds.

        Args:
            state: Current window state

        Returns:
            Tuple of (should_close, reason)
        """
        # Check count threshold
        if state['event_count'] >= self.config['window_size']:
            reason = f"count_threshold_{self.config['window_size']}"
            return (True, reason)

        # Check time threshold
        window_start = datetime.fromisoformat(state['window_start_time'])
        elapsed_seconds = (datetime.utcnow() - window_start).total_seconds()

        if elapsed_seconds >= self.config['window_duration_seconds']:
            reason = f"time_threshold_{self.config['window_duration_seconds']}s"
            return (True, reason)

        return (False, None)

    def _calculate_window_duration(self, state: Dict[str, Any]) -> float:
        """
        Calculate window duration in seconds.

        Args:
            state: Window state

        Returns:
            Duration in seconds
        """
        window_start = datetime.fromisoformat(state['window_start_time'])
        return (datetime.utcnow() - window_start).total_seconds()

    # ========== PHASE 4: Aggregation Modes ==========

    def _aggregate_and_emit(self, state: Dict[str, Any], reason: str) -> Optional[Event]:
        """
        Aggregate window state and create output event.

        Args:
            state: Window state to aggregate
            reason: Closure reason

        Returns:
            Aggregated event or None if skipped
        """
        window_start = state['window_start_time']
        window_end = datetime.utcnow().isoformat()
        duration = self._calculate_window_duration(state)

        # Dispatch based on mode
        mode = self.aggregation_mode

        if mode == 'simple':
            payload = self._aggregate_simple(state)
        elif mode == 'collect_all':
            payload = self._aggregate_collect_all(state)
        elif mode == 'statistics':
            payload = self._aggregate_statistics(state)
        elif mode == 'group_by':
            payload = self._aggregate_group_by(state)
        else:
            raise ValueError(f"Unknown aggregation mode: {mode}")

        # Add aggregation metadata to all modes
        payload['_aggregation'] = {
            'mode': mode,
            'event_count': state['event_count'],
            'window_start': window_start,
            'window_end': window_end,
            'window_duration_seconds': round(duration, 2),
            'close_reason': reason
        }

        # Create event
        aggregated_event = self.create_event(
            payload=payload,
            metadata={
                'aggregation': 'window_closed',
                'aggregated_at': window_end
            }
        )

        self.log(f'Window closed and aggregated', data={
            'mode': mode,
            'event_count': state['event_count'],
            'close_reason': reason,
            'duration_seconds': round(duration, 2)
        })

        return aggregated_event

    def _aggregate_simple(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simple aggregation - just count events.

        Args:
            state: Window state

        Returns:
            Aggregated payload
        """
        return {
            'event_count': state['event_count'],
            'window_start': state['window_start_time']
        }

    def _aggregate_collect_all(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Collect all events into array.

        Args:
            state: Window state

        Returns:
            Aggregated payload with all events
        """
        payload = {
            'events': state['events'],
            'event_count': state['event_count']
        }

        if self.include_metadata and state['metadata_list']:
            payload['metadata_list'] = state['metadata_list']

        return payload

    def _aggregate_statistics(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate statistics on numeric fields.

        Args:
            state: Window state

        Returns:
            Aggregated payload with statistics
        """
        stats_config = self.config['statistics_config']
        statistics = {}

        for field in stats_config['fields']:
            field_stats = self._calculate_field_statistics(
                state['events'],
                field,
                stats_config['operations']
            )
            statistics[field] = field_stats

        return {
            'statistics': statistics,
            'event_count': state['event_count']
        }

    def _aggregate_group_by(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Group events by field and optionally calculate per-group statistics.

        Args:
            state: Window state

        Returns:
            Aggregated payload with groups
        """
        groups = {}
        calculate_stats = 'statistics_config' in self.config

        for group_value, group_events in state['group_state'].items():
            group_data = {
                'event_count': len(group_events),
                'events': group_events
            }

            # Calculate per-group statistics if configured
            if calculate_stats:
                stats_config = self.config['statistics_config']
                group_statistics = {}

                for field in stats_config['fields']:
                    field_stats = self._calculate_field_statistics(
                        group_events,
                        field,
                        stats_config['operations']
                    )
                    group_statistics[field] = field_stats

                group_data['statistics'] = group_statistics

            groups[group_value] = group_data

        return {
            'groups': groups,
            'total_event_count': state['event_count'],
            'group_count': len(groups),
            'group_by_field': self.config['group_by_field']
        }

    def _calculate_field_statistics(self, events: List[Dict], field: str, operations: List[str]) -> Dict[str, Any]:
        """
        Calculate statistics for a field across events.

        Args:
            events: List of event payloads
            field: Field to calculate stats for
            operations: List of operations to perform

        Returns:
            Dictionary of statistics
        """
        # Extract numeric values
        values = []
        for event in events:
            value = self._get_field_value(event, field)
            if value is not None:
                try:
                    values.append(float(value))
                except (TypeError, ValueError):
                    # Skip non-numeric values
                    continue

        # Calculate statistics
        stats = {}

        for op in operations:
            if op == 'sum':
                stats['sum'] = sum(values) if values else None
            elif op == 'avg':
                stats['avg'] = sum(values) / len(values) if values else None
            elif op == 'min':
                stats['min'] = min(values) if values else None
            elif op == 'max':
                stats['max'] = max(values) if values else None
            elif op == 'count':
                stats['count'] = len(values)

        return stats

    def _get_field_value(self, payload: Dict, field_path: str) -> Any:
        """
        Extract field value using dot notation (e.g., 'user.profile.age').

        Args:
            payload: Event payload
            field_path: Field path with dots

        Returns:
            Field value or None if not found
        """
        try:
            value = payload
            for key in field_path.split('.'):
                value = value[key]
            return value
        except (KeyError, TypeError, AttributeError):
            return None
