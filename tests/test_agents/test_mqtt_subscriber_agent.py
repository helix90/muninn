"""
Tests for MQTT Subscriber Agent
"""

import pytest
from unittest.mock import MagicMock, patch

from app.extensions import db
from app.agents.types.mqtt_subscriber_agent import MqttSubscriberAgent
from app.agents.registry import agent_registry


@pytest.fixture
def test_job(app, test_user):
    """Create a test job for MQTT subscriber agent tests."""
    from app.models import Job

    with app.app_context():
        job = Job(
            name='Test MQTT Subscriber',
            job_type='mqtt_subscriber_agent',
            config={
                'host': 'localhost',
                'topic': 'test/#',
            },
            user_id=test_user.id
        )
        db.session.add(job)
        db.session.commit()
        yield job


def _make_mqtt_message(topic='test/sensor', payload=b'{"value": 42}', qos=0, retain=False):
    """Build a fake paho MQTT message object."""
    msg = MagicMock()
    msg.topic = topic
    msg.payload = payload
    msg.qos = qos
    msg.retain = retain
    return msg


def _make_agent(test_job, extra_config=None):
    """Convenience factory for MqttSubscriberAgent in tests."""
    config = {'host': 'localhost', 'topic': 'test/#'}
    if extra_config:
        config.update(extra_config)
    return MqttSubscriberAgent(
        agent_id=test_job.id,
        config=config,
        user_id=test_job.user_id,
        db_session=db.session,
    )


def _mock_fetch(agent, messages=None, connect_rc=0):
    """
    Patch _build_client so fetch() runs without a real broker.

    loop_start() synchronously triggers on_connect (with connect_rc) and
    optionally on_message for each item in messages.
    """
    mock_client = MagicMock()

    def fake_loop_start():
        mock_client.on_connect(mock_client, None, {}, connect_rc)
        for msg in (messages or []):
            mock_client.on_message(mock_client, None, msg)

    mock_client.loop_start.side_effect = fake_loop_start
    return mock_client


# ---------------------------------------------------------------------------
# Registration & capabilities
# ---------------------------------------------------------------------------

class TestMqttSubscriberAgentRegistration:

    def test_agent_is_registered(self):
        assert agent_registry.is_registered('mqtt_subscriber_agent')
        assert agent_registry.get_agent_class('mqtt_subscriber_agent') is MqttSubscriberAgent

    def test_agent_capabilities(self):
        assert MqttSubscriberAgent.can_be_scheduled is True
        assert MqttSubscriberAgent.can_receive_events is False
        assert MqttSubscriberAgent.can_create_events is True
        assert MqttSubscriberAgent.agent_type == 'mqtt_subscriber_agent'
        assert MqttSubscriberAgent.agent_category == 'source'


# ---------------------------------------------------------------------------
# Configuration validation
# ---------------------------------------------------------------------------

class TestMqttSubscriberAgentConfig:

    def test_valid_minimal_config(self, test_job):
        agent = _make_agent(test_job)
        assert agent.host == 'localhost'
        assert agent.topic == 'test/#'
        assert agent.port == 1883
        assert agent.qos == 0
        assert agent.poll_duration == 5
        assert agent.max_messages == 100
        assert agent.use_tls is False
        assert agent.message_format == 'json'

    def test_valid_full_config(self, test_job):
        agent = _make_agent(test_job, {
            'port': 8883,
            'username': 'user',
            'password': 'pass',
            'qos': 2,
            'poll_duration': 30,
            'max_messages': 500,
            'use_tls': True,
            'client_id': 'myapp',
            'message_format': 'text',
        })
        assert agent.port == 8883
        assert agent.username == 'user'
        assert agent.password == 'pass'
        assert agent.qos == 2
        assert agent.poll_duration == 30
        assert agent.max_messages == 500
        assert agent.use_tls is True
        assert agent.client_id == 'myapp'
        assert agent.message_format == 'text'

    def test_missing_host_raises(self):
        with pytest.raises(ValueError, match='host is required'):
            MqttSubscriberAgent(agent_id=1, config={'topic': 'test'}, user_id=1, db_session=None)

    def test_missing_topic_raises(self):
        with pytest.raises(ValueError, match='topic is required'):
            MqttSubscriberAgent(agent_id=1, config={'host': 'localhost'}, user_id=1, db_session=None)

    def test_invalid_port_raises(self):
        with pytest.raises(ValueError, match='port must be between'):
            MqttSubscriberAgent(agent_id=1,
                                config={'host': 'localhost', 'topic': 't', 'port': 99999},
                                user_id=1, db_session=None)

    def test_invalid_qos_raises(self):
        with pytest.raises(ValueError, match='qos must be'):
            MqttSubscriberAgent(agent_id=1,
                                config={'host': 'localhost', 'topic': 't', 'qos': 3},
                                user_id=1, db_session=None)

    def test_invalid_poll_duration_raises(self):
        with pytest.raises(ValueError, match='poll_duration must be'):
            MqttSubscriberAgent(agent_id=1,
                                config={'host': 'localhost', 'topic': 't', 'poll_duration': 0},
                                user_id=1, db_session=None)

    def test_poll_duration_upper_bound(self):
        with pytest.raises(ValueError, match='poll_duration must be'):
            MqttSubscriberAgent(agent_id=1,
                                config={'host': 'localhost', 'topic': 't', 'poll_duration': 301},
                                user_id=1, db_session=None)

    def test_invalid_message_format_raises(self):
        with pytest.raises(ValueError, match="message_format must be"):
            MqttSubscriberAgent(agent_id=1,
                                config={'host': 'localhost', 'topic': 't',
                                        'message_format': 'xml'},
                                user_id=1, db_session=None)

    def test_invalid_use_tls_raises(self):
        with pytest.raises(ValueError, match='use_tls must be a boolean'):
            MqttSubscriberAgent(agent_id=1,
                                config={'host': 'localhost', 'topic': 't', 'use_tls': 'yes'},
                                user_id=1, db_session=None)


