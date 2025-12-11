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

Action Agents:
- EmailAgent: Send via SMTP
- HTTPPostAgent: POST/PUT/PATCH/DELETE to URL
- JabberAgent: XMPP messaging
"""

# Import source agents
from app.agents.types.rss_agent import RSSAgent
from app.agents.types.web_fetch_agent import WebFetchAgent
from app.agents.types.scheduler_agent import SchedulerAgent

# Import transform agents
from app.agents.types.filter_agent import FilterAgent
from app.agents.types.deduplication_agent import DeduplicationAgent
from app.agents.types.html_parser_agent import HTMLParserAgent
from app.agents.types.template_agent import TemplateAgent

# Import action agents
from app.agents.types.email_agent import EmailAgent
from app.agents.types.http_post_agent import HTTPPostAgent
from app.agents.types.jabber_agent import JabberAgent

__all__ = [
    # Source agents
    'RSSAgent',
    'WebFetchAgent',
    'SchedulerAgent',
    # Transform agents
    'FilterAgent',
    'DeduplicationAgent',
    'HTMLParserAgent',
    'TemplateAgent',
    # Action agents
    'EmailAgent',
    'HTTPPostAgent',
    'JabberAgent',
]
