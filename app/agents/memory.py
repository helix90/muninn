"""
Memory management for Muninn agents

Provides persistent state storage for agents using the AgentMemory model.
"""

from datetime import datetime, timedelta
from typing import Any, Optional, Dict, List
from sqlalchemy.exc import IntegrityError
from app.models import AgentMemory
from app.extensions import db


class MemoryManager:
    """
    Manages persistent memory for agents.

    Provides key-value storage with optional expiration for agent state.
    Used for deduplication tracking, state management, and persistence.
    """

    def __init__(self, agent_id: int, user_id: int, db_session=None):
        """
        Initialize memory manager for an agent.

        Args:
            agent_id: ID of the agent
            user_id: ID of the user (for security/isolation)
            db_session: Database session (defaults to db.session)
        """
        self.agent_id = agent_id
        self.user_id = user_id
        self.db_session = db_session or db.session

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a value from agent memory.

        Args:
            key: Memory key
            default: Default value if key not found or expired

        Returns:
            The stored value or default
        """
        memory = self.db_session.query(AgentMemory).filter_by(
            agent_id=self.agent_id,
            key=key
        ).first()

        if memory is None:
            return default

        # Check if expired
        if memory.is_expired():
            self.delete(key)
            return default

        return memory.value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Set a value in agent memory.

        Args:
            key: Memory key
            value: Value to store (must be JSON-serializable)
            ttl: Time-to-live in seconds (None for no expiration)

        Returns:
            True if successful, False otherwise
        """
        try:
            # Calculate expiration time
            expires_at = None
            if ttl is not None:
                expires_at = datetime.utcnow() + timedelta(seconds=ttl)

            # Check if key already exists
            memory = self.db_session.query(AgentMemory).filter_by(
                agent_id=self.agent_id,
                key=key
            ).first()

            if memory:
                # Update existing
                memory.value = value
                memory.expires_at = expires_at
                memory.updated_at = datetime.utcnow()
            else:
                # Create new
                memory = AgentMemory(
                    agent_id=self.agent_id,
                    key=key,
                    value=value,
                    expires_at=expires_at
                )
                self.db_session.add(memory)

            self.db_session.commit()
            return True

        except (IntegrityError, ValueError) as e:
            self.db_session.rollback()
            return False

    def delete(self, key: str) -> bool:
        """
        Delete a value from agent memory.

        Args:
            key: Memory key

        Returns:
            True if deleted, False if not found
        """
        try:
            memory = self.db_session.query(AgentMemory).filter_by(
                agent_id=self.agent_id,
                key=key
            ).first()

            if memory:
                self.db_session.delete(memory)
                self.db_session.commit()
                return True
            return False

        except Exception:
            self.db_session.rollback()
            return False

    def exists(self, key: str) -> bool:
        """
        Check if a key exists in memory (and is not expired).

        Args:
            key: Memory key

        Returns:
            True if key exists and is not expired
        """
        value = self.get(key)
        return value is not None

    def clear(self) -> int:
        """
        Clear all memory for this agent.

        Returns:
            Number of entries deleted
        """
        try:
            count = self.db_session.query(AgentMemory).filter_by(
                agent_id=self.agent_id
            ).delete()
            self.db_session.commit()
            return count

        except Exception:
            self.db_session.rollback()
            return 0

    def get_all(self) -> Dict[str, Any]:
        """
        Get all non-expired memory for this agent.

        Returns:
            Dictionary of key-value pairs
        """
        memories = self.db_session.query(AgentMemory).filter_by(
            agent_id=self.agent_id
        ).all()

        result = {}
        expired_keys = []

        for memory in memories:
            if memory.is_expired():
                expired_keys.append(memory.key)
            else:
                result[memory.key] = memory.value

        # Clean up expired entries
        for key in expired_keys:
            self.delete(key)

        return result

    def cleanup_expired(self) -> int:
        """
        Remove all expired memory entries for this agent.

        Returns:
            Number of entries deleted
        """
        try:
            now = datetime.utcnow()
            count = self.db_session.query(AgentMemory).filter(
                AgentMemory.agent_id == self.agent_id,
                AgentMemory.expires_at.isnot(None),
                AgentMemory.expires_at < now
            ).delete()
            self.db_session.commit()
            return count

        except Exception:
            self.db_session.rollback()
            return 0

    def increment(self, key: str, amount: int = 1, ttl: Optional[int] = None) -> int:
        """
        Increment a counter in memory.

        Args:
            key: Memory key
            amount: Amount to increment by
            ttl: Time-to-live in seconds (only used if creating new key)

        Returns:
            New value after increment
        """
        current = self.get(key, 0)

        # Ensure it's an integer
        if not isinstance(current, int):
            current = 0

        new_value = current + amount
        self.set(key, new_value, ttl)
        return new_value

    def append_to_list(self, key: str, value: Any, max_length: Optional[int] = None,
                       ttl: Optional[int] = None) -> List[Any]:
        """
        Append a value to a list in memory.

        Args:
            key: Memory key
            value: Value to append
            max_length: Maximum list length (oldest items removed if exceeded)
            ttl: Time-to-live in seconds (only used if creating new key)

        Returns:
            Updated list
        """
        current = self.get(key, [])

        # Ensure it's a list
        if not isinstance(current, list):
            current = []

        current.append(value)

        # Trim to max length if specified
        if max_length and len(current) > max_length:
            current = current[-max_length:]

        self.set(key, current, ttl)
        return current

    def remove_from_list(self, key: str, value: Any) -> List[Any]:
        """
        Remove a value from a list in memory.

        Args:
            key: Memory key
            value: Value to remove

        Returns:
            Updated list
        """
        current = self.get(key, [])

        if not isinstance(current, list):
            return []

        # Remove all occurrences of the value
        current = [item for item in current if item != value]
        self.set(key, current)
        return current

    def __repr__(self):
        return f'<MemoryManager agent_id={self.agent_id}>'
