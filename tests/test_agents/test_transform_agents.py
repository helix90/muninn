"""
Tests for transform agents (FilterAgent, DeduplicationAgent, HTMLParserAgent, TemplateAgent)
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
from app.extensions import db
from app.agents.types import FilterAgent, DeduplicationAgent, HTMLParserAgent, TemplateAgent
from app.agents import agent_registry
from app.agents.enums import EventFilterType
from app.models import Event


@pytest.fixture
def test_job(app, test_user):
    """Create a test job for agent tests"""
    from app.models import Job

    with app.app_context():
        job = Job(
            name='Test Agent',
            job_type='rss_agent',
            config={'feed_url': 'https://example.com/feed.xml'},
            user_id=test_user.id
        )
        db.session.add(job)
        db.session.commit()

        yield job


@pytest.fixture
def sample_events(test_job):
    """Create sample events for testing"""
    events = [
        Event(
            agent_id=test_job.id,
            agent_type='test_agent',
            user_id=test_job.user_id,
            payload={'title': 'Python Tutorial', 'views': 100, 'link': 'https://example.com/1'},
            metadata={'source': 'test'}
        ),
        Event(
            agent_id=test_job.id,
            agent_type='test_agent',
            user_id=test_job.user_id,
            payload={'title': 'JavaScript Guide', 'views': 50, 'link': 'https://example.com/2'},
            metadata={'source': 'test'}
        ),
        Event(
            agent_id=test_job.id,
            agent_type='test_agent',
            user_id=test_job.user_id,
            payload={'title': 'Python Advanced', 'views': 200, 'link': 'https://example.com/3'},
            metadata={'source': 'test'}
        ),
    ]
    for event in events:
        db.session.add(event)
    db.session.commit()
    return events


class TestFilterAgent:
    """Tests for FilterAgent"""

    def test_filter_agent_registered(self):
        """Test that FilterAgent is registered"""
        assert agent_registry.is_registered('filter_agent')
        assert 'filter_agent' in agent_registry.get_transform_agents()

    def test_filter_agent_config_validation(self):
        """Test filter agent configuration validation"""
        # Valid config
        agent = FilterAgent(
            agent_id=1,
            config={
                'rules': [
                    {'field': 'title', 'type': 'contains', 'value': 'python'}
                ]
            },
            user_id=1
        )
        assert agent.agent_type == 'filter_agent'

        # Missing rules
        with pytest.raises(ValueError, match="requires 'rules'"):
            FilterAgent(agent_id=1, config={}, user_id=1)

        # Empty rules
        with pytest.raises(ValueError, match="at least one rule"):
            FilterAgent(agent_id=1, config={'rules': []}, user_id=1)

        # Invalid filter type
        with pytest.raises(ValueError, match="invalid type"):
            FilterAgent(
                agent_id=1,
                config={'rules': [{'field': 'title', 'type': 'invalid_type', 'value': 'test'}]},
                user_id=1
            )

    def test_filter_agent_capabilities(self):
        """Test filter agent capabilities"""
        assert FilterAgent.can_be_scheduled == False
        assert FilterAgent.can_receive_events == True
        assert FilterAgent.can_create_events == True
        assert FilterAgent.requires_input == True

    def test_filter_agent_contains(self, test_job, sample_events):
        """Test filter agent with contains rule"""
        agent = FilterAgent(
            agent_id=test_job.id,
            config={
                'rules': [
                    {'field': 'title', 'type': 'contains', 'value': 'Python', 'case_sensitive': False}
                ]
            },
            user_id=test_job.user_id
        )

        filtered = agent.process(sample_events)
        db.session.commit()

        # Should match "Python Tutorial" and "Python Advanced"
        assert len(filtered) == 2
        assert filtered[0].payload['title'] == 'Python Tutorial'
        assert filtered[1].payload['title'] == 'Python Advanced'

    def test_filter_agent_greater_than(self, test_job, sample_events):
        """Test filter agent with greater_than rule"""
        agent = FilterAgent(
            agent_id=test_job.id,
            config={
                'rules': [
                    {'field': 'views', 'type': 'greater_than', 'value': 75}
                ]
            },
            user_id=test_job.user_id
        )

        filtered = agent.process(sample_events)
        db.session.commit()

        # Should match views > 75 (100 and 200)
        assert len(filtered) == 2
        assert filtered[0].payload['views'] == 100
        assert filtered[1].payload['views'] == 200

    def test_filter_agent_multiple_rules_and_logic(self, test_job, sample_events):
        """Test filter agent with multiple rules (AND logic)"""
        agent = FilterAgent(
            agent_id=test_job.id,
            config={
                'rules': [
                    {'field': 'title', 'type': 'contains', 'value': 'Python', 'case_sensitive': False},
                    {'field': 'views', 'type': 'greater_than', 'value': 150}
                ],
                'match_all': True
            },
            user_id=test_job.user_id
        )

        filtered = agent.process(sample_events)
        db.session.commit()

        # Should match only "Python Advanced" (views=200)
        assert len(filtered) == 1
        assert filtered[0].payload['title'] == 'Python Advanced'

    def test_filter_agent_multiple_rules_or_logic(self, test_job, sample_events):
        """Test filter agent with multiple rules (OR logic)"""
        agent = FilterAgent(
            agent_id=test_job.id,
            config={
                'rules': [
                    {'field': 'title', 'type': 'contains', 'value': 'JavaScript'},
                    {'field': 'views', 'type': 'greater_than', 'value': 150}
                ],
                'match_all': False
            },
            user_id=test_job.user_id
        )

        filtered = agent.process(sample_events)
        db.session.commit()

        # Should match "JavaScript Guide" OR views > 150 ("Python Advanced")
        assert len(filtered) == 2

    def test_filter_agent_regex(self, test_job, sample_events):
        """Test filter agent with regex rule"""
        agent = FilterAgent(
            agent_id=test_job.id,
            config={
                'rules': [
                    {'field': 'title', 'type': 'regex', 'value': r'^Python\s+\w+$', 'case_sensitive': True}
                ]
            },
            user_id=test_job.user_id
        )

        filtered = agent.process(sample_events)
        db.session.commit()

        # Should match "Python Tutorial" and "Python Advanced"
        assert len(filtered) == 2

    def test_filter_agent_config_schema(self):
        """Test filter agent configuration schema"""
        schema = FilterAgent.get_config_schema()

        assert schema['agent_type'] == 'filter_agent'
        assert 'rules' in schema['required_fields']
        assert schema['capabilities']['can_receive_events'] == True


class TestDeduplicationAgent:
    """Tests for DeduplicationAgent"""

    def test_deduplication_agent_registered(self):
        """Test that DeduplicationAgent is registered"""
        assert agent_registry.is_registered('deduplication_agent')
        assert 'deduplication_agent' in agent_registry.get_transform_agents()

    def test_deduplication_agent_config_validation(self):
        """Test deduplication agent configuration validation"""
        # Valid config
        agent = DeduplicationAgent(
            agent_id=1,
            config={'uniqueness_fields': ['link']},
            user_id=1
        )
        assert agent.agent_type == 'deduplication_agent'

        # Missing uniqueness_fields
        with pytest.raises(ValueError, match="uniqueness_fields"):
            DeduplicationAgent(agent_id=1, config={}, user_id=1)

        # Empty uniqueness_fields
        with pytest.raises(ValueError, match="at least one field"):
            DeduplicationAgent(agent_id=1, config={'uniqueness_fields': []}, user_id=1)

    def test_deduplication_agent_capabilities(self):
        """Test deduplication agent capabilities"""
        assert DeduplicationAgent.can_be_scheduled == False
        assert DeduplicationAgent.can_receive_events == True
        assert DeduplicationAgent.can_create_events == True
        assert DeduplicationAgent.requires_input == True

    def test_deduplication_agent_removes_duplicates(self, test_job):
        """Test deduplication agent removes duplicate events"""
        # Create events with duplicate links
        events = [
            Event(
                agent_id=test_job.id,
                agent_type='test_agent',
                user_id=test_job.user_id,
                payload={'title': 'Article 1', 'link': 'https://example.com/article'},
                metadata={}
            ),
            Event(
                agent_id=test_job.id,
                agent_type='test_agent',
                user_id=test_job.user_id,
                payload={'title': 'Article 1 Duplicate', 'link': 'https://example.com/article'},
                metadata={}
            ),
            Event(
                agent_id=test_job.id,
                agent_type='test_agent',
                user_id=test_job.user_id,
                payload={'title': 'Article 2', 'link': 'https://example.com/article2'},
                metadata={}
            ),
        ]
        for event in events:
            db.session.add(event)
        db.session.commit()

        agent = DeduplicationAgent(
            agent_id=test_job.id,
            config={'uniqueness_fields': ['link']},
            user_id=test_job.user_id
        )

        unique = agent.process(events)
        db.session.commit()

        # Should return only 2 events (duplicate removed)
        assert len(unique) == 2
        assert unique[0].payload['link'] == 'https://example.com/article'
        assert unique[1].payload['link'] == 'https://example.com/article2'

    def test_deduplication_agent_uses_memory(self, test_job):
        """Test deduplication agent remembers seen items across runs"""
        events1 = [
            Event(
                agent_id=test_job.id,
                agent_type='test_agent',
                user_id=test_job.user_id,
                payload={'title': 'Article 1', 'link': 'https://example.com/1'},
                metadata={}
            ),
        ]
        db.session.add_all(events1)
        db.session.commit()

        agent = DeduplicationAgent(
            agent_id=test_job.id,
            config={'uniqueness_fields': ['link']},
            user_id=test_job.user_id
        )

        # First run - should return the event
        unique1 = agent.process(events1)
        db.session.commit()
        assert len(unique1) == 1

        # Create same event again
        events2 = [
            Event(
                agent_id=test_job.id,
                agent_type='test_agent',
                user_id=test_job.user_id,
                payload={'title': 'Article 1', 'link': 'https://example.com/1'},
                metadata={}
            ),
        ]
        db.session.add_all(events2)
        db.session.commit()

        # Second run - should filter it out (already seen)
        unique2 = agent.process(events2)
        db.session.commit()
        assert len(unique2) == 0

    def test_deduplication_agent_multiple_fields(self, test_job):
        """Test deduplication with multiple uniqueness fields"""
        events = [
            Event(
                agent_id=test_job.id,
                agent_type='test_agent',
                user_id=test_job.user_id,
                payload={'title': 'Article', 'author': 'John', 'link': 'https://example.com/1'},
                metadata={}
            ),
            Event(
                agent_id=test_job.id,
                agent_type='test_agent',
                user_id=test_job.user_id,
                payload={'title': 'Article', 'author': 'Jane', 'link': 'https://example.com/2'},
                metadata={}
            ),
            Event(
                agent_id=test_job.id,
                agent_type='test_agent',
                user_id=test_job.user_id,
                payload={'title': 'Article', 'author': 'John', 'link': 'https://example.com/3'},
                metadata={}
            ),
        ]
        db.session.add_all(events)
        db.session.commit()

        agent = DeduplicationAgent(
            agent_id=test_job.id,
            config={'uniqueness_fields': ['title', 'author']},
            user_id=test_job.user_id
        )

        unique = agent.process(events)
        db.session.commit()

        # Should dedupe based on title+author combo
        # "Article" + "John" appears twice, so only 2 unique
        assert len(unique) == 2

    def test_deduplication_agent_config_schema(self):
        """Test deduplication agent configuration schema"""
        schema = DeduplicationAgent.get_config_schema()

        assert schema['agent_type'] == 'deduplication_agent'
        assert 'uniqueness_fields' in schema['required_fields']


class TestHTMLParserAgent:
    """Tests for HTMLParserAgent"""

    def test_html_parser_agent_registered(self):
        """Test that HTMLParserAgent is registered"""
        assert agent_registry.is_registered('html_parser_agent')
        assert 'html_parser_agent' in agent_registry.get_transform_agents()

    def test_html_parser_agent_config_validation(self):
        """Test HTML parser agent configuration validation"""
        # Valid config
        agent = HTMLParserAgent(
            agent_id=1,
            config={'selectors': {'title': 'h1'}},
            user_id=1
        )
        assert agent.agent_type == 'html_parser_agent'

        # Missing selectors
        with pytest.raises(ValueError, match="selectors"):
            HTMLParserAgent(agent_id=1, config={}, user_id=1)

        # Empty selectors
        with pytest.raises(ValueError, match="at least one selector"):
            HTMLParserAgent(agent_id=1, config={'selectors': {}}, user_id=1)

    def test_html_parser_agent_capabilities(self):
        """Test HTML parser agent capabilities"""
        assert HTMLParserAgent.can_be_scheduled == False
        assert HTMLParserAgent.can_receive_events == True
        assert HTMLParserAgent.can_create_events == True
        assert HTMLParserAgent.requires_input == True

    def test_html_parser_agent_extract_first(self, test_job):
        """Test HTML parser agent extracting first match"""
        html_content = """
        <html>
            <head><title>Test Page</title></head>
            <body>
                <h1>Main Title</h1>
                <p class="summary">This is a summary</p>
                <a href="https://example.com">Link</a>
            </body>
        </html>
        """

        events = [
            Event(
                agent_id=test_job.id,
                agent_type='web_fetch_agent',
                user_id=test_job.user_id,
                payload={'url': 'https://example.com', 'content': html_content},
                metadata={}
            )
        ]
        db.session.add_all(events)
        db.session.commit()

        agent = HTMLParserAgent(
            agent_id=test_job.id,
            config={
                'selectors': {
                    'title': 'h1',
                    'summary': 'p.summary',
                    'link': 'a'
                },
                'extract_mode': 'first'
            },
            user_id=test_job.user_id
        )

        parsed = agent.process(events)
        db.session.commit()

        assert len(parsed) == 1
        assert parsed[0].payload['title'] == 'Main Title'
        assert parsed[0].payload['summary'] == 'This is a summary'
        assert parsed[0].payload['link'] == 'Link'

    def test_html_parser_agent_extract_all(self, test_job):
        """Test HTML parser agent extracting all matches"""
        html_content = """
        <html>
            <body>
                <article>
                    <h2>Article 1</h2>
                    <p>Summary 1</p>
                </article>
                <article>
                    <h2>Article 2</h2>
                    <p>Summary 2</p>
                </article>
            </body>
        </html>
        """

        events = [
            Event(
                agent_id=test_job.id,
                agent_type='web_fetch_agent',
                user_id=test_job.user_id,
                payload={'url': 'https://example.com', 'content': html_content},
                metadata={}
            )
        ]
        db.session.add_all(events)
        db.session.commit()

        agent = HTMLParserAgent(
            agent_id=test_job.id,
            config={
                'selectors': {
                    'article': 'article',
                    'title': 'h2',
                    'summary': 'p'
                },
                'extract_mode': 'all',
                'create_event_per_item': False
            },
            user_id=test_job.user_id
        )

        parsed = agent.process(events)
        db.session.commit()

        assert len(parsed) == 1
        assert 'items' in parsed[0].payload
        assert len(parsed[0].payload['items']) == 2
        assert parsed[0].payload['items'][0]['title'] == 'Article 1'
        assert parsed[0].payload['items'][1]['title'] == 'Article 2'

    def test_html_parser_agent_create_event_per_item(self, test_job):
        """Test HTML parser agent creating separate event per item"""
        html_content = """
        <html>
            <body>
                <div class="item">Item 1</div>
                <div class="item">Item 2</div>
                <div class="item">Item 3</div>
            </body>
        </html>
        """

        events = [
            Event(
                agent_id=test_job.id,
                agent_type='web_fetch_agent',
                user_id=test_job.user_id,
                payload={'url': 'https://example.com', 'content': html_content},
                metadata={}
            )
        ]
        db.session.add_all(events)
        db.session.commit()

        agent = HTMLParserAgent(
            agent_id=test_job.id,
            config={
                'selectors': {
                    'item': 'div.item'
                },
                'extract_mode': 'all',
                'create_event_per_item': True
            },
            user_id=test_job.user_id
        )

        parsed = agent.process(events)
        db.session.commit()

        # Should create 3 separate events
        assert len(parsed) == 3
        assert parsed[0].payload['item'] == 'Item 1'
        assert parsed[1].payload['item'] == 'Item 2'
        assert parsed[2].payload['item'] == 'Item 3'

    def test_html_parser_agent_config_schema(self):
        """Test HTML parser agent configuration schema"""
        schema = HTMLParserAgent.get_config_schema()

        assert schema['agent_type'] == 'html_parser_agent'
        assert 'selectors' in schema['required_fields']


class TestTemplateAgent:
    """Tests for TemplateAgent"""

    def test_template_agent_registered(self):
        """Test that TemplateAgent is registered"""
        assert agent_registry.is_registered('template_agent')
        assert 'template_agent' in agent_registry.get_transform_agents()

    def test_template_agent_config_validation(self):
        """Test template agent configuration validation"""
        # Valid config with single template
        agent = TemplateAgent(
            agent_id=1,
            config={'template': 'Hello {{ name }}'},
            user_id=1
        )
        assert agent.agent_type == 'template_agent'

        # Valid config with templates dict
        agent = TemplateAgent(
            agent_id=1,
            config={'templates': {'greeting': 'Hello {{ name }}'}},
            user_id=1
        )

        # Missing both template and templates
        with pytest.raises(ValueError, match="requires 'template' or 'templates'"):
            TemplateAgent(agent_id=1, config={}, user_id=1)

        # Invalid template syntax
        with pytest.raises(ValueError, match="Invalid Jinja2"):
            TemplateAgent(
                agent_id=1,
                config={'template': 'Hello {{ name '},
                user_id=1
            )

    def test_template_agent_capabilities(self):
        """Test template agent capabilities"""
        assert TemplateAgent.can_be_scheduled == False
        assert TemplateAgent.can_receive_events == True
        assert TemplateAgent.can_create_events == True
        assert TemplateAgent.requires_input == True

    def test_template_agent_single_template(self, test_job, sample_events):
        """Test template agent with single template"""
        agent = TemplateAgent(
            agent_id=test_job.id,
            config={
                'template': 'Title: {{ title }}, Views: {{ views }}',
                'output_field': 'formatted',
                'preserve_original': True
            },
            user_id=test_job.user_id
        )

        transformed = agent.process(sample_events)
        db.session.commit()

        assert len(transformed) == 3
        assert transformed[0].payload['formatted'] == 'Title: Python Tutorial, Views: 100'
        assert transformed[0].payload['title'] == 'Python Tutorial'  # Original preserved

    def test_template_agent_multiple_templates(self, test_job, sample_events):
        """Test template agent with multiple templates"""
        agent = TemplateAgent(
            agent_id=test_job.id,
            config={
                'templates': {
                    'display_title': '{{ title|upper }}',
                    'view_count': '{{ views }} views',
                    'url': '{{ link }}'
                },
                'preserve_original': False
            },
            user_id=test_job.user_id
        )

        transformed = agent.process(sample_events)
        db.session.commit()

        assert len(transformed) == 3
        assert transformed[0].payload['display_title'] == 'PYTHON TUTORIAL'
        assert transformed[0].payload['view_count'] == '100 views'
        assert 'title' not in transformed[0].payload  # Original not preserved

    def test_template_agent_jinja2_filters(self, test_job):
        """Test template agent with Jinja2 filters"""
        events = [
            Event(
                agent_id=test_job.id,
                agent_type='test_agent',
                user_id=test_job.user_id,
                payload={'name': 'john doe'},
                metadata={}
            )
        ]
        db.session.add_all(events)
        db.session.commit()

        agent = TemplateAgent(
            agent_id=test_job.id,
            config={
                'templates': {
                    'capitalized': '{{ name|title }}',
                    'default_score': '{{ score|default("N/A") }}'
                }
            },
            user_id=test_job.user_id
        )

        transformed = agent.process(events)
        db.session.commit()

        assert transformed[0].payload['capitalized'] == 'John Doe'
        assert transformed[0].payload['default_score'] == 'N/A'

    def test_template_agent_control_structures(self, test_job):
        """Test template agent with Jinja2 control structures"""
        events = [
            Event(
                agent_id=test_job.id,
                agent_type='test_agent',
                user_id=test_job.user_id,
                payload={'views': 150},
                metadata={}
            )
        ]
        db.session.add_all(events)
        db.session.commit()

        agent = TemplateAgent(
            agent_id=test_job.id,
            config={
                'template': '{% if views > 100 %}Popular{% else %}Normal{% endif %}',
                'output_field': 'popularity'
            },
            user_id=test_job.user_id
        )

        transformed = agent.process(events)
        db.session.commit()

        assert transformed[0].payload['popularity'] == 'Popular'

    def test_template_agent_config_schema(self):
        """Test template agent configuration schema"""
        schema = TemplateAgent.get_config_schema()

        assert schema['agent_type'] == 'template_agent'
        assert 'jinja2_features' in schema


class TestDatetimeformatFilter:
    """Tests for the custom datetimeformat Jinja2 filter in TemplateAgent."""

    def _agent(self, test_job, template):
        return TemplateAgent(
            agent_id=test_job.id,
            config={'template': template, 'output_field': 'result', 'preserve_original': False},
            user_id=test_job.user_id,
        )

    def _event(self, test_job, payload):
        e = Event(
            agent_id=test_job.id,
            agent_type='test_agent',
            user_id=test_job.user_id,
            payload=payload,
            metadata={},
        )
        db.session.add(e)
        db.session.commit()
        return e

    def test_default_format(self, app, test_job):
        """Default format produces human-readable date and time."""
        with app.app_context():
            event = self._event(test_job, {'ts': '2026-07-14T09:32:00.000000'})
            agent = self._agent(test_job, '{{ ts | datetimeformat }}')
            result = agent.process([event])
            db.session.commit()
            assert result[0].payload['result'] == 'July 14, 2026 at 9:32 AM'

    def test_custom_format_date_only(self, app, test_job):
        """Custom strftime format string is respected."""
        with app.app_context():
            event = self._event(test_job, {'ts': '2026-07-14T09:32:00.000000'})
            agent = self._agent(test_job, "{{ ts | datetimeformat('%d %b %Y') }}")
            result = agent.process([event])
            db.session.commit()
            assert result[0].payload['result'] == '14 Jul 2026'

    def test_custom_format_with_weekday(self, app, test_job):
        """Weekday name formats correctly."""
        with app.app_context():
            event = self._event(test_job, {'ts': '2026-07-14T09:32:00.000000'})
            agent = self._agent(test_job, "{{ ts | datetimeformat('%A') }}")
            result = agent.process([event])
            db.session.commit()
            assert result[0].payload['result'] == 'Tuesday'

    def test_afternoon_time_pm(self, app, test_job):
        """PM times render correctly."""
        with app.app_context():
            event = self._event(test_job, {'ts': '2026-07-14T15:45:00.000000'})
            agent = self._agent(test_job, "{{ ts | datetimeformat('%-I:%M %p') }}")
            result = agent.process([event])
            db.session.commit()
            assert result[0].payload['result'] == '3:45 PM'

    def test_triggered_at_field_from_scheduler(self, app, test_job):
        """Works with the triggered_at field that SchedulerAgent emits."""
        with app.app_context():
            event = self._event(test_job, {'triggered_at': '2026-01-01T00:00:00.000000'})
            agent = self._agent(test_job, '{{ triggered_at | datetimeformat }}')
            result = agent.process([event])
            db.session.commit()
            assert result[0].payload['result'] == 'January 1, 2026 at 12:00 AM'

    def test_none_value_returns_empty_string(self, app, test_job):
        """None/missing value returns empty string rather than raising."""
        with app.app_context():
            event = self._event(test_job, {'ts': None})
            agent = self._agent(test_job, '{{ ts | datetimeformat }}')
            result = agent.process([event])
            db.session.commit()
            assert result[0].payload['result'] == ''

    def test_invalid_string_returned_as_is(self, app, test_job):
        """Non-ISO strings are passed through unchanged."""
        with app.app_context():
            event = self._event(test_job, {'ts': 'not-a-date'})
            agent = self._agent(test_job, '{{ ts | datetimeformat }}')
            result = agent.process([event])
            db.session.commit()
            assert result[0].payload['result'] == 'not-a-date'


class TestAgentRegistry:
    """Tests for agent registry with transform agents"""

    def test_registry_lists_transform_agents(self):
        """Test that registry correctly identifies transform agents"""
        transform_agents = agent_registry.get_transform_agents()

        assert 'filter_agent' in transform_agents
        assert 'deduplication_agent' in transform_agents
        assert 'html_parser_agent' in transform_agents
        assert 'template_agent' in transform_agents

    def test_registry_can_create_transform_agents(self):
        """Test that registry can create transform agent instances"""
        # Create filter agent
        agent = agent_registry.create_agent(
            agent_type='filter_agent',
            agent_id=1,
            config={'rules': [{'field': 'title', 'type': 'contains', 'value': 'test'}]},
            user_id=1
        )
        assert isinstance(agent, FilterAgent)

        # Create deduplication agent
        agent = agent_registry.create_agent(
            agent_type='deduplication_agent',
            agent_id=2,
            config={'uniqueness_fields': ['link']},
            user_id=1
        )
        assert isinstance(agent, DeduplicationAgent)

        # Create HTML parser agent
        agent = agent_registry.create_agent(
            agent_type='html_parser_agent',
            agent_id=3,
            config={'selectors': {'title': 'h1'}},
            user_id=1
        )
        assert isinstance(agent, HTMLParserAgent)

        # Create template agent
        agent = agent_registry.create_agent(
            agent_type='template_agent',
            agent_id=4,
            config={'template': 'Hello {{ name }}'},
            user_id=1
        )
        assert isinstance(agent, TemplateAgent)

    def test_registry_get_capabilities(self):
        """Test getting capabilities for transform agents"""
        caps = agent_registry.get_agent_capabilities('filter_agent')

        assert caps['can_be_scheduled'] == False
        assert caps['can_receive_events'] == True
        assert caps['can_create_events'] == True
        assert caps['requires_input'] == True
