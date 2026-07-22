"""Router Agent — route events to different downstream branches by condition."""

import re
from typing import Any, Dict, List

from app.agents.base import TransformAgent
from app.agents.registry import register_agent
from app.agents.enums import EventFilterType
from app.models import Event


@register_agent
class RouterAgent(TransformAgent):
    """
    Tags each incoming event with a '_route' value in its metadata based on the
    first matching rule set. Downstream agents (FilterAgents or route_key links)
    select events by checking event.metadata['_route'].

    Configuration:
        routes (list): Ordered routing rules. First match wins.
            Each entry:
                route (str):     Route label to assign (e.g. "high_priority")
                rules (list):    Filter rules — same schema as FilterAgent
                match_all (bool): AND logic within a route's rules (default: true)
        default_route (str): Label assigned when no route matches (default: "default")

    Example:
        routes:
          - route: urgent
            rules: [{field: priority, type: equals, value: high}]
          - route: normal
            rules: [{field: priority, type: exists}]
        default_route: low
    """

    agent_type = 'router_agent'
    agent_category = 'transform'

    def validate_config(self) -> None:
        super().validate_config()

        routes = self.config.get('routes')
        if not routes:
            raise ValueError("routes is required and must be a non-empty list")
        if not isinstance(routes, list) or len(routes) == 0:
            raise ValueError("routes must be a non-empty list")

        for i, route in enumerate(routes):
            if not isinstance(route, dict):
                raise ValueError(f"routes[{i}] must be a dict")
            if not route.get('route'):
                raise ValueError(f"routes[{i}] missing 'route' name")
            rules = route.get('rules')
            if not rules or not isinstance(rules, list) or len(rules) == 0:
                raise ValueError(f"routes[{i}] must have at least one rule")
            for j, rule in enumerate(rules):
                self._validate_rule(i, j, rule)

    def _validate_rule(self, route_idx: int, rule_idx: int, rule: Dict) -> None:
        if 'field' not in rule:
            raise ValueError(f"routes[{route_idx}].rules[{rule_idx}] missing 'field'")
        if 'type' not in rule:
            raise ValueError(f"routes[{route_idx}].rules[{rule_idx}] missing 'type'")
        try:
            ft = EventFilterType(rule['type'])
        except ValueError:
            valid = [t.value for t in EventFilterType]
            raise ValueError(
                f"routes[{route_idx}].rules[{rule_idx}] invalid type '{rule['type']}'. "
                f"Valid: {valid}"
            )
        if ft not in (EventFilterType.EXISTS, EventFilterType.NOT_EXISTS):
            if 'value' not in rule:
                raise ValueError(
                    f"routes[{route_idx}].rules[{rule_idx}] missing 'value'"
                )

    def process(self, events: List[Event]) -> List[Event]:
        routes = self.config['routes']
        default_route = self.config.get('default_route', 'default')

        for event in events:
            assigned = default_route
            for route_def in routes:
                if self._matches(event, route_def['rules'], route_def.get('match_all', True)):
                    assigned = route_def['route']
                    break
            if event.event_metadata is None:
                event.event_metadata = {}
            event.event_metadata['_route'] = assigned
            self.log(f'Event {event.id} → route: {assigned}')

        return events

    def _matches(self, event: Event, rules: List[Dict], match_all: bool) -> bool:
        results = [self._check_rule(event, r) for r in rules]
        return all(results) if match_all else any(results)

    def _check_rule(self, event: Event, rule: Dict) -> bool:
        ft = EventFilterType(rule['type'])
        field_value = event.get_payload_field(rule['field'])
        expected = rule.get('value')
        case_sensitive = rule.get('case_sensitive', True)

        if ft == EventFilterType.EXISTS:
            return field_value is not None
        if ft == EventFilterType.NOT_EXISTS:
            return field_value is None
        if field_value is None:
            return False

        # Numeric
        if ft in (EventFilterType.GREATER_THAN, EventFilterType.LESS_THAN,
                  EventFilterType.GREATER_THAN_OR_EQUAL, EventFilterType.LESS_THAN_OR_EQUAL):
            try:
                fv, ev = float(field_value), float(expected)
                if ft == EventFilterType.GREATER_THAN:
                    return fv > ev
                if ft == EventFilterType.LESS_THAN:
                    return fv < ev
                if ft == EventFilterType.GREATER_THAN_OR_EQUAL:
                    return fv >= ev
                return fv <= ev
            except (TypeError, ValueError):
                return False

        # String
        fv_s = str(field_value)
        ev_s = str(expected) if expected is not None else ''
        if not case_sensitive:
            fv_s, ev_s = fv_s.lower(), ev_s.lower()

        if ft == EventFilterType.EQUALS:
            return fv_s == ev_s
        if ft == EventFilterType.NOT_EQUALS:
            return fv_s != ev_s
        if ft == EventFilterType.CONTAINS:
            return ev_s in fv_s
        if ft == EventFilterType.NOT_CONTAINS:
            return ev_s not in fv_s
        if ft == EventFilterType.STARTS_WITH:
            return fv_s.startswith(ev_s)
        if ft == EventFilterType.ENDS_WITH:
            return fv_s.endswith(ev_s)
        if ft == EventFilterType.REGEX:
            flags = 0 if case_sensitive else re.IGNORECASE
            return bool(re.search(ev_s, fv_s, flags))
        if ft == EventFilterType.IN_LIST:
            lst = expected if isinstance(expected, list) else [expected]
            return field_value in lst
        if ft == EventFilterType.NOT_IN_LIST:
            lst = expected if isinstance(expected, list) else [expected]
            return field_value not in lst
        return False

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        schema = super().get_config_schema()
        schema['required_fields'] = ['routes']
        schema['optional_fields'].extend([
            {
                'name': 'default_route',
                'type': 'text',
                'default': 'default',
                'description': (
                    "Route label assigned when no rule matches. "
                    "Downstream agents that check _route=='default' will receive these events."
                ),
            },
        ])
        return schema
