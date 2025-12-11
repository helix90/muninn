"""
Deduplication Agent - Remove duplicate events

Single responsibility: ONLY removes duplicate events based on uniqueness fields.
Uses agent memory to track seen items.
"""

from typing import List, Dict, Any
import hashlib
import json
from datetime import datetime, timedelta
from app.agents.base import TransformAgent
from app.agents.registry import register_agent
from app.models import Event


@register_agent
class DeduplicationAgent(TransformAgent):
    """
    Removes duplicate events based on uniqueness fields.

    Uses agent memory to track which items have been seen before.
    Useful for preventing duplicate emails, posts, or other actions.

    Configuration:
        uniqueness_fields (list): Fields to use for uniqueness check (e.g., ['link', 'title'])
        lookback_days (int): How many days to remember seen items (default: 7)
        memory_limit (int): Maximum number of items to remember (default: 10000)
    """

    agent_type = 'deduplication_agent'

    def validate_config(self) -> None:
        """Validate deduplication agent configuration."""
        super().validate_config()

        if 'uniqueness_fields' not in self.config:
            raise ValueError("Deduplication agent requires 'uniqueness_fields' in config")

        if not isinstance(self.config['uniqueness_fields'], list):
            raise ValueError("'uniqueness_fields' must be a list")

        if len(self.config['uniqueness_fields']) == 0:
            raise ValueError("'uniqueness_fields' must contain at least one field")

        # Validate optional fields
        if 'lookback_days' in self.config:
            if not isinstance(self.config['lookback_days'], (int, float)):
                raise ValueError("'lookback_days' must be a number")
            if self.config['lookback_days'] <= 0:
                raise ValueError("'lookback_days' must be positive")

        if 'memory_limit' in self.config:
            if not isinstance(self.config['memory_limit'], int):
                raise ValueError("'memory_limit' must be an integer")
            if self.config['memory_limit'] <= 0:
                raise ValueError("'memory_limit' must be positive")

    def process(self, events: List[Event]) -> List[Event]:
        """
        Remove duplicate events.

        Args:
            events: Events to deduplicate

        Returns:
            List of unique events (duplicates removed)
        """
        uniqueness_fields = self.config['uniqueness_fields']
        lookback_days = self.config.get('lookback_days', 7)
        memory_limit = self.config.get('memory_limit', 10000)

        # Clean up expired entries first
        self._cleanup_expired(lookback_days)

        # Get currently seen hashes
        seen_hashes = self._get_seen_hashes()

        unique_events = []
        duplicate_count = 0
        new_hashes = []

        for event in events:
            # Calculate hash for this event
            event_hash = self._calculate_hash(event, uniqueness_fields)

            if event_hash in seen_hashes:
                # Duplicate found
                duplicate_count += 1
                self.log(f'Duplicate event found', level='debug', data={
                    'hash': event_hash,
                    'fields': {field: event.get_payload_field(field) for field in uniqueness_fields}
                })
            else:
                # Unique event
                unique_events.append(event)
                new_hashes.append(event_hash)
                seen_hashes.add(event_hash)

        # Store new hashes in memory (with TTL based on lookback_days)
        if new_hashes:
            self._store_hashes(new_hashes, lookback_days)

        # Enforce memory limit
        self._enforce_memory_limit(memory_limit)

        self.log(f'Deduplicated {len(events)} events', data={
            'input_count': len(events),
            'output_count': len(unique_events),
            'duplicate_count': duplicate_count,
            'total_seen': len(seen_hashes)
        })

        return unique_events

    def _calculate_hash(self, event: Event, fields: List[str]) -> str:
        """
        Calculate hash for an event based on uniqueness fields.

        Args:
            event: Event to hash
            fields: Fields to use for uniqueness

        Returns:
            Hash string
        """
        # Collect values from specified fields
        values = []
        for field in fields:
            value = event.get_payload_field(field)
            if value is not None:
                values.append(str(value))

        # Create hash
        if not values:
            # If no values found, use event ID
            hash_input = str(event.id) if event.id else str(event.payload)
        else:
            hash_input = '|'.join(values)

        return hashlib.sha256(hash_input.encode('utf-8')).hexdigest()

    def _get_seen_hashes(self) -> set:
        """
        Get set of previously seen hashes from memory.

        Returns:
            Set of hash strings
        """
        seen_list = self.memory.get('seen_hashes', [])
        return set(seen_list)

    def _store_hashes(self, hashes: List[str], ttl_days: float) -> None:
        """
        Store new hashes in memory.

        Args:
            hashes: List of hash strings to store
            ttl_days: Time-to-live in days
        """
        # Get current hashes
        seen_list = self.memory.get('seen_hashes', [])

        # Add new hashes (avoiding duplicates)
        seen_set = set(seen_list)
        for hash_str in hashes:
            if hash_str not in seen_set:
                seen_list.append(hash_str)
                seen_set.add(hash_str)

        # Store with TTL
        ttl_seconds = int(ttl_days * 24 * 3600)
        self.memory.set('seen_hashes', seen_list, ttl=ttl_seconds)

        # Also store timestamps for cleanup
        timestamps = self.memory.get('hash_timestamps', {})
        now = datetime.utcnow().isoformat()
        for hash_str in hashes:
            timestamps[hash_str] = now
        self.memory.set('hash_timestamps', timestamps, ttl=ttl_seconds)

    def _cleanup_expired(self, lookback_days: float) -> None:
        """
        Remove expired hashes from memory.

        Args:
            lookback_days: Number of days to keep hashes
        """
        cutoff = datetime.utcnow() - timedelta(days=lookback_days)

        # Get timestamps
        timestamps = self.memory.get('hash_timestamps', {})
        if not timestamps:
            return

        # Find expired hashes
        expired_hashes = []
        for hash_str, timestamp_str in timestamps.items():
            try:
                timestamp = datetime.fromisoformat(timestamp_str)
                if timestamp < cutoff:
                    expired_hashes.append(hash_str)
            except (ValueError, TypeError):
                # Invalid timestamp, remove it
                expired_hashes.append(hash_str)

        if not expired_hashes:
            return

        # Remove expired hashes
        seen_list = self.memory.get('seen_hashes', [])
        seen_list = [h for h in seen_list if h not in expired_hashes]
        self.memory.set('seen_hashes', seen_list)

        # Remove expired timestamps
        for hash_str in expired_hashes:
            timestamps.pop(hash_str, None)
        self.memory.set('hash_timestamps', timestamps)

        self.log(f'Cleaned up {len(expired_hashes)} expired hashes', level='debug')

    def _enforce_memory_limit(self, limit: int) -> None:
        """
        Enforce maximum memory limit by removing oldest hashes.

        Args:
            limit: Maximum number of hashes to keep
        """
        seen_list = self.memory.get('seen_hashes', [])

        if len(seen_list) <= limit:
            return

        # Remove oldest entries (FIFO)
        removed_count = len(seen_list) - limit
        removed_hashes = seen_list[:removed_count]
        seen_list = seen_list[removed_count:]

        self.memory.set('seen_hashes', seen_list)

        # Also clean up timestamps
        timestamps = self.memory.get('hash_timestamps', {})
        for hash_str in removed_hashes:
            timestamps.pop(hash_str, None)
        self.memory.set('hash_timestamps', timestamps)

        self.log(f'Enforced memory limit: removed {removed_count} oldest hashes',
                level='debug', data={'limit': limit, 'current_size': len(seen_list)})

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """Get configuration schema for deduplication agent."""
        schema = super().get_config_schema()
        schema['required_fields'] = ['uniqueness_fields']
        schema['optional_fields'] = [
            {
                'name': 'lookback_days',
                'type': 'number',
                'default': 7,
                'description': 'How many days to remember seen items'
            },
            {
                'name': 'memory_limit',
                'type': 'integer',
                'default': 10000,
                'description': 'Maximum number of items to remember'
            }
        ]
        return schema