# ---------------------------------------------------------------------------
# Message parsing (_message_to_event)
# ---------------------------------------------------------------------------

class TestMqttSubscriberMessageParsing:

    def test_parse_json_message(self, test_job):
        agent = _make_agent(test_job)
        msg = _make_mqtt_message(topic='sensors/1/temp', payload=b'{"temp": 22.5}')
        event = agent._message_to_event(msg)

        assert event is not None
        assert event.payload == {'temp': 22.5}
        assert event.event_metadata['topic'] == 'sensors/1/temp'
        assert event.event_metadata['broker'] == 'localhost'
        assert event.event_metadata['qos'] == 0
        assert event.event_metadata['retain'] is False

    def test_parse_json_scalar_wraps_in_dict(self, test_job):
        agent = _make_agent(test_job)
        msg = _make_mqtt_message(payload=b'42')
        event = agent._message_to_event(msg)

        assert event is not None
        assert event.payload == {'value': 42}

    def test_parse_json_array_wraps_in_dict(self, test_job):
        agent = _make_agent(test_job)
        msg = _make_mqtt_message(payload=b'[1, 2, 3]')
        event = agent._message_to_event(msg)

        assert event is not None
        assert event.payload == {'value': [1, 2, 3]}

    def test_invalid_json_returns_none(self, test_job):
        agent = _make_agent(test_job)
        msg = _make_mqtt_message(payload=b'not-json')
        event = agent._message_to_event(msg)

        assert event is None

    def test_parse_text_message(self, test_job):
        agent = _make_agent(test_job, {'message_format': 'text'})
        msg = _make_mqtt_message(payload=b'hello world')
        event = agent._message_to_event(msg)

        assert event is not None
        assert event.payload == {'body': 'hello world'}

    def test_text_mode_passes_non_json(self, test_job):
        agent = _make_agent(test_job, {'message_format': 'text'})
        msg = _make_mqtt_message(payload=b'plain text payload')
        event = agent._message_to_event(msg)

        assert event is not None
        assert 'body' in event.payload

    def test_retain_flag_stored_in_metadata(self, test_job):
        agent = _make_agent(test_job)
        msg = _make_mqtt_message(payload=b'{"x": 1}', retain=True)
        event = agent._message_to_event(msg)

        assert event is not None
        assert event.event_metadata['retain'] is True


# ---------------------------------------------------------------------------
# fetch() behaviour (broker interaction mocked via _build_client)
# ---------------------------------------------------------------------------

