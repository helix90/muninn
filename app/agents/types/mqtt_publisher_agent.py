"""
MQTT Publisher Agent - Publish events to MQTT topics via a Mosquitto broker

For each incoming event, renders the topic and message body from Jinja2 templates
using the event's payload fields, then publishes to the configured broker.
"""

import socket
import logging
from typing import Any, Dict, List, Optional

from jinja2 import Environment, BaseLoader, TemplateError, UndefinedError
import paho.mqtt.client as mqtt

from app.agents.base import ActionAgent
from app.agents.registry import register_agent
from app.models import Event

logger = logging.getLogger(__name__)

# Support paho-mqtt 1.x and 2.x side-by-side
try:
    _CALLBACK_API_VERSION = mqtt.CallbackAPIVersion.VERSION1
except AttributeError:
    _CALLBACK_API_VERSION = None


@register_agent
class MqttPublisherAgent(ActionAgent):
    """
    Action agent that publishes events to MQTT topics.

    Connects to a Mosquitto (or compatible) MQTT broker and publishes one message
    per incoming event. The topic and message body are Jinja2 templates rendered
    with the event's payload fields. Supports QoS levels, retained messages,
    TLS, and username/password authentication.

    Configuration:
        host (str): MQTT broker hostname or IP address (required)
        topic_template (str): Jinja2 template for the publish topic (required)
        message_template (str): Jinja2 template for the message body (required)
        port (int): Broker port (default: 1883, or 8883 for TLS)
        username (str): MQTT username (optional)
        password (str): MQTT password; supports {{credential:*}} templating (optional)
        qos (int): Quality of Service level 0, 1, or 2 (default: 0)
        retain (bool): Publish with retain flag — broker stores last message (default: False)
        use_tls (bool): Enable TLS/SSL encryption (default: False)
        client_id (str): MQTT client identifier (auto-generated if empty)
    """

    agent_type = 'mqtt_publisher_agent'
    agent_category = 'action'

    def __init__(self, agent_id: int, config: Dict[str, Any], user_id: int, db_session=None):
        self.host = config.get('host', '')
        self.port = int(config.get('port', 1883))
        self.username = config.get('username', '')
        self.password = config.get('password', '')
        self.topic_template = config.get('topic_template', '')
        self.message_template = config.get('message_template', '')
        self.qos = int(config.get('qos', 0))
        self.retain = config.get('retain', False)
        self.use_tls = config.get('use_tls', False)
        self.client_id = config.get('client_id', '')

        super().__init__(agent_id, config, user_id, db_session)

    def validate_config(self) -> None:
        super().validate_config()

        if not self.host:
            raise ValueError("host is required")

        if not self.topic_template:
            raise ValueError("topic_template is required")

        if not self.message_template:
            raise ValueError("message_template is required")

        if not 1 <= self.port <= 65535:
            raise ValueError("port must be between 1 and 65535")

        if self.qos not in (0, 1, 2):
            raise ValueError("qos must be 0, 1, or 2")

        if not isinstance(self.retain, bool):
            raise ValueError("retain must be a boolean")

        if not isinstance(self.use_tls, bool):
            raise ValueError("use_tls must be a boolean")

        env = Environment(loader=BaseLoader())
        try:
            env.from_string(self.topic_template)
        except TemplateError as e:
            raise ValueError(f"Invalid topic_template: {e}")

        try:
            env.from_string(self.message_template)
        except TemplateError as e:
            raise ValueError(f"Invalid message_template: {e}")

    def act(self, events: List[Event]) -> None:
        """
        Publish one MQTT message per incoming event.

        Opens a single connection to the broker for the batch, publishes each
        event, then closes the connection.
        """
        client = None
        try:
            client = self._build_client()

            if self.username:
                client.username_pw_set(self.username, self.password or None)

            if self.use_tls:
                client.tls_set()

            client.connect(self.host, self.port, keepalive=60)
            client.loop_start()

            for event in events:
                try:
                    context = self._build_context(event)
                    topic = self._render_template(self.topic_template, context, 'topic_template')
                    message = self._render_template(self.message_template, context, 'message_template')

                    if topic is None or message is None:
                        self.log('Skipping event: template rendered empty result', level='warning')
                        continue

                    result = client.publish(topic, message, qos=self.qos, retain=self.retain)

                    if result.rc == mqtt.MQTT_ERR_SUCCESS:
                        self.log(f'Published to {topic}',
                                 data={'qos': self.qos, 'retain': self.retain})
                    else:
                        self.log(f'Publish failed for topic {topic} (rc={result.rc})',
                                 level='error')

                except UndefinedError as e:
                    self.log(f'Template variable missing: {e}', level='error')
                    continue
                except Exception as e:
                    self.log(f'Error publishing event: {e}', level='error')
                    continue

        except socket.gaierror as e:
            self.log(f'Cannot resolve hostname: {self.host}', level='error',
                     data={'error': str(e)})
        except ConnectionRefusedError as e:
            self.log(f'Connection refused at {self.host}:{self.port}', level='error',
                     data={'error': str(e)})
        except OSError as e:
            self.log(f'Network error connecting to {self.host}:{self.port}', level='error',
                     data={'error': str(e)})
        except Exception as e:
            self.log(f'Unexpected MQTT error: {e}', level='error', data={'error': str(e)})
        finally:
            if client:
                try:
                    client.loop_stop()
                    client.disconnect()
                except Exception:
                    pass

    def _build_client(self) -> mqtt.Client:
        """Create a paho MQTT client compatible with both paho-mqtt 1.x and 2.x."""
        client_id = self.client_id or f'muninn-pub-{self.agent_id}'
        if _CALLBACK_API_VERSION is not None:
            return mqtt.Client(
                callback_api_version=_CALLBACK_API_VERSION,
                client_id=client_id,
            )
        return mqtt.Client(client_id=client_id)

    def _build_context(self, event: Event) -> Dict[str, Any]:
        """Build Jinja2 template context from event payload and metadata."""
        context = {}
        if event.payload:
            context.update(event.payload)
        if event.metadata:
            context['metadata'] = event.metadata
        context['event_id'] = event.id
        context['event_created_at'] = event.created_at.isoformat() if event.created_at else None
        return context

    def _render_template(self, template_str: str, context: Dict[str, Any],
                         field_name: str) -> Optional[str]:
        """Render a Jinja2 template string with event context."""
        try:
            env = Environment(loader=BaseLoader())
            template = env.from_string(template_str)
            rendered = template.render(**context)
            return rendered if rendered.strip() else None
        except UndefinedError:
            raise
        except TemplateError as e:
            self.log(f'Template error in {field_name}: {e}', level='error')
            return None
        except Exception as e:
            self.log(f'Unexpected error rendering {field_name}: {e}', level='error')
            return None

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        schema = super().get_config_schema()
        schema['required_fields'] = ['host', 'topic_template', 'message_template']
        schema['optional_fields'].extend([
            {
                'name': 'host',
                'type': 'text',
                'description': 'MQTT broker hostname or IP address'
            },
            {
                'name': 'topic_template',
                'type': 'text',
                'description': (
                    'Jinja2 template for the MQTT topic. Use a literal string for a fixed topic '
                    'or reference event fields for dynamic routing. '
                    'Example: sensors/{{ sensor_id }}/data'
                )
            },
            {
                'name': 'message_template',
                'type': 'textarea',
                'description': (
                    'Jinja2 template for the message body. Event payload fields are available '
                    'as template variables. '
                    'Example: {"temperature": {{ temp }}, "unit": "celsius"}'
                )
            },
            {
                'name': 'port',
                'type': 'integer',
                'default': 1883,
                'description': 'Broker port (1883 standard, 8883 for TLS)'
            },
            {
                'name': 'username',
                'type': 'text',
                'default': '',
                'description': 'MQTT username (optional)'
            },
            {
                'name': 'password',
                'type': 'password',
                'default': '',
                'description': 'MQTT password. Supports {{credential:mqtt_password}}'
            },
            {
                'name': 'qos',
                'type': 'integer',
                'default': 0,
                'description': 'Quality of Service: 0 = at most once, 1 = at least once, 2 = exactly once'
            },
            {
                'name': 'retain',
                'type': 'boolean',
                'default': False,
                'description': 'Publish with retain flag — the broker stores this as the last known value for the topic'
            },
            {
                'name': 'use_tls',
                'type': 'boolean',
                'default': False,
                'description': 'Enable TLS/SSL encryption (set port to 8883 when enabled)'
            },
            {
                'name': 'client_id',
                'type': 'text',
                'default': '',
                'description': 'MQTT client identifier (auto-generated as muninn-pub-{id} if empty)'
            },
        ])
        return schema

    def __repr__(self):
        return f'<MqttPublisherAgent {self.agent_id}: {self.topic_template}@{self.host}:{self.port}>'
