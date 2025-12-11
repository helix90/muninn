"""
RSS Agent - Fetch RSS/Atom feeds

Single responsibility: ONLY fetch and parse RSS feeds.
Does NOT filter or apply rules (that's FilterAgent's job).
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import feedparser
from app.agents.base import SourceAgent
from app.agents.registry import register_agent
from app.models import Event


@register_agent
class RSSAgent(SourceAgent):
    """
    Fetches entries from RSS/Atom feeds.

    Configuration:
        feed_url (str): URL of the RSS/Atom feed
        max_entries (int): Maximum number of entries to fetch (default: 50)
        include_content (bool): Include full content in payload (default: False)
        days_back (int): Only fetch entries from last N days (default: 7)
    """

    agent_type = 'rss_agent'

    def validate_config(self) -> None:
        """Validate RSS agent configuration."""
        super().validate_config()

        if 'feed_url' not in self.config:
            raise ValueError("RSS agent requires 'feed_url' in config")

        if not isinstance(self.config['feed_url'], str):
            raise ValueError("'feed_url' must be a string")

        if not self.config['feed_url'].startswith(('http://', 'https://')):
            raise ValueError("'feed_url' must be a valid HTTP(S) URL")

        # Validate optional fields
        if 'max_entries' in self.config:
            if not isinstance(self.config['max_entries'], int) or self.config['max_entries'] < 1:
                raise ValueError("'max_entries' must be a positive integer")

        if 'include_content' in self.config:
            if not isinstance(self.config['include_content'], bool):
                raise ValueError("'include_content' must be a boolean")

        if 'days_back' in self.config:
            if not isinstance(self.config['days_back'], int) or self.config['days_back'] < 1:
                raise ValueError("'days_back' must be a positive integer")

    def fetch(self) -> List[Event]:
        """
        Fetch entries from RSS feed.

        Returns:
            List of Event objects, one per RSS entry
        """
        feed_url = self.config['feed_url']
        max_entries = self.config.get('max_entries', 50)
        include_content = self.config.get('include_content', False)
        days_back = self.config.get('days_back', 7)

        self.log(f'Fetching RSS feed: {feed_url}')

        try:
            # Parse the feed
            feed = feedparser.parse(feed_url)

            if feed.bozo:
                # Feed has errors but might still be parseable
                self.log(f'Feed parsing warning: {feed.get("bozo_exception", "Unknown error")}',
                        level='warning')

            # Calculate cutoff date
            cutoff_date = datetime.utcnow() - timedelta(days=days_back)

            events = []
            entries_processed = 0

            for entry in feed.entries[:max_entries]:
                # Extract publish date
                published = self._extract_published_date(entry)

                # Skip if too old
                if published and published < cutoff_date:
                    self.log(f'Skipping old entry: {entry.get("title", "Untitled")}',
                            level='debug')
                    continue

                # Create event payload
                payload = {
                    'title': entry.get('title', ''),
                    'link': entry.get('link', ''),
                    'summary': entry.get('summary', ''),
                    'published': published.isoformat() if published else None,
                    'author': entry.get('author', ''),
                    'id': entry.get('id', entry.get('link', '')),
                }

                # Optionally include full content
                if include_content and 'content' in entry:
                    payload['content'] = entry.content[0].value if entry.content else ''

                # Add metadata about the feed
                metadata = {
                    'feed_url': feed_url,
                    'feed_title': feed.feed.get('title', ''),
                    'feed_link': feed.feed.get('link', ''),
                    'fetched_at': datetime.utcnow().isoformat()
                }

                # Create event
                event = self.create_event(payload=payload, metadata=metadata)
                events.append(event)
                entries_processed += 1

            self.log(f'Fetched {entries_processed} entries from RSS feed', data={
                'feed_url': feed_url,
                'entries_processed': entries_processed,
                'feed_title': feed.feed.get('title', '')
            })

            return events

        except Exception as e:
            self.log(f'Error fetching RSS feed: {e}', level='error', data={
                'feed_url': feed_url,
                'error': str(e)
            })
            return []

    def _extract_published_date(self, entry: Dict) -> Optional[datetime]:
        """
        Extract published date from RSS entry.

        Tries multiple date fields in order:
        - published_parsed
        - updated_parsed
        - created_parsed

        Args:
            entry: RSS entry dictionary

        Returns:
            datetime object or None
        """
        import time

        # Try different date fields
        for date_field in ['published_parsed', 'updated_parsed', 'created_parsed']:
            if date_field in entry and entry[date_field]:
                try:
                    return datetime.fromtimestamp(time.mktime(entry[date_field]))
                except (ValueError, TypeError, OverflowError):
                    continue

        return None

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """Get configuration schema for RSS agent."""
        schema = super().get_config_schema()
        schema['required_fields'] = ['feed_url']
        schema['optional_fields'] = [
            {
                'name': 'max_entries',
                'type': 'integer',
                'default': 50,
                'description': 'Maximum number of entries to fetch'
            },
            {
                'name': 'include_content',
                'type': 'boolean',
                'default': False,
                'description': 'Include full content in payload'
            },
            {
                'name': 'days_back',
                'type': 'integer',
                'default': 7,
                'description': 'Only fetch entries from last N days'
            }
        ]
        return schema