class TestMqttSubscriberAgentFetch:

    @patch('app.agents.types.mqtt_subscriber_agent.time.sleep')
    def test_fetch_returns_events_for_received_messages(self, mock_sleep, test_job):
        agent = _make_agent(test_job)
        messages = [
            _make_mqtt_message(topic='test/a', payload=b'{"v": 1}'),
            _make_mqtt_message(topic='test/b', payload=b'{"v": 2}'),
        ]
        mock_client = _mock_fetch(agent, messages=messages)

        with patch.object(agent, '_build_client', return_value=mock_client):
            events = agent.fetch()

        assert len(events) == 2
        assert events[0].payload == {'v': 1}
        assert events[1].payload == {'v': 2}

    @patch('app.agents.types.mqtt_subscriber_agent.time.sleep')
    def test_fetch_with_no_messages_returns_empty(self, mock_sleep, test_job):
        agent = _make_agent(test_job)
        mock_client = _mock_fetch(agent, messages=[])

        with patch.object(agent, '_build_client', return_value=mock_client):
            events = agent.fetch()

        assert events == []

    @patch('app.agents.types.mqtt_subscriber_agent.time.sleep')
    def test_fetch_respects_max_messages(self, mock_sleep, test_job):
        agent = _make_agent(test_job, {'max_messages': 2})
        messages = [_make_mqtt_message(payload=f'{{"i": {i}}}'.encode()) for i in range(10)]
        mock_client = _mock_fetch(agent, messages=messages)

        with patch.object(agent, '_build_client', return_value=mock_client):
            events = agent.fetch()

        assert len(events) == 2

    @patch('app.agents.types.mqtt_subscriber_agent.time.sleep')
    def test_fetch_skips_invalid_json_when_format_is_json(self, mock_sleep, test_job):
        agent = _make_agent(test_job)
        messages = [
            _make_mqtt_message(payload=b'{"good": true}'),
            _make_mqtt_message(payload=b'not-json'),
            _make_mqtt_message(payload=b'{"also": "good"}'),
        ]
        mock_client = _mock_fetch(agent, messages=messages)

        with patch.object(agent, '_build_client', return_value=mock_client):
            events = agent.fetch()

        assert len(events) == 2

    @patch('app.agents.types.mqtt_subscriber_agent.time.sleep')
    def test_fetch_subscribes_with_correct_topic_and_qos(self, mock_sleep, test_job):
        agent = _make_agent(test_job, {'topic': 'home/+/status', 'qos': 1})
        mock_client = _mock_fetch(agent)

        with patch.object(agent, '_build_client', return_value=mock_client):
            agent.fetch()

        mock_client.subscribe.assert_called_once_with('home/+/status', qos=1)

    @patch('app.agents.types.mqtt_subscriber_agent.time.sleep')
    def test_fetch_sets_credentials_when_username_provided(self, mock_sleep, test_job):
        agent = _make_agent(test_job, {'username': 'user', 'password': 'secret'})
        mock_client = _mock_fetch(agent)

        with patch.object(agent, '_build_client', return_value=mock_client):
            agent.fetch()

        mock_client.username_pw_set.assert_called_once_with('user', 'secret')

    @patch('app.agents.types.mqtt_subscriber_agent.time.sleep')
    def test_fetch_skips_credentials_when_no_username(self, mock_sleep, test_job):
        agent = _make_agent(test_job)
        mock_client = _mock_fetch(agent)

        with patch.object(agent, '_build_client', return_value=mock_client):
            agent.fetch()

        mock_client.username_pw_set.assert_not_called()

    @patch('app.agents.types.mqtt_subscriber_agent.time.sleep')
    def test_fetch_enables_tls_when_configured(self, mock_sleep, test_job):
        agent = _make_agent(test_job, {'use_tls': True, 'port': 8883})
        mock_client = _mock_fetch(agent)

        with patch.object(agent, '_build_client', return_value=mock_client):
            agent.fetch()

        mock_client.tls_set.assert_called_once()

    @patch('app.agents.types.mqtt_subscriber_agent.time.sleep')
    def test_fetch_updates_memory_after_run(self, mock_sleep, test_job):
        agent = _make_agent(test_job)
        mock_client = _mock_fetch(agent)

        with patch.object(agent, '_build_client', return_value=mock_client):
            agent.fetch()

        assert agent.memory.get('last_sync_at') is not None


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestMqttSubscriberAgentErrors:

    def test_connection_refused_returns_empty(self, test_job):
        agent = _make_agent(test_job)

        with patch.object(agent, '_build_client') as mock_build:
            mock_client = MagicMock()
            mock_client.connect.side_effect = ConnectionRefusedError('refused')
            mock_build.return_value = mock_client

            events = agent.fetch()

        assert events == []

    def test_hostname_resolution_failure_returns_empty(self, test_job):
        import socket
        agent = _make_agent(test_job)

        with patch.object(agent, '_build_client') as mock_build:
            mock_client = MagicMock()
            mock_client.connect.side_effect = socket.gaierror('name resolution failed')
            mock_build.return_value = mock_client

            events = agent.fetch()

        assert events == []

    def test_broker_refusing_connection_returns_empty(self, test_job):
        # on_connect called with rc != 0 (broker refused)
        agent = _make_agent(test_job)
        mock_client = _mock_fetch(agent, connect_rc=5)  # 5 = not authorised

        with patch.object(agent, '_build_client', return_value=mock_client):
            events = agent.fetch()

        assert events == []

    @patch('app.agents.types.mqtt_subscriber_agent.time.sleep')
    def test_unexpected_error_returns_empty(self, mock_sleep, test_job):
        agent = _make_agent(test_job)

        with patch.object(agent, '_build_client') as mock_build:
            mock_build.side_effect = RuntimeError('unexpected')
            events = agent.fetch()

        assert events == []


# ---------------------------------------------------------------------------
# Config schema
# ---------------------------------------------------------------------------

class TestMqttSubscriberAgentConfigSchema:

    def test_schema_required_fields(self):
        schema = MqttSubscriberAgent.get_config_schema()
        assert 'host' in schema['required_fields']
        assert 'topic' in schema['required_fields']

    def test_schema_optional_fields(self):
        schema = MqttSubscriberAgent.get_config_schema()
        field_names = [f['name'] for f in schema['optional_fields']]
        for expected in ('port', 'username', 'password', 'qos',
                         'poll_duration', 'max_messages', 'use_tls',
                         'client_id', 'message_format'):
            assert expected in field_names

    def test_schema_capabilities(self):
        schema = MqttSubscriberAgent.get_config_schema()
        caps = schema['capabilities']
        assert caps['can_be_scheduled'] is True
        assert caps['can_receive_events'] is False
        assert caps['can_create_events'] is True
