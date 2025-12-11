"""
Agent type implementations

Source Agents:
- RSSAgent: Fetch RSS/Atom feeds
- WebFetchAgent: HTTP GET requests
- SchedulerAgent: Time-based triggers

Transform Agents:
- FilterAgent: Rule-based filtering
- DeduplicationAgent: Remove duplicates
- HTMLParserAgent: Parse HTML via CSS selectors
- TemplateAgent: Transform via Jinja2
- DigestAgent: Batch events

Action Agents:
- EmailAgent: Send via SMTP
- HTTPPostAgent: POST to URL
- JabberAgent: XMPP messaging
"""

# Import source agents
from app.agents.types.rss_agent import RSSAgent
from app.agents.types.web_fetch_agent import WebFetchAgent
from app.agents.types.scheduler_agent import SchedulerAgent

__all__ = [
    'RSSAgent',
    'WebFetchAgent',
    'SchedulerAgent',
]
