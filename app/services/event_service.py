"""
Event Service - Event propagation engine

Handles propagation of events through agent networks.
Events flow from source agents → transform agents → action agents.
"""

from typing import List, Dict, Any, Set, Optional
from datetime import datetime
import logging
from sqlalchemy import cast, String
from app.models import Event, AgentLink
from app.extensions import db

logger = logging.getLogger(__name__)


class EventService:
    """
    Service for propagating events through agent networks.

    Implements event-based data flow between agents,
    handling fan-out, fan-in, and cycle prevention.
    """

    def __init__(self, db_session=None, max_depth=10):
        """
        Initialize EventService.

        Args:
            db_session: Database session (optional, uses default if not provided)
            max_depth: Maximum propagation depth to prevent infinite loops
        """
        self.db_session = db_session or db.session
        self.max_depth = max_depth

    def propagate_events(self, events: List[Event]) -> Dict[str, Any]:
        """
        Propagate events through the agent network.

        Takes events from a source agent and propagates them through
        all connected downstream agents recursively.

        Args:
            events: List of events to propagate

        Returns:
            Dictionary with propagation statistics:
            {
                'events_propagated': int,
                'agents_executed': int,
                'events_created': int,
                'max_depth_reached': bool,
                'agent_execution_counts': Dict[int, int]
            }
        """
        if not events:
            return {
                'events_propagated': 0,
                'agents_executed': 0,
                'events_created': 0,
                'max_depth_reached': False,
                'agent_execution_counts': {}
            }

        # Statistics tracking
        stats = {
            'events_propagated': 0,
            'agents_executed': 0,
            'events_created': 0,
            'max_depth_reached': False,
            'agent_execution_counts': {}  # agent_id -> execution_count
        }

        # Start propagation from depth 0
        self._propagate_recursive(
            events=events,
            depth=0,
            stats=stats,
            visited_agent_ids=set()
        )

        return stats

    def _propagate_recursive(
        self,
        events: List[Event],
        depth: int,
        stats: Dict[str, Any],
        visited_agent_ids: Set[int]
    ) -> None:
        """
        Recursively propagate events through agent network.

        Args:
            events: Events to propagate
            depth: Current recursion depth
            stats: Statistics dict to update
            visited_agent_ids: Set of agent IDs already visited in this path
        """
        # Check max depth
        if depth >= self.max_depth:
            stats['max_depth_reached'] = True
            logger.warning(f'Max propagation depth ({self.max_depth}) reached')
            return

        if not events:
            return

        # Group events by source agent
        events_by_agent = {}
        for event in events:
            agent_id = event.agent_id
            if agent_id not in events_by_agent:
                events_by_agent[agent_id] = []
            events_by_agent[agent_id].append(event)

        # For each source agent, find and execute downstream agents
        for source_agent_id, agent_events in events_by_agent.items():
            # Get downstream agents
            downstream_agents = self._get_downstream_agents(source_agent_id)

            if not downstream_agents:
                # No downstream agents, events end here
                stats['events_propagated'] += len(agent_events)
                continue

            # Execute each downstream agent with the events
            for target_agent in downstream_agents:
                target_agent_id = target_agent.id

                # Skip if this creates a cycle
                if target_agent_id in visited_agent_ids:
                    logger.warning(
                        f'Cycle detected: agent {target_agent_id} already visited, skipping'
                    )
                    continue

                # Execute the agent
                try:
                    new_events = self._execute_agent(target_agent, agent_events)

                    # Update statistics
                    stats['agents_executed'] += 1
                    stats['agent_execution_counts'][target_agent_id] = \
                        stats['agent_execution_counts'].get(target_agent_id, 0) + 1
                    stats['events_propagated'] += len(agent_events)

                    if new_events:
                        stats['events_created'] += len(new_events)

                        # Recursively propagate new events
                        new_visited = visited_agent_ids.copy()
                        new_visited.add(target_agent_id)  # Add the target agent we just executed

                        self._propagate_recursive(
                            events=new_events,
                            depth=depth + 1,
                            stats=stats,
                            visited_agent_ids=new_visited
                        )

                except Exception as e:
                    logger.error(
                        f'Error executing agent {target_agent_id}: {e}',
                        exc_info=True
                    )
                    # Continue with other agents even if one fails

    def _get_downstream_agents(self, source_agent_id: int) -> List:
        """
        Get all active downstream agents for a source agent.

        Args:
            source_agent_id: ID of source agent

        Returns:
            List of Job/Agent model instances
        """
        from app.models import Job

        # Query agent links
        links = self.db_session.query(AgentLink).filter(
            AgentLink.source_agent_id == source_agent_id,
            AgentLink.is_active == True
        ).all()

        if not links:
            return []

        # Get target agent IDs
        target_agent_ids = [link.target_agent_id for link in links]

        # Get agent instances
        agents = self.db_session.query(Job).filter(
            Job.id.in_(target_agent_ids),
            Job.is_active == True
        ).all()

        return agents

    def _execute_agent(self, agent_model, events: List[Event]) -> List[Event]:
        """
        Execute an agent with incoming events.

        Args:
            agent_model: Job/Agent database model instance
            events: Events to process

        Returns:
            List of new events created by the agent (empty for action agents)
        """
        from app.agents.registry import agent_registry
        from app.models import AgentRun
        from datetime import datetime

        # Check if agent can receive events first (before creating run record)
        agent_class = agent_registry.get_agent_class(agent_model.job_type)
        if agent_class and not agent_class.can_receive_events:
            logger.warning(
                f'Agent {agent_model.id} ({agent_model.job_type}) '
                f'cannot receive events, skipping'
            )
            return []

        # Create AgentRun record to track this execution
        agent_run = AgentRun(
            agent_id=agent_model.id,
            status='running',
            started_at=datetime.utcnow(),
            manual=False,  # Triggered by event propagation
            input_event_ids=[e.id for e in events]
        )
        self.db_session.add(agent_run)
        self.db_session.flush()  # Get the agent_run.id

        # Create agent instance
        try:
            agent = agent_registry.create_agent(
                agent_type=agent_model.job_type,
                agent_id=agent_model.id,
                config=agent_model.config,
                user_id=agent_model.user_id,
                db_session=self.db_session
            )
        except Exception as e:
            logger.error(f'Failed to create agent {agent_model.id}: {e}')
            agent_run.status = 'failed'
            agent_run.completed_at = datetime.utcnow()
            agent_run.error_message = str(e)
            self.db_session.commit()
            return []

        # Execute agent with events
        try:
            new_events = agent.check(events)

            # Update agent_id for all returned events to reflect the processing agent
            # and persist new events to database
            if new_events:
                for event in new_events:
                    # Update the agent_id to the current agent
                    event.agent_id = agent_model.id
                    event.agent_type = agent_model.job_type

                    # Add to session (will update if exists, insert if new)
                    self.db_session.add(event)
                self.db_session.flush()  # Get event IDs

                # Update agent_run with output event IDs
                agent_run.output_event_ids = [e.id for e in new_events]

            # Mark run as completed
            agent_run.status = 'completed'
            agent_run.completed_at = datetime.utcnow()
            self.db_session.commit()

            logger.info(
                f'Agent {agent_model.id} executed via propagation: '
                f'{len(events)} input events -> {len(new_events) if new_events else 0} output events'
            )

            return new_events if new_events else []

        except Exception as e:
            logger.error(
                f'Error processing events in agent {agent_model.id}: {e}',
                exc_info=True
            )
            # Mark run as failed
            agent_run.status = 'failed'
            agent_run.completed_at = datetime.utcnow()
            agent_run.error_message = str(e)
            self.db_session.commit()
            return []

    def get_agent_network_stats(self, agent_id: int) -> Dict[str, Any]:
        """
        Get statistics about an agent's network connections.

        Args:
            agent_id: Agent ID

        Returns:
            Dictionary with network statistics
        """
        # Count downstream agents
        downstream_count = self.db_session.query(AgentLink).filter(
            AgentLink.source_agent_id == agent_id,
            AgentLink.is_active == True
        ).count()

        # Count upstream agents
        upstream_count = self.db_session.query(AgentLink).filter(
            AgentLink.target_agent_id == agent_id,
            AgentLink.is_active == True
        ).count()

        return {
            'agent_id': agent_id,
            'downstream_agents': downstream_count,
            'upstream_agents': upstream_count,
            'is_source': upstream_count == 0,
            'is_terminal': downstream_count == 0
        }

    def validate_agent_link(
        self,
        source_agent_id: int,
        target_agent_id: int
    ) -> tuple[bool, str]:
        """
        Validate if a link between two agents is valid.

        Args:
            source_agent_id: Source agent ID
            target_agent_id: Target agent ID

        Returns:
            Tuple of (is_valid, error_message)
        """
        from app.models import Job
        from app.agents.registry import agent_registry

        # Same agent check
        if source_agent_id == target_agent_id:
            return False, "Cannot link agent to itself"

        # Get agents
        source = self.db_session.query(Job).get(source_agent_id)
        target = self.db_session.query(Job).get(target_agent_id)

        if not source:
            return False, f"Source agent {source_agent_id} not found"
        if not target:
            return False, f"Target agent {target_agent_id} not found"

        # Check if source can create events
        try:
            source_class = agent_registry.get_agent_class(source.job_type)
            if not source_class.can_create_events:
                return False, f"Source agent ({source.job_type}) cannot create events"
        except ValueError:
            return False, f"Unknown source agent type: {source.job_type}"

        # Check if target can receive events
        try:
            target_class = agent_registry.get_agent_class(target.job_type)
            if not target_class.can_receive_events:
                return False, f"Target agent ({target.job_type}) cannot receive events"
        except ValueError:
            return False, f"Unknown target agent type: {target.job_type}"

        # Check for existing link
        existing = self.db_session.query(AgentLink).filter(
            AgentLink.source_agent_id == source_agent_id,
            AgentLink.target_agent_id == target_agent_id
        ).first()

        if existing:
            return False, "Link already exists"

        return True, ""

    def get_events_for_agent(
        self,
        agent_id: int,
        limit: Optional[int] = None,
        offset: int = 0,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        payload_search: Optional[str] = None
    ) -> List[Event]:
        """
        Get events for a specific agent with optional filtering.

        Args:
            agent_id: ID of the agent
            limit: Maximum number of events to return (None = all)
            offset: Number of events to skip (for pagination)
            start_date: Filter events after this date
            end_date: Filter events before this date
            payload_search: Text to search for in payload JSON

        Returns:
            List of Event objects
        """
        query = self.db_session.query(Event).filter(Event.agent_id == agent_id)

        # Apply date filters
        if start_date:
            query = query.filter(Event.created_at >= start_date)
        if end_date:
            query = query.filter(Event.created_at <= end_date)

        # Apply payload search (search within JSON payload)
        if payload_search:
            query = query.filter(cast(Event.payload, String).contains(payload_search))

        # Order by most recent first
        query = query.order_by(Event.created_at.desc())

        # Apply pagination
        if offset:
            query = query.offset(offset)
        if limit:
            query = query.limit(limit)

        return query.all()

    def count_events_for_agent(
        self,
        agent_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        payload_search: Optional[str] = None
    ) -> int:
        """
        Count events for a specific agent with optional filtering.

        Args:
            agent_id: ID of the agent
            start_date: Filter events after this date
            end_date: Filter events before this date
            payload_search: Text to search for in payload JSON

        Returns:
            Count of matching events
        """
        query = self.db_session.query(Event).filter(Event.agent_id == agent_id)

        # Apply date filters
        if start_date:
            query = query.filter(Event.created_at >= start_date)
        if end_date:
            query = query.filter(Event.created_at <= end_date)

        # Apply payload search
        if payload_search:
            query = query.filter(cast(Event.payload, String).contains(payload_search))

        return query.count()

    def get_all_events(
        self,
        user_id: int,
        limit: Optional[int] = None,
        offset: int = 0,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        agent_type: Optional[str] = None,
        agent_id: Optional[int] = None,
        payload_search: Optional[str] = None
    ) -> List[Event]:
        """
        Get all events for a user with comprehensive filtering.

        Args:
            user_id: ID of the user
            limit: Maximum number of events to return
            offset: Number of events to skip
            start_date: Filter events after this date
            end_date: Filter events before this date
            agent_type: Filter by agent type (rss_agent, filter_agent, etc.)
            agent_id: Filter by specific agent ID
            payload_search: Text to search for in payload JSON

        Returns:
            List of Event objects
        """
        # SECURITY: Filter by user_id to enforce data isolation
        query = self.db_session.query(Event).filter(Event.user_id == user_id)

        # Apply agent filters
        if agent_type:
            query = query.filter(Event.agent_type == agent_type)
        if agent_id:
            query = query.filter(Event.agent_id == agent_id)

        # Apply date filters
        if start_date:
            query = query.filter(Event.created_at >= start_date)
        if end_date:
            query = query.filter(Event.created_at <= end_date)

        # Apply payload search
        if payload_search:
            query = query.filter(cast(Event.payload, String).contains(payload_search))

        # Order by most recent first
        query = query.order_by(Event.created_at.desc())

        # Apply pagination
        if offset:
            query = query.offset(offset)
        if limit:
            query = query.limit(limit)

        return query.all()

    def count_all_events(
        self,
        user_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        agent_type: Optional[str] = None,
        agent_id: Optional[int] = None,
        payload_search: Optional[str] = None
    ) -> int:
        """
        Count all events for a user with comprehensive filtering.

        Args:
            user_id: ID of the user
            start_date: Filter events after this date
            end_date: Filter events before this date
            agent_type: Filter by agent type
            agent_id: Filter by specific agent ID
            payload_search: Text to search for in payload JSON

        Returns:
            Count of matching events
        """
        # SECURITY: Filter by user_id to enforce data isolation
        query = self.db_session.query(Event).filter(Event.user_id == user_id)

        # Apply agent filters
        if agent_type:
            query = query.filter(Event.agent_type == agent_type)
        if agent_id:
            query = query.filter(Event.agent_id == agent_id)

        # Apply date filters
        if start_date:
            query = query.filter(Event.created_at >= start_date)
        if end_date:
            query = query.filter(Event.created_at <= end_date)

        # Apply payload search
        if payload_search:
            query = query.filter(cast(Event.payload, String).contains(payload_search))

        return query.count()
