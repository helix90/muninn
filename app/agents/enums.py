"""
Enumerations for the Muninn Agent System
"""

from enum import Enum


class AgentStatus(str, Enum):
    """Status of an agent"""
    ACTIVE = 'active'
    PAUSED = 'paused'
    DISABLED = 'disabled'
    ERROR = 'error'


class AgentRunStatus(str, Enum):
    """Status of an agent run"""
    PENDING = 'pending'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'
    SKIPPED = 'skipped'


class AgentType(str, Enum):
    """Types of agents in the system"""
    # Source agents - create events from external sources
    RSS_AGENT = 'rss_agent'
    WEB_FETCH_AGENT = 'web_fetch_agent'
    SCHEDULER_AGENT = 'scheduler_agent'

    # Transform agents - process events to create new events
    FILTER_AGENT = 'filter_agent'
    DEDUPLICATION_AGENT = 'deduplication_agent'
    HTML_PARSER_AGENT = 'html_parser_agent'
    JSON_EXTRACT_AGENT = 'json_extract_agent'
    TEMPLATE_AGENT = 'template_agent'
    DIGEST_AGENT = 'digest_agent'

    # Action agents - consume events without creating new ones
    EMAIL_AGENT = 'email_agent'
    HTTP_POST_AGENT = 'http_post_agent'
    JABBER_AGENT = 'jabber_agent'


class EventFilterType(str, Enum):
    """Types of filters for filtering events"""
    EQUALS = 'equals'
    NOT_EQUALS = 'not_equals'
    CONTAINS = 'contains'
    NOT_CONTAINS = 'not_contains'
    STARTS_WITH = 'starts_with'
    ENDS_WITH = 'ends_with'
    REGEX = 'regex'
    GREATER_THAN = 'greater_than'
    LESS_THAN = 'less_than'
    GREATER_THAN_OR_EQUAL = 'greater_than_or_equal'
    LESS_THAN_OR_EQUAL = 'less_than_or_equal'
    IN_LIST = 'in_list'
    NOT_IN_LIST = 'not_in_list'
    EXISTS = 'exists'
    NOT_EXISTS = 'not_exists'


class AgentCapability(str, Enum):
    """Capabilities that agents can have"""
    CAN_BE_SCHEDULED = 'can_be_scheduled'
    CAN_RECEIVE_EVENTS = 'can_receive_events'
    CAN_CREATE_EVENTS = 'can_create_events'
    REQUIRES_INPUT = 'requires_input'
