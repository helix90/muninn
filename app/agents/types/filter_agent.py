"""
Filter Agent - Rule-based event filtering

Single responsibility: ONLY filters events based on rules.
Does NOT fetch data or perform actions.
"""

from typing import List, Dict, Any
import re
from app.agents.base import TransformAgent
from app.agents.registry import register_agent
from app.agents.enums import EventFilterType
from app.models import Event


@register_agent
class FilterAgent(TransformAgent):
    """
    Filters events based on configurable rules.

    Configuration:
        rules (list): List of filter rules to apply
            Each rule: {field, type, value, case_sensitive}
        match_all (bool): True = AND logic, False = OR logic (default: True)
    """

    agent_type = 'filter_agent'

    def validate_config(self) -> None:
        """Validate filter agent configuration."""
        super().validate_config()

        if 'rules' not in self.config:
            raise ValueError("Filter agent requires 'rules' in config")

        if not isinstance(self.config['rules'], list):
            raise ValueError("'rules' must be a list")

        if len(self.config['rules']) == 0:
            raise ValueError("'rules' must contain at least one rule")

        # Validate each rule
        for i, rule in enumerate(self.config['rules']):
            if not isinstance(rule, dict):
                raise ValueError(f"Rule {i} must be a dictionary")

            if 'field' not in rule:
                raise ValueError(f"Rule {i} missing 'field'")

            if 'type' not in rule:
                raise ValueError(f"Rule {i} missing 'type'")

            # Validate filter type
            try:
                filter_type = EventFilterType(rule['type'])
            except ValueError:
                valid_types = [t.value for t in EventFilterType]
                raise ValueError(
                    f"Rule {i} has invalid type '{rule['type']}'. "
                    f"Valid types: {valid_types}"
                )

            # Some filter types require a value
            if filter_type not in [EventFilterType.EXISTS, EventFilterType.NOT_EXISTS]:
                if 'value' not in rule:
                    raise ValueError(f"Rule {i} missing 'value'")

        # Validate match_all
        if 'match_all' in self.config:
            if not isinstance(self.config['match_all'], bool):
                raise ValueError("'match_all' must be a boolean")

    def process(self, events: List[Event]) -> List[Event]:
        """
        Filter events based on rules.

        Args:
            events: Events to filter

        Returns:
            List of events that match the filter rules
        """
        rules = self.config['rules']
        match_all = self.config.get('match_all', True)

        filtered_events = []

        for event in events:
            if self._matches_rules(event, rules, match_all):
                filtered_events.append(event)

        self.log(f'Filtered {len(events)} events down to {len(filtered_events)}', data={
            'input_count': len(events),
            'output_count': len(filtered_events),
            'match_all': match_all,
            'rule_count': len(rules)
        })

        return filtered_events

    def _matches_rules(self, event: Event, rules: List[Dict], match_all: bool) -> bool:
        """
        Check if event matches the filter rules.

        Args:
            event: Event to check
            rules: List of filter rules
            match_all: If True, all rules must match (AND). If False, any rule can match (OR)

        Returns:
            True if event matches, False otherwise
        """
        matches = []

        for rule in rules:
            field = rule['field']
            filter_type = EventFilterType(rule['type'])
            value = rule.get('value')
            case_sensitive = rule.get('case_sensitive', True)

            # Get field value from event payload
            field_value = event.get_payload_field(field)

            # Check if rule matches
            rule_matches = self._check_rule(field_value, filter_type, value, case_sensitive)
            matches.append(rule_matches)

        # Apply AND/OR logic
        if match_all:
            return all(matches)
        else:
            return any(matches)

    def _check_rule(self, field_value: Any, filter_type: EventFilterType,
                    expected_value: Any, case_sensitive: bool) -> bool:
        """
        Check if a single rule matches.

        Args:
            field_value: Value from event payload
            filter_type: Type of filter to apply
            expected_value: Expected value for comparison
            case_sensitive: Whether string comparisons are case-sensitive

        Returns:
            True if rule matches, False otherwise
        """
        # Handle None/missing values
        if filter_type == EventFilterType.EXISTS:
            return field_value is not None

        if filter_type == EventFilterType.NOT_EXISTS:
            return field_value is None

        if field_value is None:
            return False

        # Convert to strings for string operations (if needed)
        if filter_type in [EventFilterType.CONTAINS, EventFilterType.NOT_CONTAINS,
                          EventFilterType.STARTS_WITH, EventFilterType.ENDS_WITH,
                          EventFilterType.REGEX]:
            field_str = str(field_value)
            expected_str = str(expected_value)

            if not case_sensitive:
                field_str = field_str.lower()
                expected_str = expected_str.lower()

            if filter_type == EventFilterType.CONTAINS:
                return expected_str in field_str

            elif filter_type == EventFilterType.NOT_CONTAINS:
                return expected_str not in field_str

            elif filter_type == EventFilterType.STARTS_WITH:
                return field_str.startswith(expected_str)

            elif filter_type == EventFilterType.ENDS_WITH:
                return field_str.endswith(expected_str)

            elif filter_type == EventFilterType.REGEX:
                flags = 0 if case_sensitive else re.IGNORECASE
                return bool(re.search(expected_str, field_str, flags))

        # Equality checks
        if filter_type == EventFilterType.EQUALS:
            if isinstance(field_value, str) and isinstance(expected_value, str):
                if not case_sensitive:
                    return field_value.lower() == expected_value.lower()
            return field_value == expected_value

        elif filter_type == EventFilterType.NOT_EQUALS:
            if isinstance(field_value, str) and isinstance(expected_value, str):
                if not case_sensitive:
                    return field_value.lower() != expected_value.lower()
            return field_value != expected_value

        # Numeric comparisons
        elif filter_type == EventFilterType.GREATER_THAN:
            try:
                return float(field_value) > float(expected_value)
            except (TypeError, ValueError):
                return False

        elif filter_type == EventFilterType.LESS_THAN:
            try:
                return float(field_value) < float(expected_value)
            except (TypeError, ValueError):
                return False

        elif filter_type == EventFilterType.GREATER_THAN_OR_EQUAL:
            try:
                return float(field_value) >= float(expected_value)
            except (TypeError, ValueError):
                return False

        elif filter_type == EventFilterType.LESS_THAN_OR_EQUAL:
            try:
                return float(field_value) <= float(expected_value)
            except (TypeError, ValueError):
                return False

        # List membership checks
        elif filter_type == EventFilterType.IN_LIST:
            if not isinstance(expected_value, list):
                return False
            return field_value in expected_value

        elif filter_type == EventFilterType.NOT_IN_LIST:
            if not isinstance(expected_value, list):
                return True
            return field_value not in expected_value

        return False

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """Get configuration schema for filter agent."""
        schema = super().get_config_schema()
        schema['required_fields'] = ['rules']
        schema['optional_fields'] = [
            {
                'name': 'match_all',
                'type': 'boolean',
                'default': True,
                'description': 'If true, all rules must match (AND logic). If false, any rule can match (OR logic)'
            }
        ]
        schema['rule_schema'] = {
            'field': {'type': 'string', 'required': True, 'description': 'Field path in event payload (e.g., "title" or "user.name")'},
            'type': {'type': 'string', 'required': True, 'description': f'Filter type: {[t.value for t in EventFilterType]}'},
            'value': {'type': 'any', 'required': False, 'description': 'Value to compare against (not needed for exists/not_exists)'},
            'case_sensitive': {'type': 'boolean', 'default': True, 'description': 'Whether string comparisons are case-sensitive'}
        }
        return schema
