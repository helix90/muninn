"""
Agent registry for dynamic agent type management

Provides registration and instantiation of agent types.
Similar to the job registry but for the new agent system.
"""

from typing import Dict, Type, List, Any, Optional
from app.agents.base import BaseAgent, SourceAgent, TransformAgent, ActionAgent


class AgentRegistry:
    """
    Registry for agent types.

    Manages registration of agent classes and provides methods for
    creating agent instances and retrieving agent metadata.
    """

    def __init__(self):
        """Initialize the agent registry."""
        self._registry: Dict[str, Type[BaseAgent]] = {}

    def register(self, agent_class: Type[BaseAgent]) -> None:
        """
        Register an agent class.

        Args:
            agent_class: Agent class to register

        Raises:
            ValueError: If agent_type is not set or already registered
        """
        if not hasattr(agent_class, 'agent_type') or agent_class.agent_type is None:
            raise ValueError(f"{agent_class.__name__} must set agent_type")

        agent_type = agent_class.agent_type

        if agent_type in self._registry:
            raise ValueError(f"Agent type '{agent_type}' is already registered")

        self._registry[agent_type] = agent_class

    def unregister(self, agent_type: str) -> bool:
        """
        Unregister an agent type.

        Args:
            agent_type: Agent type to unregister

        Returns:
            True if unregistered, False if not found
        """
        if agent_type in self._registry:
            del self._registry[agent_type]
            return True
        return False

    def is_registered(self, agent_type: str) -> bool:
        """
        Check if an agent type is registered.

        Args:
            agent_type: Agent type to check

        Returns:
            True if registered, False otherwise
        """
        return agent_type in self._registry

    def get_agent_class(self, agent_type: str) -> Type[BaseAgent]:
        """
        Get the agent class for a given type.

        Args:
            agent_type: Agent type

        Returns:
            Agent class

        Raises:
            ValueError: If agent type not registered
        """
        if agent_type not in self._registry:
            raise ValueError(f"Unknown agent type: {agent_type}")

        return self._registry[agent_type]

    def create_agent(self, agent_type: str, agent_id: int, config: Dict[str, Any],
                     user_id: int, db_session=None) -> BaseAgent:
        """
        Create an agent instance.

        Args:
            agent_type: Type of agent to create
            agent_id: Database ID of the agent
            config: Agent configuration
            user_id: ID of the user
            db_session: Database session (optional)

        Returns:
            Agent instance

        Raises:
            ValueError: If agent type not registered or config invalid
        """
        agent_class = self.get_agent_class(agent_type)

        try:
            return agent_class(
                agent_id=agent_id,
                config=config,
                user_id=user_id,
                db_session=db_session
            )
        except Exception as e:
            raise ValueError(f"Failed to create {agent_type} agent: {e}")

    def get_registered_types(self) -> List[str]:
        """
        Get list of all registered agent types.

        Returns:
            List of agent type strings
        """
        return list(self._registry.keys())

    def get_all_types(self) -> List[str]:
        """
        Get list of all registered agent types.

        Alias for get_registered_types() for compatibility.

        Returns:
            List of agent type strings
        """
        return self.get_registered_types()

    def get_config_schema(self, agent_type: str) -> Dict[str, Any]:
        """
        Get configuration schema for an agent type.

        Args:
            agent_type: Agent type

        Returns:
            Configuration schema dictionary

        Raises:
            ValueError: If agent type not registered
        """
        agent_class = self.get_agent_class(agent_type)
        return agent_class.get_config_schema()

    def get_all_schemas(self) -> Dict[str, Dict[str, Any]]:
        """
        Get configuration schemas for all registered agent types.

        Returns:
            Dictionary mapping agent types to their schemas
        """
        return {
            agent_type: agent_class.get_config_schema()
            for agent_type, agent_class in self._registry.items()
        }

    def get_source_agents(self) -> Dict[str, Dict[str, str]]:
        """
        Get source agent types with metadata.

        Returns:
            Dictionary mapping agent types to their info (name, description)
        """
        return {
            agent_type: {
                'name': agent_class.agent_type.replace('_', ' ').title(),
                'description': (agent_class.__doc__ or 'No description').strip().split('\n')[0]
            }
            for agent_type, agent_class in self._registry.items()
            if issubclass(agent_class, SourceAgent)
        }

    def get_transform_agents(self) -> Dict[str, Dict[str, str]]:
        """
        Get transform agent types with metadata.

        Returns:
            Dictionary mapping agent types to their info (name, description)
        """
        return {
            agent_type: {
                'name': agent_class.agent_type.replace('_', ' ').title(),
                'description': (agent_class.__doc__ or 'No description').strip().split('\n')[0]
            }
            for agent_type, agent_class in self._registry.items()
            if issubclass(agent_class, TransformAgent) and not issubclass(agent_class, SourceAgent)
        }

    def get_action_agents(self) -> Dict[str, Dict[str, str]]:
        """
        Get action agent types with metadata.

        Returns:
            Dictionary mapping agent types to their info (name, description)
        """
        return {
            agent_type: {
                'name': agent_class.agent_type.replace('_', ' ').title(),
                'description': (agent_class.__doc__ or 'No description').strip().split('\n')[0]
            }
            for agent_type, agent_class in self._registry.items()
            if issubclass(agent_class, ActionAgent)
        }

    def get_agent_capabilities(self, agent_type: str) -> Dict[str, bool]:
        """
        Get capabilities for an agent type.

        Args:
            agent_type: Agent type

        Returns:
            Dictionary of capability flags

        Raises:
            ValueError: If agent type not registered
        """
        agent_class = self.get_agent_class(agent_type)
        return {
            'can_be_scheduled': agent_class.can_be_scheduled,
            'can_receive_events': agent_class.can_receive_events,
            'can_create_events': agent_class.can_create_events,
            'requires_input': agent_class.requires_input
        }

    def validate_agent_config(self, agent_type: str, config: Dict[str, Any]) -> bool:
        """
        Validate configuration for an agent type.

        Args:
            agent_type: Agent type
            config: Configuration to validate

        Returns:
            True if valid

        Raises:
            ValueError: If agent type not registered or config invalid
        """
        agent_class = self.get_agent_class(agent_type)

        # Try to create a temporary instance to validate config
        try:
            temp_agent = agent_class(
                agent_id=0,
                config=config,
                user_id=0
            )
            return True
        except Exception as e:
            raise ValueError(f"Invalid configuration for {agent_type}: {e}")

    def __repr__(self):
        return f'<AgentRegistry types={len(self._registry)}>'


# Global agent registry instance
agent_registry = AgentRegistry()


def register_agent(agent_class: Type[BaseAgent]) -> Type[BaseAgent]:
    """
    Decorator for registering agent classes.

    Usage:
        @register_agent
        class MyAgent(SourceAgent):
            agent_type = 'my_agent'
            ...

    Args:
        agent_class: Agent class to register

    Returns:
        The same agent class (for chaining)
    """
    agent_registry.register(agent_class)
    return agent_class
