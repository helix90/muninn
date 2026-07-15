"""
Tests for MQTT Publisher Agent
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

import paho.mqtt.client as mqtt

from app.extensions import db
from app.agents.types.mqtt_publisher_agent import MqttPublisherAgent
from app.agents.registry import agent_registry


@pytest.fixture
def test_job(app, test_user):
    """Create a test job for MQTT publisher agent tests."""
    from app.models import Job

    with app.app_context():
        job = Job(
            name='Test MQTT Publisher',
            job_type='mqtt_publisher_agent',
            config={
                'host': 'localhost',
                'topic_template': 'sensors/data',
                'message_template': '{"value": {{ value }}}',
            },
            user_id=test_user.id
        )
        db.session.add(job)
        db.session.commit()
        yield job


def _make_event(payload=None, metadata=None):
    """Build a fake Event object for act() testing."""
    event = MagicMock()
    event.id = 1
    event.payload = payload or {'value': 42}
    event.metadata = metadata or {}
    event.created_at = datetime(2026, 4, 27, 12, 0, 0)
    return event


def _make_agent(test_job, extra_config=None):
    config = {
        'host': 'localhost',
        'topic_template': 'sensors/data',
        'message_template': '{"value": {{ value }}}',
    }
    if extra_config:
        config.update(extra_config)
    return MqttPublisherAgent(
        agent_id=test_job.id,
        config=config,
        user_id=test_job.user_id,
        db_session=db.session,
    )


def _mock_client():
    """Return a MagicMock client with a successful publish result."""
    mock_client = MagicMock()
    mock_result = MagicMock()
    mock_result.rc = mqtt.MQTT_ERR_SUCCESS
    mock_client.publish.return_value = mock_result
    return mock_client


# ---------------------------------------------------------------------------
# Registration & capabilities
# ---------------------------------------------------------------------------

class TestMqttPublisherAgentRegistration:

    def test_agent_is_registered(self):
        assert agent_registry.is_registered('mqtt_publisher_agent')
        assert agent_registry.get_agent_class('mqtt_publisher_agent') is MqttPublisherAgent

    def test_agent_capabilities(self):
        assert MqttPublisherAgent.can_be_scheduled is False
        assert MqttPublisherAgent.can_receive_events is True
        assert MqttPublisherAgent.can_create_events is False
        assert MqttPublisherAgent.agent_type == 'mqtt_publisher_agent'
        assert MqttPublisherAgent.agent_category == 'action'


# ---------------------------------------------------------------------------
# Configuration validation
# ---------------------------------------------------------------------------

class TestMqttPublisherAgentConfig:

    def test_valid_minimal_config(self, test_job):
        agent = _make_agent(test_job)
        assert agent.host == 'localhost'
        assert agent.topic_template == 'sensors/data'
        assert agent.message_template == '{"value": {{ value }}}'
        assert agent.port == 1883
        assert agent.qos == 0
        assert agent.retain is False
        assert agent.use_tls is False

    def test_valid_full_config(self, test_job):
        agent = _make_agent(test_job, {
            'port': 8883,
            'username': 'user',
            'password': 'secret',
            'qos': 1,
            'retain': True,
            'use_tls': True,
            'client_id': 'myapp',
        })
        assert agent.port == 8883
        assert agent.username == 'user'
        assert agent.password == 'secret'
        assert agent.qos == 1
        assert agent.retain is True
        assert agent.use_tls is True
        assert agent.client_id == 'myapp'

    def test_missing_host_raises(self):
        with pytest.raises(ValueError, match='host is required'):
            MqttPublisherAgent(agent_id=1,
                               config={'topic_template': 't', 'message_template': 'm'},
                               user_id=1, db_session=None)

    def test_missing_topic_template_raises(self):
        with pytest.raises(ValueError, match='topic_template is required'):
            MqttPublisherAgent(agent_id=1,
                               config={'host': 'localhost', 'message_template': 'm'},
                               user_id=1, db_session=None)

    def test_missing_message_template_raises(self):
        with pytest.raises(ValueError, match='message_template is required'):
            MqttPublisherAgent(agent_id=1,
                               config={'host': 'localhost', 'topic_template': 't'},
                               user_id=1, db_session=None)

    def test_invalid_port_raises(self):
        with pytest.raises(ValueError, match='port must be between'):
            MqttPublisherAgent(agent_id=1,
                               config={'host': 'localhost', 'topic_template': 't',
                                       'message_template': 'm', 'port': 0},
                               user_id=1, db_session=None)

    def test_invalid_qos_raises(self):
        with pytest.raises(ValueError, match='qos must be'):
            MqttPublisherAgent(agent_id=1,
                               config={'host': 'localhost', 'topic_template': 't',
                                       'message_template': 'm', 'qos': 5},
                               user_id=1, db_session=None)

    def test_invalid_retain_raises(self):
        with pytest.raises(ValueError, match='retain must be a boolean'):
            MqttPublisherAgent(agent_id=1,
                               config={'host': 'localhost', 'topic_template': 't',
                                       'message_template': 'm', 'retain': 'yes'},
                               user_id=1, db_session=None)

    def test_invalid_topic_template_raises(self):
        with pytest.raises(ValueError, match='Invalid topic_template'):
            MqttPublisherAgent(agent_id=1,
                               config={'host': 'localhost',
                                       'topic_template': '{% invalid %}',
                                       'message_template': 'ok'},
                               user_id=1, db_session=None)

    def test_invalid_message_template_raises(self):
        with pytest.raises(ValueError, match='Invalid message_template'):
            MqttPublisherAgent(agent_id=1,
                               config={'host': 'localhost',
                                       'topic_template': 'ok',
                                       'message_template': '{% broken'},
                               user_id=1, db_session=None)


# ---------------------------------------------------------------------------
# act() behaviour
# ---------------------------------------------------------------------------

class TestMqttPublisherAgentAct:

    def test_act_publishes_one_message_per_event(self, test_job):
        agent = _make_agent(test_job)
        events = [_make_event({'value': 10}), _make_event({'value': 20})]
        mock_client = _mock_client()

        with patch.object(agent, '_build_client', return_value=mock_client):
            agent.act(events)

        assert mock_client.publish.call_count == 2

    def test_act_renders_static_topic(self, test_job):
        agent = _make_agent(test_job, {'topic_template': 'my/fixed/topic'})
        events = [_make_event({'value': 1})]
        mock_client = _mock_client()

        with patch.object(agent, '_build_client', return_value=mock_client):
            agent.act(events)

        call_args = mock_client.publish.call_args
        assert call_args[0][0] == 'my/fixed/topic'

    def test_act_renders_dynamic_topic(self, test_job):
        agent = _make_agent(test_job, {'topic_template': 'sensors/{{ sensor_id }}/data'})
        events = [_make_event({'value': 1, 'sensor_id': 'abc123'})]
        mock_client = _mock_client()

        with patch.object(agent, '_build_client', return_value=mock_client):
            agent.act(events)

        call_args = mock_client.publish.call_args
        assert call_args[0][0] == 'sensors/abc123/data'

    def test_act_renders_message_with_event_payload(self, test_job):
        agent = _make_agent(test_job, {'message_template': 'temp={{ temp }}'})
        events = [_make_event({'value': 1, 'temp': 22.5})]
        mock_client = _mock_client()

        with patch.object(agent, '_build_client', return_value=mock_client):
            agent.act(events)

        call_args = mock_client.publish.call_args
        assert call_args[0][1] == 'temp=22.5'

    def test_act_passes_qos_and_retain(self, test_job):
        agent = _make_agent(test_job, {'qos': 2, 'retain': True})
        events = [_make_event()]
        mock_client = _mock_client()

        with patch.object(agent, '_build_client', return_value=mock_client):
            agent.act(events)

        call_kwargs = mock_client.publish.call_args[1]
        assert call_kwargs['qos'] == 2
        assert call_kwargs['retain'] is True

    def test_act_sets_credentials_when_username_provided(self, test_job):
        agent = _make_agent(test_job, {'username': 'user', 'password': 'pass'})
        events = [_make_event()]
        mock_client = _mock_client()

        with patch.object(agent, '_build_client', return_value=mock_client):
            agent.act(events)

        mock_client.username_pw_set.assert_called_once_with('user', 'pass')

    def test_act_skips_credentials_when_no_username(self, test_job):
        agent = _make_agent(test_job)
        events = [_make_event()]
        mock_client = _mock_client()

        with patch.object(agent, '_build_client', return_value=mock_client):
            agent.act(events)

        mock_client.username_pw_set.assert_not_called()

    def test_act_enables_tls_when_configured(self, test_job):
        agent = _make_agent(test_job, {'use_tls': True, 'port': 8883})
        events = [_make_event()]
        mock_client = _mock_client()

        with patch.object(agent, '_build_client', return_value=mock_client):
            agent.act(events)

        mock_client.tls_set.assert_called_once()

    def test_act_skips_event_when_template_variable_undefined(self, test_job):
        # message_template references {{ missing_field }} — event lacks it
        agent = _make_agent(test_job, {
            'topic_template': 'test/topic',
            'message_template': '{{ missing_field }}',
        })
        events = [_make_event({'value': 1})]  # no 'missing_field' key
        mock_client = _mock_client()

        with patch.object(agent, '_build_client', return_value=mock_client):
            agent.act(events)

        # Publish should not be called for events with undefined template vars
        mock_client.publish.assert_not_called()

    def test_act_continues_after_per_event_error(self, test_job):
        # First publish fails, second succeeds
        agent = _make_agent(test_job)
        events = [_make_event({'value': 1}), _make_event({'value': 2})]

        mock_client = MagicMock()
        fail_result = MagicMock()
        fail_result.rc = 1  # failure
        ok_result = MagicMock()
        ok_result.rc = mqtt.MQTT_ERR_SUCCESS
        mock_client.publish.side_effect = [fail_result, ok_result]

        with patch.object(agent, '_build_client', return_value=mock_client):
            # Should not raise
            agent.act(events)

        assert mock_client.publish.call_count == 2

    def test_act_always_disconnects_on_success(self, test_job):
        agent = _make_agent(test_job)
        events = [_make_event()]
        mock_client = _mock_client()

        with patch.object(agent, '_build_client', return_value=mock_client):
            agent.act(events)

        mock_client.loop_stop.assert_called()
        mock_client.disconnect.assert_called()

    def test_act_always_disconnects_on_connection_error(self, test_job):
        agent = _make_agent(test_job)
        mock_client = MagicMock()
        mock_client.connect.side_effect = ConnectionRefusedError('refused')

        with patch.object(agent, '_build_client', return_value=mock_client):
            agent.act([_make_event()])  # must not raise

        mock_client.loop_stop.assert_called()
        mock_client.disconnect.assert_called()


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestMqttPublisherAgentErrors:

    def test_connection_refused_does_not_raise(self, test_job):
        agent = _make_agent(test_job)
        mock_client = MagicMock()
        mock_client.connect.side_effect = ConnectionRefusedError('refused')

        with patch.object(agent, '_build_client', return_value=mock_client):
            agent.act([_make_event()])  # should not raise

    def test_hostname_resolution_failure_does_not_raise(self, test_job):
        import socket
        agent = _make_agent(test_job)
        mock_client = MagicMock()
        mock_client.connect.side_effect = socket.gaierror('resolution failed')

        with patch.object(agent, '_build_client', return_value=mock_client):
            agent.act([_make_event()])  # should not raise

    def test_unexpected_error_does_not_raise(self, test_job):
        agent = _make_agent(test_job)

        with patch.object(agent, '_build_client', side_effect=RuntimeError('boom')):
            agent.act([_make_event()])  # should not raise


# ---------------------------------------------------------------------------
# Template rendering (_render_template / _build_context)
# ---------------------------------------------------------------------------

class TestMqttPublisherTemplateRendering:

    def test_build_context_includes_payload_fields(self, test_job):
        agent = _make_agent(test_job)
        event = _make_event({'temperature': 25, 'humidity': 60})
        ctx = agent._build_context(event)
        assert ctx['temperature'] == 25
        assert ctx['humidity'] == 60

    def test_build_context_includes_metadata(self, test_job):
        agent = _make_agent(test_job)
        event = _make_event(metadata={'source': 'sensor_a'})
        ctx = agent._build_context(event)
        assert ctx['metadata']['source'] == 'sensor_a'

    def test_build_context_includes_event_id(self, test_job):
        agent = _make_agent(test_job)
        event = _make_event()
        event.id = 99
        ctx = agent._build_context(event)
        assert ctx['event_id'] == 99

    def test_render_template_literal_string(self, test_job):
        agent = _make_agent(test_job)
        result = agent._render_template('hello world', {}, 'test')
        assert result == 'hello world'

    def test_render_template_with_variable(self, test_job):
        agent = _make_agent(test_job)
        result = agent._render_template('v={{ val }}', {'val': 7}, 'test')
        assert result == 'v=7'

    def test_render_template_empty_result_returns_none(self, test_job):
        agent = _make_agent(test_job)
        result = agent._render_template('   ', {}, 'test')
        assert result is None


# ---------------------------------------------------------------------------
# Config schema
# ---------------------------------------------------------------------------

class TestMqttPublisherAgentConfigSchema:

    def test_schema_required_fields(self):
        schema = MqttPublisherAgent.get_config_schema()
        assert 'host' in schema['required_fields']
        assert 'topic_template' in schema['required_fields']
        assert 'message_template' in schema['required_fields']

    def test_schema_optional_fields(self):
        schema = MqttPublisherAgent.get_config_schema()
        field_names = [f['name'] for f in schema['optional_fields']]
        for expected in ('port', 'username', 'password', 'qos',
                         'retain', 'use_tls', 'client_id'):
            assert expected in field_names

    def test_schema_capabilities(self):
        schema = MqttPublisherAgent.get_config_schema()
        caps = schema['capabilities']
        assert caps['can_be_scheduled'] is False
        assert caps['can_receive_events'] is True
        assert caps['can_create_events'] is False
