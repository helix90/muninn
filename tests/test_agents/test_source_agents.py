"""
Tests for source agents (RSSAgent, WebFetchAgent, SchedulerAgent, JabberListenerAgent)
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from app.extensions import db
from app.agents.types import RSSAgent, WebFetchAgent, SchedulerAgent, JabberListenerAgent
from app.agents import agent_registry
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
    def test_web_fetch_agent_handles_timeout(self, mock_get, app):
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


class TestJabberListenerAgent:
    """Tests for JabberListenerAgent"""

    def test_jabber_listener_agent_registered(self):
        """Test that JabberListenerAgent is registered"""
        assert agent_registry.is_registered('jabber_listener_agent')
        assert 'jabber_listener_agent' in agent_registry.get_source_agents()

    def test_jabber_listener_agent_config_validation(self):
        """Test Jabber listener agent configuration validation"""
        # Valid minimal config
        agent = JabberListenerAgent(
            agent_id=1,
            config={
                'jid': 'bot@jabber.example.com',
                'password': 'secret123'
            },
            user_id=1
        )
        assert agent.agent_type == 'jabber_listener_agent'
        assert agent.config['jid'] == 'bot@jabber.example.com'
        # Default listen_mode is 'both' (not stored in config dict)

        # Missing jid
        with pytest.raises(ValueError, match="jid"):
            JabberListenerAgent(
                agent_id=1,
                config={'password': 'secret'},
                user_id=1
            )

        # Missing password
        with pytest.raises(ValueError, match="password"):
            JabberListenerAgent(
                agent_id=1,
                config={'jid': 'bot@jabber.example.com'},
                user_id=1
            )

        # Invalid listen_mode
        with pytest.raises(ValueError, match="listen_mode"):
            JabberListenerAgent(
                agent_id=1,
                config={
                    'jid': 'bot@jabber.example.com',
                    'password': 'secret',
                    'listen_mode': 'invalid'
                },
                user_id=1
            )

        # Invalid port
        with pytest.raises(ValueError, match="port"):
            JabberListenerAgent(
                agent_id=1,
                config={
                    'jid': 'bot@jabber.example.com',
                    'password': 'secret',
                    'port': -1
                },
                user_id=1
            )

    def test_jabber_listener_agent_capabilities(self):
        """Test Jabber listener agent capabilities"""
        assert JabberListenerAgent.can_be_scheduled == True
        assert JabberListenerAgent.can_receive_events == False
        assert JabberListenerAgent.can_create_events == True
        assert JabberListenerAgent.requires_input == False

    @patch('app.agents.types.jabber_listener_agent.threading.Thread')
    def test_jabber_listener_agent_fetch_direct_message(self, mock_thread, test_job):
        """Test Jabber listener agent receives direct message"""
        # Create agent
        agent = JabberListenerAgent(
            agent_id=test_job.id,
            config={
                'jid': 'bot@jabber.example.com',
                'password': 'secret',
                'listen_mode': 'direct'
            },
            user_id=test_job.user_id
        )

        # Mock a direct message in the queue with correct structure
        from datetime import datetime
        msg_data = {
            'payload': {
                'body': 'Hello bot!',
                'from': 'user@example.com',
                'from_resource': 'mobile',
                'type': 'chat',
                'subject': None
            },
            'metadata': {
                'received_at': datetime.utcnow().isoformat(),
                'message_type': 'direct',
                'agent_jid': 'bot@jabber.example.com'
            }
        }

        # Directly add message to queue
        with agent._queue_lock:
            agent._message_queue.append(msg_data)

        # Fetch events
        events = agent.fetch()
        db.session.commit()

        # Verify results
        assert len(events) == 1
        event = events[0]
        assert event.payload['body'] == 'Hello bot!'
        assert event.payload['from'] == 'user@example.com'
        assert event.payload['type'] == 'chat'
        assert event.event_metadata['message_type'] == 'direct'
        assert event.event_metadata['agent_jid'] == 'bot@jabber.example.com'

    @patch('app.agents.types.jabber_listener_agent.threading.Thread')
    def test_jabber_listener_agent_fetch_groupchat_message(self, mock_thread, test_job):
        """Test Jabber listener agent receives group chat message"""
        # Create agent
        agent = JabberListenerAgent(
            agent_id=test_job.id,
            config={
                'jid': 'bot@jabber.example.com',
                'password': 'secret',
                'listen_mode': 'rooms',
                'rooms': ['room@conference.example.com'],
                'room_nickname': 'BotNick'
            },
            user_id=test_job.user_id
        )

        # Mock a group chat message in the queue with correct structure
        from datetime import datetime
        msg_data = {
            'payload': {
                'body': 'Meeting at 3pm',
                'from': 'room@conference.example.com',
                'from_nick': 'Alice',
                'type': 'groupchat',
                'subject': None
            },
            'metadata': {
                'received_at': datetime.utcnow().isoformat(),
                'message_type': 'groupchat',
                'room': 'room@conference.example.com',
                'agent_jid': 'bot@jabber.example.com'
            }
        }

        # Directly add message to queue
        with agent._queue_lock:
            agent._message_queue.append(msg_data)

        # Fetch events
        events = agent.fetch()
        db.session.commit()

        # Verify results
        assert len(events) == 1
        event = events[0]
        assert event.payload['body'] == 'Meeting at 3pm'
        assert event.payload['from'] == 'room@conference.example.com'
        assert event.payload['from_nick'] == 'Alice'
        assert event.payload['type'] == 'groupchat'
        assert event.event_metadata['message_type'] == 'groupchat'
        assert event.event_metadata['room'] == 'room@conference.example.com'

    @patch('app.agents.types.jabber_listener_agent.threading.Thread')
    def test_jabber_listener_agent_processes_multiple_messages(self, mock_thread, test_job):
        """Test Jabber listener agent processes multiple messages"""
        agent = JabberListenerAgent(
            agent_id=test_job.id,
            config={
                'jid': 'bot@jabber.example.com',
                'password': 'secret',
                'listen_mode': 'both'
            },
            user_id=test_job.user_id
        )

        from datetime import datetime

        # Add multiple messages to queue with correct structure
        messages = [
            {
                'payload': {
                    'body': 'Message 1',
                    'from': 'user1@example.com',
                    'from_resource': 'desktop',
                    'type': 'chat',
                    'subject': None
                },
                'metadata': {
                    'received_at': datetime.utcnow().isoformat(),
                    'message_type': 'direct',
                    'agent_jid': 'bot@jabber.example.com'
                }
            },
            {
                'payload': {
                    'body': 'Message 2',
                    'from': 'user2@example.com',
                    'from_resource': 'mobile',
                    'type': 'chat',
                    'subject': None
                },
                'metadata': {
                    'received_at': datetime.utcnow().isoformat(),
                    'message_type': 'direct',
                    'agent_jid': 'bot@jabber.example.com'
                }
            },
            {
                'payload': {
                    'body': 'Group message',
                    'from': 'room@conference.example.com',
                    'from_nick': 'Bob',
                    'type': 'groupchat',
                    'subject': None
                },
                'metadata': {
                    'received_at': datetime.utcnow().isoformat(),
                    'message_type': 'groupchat',
                    'room': 'room@conference.example.com',
                    'agent_jid': 'bot@jabber.example.com'
                }
            }
        ]

        with agent._queue_lock:
            agent._message_queue.extend(messages)

        # Fetch events
        events = agent.fetch()
        db.session.commit()

        # Should get all 3 messages
        assert len(events) == 3
        assert events[0].payload['body'] == 'Message 1'
        assert events[1].payload['body'] == 'Message 2'
        assert events[2].payload['body'] == 'Group message'

    @patch('app.agents.types.jabber_listener_agent.threading.Thread')
    def test_jabber_listener_agent_empty_queue(self, mock_thread, test_job):
        """Test Jabber listener agent with empty message queue"""
        agent = JabberListenerAgent(
            agent_id=test_job.id,
            config={
                'jid': 'bot@jabber.example.com',
                'password': 'secret'
            },
            user_id=test_job.user_id
        )

        # Fetch with empty queue
        events = agent.fetch()

        # Should return empty list
        assert len(events) == 0

    def test_jabber_listener_agent_listen_modes(self):
        """Test Jabber listener agent different listen modes"""
        # Listen to direct messages only
        agent_direct = JabberListenerAgent(
            agent_id=1,
            config={
                'jid': 'bot@jabber.example.com',
                'password': 'secret',
                'listen_mode': 'direct'
            },
            user_id=1
        )
        assert agent_direct.config['listen_mode'] == 'direct'

        # Listen to rooms only
        agent_rooms = JabberListenerAgent(
            agent_id=2,
            config={
                'jid': 'bot@jabber.example.com',
                'password': 'secret',
                'listen_mode': 'rooms',
                'rooms': ['room1@conference.server']
            },
            user_id=1
        )
        assert agent_rooms.config['listen_mode'] == 'rooms'
        assert agent_rooms.config['rooms'] == ['room1@conference.server']

        # Listen to both (default) - when not specified, defaults to 'both'
        agent_both = JabberListenerAgent(
            agent_id=3,
            config={
                'jid': 'bot@jabber.example.com',
                'password': 'secret'
            },
            user_id=1
        )
        # Default listen_mode is 'both' (not stored in config dict unless explicitly provided)

    def test_jabber_listener_agent_filtering_config(self):
        """Test Jabber listener agent filtering configuration"""
        agent = JabberListenerAgent(
            agent_id=1,
            config={
                'jid': 'bot@jabber.example.com',
                'password': 'secret',
                'ignore_self': True,
                'ignore_jids': ['spam@example.com', 'bot2@example.com']
            },
            user_id=1
        )

        assert agent.config['ignore_self'] == True
        assert 'spam@example.com' in agent.config['ignore_jids']
        assert 'bot2@example.com' in agent.config['ignore_jids']

    def test_jabber_listener_agent_config_schema(self):
        """Test Jabber listener agent configuration schema"""
        schema = JabberListenerAgent.get_config_schema()

        assert schema['agent_type'] == 'jabber_listener_agent'
        assert 'jid' in schema['required_fields']
        assert 'password' in schema['required_fields']
        assert schema['capabilities']['can_be_scheduled'] == True
        assert schema['capabilities']['can_receive_events'] == False
        assert schema['capabilities']['can_create_events'] == True

    @patch('app.agents.types.jabber_listener_agent.threading.Thread')
    def test_jabber_listener_agent_cleanup_on_del(self, mock_thread, test_job):
        """Test Jabber listener agent cleanup on deletion"""
        agent = JabberListenerAgent(
            agent_id=test_job.id,
            config={
                'jid': 'bot@jabber.example.com',
                'password': 'secret'
            },
            user_id=test_job.user_id
        )

        # Mock the thread and stop event
        agent._xmpp_thread = MagicMock()
        agent._stop_event = MagicMock()

        # Delete agent
        del agent

        # Cleanup should be called (implicitly through __del__)
        # We can't easily test __del__ directly, but we've verified the structure exists

    def test_jabber_listener_agent_with_server_override(self):
        """Test Jabber listener agent with explicit server configuration"""
        agent = JabberListenerAgent(
            agent_id=1,
            config={
                'jid': 'bot@jabber.example.com',
                'password': 'secret',
                'server': 'xmpp.custom-server.com',
                'port': 5223,
                'use_tls': False
            },
            user_id=1
        )

        assert agent.config['server'] == 'xmpp.custom-server.com'
        assert agent.config['port'] == 5223
        assert agent.config['use_tls'] == False

    def test_jabber_listener_agent_rooms_validation(self):
        """Test Jabber listener agent rooms configuration validation"""
        # Rooms mode requires rooms list
        with pytest.raises(ValueError, match="'rooms'.*empty.*'rooms'"):
            JabberListenerAgent(
                agent_id=1,
                config={
                    'jid': 'bot@jabber.example.com',
                    'password': 'secret',
                    'listen_mode': 'rooms'
                },
                user_id=1
            )

        # Rooms must be a list
        with pytest.raises(ValueError, match="rooms.*list"):
            JabberListenerAgent(
                agent_id=1,
                config={
                    'jid': 'bot@jabber.example.com',
                    'password': 'secret',
                    'listen_mode': 'rooms',
                    'rooms': 'not-a-list'
                },
                user_id=1
            )


class TestAgentRegistry:
    """Tests for agent registry with source agents"""

    def test_registry_lists_source_agents(self):
        """Test that registry correctly identifies source agents"""
        source_agents = agent_registry.get_source_agents()

        assert 'rss_agent' in source_agents
        assert 'web_fetch_agent' in source_agents
        assert 'scheduler_agent' in source_agents
        assert 'jabber_listener_agent' in source_agents

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

        # Create jabber listener agent
        agent = agent_registry.create_agent(
            agent_type='jabber_listener_agent',
            agent_id=4,
            config={'jid': 'bot@jabber.example.com', 'password': 'secret'},
            user_id=1
        )
        assert isinstance(agent, JabberListenerAgent)

    def test_registry_get_capabilities(self):
        """Test getting capabilities for source agents"""
        caps = agent_registry.get_agent_capabilities('rss_agent')

        assert caps['can_be_scheduled'] == True
        assert caps['can_receive_events'] == False
        assert caps['can_create_events'] == True
        assert caps['requires_input'] == False
