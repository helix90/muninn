"""
Agent Service - Agent execution and management

Handles execution of individual agents and integration with event propagation.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
from app.models import Job, AgentRun, Event
from app.agents.registry import agent_registry
from app.services.event_service import EventService
from app.extensions import db

logger = logging.getLogger(__name__)


class AgentService:
    """
    Service for executing and managing agents.

    Handles:
    - Running source agents (scheduled or manual)
    - Recording agent execution runs
    - Triggering event propagation
    - Error handling and logging
    """

    def __init__(self, db_session=None):
        """
        Initialize AgentService.

        Args:
            db_session: Database session (optional, uses default if not provided)
        """
        self.db_session = db_session or db.session
        self.event_service = EventService(db_session=self.db_session)

    def run_agent(
        self,
        agent_id: int,
        manual: bool = False,
        propagate: bool = True
    ) -> Dict[str, Any]:
        """
        Execute an agent and optionally propagate its events.

        Args:
            agent_id: ID of the agent to execute
            manual: Whether this is a manual run (vs scheduled)
            propagate: Whether to propagate events through the network

        Returns:
            Dictionary with execution results:
            {
                'success': bool,
                'agent_run_id': int,
                'events_created': int,
                'error': str (if failed),
                'propagation_stats': dict (if propagated)
            }
        """
        # Get agent from database
        agent_model = self.db_session.query(Job).get(agent_id)
        if not agent_model:
            return {
                'success': False,
                'error': f'Agent {agent_id} not found'
            }

        if not agent_model.is_active:
            return {
                'success': False,
                'error': f'Agent {agent_id} is not active'
            }

        # Create agent run record
        agent_run = AgentRun(
            agent_id=agent_id,
            status='running',
            started_at=datetime.utcnow(),
            manual=manual
        )
        self.db_session.add(agent_run)
        self.db_session.commit()

        result = {
            'success': False,
            'agent_run_id': agent_run.id,
            'events_created': 0
        }

        try:
            # Create agent instance
            agent = agent_registry.create_agent(
                agent_type=agent_model.job_type,
                agent_id=agent_model.id,
                config=agent_model.config,
                user_id=agent_model.user_id,
                db_session=self.db_session
            )

            # Check if agent can be executed directly
            # (Source agents can run without input, transform/action need events)
            if agent.requires_input:
                result['error'] = (
                    f'Agent {agent_id} ({agent_model.job_type}) requires input events, '
                    'cannot be run directly'
                )
                agent_run.status = 'failed'
                agent_run.error_message = result['error']
                agent_run.completed_at = datetime.utcnow()
                self.db_session.commit()
                return result

            # Execute agent (check method handles source agents)
            # Source agents receive empty list since they don't process input events
            events = agent.check([])

            # Persist events to database
            if events:
                for event in events:
                    self.db_session.add(event)
                self.db_session.commit()

                result['events_created'] = len(events)

                # Store event IDs in agent_run
                agent_run.output_event_ids = [event.id for event in events]

            # Mark agent run as successful
            agent_run.status = 'completed'
            agent_run.completed_at = datetime.utcnow()
            self.db_session.commit()

            result['success'] = True

            # Propagate events if requested and events were created
            if propagate and events:
                try:
                    propagation_stats = self.event_service.propagate_events(events)
                    result['propagation_stats'] = propagation_stats
                except Exception as e:
                    logger.error(f'Error propagating events from agent {agent_id}: {e}', exc_info=True)
                    result['propagation_error'] = str(e)

            return result

        except Exception as e:
            logger.error(f'Error executing agent {agent_id}: {e}', exc_info=True)

            # Mark agent run as failed
            agent_run.status = 'failed'
            agent_run.error_message = str(e)
            agent_run.completed_at = datetime.utcnow()
            self.db_session.commit()

            result['error'] = str(e)
            return result

    def run_multiple_agents(
        self,
        agent_ids: List[int],
        manual: bool = False,
        propagate: bool = True
    ) -> Dict[str, Any]:
        """
        Execute multiple agents.

        Args:
            agent_ids: List of agent IDs to execute
            manual: Whether these are manual runs
            propagate: Whether to propagate events

        Returns:
            Dictionary with results for each agent
        """
        results = {}

        for agent_id in agent_ids:
            results[agent_id] = self.run_agent(
                agent_id=agent_id,
                manual=manual,
                propagate=propagate
            )

        return results

    def get_agent_run_history(
        self,
        agent_id: int,
        limit: int = 10,
        offset: int = 0
    ) -> List[AgentRun]:
        """
        Get execution history for an agent.

        Args:
            agent_id: Agent ID
            limit: Maximum number of runs to return
            offset: Number of runs to skip

        Returns:
            List of AgentRun records
        """
        runs = self.db_session.query(AgentRun).filter(
            AgentRun.agent_id == agent_id
        ).order_by(
            AgentRun.started_at.desc()
        ).limit(limit).offset(offset).all()

        return runs

    def get_agent_statistics(self, agent_id: int) -> Dict[str, Any]:
        """
        Get execution statistics for an agent.

        Args:
            agent_id: Agent ID

        Returns:
            Dictionary with statistics
        """
        from sqlalchemy import func

        # Total runs
        total_runs = self.db_session.query(func.count(AgentRun.id)).filter(
            AgentRun.agent_id == agent_id
        ).scalar()

        # Successful runs
        successful_runs = self.db_session.query(func.count(AgentRun.id)).filter(
            AgentRun.agent_id == agent_id,
            AgentRun.status == 'completed'
        ).scalar()

        # Failed runs
        failed_runs = self.db_session.query(func.count(AgentRun.id)).filter(
            AgentRun.agent_id == agent_id,
            AgentRun.status == 'failed'
        ).scalar()

        # Last run
        last_run = self.db_session.query(AgentRun).filter(
            AgentRun.agent_id == agent_id
        ).order_by(AgentRun.started_at.desc()).first()

        # Total events created
        total_events = self.db_session.query(func.count(Event.id)).filter(
            Event.agent_id == agent_id
        ).scalar()

        return {
            'agent_id': agent_id,
            'total_runs': total_runs or 0,
            'successful_runs': successful_runs or 0,
            'failed_runs': failed_runs or 0,
            'success_rate': (successful_runs / total_runs * 100) if total_runs > 0 else 0,
            'total_events_created': total_events or 0,
            'last_run_at': last_run.started_at if last_run else None,
            'last_run_status': last_run.status if last_run else None
        }

    def get_schedulable_agents(self) -> List[Job]:
        """
        Get all agents that can be scheduled (source agents).

        Returns:
            List of Job/Agent model instances
        """
        # Get all active agents
        agents = self.db_session.query(Job).filter(
            Job.is_active == True
        ).all()

        # Filter for agents that can be scheduled
        schedulable = []
        for agent in agents:
            try:
                agent_class = agent_registry.get_agent_class(agent.job_type)
                if agent_class.can_be_scheduled:
                    schedulable.append(agent)
            except ValueError:
                # Unknown agent type, skip
                continue

        return schedulable

    def validate_agent_config(
        self,
        agent_type: str,
        config: Dict[str, Any]
    ) -> tuple[bool, str]:
        """
        Validate agent configuration.

        Args:
            agent_type: Agent type
            config: Configuration dictionary

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            agent_registry.validate_agent_config(agent_type, config)
            return True, ""
        except ValueError as e:
            return False, str(e)

    def get_agent_capabilities(self, agent_type: str) -> Dict[str, bool]:
        """
        Get capabilities for an agent type.

        Args:
            agent_type: Agent type

        Returns:
            Dictionary of capability flags
        """
        try:
            return agent_registry.get_agent_capabilities(agent_type)
        except ValueError as e:
            return {'error': str(e)}

    def create_agent_link(
        self,
        source_agent_id: int,
        target_agent_id: int,
        config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a link between two agents.

        Args:
            source_agent_id: Source agent ID
            target_agent_id: Target agent ID
            config: Optional link configuration

        Returns:
            Dictionary with result:
            {
                'success': bool,
                'link_id': int (if successful),
                'error': str (if failed)
            }
        """
        from app.models import AgentLink

        # Validate the link
        is_valid, error = self.event_service.validate_agent_link(
            source_agent_id,
            target_agent_id
        )

        if not is_valid:
            return {
                'success': False,
                'error': error
            }

        # Create the link
        try:
            link = AgentLink(
                source_agent_id=source_agent_id,
                target_agent_id=target_agent_id,
                config=config or {}
            )
            self.db_session.add(link)
            self.db_session.commit()

            return {
                'success': True,
                'link_id': link.id
            }

        except Exception as e:
            self.db_session.rollback()
            return {
                'success': False,
                'error': str(e)
            }

    def delete_agent_link(self, link_id: int) -> Dict[str, Any]:
        """
        Delete an agent link.

        Args:
            link_id: Agent link ID

        Returns:
            Dictionary with result
        """
        from app.models import AgentLink

        try:
            link = self.db_session.query(AgentLink).get(link_id)
            if not link:
                return {
                    'success': False,
                    'error': f'Link {link_id} not found'
                }

            self.db_session.delete(link)
            self.db_session.commit()

            return {'success': True}

        except Exception as e:
            self.db_session.rollback()
            return {
                'success': False,
                'error': str(e)
            }
