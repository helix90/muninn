"""
RSS reader job for RSS feed parsing and monitoring
"""

import feedparser
from typing import Dict, Any, Optional, List
from datetime import datetime
from app.utils.validators import validate_url
from ..base import BaseJob


class RSSReaderJob(BaseJob):
    """Job for reading and parsing RSS feeds."""
    
    job_type = 'rss_reader'
    required_config_fields = ['feed_url']
    optional_config_fields = ['max_entries', 'include_content', 'filter_keywords', 'exclude_keywords']
    
    def _validate_config_values(self):
        """Validate configuration field values."""
        # Validate feed URL
        feed_url = self.config.get('feed_url')
        if not feed_url or not validate_url(feed_url):
            raise ValueError("Invalid RSS feed URL provided")

        # Validate max_entries
        max_entries = self.config.get('max_entries')
        if max_entries is not None:
            if not isinstance(max_entries, int) or max_entries <= 0:
                raise ValueError("max_entries must be a positive integer")

        # Validate filter keywords
        for keyword_type in ['filter_keywords', 'exclude_keywords']:
            keywords = self.config.get(keyword_type)
            if keywords is not None:
                if not isinstance(keywords, list):
                    raise ValueError(f"{keyword_type} must be a list")
                if not all(isinstance(k, str) for k in keywords):
                    raise ValueError(f"All {keyword_type} must be strings")
    
    def _filter_entries(self, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter RSS entries based on configuration."""
        filtered_entries = entries
        
        # Apply keyword filtering
        filter_keywords = self.config.get('filter_keywords', [])
        if filter_keywords:
            filtered_entries = [
                entry for entry in filtered_entries
                if any(keyword.lower() in entry.get('title', '').lower() 
                      or keyword.lower() in entry.get('summary', '').lower()
                      for keyword in filter_keywords)
            ]
        
        # Apply keyword exclusion
        exclude_keywords = self.config.get('exclude_keywords', [])
        if exclude_keywords:
            filtered_entries = [
                entry for entry in filtered_entries
                if not any(keyword.lower() in entry.get('title', '').lower() 
                          or keyword.lower() in entry.get('summary', '').lower()
                          for keyword in exclude_keywords)
            ]
        
        return filtered_entries
    
    def _parse_entry(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Parse a single RSS entry."""
        parsed_entry = {
            'title': entry.get('title', ''),
            'link': entry.get('link', ''),
            'summary': entry.get('summary', ''),
            'published': entry.get('published', ''),
            'author': entry.get('author', ''),
            'id': entry.get('id', ''),
        }
        
        # Include content if requested
        if self.config.get('include_content', False):
            parsed_entry['content'] = entry.get('content', [{}])[0].get('value', '') if entry.get('content') else ''
        
        # Parse published date
        if parsed_entry['published']:
            try:
                # Try to parse the date
                parsed_date = datetime(*entry.get('published_parsed', (0, 0, 0, 0, 0, 0, 0, 0, 0))[:6])
                parsed_entry['published_parsed'] = parsed_date.isoformat()
            except Exception:
                parsed_entry['published_parsed'] = None
        
        return parsed_entry
    
    def execute(self, input_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute the RSS reading job.
        
        Args:
            input_data: Optional input data (not used for RSS reading)
            
        Returns:
            Dictionary containing parsed RSS feed data
        """
        try:
            self.pre_execute(input_data)
            
            # Parse RSS feed
            feed_url = self.config['feed_url']
            feed = feedparser.parse(feed_url)
            
            if feed.bozo:
                raise ValueError(f"Invalid RSS feed: {feed.bozo_exception}")
            
            # Extract feed metadata
            feed_info = {
                'title': feed.feed.get('title', ''),
                'description': feed.feed.get('description', ''),
                'link': feed.feed.get('link', ''),
                'language': feed.feed.get('language', ''),
                'updated': feed.feed.get('updated', ''),
                'generator': feed.feed.get('generator', ''),
                'subtitle': feed.feed.get('subtitle', ''),
            }
            
            # Parse entries
            entries = [self._parse_entry(entry) for entry in feed.entries]
            
            # Apply filtering
            filtered_entries = self._filter_entries(entries)
            
            # Limit entries if specified
            max_entries = self.config.get('max_entries')
            if max_entries and len(filtered_entries) > max_entries:
                filtered_entries = filtered_entries[:max_entries]
            
            # Prepare result
            result = {
                'feed_url': feed_url,
                'feed_info': feed_info,
                'total_entries': len(entries),
                'filtered_entries': len(filtered_entries),
                'entries': filtered_entries,
                'parse_status': 'success',
                'timestamp': datetime.utcnow().isoformat()
            }
            
            self.post_execute(result, success=True)
            return result
            
        except Exception as e:
            error_result = self.handle_error(e)
            self.post_execute(error_result, success=False)
            return error_result
    
    def get_config_schema(self) -> Dict[str, Any]:
        """Get the configuration schema for RSS reader jobs."""
        schema = super().get_config_schema()
        schema.update({
            'description': 'Reads and parses RSS feeds with filtering capabilities',
            'example_config': {
                'feed_url': 'https://example.com/feed.xml',
                'max_entries': 50,
                'include_content': True,
                'filter_keywords': ['python', 'automation'],
                'exclude_keywords': ['spam', 'advertisement']
            }
        })
        return schema
