"""
JSONPath Agent - Extract fields from JSON payloads using JSONPath expressions

This transform agent extracts specific fields from incoming event payloads using
JSONPath query expressions. Supports both single field extraction and multi-field
extraction modes. Uses jsonpath-ng library for standard JSONPath syntax.
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from jsonpath_ng import parse
from jsonpath_ng.exceptions import JsonPathParserError

from app.agents.base import TransformAgent
from app.agents.registry import register_agent
from app.models import Event

logger = logging.getLogger(__name__)


@register_agent
class JSONPathAgent(TransformAgent):
    """
    Transform agent that extracts fields from JSON payloads using JSONPath.

    Supports two operation modes:
    1. Simple mode: Extract a single field using 'path' config
    2. Multi-field mode: Extract multiple fields using 'extractions' config

    Configuration:
        path (str): JSONPath expression (simple mode) e.g., "$.user.email"
        output_field (str): Output field name (simple mode, default: "extracted")
        extractions (list): List of extraction rules (multi-field mode)
            Each extraction: {"path": "$.field", "output_field": "output_name"}
        preserve_original (bool): Include original payload in output (default: False)
        on_missing (str): Behavior when path not found: 'skip', 'null', 'error' (default: 'skip')
        flatten_lists (bool): Flatten list results to single value (default: False)
    """

    agent_type = 'jsonpath_agent'
    agent_category = 'transform'

    def __init__(self, agent_id: int, config: Dict[str, Any], user_id: int, db_session=None):
        """Initialize the JSONPath agent."""
        # Extract config values BEFORE calling super().__init__()
        # because validate_config() needs these
        self.on_missing = config.get('on_missing', 'skip')
        self.preserve_original = config.get('preserve_original', False)
        self.flatten_lists = config.get('flatten_lists', False)

        # Pre-compile JSONPath expressions for performance
        self.compiled_path = None
        self.compiled_extractions = []

        # Simple mode
        if 'path' in config:
            try:
                self.compiled_path = parse(config['path'])
            except JsonPathParserError as e:
                # Will be caught by validate_config() later
                logger.warning(f"Invalid JSONPath in config: {e}")

        # Multi-field mode
        if 'extractions' in config and isinstance(config.get('extractions'), list):
            for extraction in config['extractions']:
                if 'path' in extraction:
                    try:
                        compiled = parse(extraction['path'])
                        self.compiled_extractions.append({
                            'compiled': compiled,
                            'output_field': extraction.get('output_field', 'extracted'),
                            'original_path': extraction['path']
                        })
                    except JsonPathParserError as e:
                        logger.warning(f"Invalid JSONPath in extraction: {e}")

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

        # Must have either 'path' or 'extractions'
        has_path = 'path' in self.config
        has_extractions = 'extractions' in self.config

        if not (has_path or has_extractions):
            raise ValueError("Must specify either 'path' (simple mode) or 'extractions' (multi-field mode)")

        if has_path and has_extractions:
            raise ValueError("Cannot specify both 'path' and 'extractions' - choose one mode")

        # Validate JSONPath expressions in simple mode
        if has_path:
            try:
                parse(self.config['path'])
            except JsonPathParserError as e:
                raise ValueError(f"Invalid JSONPath expression '{self.config['path']}': {e}")

        # Validate extractions in multi-field mode
        if has_extractions:
            if not isinstance(self.config['extractions'], list):
                raise ValueError("'extractions' must be a list")

            if len(self.config['extractions']) == 0:
                raise ValueError("'extractions' must contain at least one extraction rule")

            for i, extraction in enumerate(self.config['extractions']):
                if not isinstance(extraction, dict):
                    raise ValueError(f"Extraction {i} must be a dictionary")

                if 'path' not in extraction:
                    raise ValueError(f"Extraction {i} missing 'path' field")

                if 'output_field' not in extraction:
                    raise ValueError(f"Extraction {i} missing 'output_field' field")

                # Validate JSONPath syntax
                try:
                    parse(extraction['path'])
                except JsonPathParserError as e:
                    raise ValueError(f"Invalid JSONPath in extraction {i} ('{extraction['path']}'): {e}")

        # Validate on_missing
        if self.on_missing not in ['skip', 'null', 'error']:
            raise ValueError("'on_missing' must be 'skip', 'null', or 'error'")

        # Validate preserve_original
        if not isinstance(self.preserve_original, bool):
            raise ValueError("'preserve_original' must be a boolean")

        # Validate flatten_lists
        if not isinstance(self.flatten_lists, bool):
            raise ValueError("'flatten_lists' must be a boolean")

    def process(self, events: List[Event]) -> List[Event]:
        """
        Process events and extract fields using JSONPath.

        Args:
            events: List of events to process

        Returns:
            List of new events with extracted data
        """
        output_events = []

        for event in events:
            try:
                # Extract data based on mode (simple or multi-field)
                if 'path' in self.config:
                    # Simple mode: single extraction
                    extracted = self._extract_simple(event)
                else:
                    # Multi-field mode: multiple extractions
                    extracted = self._extract_multiple(event)

                # Handle missing data
                if extracted is None:
                    if self.on_missing == 'skip':
                        self.log(f'Skipping event {event.id}: no data extracted', level='debug')
                        continue
                    elif self.on_missing == 'null':
                        # Create output with null value
                        if 'path' in self.config:
                            output_field = self.config.get('output_field', 'extracted')
                            extracted = {output_field: None}
                        else:
                            # For multi-field, create dict with all fields as None
                            extracted = {}
                            for extraction in self.config['extractions']:
                                extracted[extraction['output_field']] = None
                    else:  # 'error'
                        raise ValueError(f'No data extracted from event {event.id}')

                # Preserve original if configured
                if self.preserve_original:
                    output_payload = {**event.payload, **extracted}
                else:
                    output_payload = extracted

                # Create new event with extracted data
                new_event = self.create_event(
                    payload=output_payload,
                    metadata={
                        'source_event_id': event.id,
                        'transformer': 'jsonpath',
                        'extracted_at': datetime.utcnow().isoformat(),
                        'extraction_mode': 'simple' if 'path' in self.config else 'multi-field'
                    }
                )
                output_events.append(new_event)

            except Exception as e:
                self.log(f'Error processing event {event.id}: {e}', level='error')
                if self.on_missing == 'error':
                    raise
                continue

        if output_events:
            self.log(f'Transformed {len(events)} → {len(output_events)} events', data={
                'input_count': len(events),
                'output_count': len(output_events)
            })

        return output_events

    def _extract_simple(self, event: Event) -> Optional[Dict]:
        """
        Extract single field from event payload (simple mode).

        Args:
            event: Event to extract from

        Returns:
            Dictionary with extracted field, or None if not found
        """
        # Use pre-compiled path
        path_expr = self.compiled_path

        # Find matches in payload
        matches = path_expr.find(event.payload)

        if not matches:
            return None

        # Get values from matches
        values = [match.value for match in matches]

        # Flatten if configured and result is single item
        if self.flatten_lists and len(values) == 1:
            value = values[0]
        elif len(values) == 1:
            value = values[0]
        else:
            value = values

        # Build output dict
        output_field = self.config.get('output_field', 'extracted')
        return {output_field: value}

    def _extract_multiple(self, event: Event) -> Optional[Dict]:
        """
        Extract multiple fields from event payload (multi-field mode).

        Args:
            event: Event to extract from

        Returns:
            Dictionary with all extracted fields, or None if no fields extracted
        """
        result = {}
        any_found = False

        # Use pre-compiled extractions
        for compiled_extraction in self.compiled_extractions:
            path_expr = compiled_extraction['compiled']
            output_field = compiled_extraction['output_field']

            # Find matches
            matches = path_expr.find(event.payload)

            if not matches:
                # Handle missing field
                if self.on_missing == 'null':
                    result[output_field] = None
                elif self.on_missing == 'error':
                    raise ValueError(f"Path not found: {compiled_extraction['original_path']}")
                # else: skip (don't add to result)
                continue

            any_found = True
            values = [match.value for match in matches]

            # Flatten if configured and result is single item
            if self.flatten_lists and len(values) == 1:
                value = values[0]
            elif len(values) == 1:
                value = values[0]
            else:
                value = values

            result[output_field] = value

        return result if any_found or self.on_missing == 'null' else None

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """
        Get the configuration schema for this agent.

        Returns:
            Configuration schema dictionary
        """
        schema = super().get_config_schema()
        schema['required_fields'] = []  # Either 'path' or 'extractions' required (validated in validate_config)
        schema['optional_fields'].extend([
            {
                'name': 'path',
                'type': 'text',
                'description': 'JSONPath expression to extract (simple mode). Examples: "$.user.email", "$.items[*].name", "$..price". Use this for single field extraction.'
            },
            {
                'name': 'output_field',
                'type': 'text',
                'default': 'extracted',
                'description': 'Field name for extracted data in output payload (simple mode only). Default: "extracted".'
            },
            {
                'name': 'extractions',
                'type': 'array',
                'description': 'List of extraction rules for multi-field mode. Each rule must have "path" and "output_field". Example: [{"path": "$.user.email", "output_field": "email"}, {"path": "$.order.total", "output_field": "amount"}]'
            },
            {
                'name': 'preserve_original',
                'type': 'boolean',
                'default': False,
                'description': 'Include original payload in output events. If True, extracted fields are merged with original payload. If False, only extracted fields are included.'
            },
            {
                'name': 'on_missing',
                'type': 'select',
                'options': ['skip', 'null', 'error'],
                'default': 'skip',
                'description': 'Behavior when JSONPath not found: "skip" (skip event), "null" (use null value), "error" (raise error and stop processing).'
            },
            {
                'name': 'flatten_lists',
                'type': 'boolean',
                'default': False,
                'description': 'If JSONPath returns a list with one item, extract just the item instead of the list. Useful for paths like "$.items[0]" to get the item directly.'
            }
        ])
        return schema

    def __repr__(self):
        """String representation of the agent."""
        if 'path' in self.config:
            mode = f'simple: {self.config["path"]}'
        else:
            num_extractions = len(self.config.get('extractions', []))
            mode = f'multi-field: {num_extractions} fields'
        return f'<JSONPathAgent {self.agent_id}: {mode}>'
