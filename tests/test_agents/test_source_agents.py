"""
Tests for source agents (RSSAgent, WebFetchAgent, SchedulerAgent)
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from app import create_app
from app.extensions import db
from app.agents.types import RSSAgent, WebFetchAgent, SchedulerAgent
from app.agents import agent_registry
from app.models import Event


@pytest.fixture
def app():
    """Create application for testing"""
    app = create_app('testing')
    return app


@pytest.fixture
def app_context(app):
    """Create application context and database tables"""
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def test_job(app_context):
    """Create a test job for agent tests"""
    from app.models import Job, User

    # Create a test user first
    user = User(username='testuser', email='test@example.com', password='password123')
    db.session.add(user)
    db.session.flush()

    # Create a test job
    job = Job(
        name='Test Agent',
        job_type='web_scraper',  # Use existing job type
        config={},
        user_id=user.id
    )
    db.session.add(job)
    db.session.commit()

    return job


class TestRSSAgent:
    """Tests for RSSAgent"""

    def test_rss_agent_registered(self):
        """Test that RSSAgent is registered"""
        assert agent_registry.is_registered('rss_agent')
        assert 'rss_agent' in agent_registry.get_source_agents()

    def test_rss_agent_config_validation(self):
        """Test RSS agent configuration validation"""
        # Valid config
        agent = RSSAgent(
            agent_id=1,
            config={'feed_url': 'https://example.com/feed.xml'},
            user_id=1
        )
        assert agent.agent_type == 'rss_agent'

        # Missing feed_url
        with pytest.raises(ValueError, match="requires 'feed_url'"):
            RSSAgent(
                agent_id=1,
                config={},
                user_id=1
            )

        # Invalid URL
        with pytest.raises(ValueError, match="valid HTTP"):
            RSSAgent(
                agent_id=1,
                config={'feed_url': 'not-a-url'},
                user_id=1
            )

        # Invalid max_entries
        with pytest.raises(ValueError, match="max_entries"):
            RSSAgent(
                agent_id=1,
                config={'feed_url': 'https://example.com/feed.xml', 'max_entries': -1},
                user_id=1
            )

    def test_rss_agent_capabilities(self):
        """Test RSS agent capabilities"""
        assert RSSAgent.can_be_scheduled == True
        assert RSSAgent.can_receive_events == False
        assert RSSAgent.can_create_events == True
        assert RSSAgent.requires_input == False

    @patch('feedparser.parse')
    def test_rss_agent_fetch_success(self, mock_parse, test_job):
        """Test RSS agent fetching entries successfully"""
        # Mock feedparser response
        mock_feed = Mock()
        mock_feed.bozo = False
        mock_feed.feed = {
            'title': 'Test Feed',
            'link': 'https://example.com'
        }

        # Create mock entry with published_parsed
        import time
        published_time = datetime.utcnow() - timedelta(hours=1)
        published_parsed = time.strptime(published_time.isoformat()[:19], '%Y-%m-%dT%H:%M:%S')

        # Use dict-like objects for entries (feedparser returns dicts)
        entry1 = {
            'title': 'Test Entry 1',
            'link': 'https://example.com/entry1',
            'summary': 'Test summary 1',
            'author': 'Test Author',
            'id': 'entry1',
            'published_parsed': published_parsed
        }
        entry2 = {
            'title': 'Test Entry 2',
            'link': 'https://example.com/entry2',
            'summary': 'Test summary 2',
            'author': '',
            'id': 'entry2',
            'published_parsed': published_parsed
        }
        mock_feed.entries = [entry1, entry2]
        mock_parse.return_value = mock_feed

        # Create agent and fetch
        agent = RSSAgent(
            agent_id=test_job.id,
            config={
                'feed_url': 'https://example.com/feed.xml',
                'max_entries': 10
            },
            user_id=test_job.user_id
        )

        events = agent.fetch()
        db.session.commit()  # Commit events to database

        # Verify results
        assert len(events) == 2
        assert all(isinstance(e, Event) for e in events)
        assert events[0].payload['title'] == 'Test Entry 1'
        assert events[0].payload['link'] == 'https://example.com/entry1'
        assert events[0].event_metadata['feed_url'] == 'https://example.com/feed.xml'

    @patch('feedparser.parse')
    def test_rss_agent_filters_old_entries(self, mock_parse, test_job):
        """Test RSS agent filters out old entries based on days_back"""
        # Mock feedparser response with old and new entries
        mock_feed = Mock()
        mock_feed.bozo = False
        mock_feed.feed = {'title': 'Test Feed', 'link': 'https://example.com'}

        import time

        # Old entry (10 days ago)
        old_time = datetime.utcnow() - timedelta(days=10)
        old_parsed = time.strptime(old_time.isoformat()[:19], '%Y-%m-%dT%H:%M:%S')

        # New entry (1 hour ago)
        new_time = datetime.utcnow() - timedelta(hours=1)
        new_parsed = time.strptime(new_time.isoformat()[:19], '%Y-%m-%dT%H:%M:%S')

        # Use dict-like objects for entries
        old_entry = {
            'title': 'Old Entry',
            'link': 'https://example.com/old',
            'summary': '',
            'author': '',
            'id': 'old',
            'published_parsed': old_parsed
        }
        new_entry = {
            'title': 'New Entry',
            'link': 'https://example.com/new',
            'summary': '',
            'author': '',
            'id': 'new',
            'published_parsed': new_parsed
        }
        mock_feed.entries = [old_entry, new_entry]
        mock_parse.return_value = mock_feed

        # Create agent with days_back=7
        agent = RSSAgent(
            agent_id=test_job.id,
            config={
                'feed_url': 'https://example.com/feed.xml',
                'days_back': 7
            },
            user_id=test_job.user_id
        )

        events = agent.fetch()
        db.session.commit()

        # Should only get the new entry
        assert len(events) == 1
        assert events[0].payload['title'] == 'New Entry'

    def test_rss_agent_config_schema(self):
        """Test RSS agent configuration schema"""
        schema = RSSAgent.get_config_schema()

        assert schema['agent_type'] == 'rss_agent'
        assert 'feed_url' in schema['required_fields']
        assert schema['capabilities']['can_be_scheduled'] == True


class TestWebFetchAgent:
    """Tests for WebFetchAgent"""

    def test_web_fetch_agent_registered(self):
        """Test that WebFetchAgent is registered"""
        assert agent_registry.is_registered('web_fetch_agent')
        assert 'web_fetch_agent' in agent_registry.get_source_agents()

    def test_web_fetch_agent_config_validation(self):
        """Test web fetch agent configuration validation"""
        # Valid config
        agent = WebFetchAgent(
            agent_id=1,
            config={'url': 'https://example.com'},
            user_id=1
        )
        assert agent.agent_type == 'web_fetch_agent'

        # Missing URL
        with pytest.raises(ValueError, match="requires 'url'"):
            WebFetchAgent(agent_id=1, config={}, user_id=1)

        # Invalid URL
        with pytest.raises(ValueError, match="valid HTTP"):
            WebFetchAgent(
                agent_id=1,
                config={'url': 'not-a-url'},
                user_id=1
            )

        # Invalid timeout
        with pytest.raises(ValueError, match="timeout"):
            WebFetchAgent(
                agent_id=1,
                config={'url': 'https://example.com', 'timeout': -1},
                user_id=1
            )

    def test_web_fetch_agent_capabilities(self):
        """Test web fetch agent capabilities"""
        assert WebFetchAgent.can_be_scheduled == True
        assert WebFetchAgent.can_receive_events == False
        assert WebFetchAgent.can_create_events == True
        assert WebFetchAgent.requires_input == False

    @patch('app.agents.types.web_fetch_agent.requests.get')
    def test_web_fetch_agent_fetch_success(self, mock_get, test_job):
        """Test web fetch agent fetching page successfully"""
        # Mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.url = 'https://example.com'
        mock_response.encoding = 'utf-8'
        mock_response.headers = {
            'content-type': 'text/html',
            'content-length': '100'
        }
        mock_response.elapsed = timedelta(milliseconds=150)
        mock_response.iter_content = lambda chunk_size: [b'<html>Test</html>']
        mock_get.return_value = mock_response

        # Create agent and fetch
        agent = WebFetchAgent(
            agent_id=test_job.id,
            config={'url': 'https://example.com'},
            user_id=test_job.user_id
        )

        events = agent.fetch()
        db.session.commit()

        # Verify results
        assert len(events) == 1
        event = events[0]
        assert event.payload['url'] == 'https://example.com'
        assert event.payload['status_code'] == 200
        assert event.payload['content'] == '<html>Test</html>'
        assert event.event_metadata['elapsed_ms'] == 150.0

    @patch('app.agents.types.web_fetch_agent.requests.get')
    def test_web_fetch_agent_handles_timeout(self, mock_get, app_context):
        """Test web fetch agent handles timeout"""
        import requests
        mock_get.side_effect = requests.exceptions.Timeout()

        agent = WebFetchAgent(
            agent_id=1,
            config={'url': 'https://example.com', 'timeout': 5},
            user_id=1
        )

        events = agent.fetch()
        assert len(events) == 0  # No events on timeout

    def test_web_fetch_agent_config_schema(self):
        """Test web fetch agent configuration schema"""
        schema = WebFetchAgent.get_config_schema()

        assert schema['agent_type'] == 'web_fetch_agent'
        assert 'url' in schema['required_fields']
        assert schema['capabilities']['can_be_scheduled'] == True


class TestSchedulerAgent:
    """Tests for SchedulerAgent"""

    def test_scheduler_agent_registered(self):
        """Test that SchedulerAgent is registered"""
        assert agent_registry.is_registered('scheduler_agent')
        assert 'scheduler_agent' in agent_registry.get_source_agents()

    def test_scheduler_agent_config_validation(self):
        """Test scheduler agent configuration validation"""
        # Valid config (all fields optional)
        agent = SchedulerAgent(
            agent_id=1,
            config={},
            user_id=1
        )
        assert agent.agent_type == 'scheduler_agent'

        # With message
        agent = SchedulerAgent(
            agent_id=1,
            config={'message': 'Test message'},
            user_id=1
        )
        assert agent.config['message'] == 'Test message'

        # Invalid message type
        with pytest.raises(ValueError, match="message"):
            SchedulerAgent(
                agent_id=1,
                config={'message': 123},
                user_id=1
            )

    def test_scheduler_agent_capabilities(self):
        """Test scheduler agent capabilities"""
        assert SchedulerAgent.can_be_scheduled == True
        assert SchedulerAgent.can_receive_events == False
        assert SchedulerAgent.can_create_events == True
        assert SchedulerAgent.requires_input == False

    def test_scheduler_agent_fetch(self, test_job):
        """Test scheduler agent creates event"""
        agent = SchedulerAgent(
            agent_id=test_job.id,
            config={
                'message': 'Daily trigger',
                'data': {'job': 'backup'}
            },
            user_id=test_job.user_id
        )

        events = agent.fetch()
        db.session.commit()

        # Verify event created
        assert len(events) == 1
        event = events[0]
        assert event.payload['message'] == 'Daily trigger'
        assert event.payload['job'] == 'backup'
        assert 'triggered_at' in event.payload
        assert event.event_metadata['trigger_type'] == 'scheduled'

    def test_scheduler_agent_tracks_last_run(self, test_job):
        """Test scheduler agent tracks last run time in memory"""
        agent = SchedulerAgent(
            agent_id=test_job.id,
            config={},
            user_id=test_job.user_id
        )

        # First run
        events = agent.fetch()
        db.session.commit()
        assert len(events) == 1

        # Check memory
        last_run = agent.memory.get('last_run_at')
        assert last_run is not None

    def test_scheduler_agent_config_schema(self):
        """Test scheduler agent configuration schema"""
        schema = SchedulerAgent.get_config_schema()

        assert schema['agent_type'] == 'scheduler_agent'
        assert len(schema['required_fields']) == 0  # All optional
        assert schema['capabilities']['can_be_scheduled'] == True


class TestAgentRegistry:
    """Tests for agent registry with source agents"""

    def test_registry_lists_source_agents(self):
        """Test that registry correctly identifies source agents"""
        source_agents = agent_registry.get_source_agents()

        assert 'rss_agent' in source_agents
        assert 'web_fetch_agent' in source_agents
        assert 'scheduler_agent' in source_agents

    def test_registry_can_create_source_agents(self):
        """Test that registry can create source agent instances"""
        # Create RSS agent
        agent = agent_registry.create_agent(
            agent_type='rss_agent',
            agent_id=1,
            config={'feed_url': 'https://example.com/feed.xml'},
            user_id=1
        )
        assert isinstance(agent, RSSAgent)

        # Create web fetch agent
        agent = agent_registry.create_agent(
            agent_type='web_fetch_agent',
            agent_id=2,
            config={'url': 'https://example.com'},
            user_id=1
        )
        assert isinstance(agent, WebFetchAgent)

        # Create scheduler agent
        agent = agent_registry.create_agent(
            agent_type='scheduler_agent',
            agent_id=3,
            config={},
            user_id=1
        )
        assert isinstance(agent, SchedulerAgent)

    def test_registry_get_capabilities(self):
        """Test getting capabilities for source agents"""
        caps = agent_registry.get_agent_capabilities('rss_agent')

        assert caps['can_be_scheduled'] == True
        assert caps['can_receive_events'] == False
        assert caps['can_create_events'] == True
        assert caps['requires_input'] == False
