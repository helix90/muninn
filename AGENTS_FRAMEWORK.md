# Muninn Agent System Framework

Comprehensive guide to building automation workflows with single-responsibility agents.

## Table of Contents

- [Overview](#overview)
- [Agent Types](#agent-types)
- [Core Concepts](#core-concepts)
- [Creating Agents](#creating-agents)
- [Event Propagation](#event-propagation)
- [Agent Development](#agent-development)
- [Examples](#examples)
- [Best Practices](#best-practices)
- [API Reference](#api-reference)

## Overview

Muninn's agent system is inspired by Huginn and follows a single-responsibility principle. Each agent does one thing well, and agents connect together to create powerful automation workflows.

### Philosophy

**Single Responsibility**: Each agent performs exactly one task
- RSSAgent fetches RSS feeds (doesn't filter)
- FilterAgent filters events (doesn't fetch)
- EmailAgent sends emails (doesn't transform data)

**Event-Driven**: Agents communicate through events
- Source agents create events from external sources
- Transform agents process events and create new ones
- Action agents consume events and perform actions

**Composable**: Complex workflows emerge from simple components
- RSS → Filter → Dedupe → Email
- WebFetch → HTMLParser → Template → HTTPPost
- Multiple sources → Digest → Single notification

## Agent Types

### Source Agents (Create Events)

Source agents fetch data from external sources and create events. They can be scheduled to run automatically.

**Capabilities:**
- `can_be_scheduled: True` - Can run on a schedule
- `can_receive_events: False` - Don't take input
- `can_create_events: True` - Produce events
- `requires_input: False` - Run independently

#### RSSAgent

Fetches and parses RSS/Atom feeds.

```python
{
    "feed_url": "https://hnrss.org/newest",
    "max_entries": 50,
    "include_content": True
}
```

**Output Events:**
```json
{
    "title": "Article Title",
    "link": "https://example.com/article",
    "summary": "Article description",
    "content": "Full article text",
    "published": "2025-01-15T10:30:00Z",
    "author": "Author Name"
}
```

#### WebFetchAgent

Performs HTTP GET requests to fetch web pages.

```python
{
    "url": "https://example.com/data",
    "headers": {
        "User-Agent": "Muninn/1.0"
    },
    "timeout": 30
}
```

**Output Events:**
```json
{
    "url": "https://example.com/data",
    "status_code": 200,
    "content": "<html>...</html>",
    "headers": {...}
}
```

#### SchedulerAgent

Generates time-based trigger events.

```python
{
    "interval_minutes": 60,
    "message": "Hourly trigger"
}
```

### Transform Agents (Process Events)

Transform agents receive events, process them, and create new events. They form the middle layer of workflows.

**Capabilities:**
- `can_be_scheduled: False` - Triggered by events
- `can_receive_events: True` - Take input events
- `can_create_events: True` - Produce output events
- `requires_input: True` - Need events to run

#### FilterAgent

Filters events based on rules.

```python
{
    "rules": [
        {
            "field": "title",
            "type": "contains",
            "value": "Python",
            "case_sensitive": False
        },
        {
            "field": "score",
            "type": "greater_than",
            "value": 100
        }
    ],
    "match_all": True  # AND logic (default), False for OR
}
```

**Rule Types:**
- `contains` - String contains substring
- `not_contains` - String doesn't contain substring
- `equals` - Exact match
- `not_equals` - Not equal
- `regex` - Regular expression match
- `greater_than` - Numeric >
- `less_than` - Numeric <
- `exists` - Field exists
- `not_exists` - Field doesn't exist

#### DeduplicationAgent

Removes duplicate events using agent memory.

```python
{
    "uniqueness_fields": ["link"],
    "lookback_days": 7,
    "memory_limit": 10000
}
```

**How it works:**
- Computes hash of uniqueness fields
- Stores hash in agent memory
- Only passes events with new hashes
- Automatically expires old hashes

#### HTMLParserAgent

Extracts data from HTML using CSS selectors.

```python
{
    "selectors": {
        "title": "h1.title",
        "price": ".price",
        "description": "p.desc"
    },
    "extract_multiple": False
}
```

**Output Events:**
```json
{
    "title": "Product Name",
    "price": "$29.99",
    "description": "Product description"
}
```

#### JSONExtractAgent

Extracts data from JSON using JSONPath.

```python
{
    "extractions": {
        "user_name": "$.user.name",
        "user_email": "$.user.email",
        "items": "$.items[*].title"
    }
}
```

#### TemplateAgent

Transforms event data using Jinja2 templates.

```python
{
    "template": "{{ title }} - {{ link }}",
    "output_field": "formatted",
    "preserve_original": True
}
```

**Or multiple templates:**
```python
{
    "templates": {
        "subject": "New Article: {{ title }}",
        "body": "{{ title }}\n\n{{ summary }}\n\n{{ link }}"
    },
    "preserve_original": True
}
```

**Output Events:**
```json
{
    "title": "Article Title",
    "link": "https://example.com",
    "formatted": "Article Title - https://example.com"
}
```

#### DigestAgent

Batches multiple events into a single event.

```python
{
    "batch_size": 10,
    "batch_timeout_minutes": 60,
    "template": "{% for event in events %}{{ event.title }}\n{% endfor %}"
}
```

### Action Agents (Perform Actions)

Action agents consume events and perform terminal actions. They don't create new events.

**Capabilities:**
- `can_be_scheduled: False` - Triggered by events
- `can_receive_events: True` - Take input events
- `can_create_events: False` - Terminal agents
- `requires_input: True` - Need events to run

#### EmailAgent

Sends emails via SMTP.

```python
{
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "username": "alerts@example.com",
    "password": "app_password",
    "use_tls": True,
    "from_email": "alerts@example.com",
    "to_email": "user@example.com",
    "subject_template": "Alert: {{ title }}",
    "body_template": "{{ title }}\n\n{{ summary }}\n\n{{ link }}"
}
```

**Template Variables:**
- All event payload fields available
- `{{ title }}`, `{{ link }}`, `{{ content }}`, etc.

#### HTTPPostAgent

Sends HTTP POST requests.

```python
{
    "url": "https://api.example.com/webhook",
    "method": "POST",
    "headers": {
        "Content-Type": "application/json",
        "Authorization": "Bearer token123"
    },
    "payload_template": {
        "title": "{{ title }}",
        "url": "{{ link }}",
        "timestamp": "{{ published }}"
    }
}
```

**Methods:** GET, POST, PUT, PATCH, DELETE

#### JabberAgent

Sends XMPP/Jabber messages.

```python
{
    "jid": "bot@jabber.example.com",
    "password": "bot_password",
    "recipient": "user@jabber.example.com",
    "message_template": "{{ title }}: {{ link }}"
}
```

## Core Concepts

### Events

Events are the data objects that flow between agents.

**Structure:**
```python
Event(
    agent_id=1,              # Creating agent
    agent_type='rss_agent',  # Agent type
    user_id=1,               # Owner
    payload={                # Event data
        "title": "...",
        "link": "..."
    },
    metadata={               # System metadata
        "created_at": "...",
        "source": "..."
    },
    expires_at=None          # Optional expiration
)
```

**Payload vs Metadata:**
- **Payload**: User data that transforms through workflow
- **Metadata**: System data (timestamps, IDs, tracking)

### Agent Links

Links define how events flow between agents.

```python
AgentLink(
    source_agent_id=1,   # RSS agent
    target_agent_id=2,   # Filter agent
    config={},           # Optional link config
    is_active=True
)
```

**Network Topologies:**
- **Linear**: A → B → C
- **Fan-out**: A → B, A → C (one source, multiple targets)
- **Fan-in**: A → C, B → C (multiple sources, one target)
- **Diamond**: A → B → D, A → C → D

### Agent Memory

Agents can store persistent state in agent memory.

**Usage:**
```python
# In agent code
self.memory.set('last_seen_id', '12345')
value = self.memory.get('last_seen_id')
self.memory.delete('last_seen_id')
```

**Common Uses:**
- Deduplication tracking (seen item IDs)
- Rate limiting counters
- State between runs
- Checkpoint positions

**Expiration:**
```python
self.memory.set('temp_data', 'value', expires_in_seconds=3600)
```

### Event Propagation

When a source agent runs:

1. **Execute Source**: Source agent creates events
2. **Find Downstream**: Query AgentLink for connected agents
3. **Execute Transform**: Pass events to each downstream agent
4. **Collect Events**: Transform agents create new events
5. **Repeat**: Recursively propagate new events
6. **Terminal**: Action agents consume events (end of chain)

**Protection:**
- **Cycle Detection**: Tracks visited agents per path
- **Max Depth**: Configurable limit (default: 10)
- **Error Isolation**: Failures in one branch don't affect others

## Creating Agents

### Via Web Interface

1. Navigate to **Agents** → **Create New Agent**
2. Select agent type (Source/Transform/Action)
3. Configure agent settings
4. Set schedule (for source agents)
5. Save agent

### Via API

```python
from app.models import Job
from app.extensions import db

agent = Job(
    name='Hacker News RSS',
    job_type='rss_agent',
    config={
        'feed_url': 'https://hnrss.org/newest',
        'max_entries': 50
    },
    schedule='*/30 * * * *',  # Every 30 minutes
    user_id=current_user.id,
    is_active=True
)
db.session.add(agent)
db.session.commit()
```

### Linking Agents

```python
from app.models import AgentLink

link = AgentLink(
    source_agent_id=rss_agent.id,
    target_agent_id=filter_agent.id
)
db.session.add(link)
db.session.commit()
```

### Via AgentService

```python
from app.services.agent_service import AgentService

service = AgentService(db.session)

# Create link with validation
result = service.create_agent_link(
    source_agent_id=1,
    target_agent_id=2
)

if result['success']:
    print(f"Link created: {result['link_id']}")
else:
    print(f"Error: {result['error']}")
```

## Event Propagation

### Manual Execution

```python
from app.services.agent_service import AgentService

service = AgentService(db.session)

result = service.run_agent(
    agent_id=1,
    manual=True,
    propagate=True  # Auto-propagate events
)

print(f"Created {result['events_created']} events")
print(f"Executed {result['propagation_stats']['agents_executed']} agents")
```

### Scheduled Execution

Agents with `schedule` field run automatically:

```python
agent.schedule = '0 */6 * * *'  # Every 6 hours
agent.schedule_enabled = True
db.session.commit()
```

**Cron Format:**
```
┌───────────── minute (0 - 59)
│ ┌───────────── hour (0 - 23)
│ │ ┌───────────── day of month (1 - 31)
│ │ │ ┌───────────── month (1 - 12)
│ │ │ │ ┌───────────── day of week (0 - 6) (Sunday=0)
│ │ │ │ │
* * * * *
```

## Agent Development

### Creating a New Agent

1. **Define Agent Class**

```python
# app/agents/types/my_agent.py
from app.agents.base import SourceAgent
from app.models import Event

class MyAgent(SourceAgent):
    """My custom agent"""

    agent_type = 'my_agent'

    def __init__(self, agent_id, config, user_id, db_session=None):
        super().__init__(agent_id, config, user_id, db_session)

        # Validate config
        if 'required_field' not in config:
            raise ValueError("MyAgent requires 'required_field' in config")

        self.required_field = config['required_field']

    def check(self):
        """Execute agent and return events"""
        events = []

        # Do work here
        data = self._fetch_data()

        # Create events
        for item in data:
            event = self.create_event(
                payload={
                    'title': item['title'],
                    'data': item['data']
                },
                metadata={}
            )
            events.append(event)

        return events

    def _fetch_data(self):
        # Implementation
        return []
```

2. **Register Agent**

```python
# app/agents/types/__init__.py
from app.agents.types.my_agent import MyAgent

__all__ = [
    # ... existing agents
    'MyAgent',
]
```

3. **Register with Registry**

```python
# app/agents/registry.py
from app.agents.types import MyAgent

# Registration happens automatically via decorators
# Or manually:
agent_registry.register(
    agent_type='my_agent',
    agent_class=MyAgent,
    name='My Agent',
    description='Does something awesome',
    category='source',
    config_schema={
        'fields': [
            {
                'name': 'required_field',
                'label': 'Required Field',
                'type': 'text',
                'required': True,
                'description': 'This field is required'
            }
        ]
    }
)
```

### Transform Agent Example

```python
from app.agents.base import TransformAgent

class MyTransformAgent(TransformAgent):
    """Transforms events"""

    agent_type = 'my_transform_agent'

    def process(self, events):
        """Process incoming events and return new events"""
        output_events = []

        for event in events:
            # Transform data
            transformed_data = self._transform(event.payload)

            # Create new event
            new_event = self.create_event(
                payload=transformed_data,
                metadata={'original_agent': event.agent_id}
            )
            output_events.append(new_event)

        return output_events

    def _transform(self, data):
        # Implementation
        return data
```

### Action Agent Example

```python
from app.agents.base import ActionAgent

class MyActionAgent(ActionAgent):
    """Performs an action"""

    agent_type = 'my_action_agent'

    def process(self, events):
        """Process events and perform action (return empty list)"""
        for event in events:
            self._perform_action(event.payload)

        # Action agents don't create events
        return []

    def _perform_action(self, data):
        # Implementation
        pass
```

## Examples

### Example 1: News Aggregator

**Goal**: Monitor Hacker News, filter Python articles, remove duplicates, send email digest.

**Agents:**
1. **RSSAgent**: Fetch Hacker News feed (every 30 min)
2. **FilterAgent**: Keep only Python articles
3. **DeduplicationAgent**: Remove duplicates (7 day window)
4. **DigestAgent**: Batch into hourly digest
5. **EmailAgent**: Send digest email

**Configuration:**

```python
# 1. RSS Agent
rss = Job(
    name='Hacker News RSS',
    job_type='rss_agent',
    config={
        'feed_url': 'https://hnrss.org/newest',
        'max_entries': 50
    },
    schedule='*/30 * * * *',
    user_id=user.id
)

# 2. Filter Agent
filter = Job(
    name='Python Filter',
    job_type='filter_agent',
    config={
        'rules': [
            {'field': 'title', 'type': 'contains', 'value': 'Python', 'case_sensitive': False}
        ]
    },
    user_id=user.id
)

# 3. Deduplication Agent
dedupe = Job(
    name='Deduplicator',
    job_type='deduplication_agent',
    config={
        'uniqueness_fields': ['link'],
        'lookback_days': 7
    },
    user_id=user.id
)

# 4. Digest Agent
digest = Job(
    name='Hourly Digest',
    job_type='digest_agent',
    config={
        'batch_timeout_minutes': 60,
        'template': '{% for event in events %}- {{ event.title }}: {{ event.link }}\n{% endfor %}'
    },
    user_id=user.id
)

# 5. Email Agent
email = Job(
    name='Email Notifier',
    job_type='email_agent',
    config={
        'smtp_server': 'smtp.gmail.com',
        'smtp_port': 587,
        'username': 'alerts@example.com',
        'password': 'app_password',
        'from_email': 'alerts@example.com',
        'to_email': 'user@example.com',
        'subject_template': 'Python News Digest',
        'body_template': '{{ content }}'
    },
    user_id=user.id
)

# Create links
AgentLink(source_agent_id=rss.id, target_agent_id=filter.id)
AgentLink(source_agent_id=filter.id, target_agent_id=dedupe.id)
AgentLink(source_agent_id=dedupe.id, target_agent_id=digest.id)
AgentLink(source_agent_id=digest.id, target_agent_id=email.id)
```

### Example 2: Price Monitor

**Goal**: Monitor product prices, alert on drops > 10%.

**Agents:**
1. **WebFetchAgent**: Fetch product pages (hourly)
2. **HTMLParserAgent**: Extract price
3. **TemplateAgent**: Calculate price change (using memory)
4. **FilterAgent**: Keep only >10% drops
5. **HTTPPostAgent**: Send webhook notification

### Example 3: Social Media Aggregator

**Goal**: Aggregate from multiple sources, deduplicate, post to Slack.

**Agents:**
1. **RSSAgent** (HN): Fetch Hacker News
2. **RSSAgent** (Reddit): Fetch Reddit
3. **RSSAgent** (Lobsters): Fetch Lobsters
4. **FilterAgent**: Common filter (all → filter)
5. **DeduplicationAgent**: Remove cross-posted items
6. **TemplateAgent**: Format for Slack
7. **HTTPPostAgent**: Post to Slack webhook

**Network:**
```
HN RSS ─┐
        ├─→ Filter → Dedupe → Template → Slack
Reddit ─┤
        │
Lobsters┘
```

## Best Practices

### Agent Design

1. **Single Responsibility**: Each agent does one thing
2. **Stateless When Possible**: Avoid memory unless needed
3. **Fail Gracefully**: Handle errors, don't crash
4. **Validate Config**: Check required fields in `__init__`
5. **Clear Names**: Descriptive agent and field names

### Workflow Design

1. **Start Simple**: Begin with 2-3 agents, add more later
2. **Test Incrementally**: Test each agent individually first
3. **Use Deduplication**: Prevent duplicate notifications
4. **Batch When Possible**: Use DigestAgent for multiple events
5. **Monitor Performance**: Check agent statistics regularly

### Configuration

1. **Use Templates**: Leverage Jinja2 for flexibility
2. **Secure Credentials**: Store passwords securely
3. **Set Timeouts**: Prevent hanging HTTP requests
4. **Reasonable Limits**: Don't fetch 10,000 RSS entries
5. **Test Schedules**: Start with longer intervals

### Debugging

1. **Check Agent Runs**: View execution history
2. **Inspect Events**: Look at event payloads
3. **Review Logs**: Check application logs
4. **Test Manually**: Run agents manually first
5. **Isolate Issues**: Test each agent separately

## API Reference

### AgentService

```python
from app.services.agent_service import AgentService

service = AgentService(db.session)

# Run agent
result = service.run_agent(agent_id=1, manual=True, propagate=True)

# Get statistics
stats = service.get_agent_statistics(agent_id=1)

# Get run history
runs = service.get_agent_run_history(agent_id=1, limit=10)

# Create link
result = service.create_agent_link(source_id=1, target_id=2)

# Delete link
result = service.delete_agent_link(link_id=1)

# Validate config
is_valid, error = service.validate_agent_config('rss_agent', config)

# Get capabilities
caps = service.get_agent_capabilities('rss_agent')
```

### EventService

```python
from app.services.event_service import EventService

service = EventService(db.session)

# Propagate events
stats = service.propagate_events(events)

# Get network stats
stats = service.get_agent_network_stats(agent_id=1)

# Validate link
is_valid, error = service.validate_agent_link(source_id=1, target_id=2)
```

### Agent Registry

```python
from app.agents.registry import agent_registry

# Get agent types
agent_types = agent_registry.get_registered_types()

# Get by category
source_agents = agent_registry.get_source_agents()
transform_agents = agent_registry.get_transform_agents()
action_agents = agent_registry.get_action_agents()

# Get agent class
agent_class = agent_registry.get_agent_class('rss_agent')

# Create agent instance
agent = agent_registry.create_agent(
    agent_type='rss_agent',
    agent_id=1,
    config={'feed_url': 'https://example.com/feed.xml'},
    user_id=1,
    db_session=db.session
)

# Get config schema
schema = agent_registry.get_config_schema('rss_agent')
```

### Memory Manager

```python
from app.agents.memory import MemoryManager

memory = MemoryManager(agent_id=1, user_id=1, db_session=db.session)

# Set value
memory.set('key', 'value')

# Set with expiration
memory.set('temp', 'data', expires_in_seconds=3600)

# Get value
value = memory.get('key')  # Returns None if not found

# Delete value
memory.delete('key')

# Clear all
memory.clear()
```

## Troubleshooting

### Agent Not Running

- Check `is_active` is True
- Verify schedule syntax (for source agents)
- Check `schedule_enabled` is True
- Review error logs

### Events Not Propagating

- Verify AgentLink exists and `is_active` is True
- Check downstream agent is active
- Review agent capabilities (can_receive_events)
- Check for cycles or max depth reached

### Memory Not Persisting

- Verify database connection
- Check agent_id is correct
- Ensure session commits
- Review expiration times

### Performance Issues

- Reduce RSS `max_entries`
- Increase schedule intervals
- Add filters earlier in chain
- Use batch processing (DigestAgent)
- Check database indexes

## Additional Resources

- **Examples**: See `tests/test_agents/test_end_to_end.py` for complete workflow examples
- **Agent Code**: Explore `app/agents/types/` for implementation details
- **Tests**: Review `tests/test_agents/` for usage patterns
- **Web Interface**: Use `/agents` routes for visual management

---

**Questions?** Check the test files for practical examples or review the source code for implementation details.
