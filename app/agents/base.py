"""
Base agent classes for the Muninn agent system

Defines the abstract base classes and agent hierarchy:
- BaseAgent: Abstract base for all agents
- SourceAgent: Agents that create events from external sources
- TransformAgent: Agents that process events to create new events
- ActionAgent: Agents that consume events without creating new ones
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from app.agents.memory import MemoryManager
from app.models import Event
from app.extensions import db


class BaseAgent(ABC):
    """
    Abstract base class for all Muninn agents.

    Agents are single-responsibility components that either:
    - Create events from external sources (SourceAgent)
    - Transform events into new events (TransformAgent)
    - Consume events and perform actions (ActionAgent)
    """

    # Agent type identifier (must be set by subclasses)
    agent_type: str = None

    # Agent capabilities (set by subclass hierarchy)
    can_be_scheduled: bool = False
    can_receive_events: bool = False
    can_create_events: bool = False
    requires_input: bool = False

    def __init__(self, agent_id: int, config: Dict[str, Any], user_id: int, db_session=None):
        """
        Initialize the agent.

        Args:
            agent_id: Database ID of this agent instance
            config: Agent configuration dictionary
            user_id: ID of the user who owns this agent
            db_session: Database session (defaults to db.session)
        """
        if self.agent_type is None:
            raise ValueError(f"{self.__class__.__name__} must set agent_type")

        self.agent_id = agent_id
        self.config = config
        self.user_id = user_id
        self.db_session = db_session or db.session

        # Initialize memory manager
        self.memory = MemoryManager(agent_id, user_id, db_session)

        # Validate configuration on initialization
        self.validate_config()

    @abstractmethod
    def check(self, incoming_events: List[Event]) -> List[Event]:
        """
        Main agent execution method.

        This is called by the scheduler (for SourceAgents) or when receiving
        events from upstream agents (for Transform/ActionAgents).

        Args:
            incoming_events: List of events to process (empty for SourceAgents)

        Returns:
            List of new events created by this agent (empty for ActionAgents)
        """
        pass

    def validate_config(self) -> None:
        """
        Validate agent configuration.

        Override this method to implement config validation.
        Raise ValueError if configuration is invalid.
        """
        if not isinstance(self.config, dict):
            raise ValueError("Agent config must be a dictionary")

    def create_event(self, payload: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None,
                     expires_at: Optional[datetime] = None) -> Event:
        """
        Create a new event from this agent.

        Args:
            payload: Event data payload
            metadata: Event metadata (optional)
            expires_at: Event expiration time (optional)

        Returns:
            Created Event object
        """
        if not self.can_create_events:
            raise RuntimeError(f"{self.__class__.__name__} cannot create events")

        event = Event(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            user_id=self.user_id,
            payload=payload,
            metadata=metadata or {},
            expires_at=expires_at
        )

        self.db_session.add(event)
        return event

    def log(self, message: str, level: str = 'info', data: Optional[Dict] = None) -> None:
        """
        Log an agent message.

        Args:
            message: Log message
            level: Log level (debug, info, warning, error)
            data: Additional data to log
        """
        # TODO: Implement proper logging system
        # For now, just store in memory for debugging
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': level,
            'message': message,
            'data': data or {}
        }

        # Store last 100 log entries in memory
        self.memory.append_to_list('_logs', log_entry, max_length=100)

    def _cleanup_old_events(self) -> int:
        """
        Clean up old events based on event_retention_days config.

        Deletes events older than the configured retention period.
        Following the Huginn model, each agent specifies its own retention.

        Returns:
            Number of events deleted
        """
        retention_days = self.config.get('event_retention_days', 90)

        if retention_days <= 0:
            # Retention disabled (keep forever)
            return 0

        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

        try:
            # Delete old events created by this agent
            deleted_count = self.db_session.query(Event).filter(
                Event.agent_id == self.agent_id,
                Event.created_at < cutoff_date
            ).delete(synchronize_session=False)

            if deleted_count > 0:
                self.db_session.commit()
                self.log(f'Cleaned up {deleted_count} events older than {retention_days} days',
                        level='info', data={'retention_days': retention_days, 'deleted_count': deleted_count})

            return deleted_count

        except Exception as e:
            self.log(f'Error cleaning up old events: {e}', level='error')
            self.db_session.rollback()
            return 0

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """
        Get the configuration schema for this agent type.

        Returns a dictionary describing the required and optional config fields.
        Override this method to provide schema information.

        Returns:
            Configuration schema dictionary
        """
        return {
            'agent_type': cls.agent_type,
            'required_fields': [],
            'optional_fields': [
                {
                    'name': 'event_retention_days',
                    'type': 'integer',
                    'default': 90,
                    'description': 'Number of days to keep events (0 = keep forever)'
                }
            ],
            'capabilities': {
                'can_be_scheduled': cls.can_be_scheduled,
                'can_receive_events': cls.can_receive_events,
                'can_create_events': cls.can_create_events,
                'requires_input': cls.requires_input
            }
        }

    def __repr__(self):
        return f'<{self.__class__.__name__} id={self.agent_id}>'


class SourceAgent(BaseAgent):
    """
    Base class for source agents.

    Source agents create events from external sources like RSS feeds,
    web APIs, or scheduled triggers. They run on a schedule and do not
    receive events from other agents.

    Characteristics:
    - Can be scheduled (runs periodically)
    - Cannot receive events
    - Can create events
    - Does not require input
    """

    can_be_scheduled = True
    can_receive_events = False
    can_create_events = True
    requires_input = False

    def check(self, incoming_events: List[Event]) -> List[Event]:
        """
        Fetch data from external source and create events.

        Args:
            incoming_events: Always empty for source agents

        Returns:
            List of events created from external source
        """
        # Clean up old events based on retention policy
        self._cleanup_old_events()

        if incoming_events:
            self.log('Warning: Source agent received events (ignoring)', level='warning')

        # Call the fetch method implemented by subclass
        return self.fetch()

    @abstractmethod
    def fetch(self) -> List[Event]:
        """
        Fetch data from external source.

        Implement this method in subclasses to fetch data from
        RSS feeds, web APIs, databases, etc.

        Returns:
            List of events created from fetched data
        """
        pass


class TransformAgent(BaseAgent):
    """
    Base class for transform agents.

    Transform agents process events from upstream agents and create
    new events. They filter, parse, deduplicate, or transform data.

    Characteristics:
    - Cannot be scheduled (event-driven)
    - Can receive events
    - Can create events
    - Requires input
    """

    can_be_scheduled = False
    can_receive_events = True
    can_create_events = True
    requires_input = True

    def check(self, incoming_events: List[Event]) -> List[Event]:
        """
        Process incoming events and create new events.

        Args:
            incoming_events: Events to process

        Returns:
            List of transformed/filtered events
        """
        # Clean up old events based on retention policy
        self._cleanup_old_events()

        if not incoming_events:
            self.log('No incoming events to process', level='debug')
            return []

        # Call the process method implemented by subclass
        return self.process(incoming_events)

    @abstractmethod
    def process(self, events: List[Event]) -> List[Event]:
        """
        Process events and create new events.

        Implement this method in subclasses to filter, transform,
        deduplicate, or otherwise process events.

        Args:
            events: Events to process

        Returns:
            List of new events
        """
        pass


class ActionAgent(BaseAgent):
    """
    Base class for action agents.

    Action agents consume events and perform terminal actions like
    sending emails, posting to webhooks, or sending messages. They
    do not create new events.

    Characteristics:
    - Cannot be scheduled (event-driven)
    - Can receive events
    - Cannot create events
    - Requires input
    """

    can_be_scheduled = False
    can_receive_events = True
    can_create_events = False
    requires_input = True

    def check(self, incoming_events: List[Event]) -> List[Event]:
        """
        Process incoming events and perform actions.

        Args:
            incoming_events: Events to act upon

        Returns:
            Always returns empty list (action agents don't create events)
        """
        # Clean up old events based on retention policy
        self._cleanup_old_events()

        if not incoming_events:
            self.log('No incoming events to act on', level='debug')
            return []

        # Call the act method implemented by subclass
        self.act(incoming_events)

        # Action agents never create events
        return []

    @abstractmethod
    def act(self, events: List[Event]) -> None:
        """
        Perform actions based on events.

        Implement this method in subclasses to send emails, post to
        webhooks, send messages, etc.

        Args:
            events: Events to act upon
        """
        pass
