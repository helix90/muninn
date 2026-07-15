"""
MQTT Subscriber Agent - Subscribe to MQTT topics and create events from messages

Connects to a Mosquitto (or compatible) MQTT broker on a schedule, subscribes to the
configured topic(s), and collects messages during a configurable poll window.
"""

import json
import socket
import threading
import time
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import paho.mqtt.client as mqtt

from app.agents.base import SourceAgent
from app.agents.registry import register_agent
from app.models import Event

logger = logging.getLogger(__name__)

# Support paho-mqtt 1.x and 2.x side-by-side
try:
    _CALLBACK_API_VERSION = mqtt.CallbackAPIVersion.VERSION1
except AttributeError:
    _CALLBACK_API_VERSION = None


@register_agent
class MqttSubscriberAgent(SourceAgent):
    """
    Source agent that subscribes to MQTT topics and creates events from received messages.

    Connects to a Mosquitto (or compatible) MQTT broker, subscribes to the configured
    topic(s), and polls for messages during a configurable window. Supports JSON and
    plain-text payloads, QoS levels 0-2, TLS, and username/password authentication.

    Configuration:
        host (str): MQTT broker hostname or IP address (required)
        topic (str): MQTT topic to subscribe to; supports wildcards + and # (required)
        port (int): Broker port (default: 1883, or 8883 for TLS)
        username (str): MQTT username (optional)
        password (str): MQTT password; supports {{credential:*}} templating (optional)
        qos (int): Quality of Service level 0, 1, or 2 (default: 0)
        poll_duration (int): Seconds to listen for messages per run (default: 5, max: 300)
        max_messages (int): Maximum messages to collect per run (default: 100)
        use_tls (bool): Enable TLS/SSL encryption (default: False)
        client_id (str): MQTT client identifier (auto-generated if empty)
        message_format (str): 'json' or 'text' (default: 'json')
    """

    agent_type = 'mqtt_subscriber_agent'
    agent_category = 'source'

    def __init__(self, agent_id: int, config: Dict[str, Any], user_id: int, db_session=None):
        self.host = config.get('host', '')
        self.port = int(config.get('port', 1883))
        self.username = config.get('username', '')
        self.password = config.get('password', '')
        self.topic = config.get('topic', '')
        self.qos = int(config.get('qos', 0))
        self.poll_duration = int(config.get('poll_duration', 5))
        self.max_messages = int(config.get('max_messages', 100))
        self.use_tls = config.get('use_tls', False)
        self.client_id = config.get('client_id', '')
        self.message_format = config.get('message_format', 'json')

        super().__init__(agent_id, config, user_id, db_session)

    def validate_config(self) -> None:
        super().validate_config()

        if not self.host:
            raise ValueError("host is required")

        if not self.topic:
            raise ValueError("topic is required")

        if not 1 <= self.port <= 65535:
            raise ValueError("port must be between 1 and 65535")

        if self.qos not in (0, 1, 2):
            raise ValueError("qos must be 0, 1, or 2")

        if not 1 <= self.poll_duration <= 300:
            raise ValueError("poll_duration must be between 1 and 300")

        if not 1 <= self.max_messages <= 10000:
            raise ValueError("max_messages must be between 1 and 10000")

        if not isinstance(self.use_tls, bool):
            raise ValueError("use_tls must be a boolean")

        if self.message_format not in ('json', 'text'):
            raise ValueError("message_format must be 'json' or 'text'")

    def fetch(self) -> List[Event]:
        """
        Connect to the MQTT broker, subscribe to the topic, collect messages
        for poll_duration seconds, then disconnect and return events.
        """
        collected = []
        connected_event = threading.Event()
        error_holder = [None]

        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                client.subscribe(self.topic, qos=self.qos)
                connected_event.set()
            else:
                error_holder[0] = f'Broker refused connection (rc={rc})'
                connected_event.set()

        def on_message(client, userdata, msg):
            if len(collected) < self.max_messages:
                collected.append(msg)

        client = None
        try:
            client = self._build_client()
            client.on_connect = on_connect
            client.on_message = on_message

            if self.username:
                client.username_pw_set(self.username, self.password or None)

            if self.use_tls:
                client.tls_set()

            client.connect(self.host, self.port, keepalive=60)
            client.loop_start()

            if not connected_event.wait(timeout=10):
                self.log('Timed out waiting for MQTT connection', level='error',
                         data={'host': self.host, 'port': self.port})
                client.loop_stop()
                client.disconnect()
                return []

            if error_holder[0]:
                self.log(f'MQTT connection failed: {error_holder[0]}', level='error')
                client.loop_stop()
                client.disconnect()
                return []

            time.sleep(self.poll_duration)

            client.loop_stop()
            client.disconnect()

        except socket.gaierror as e:
            self.log(f'Cannot resolve hostname: {self.host}', level='error',
                     data={'error': str(e)})
            return []
        except ConnectionRefusedError as e:
            self.log(f'Connection refused at {self.host}:{self.port}', level='error',
                     data={'error': str(e)})
            return []
        except OSError as e:
            self.log(f'Network error connecting to {self.host}:{self.port}', level='error',
                     data={'error': str(e)})
            return []
        except Exception as e:
            self.log(f'Unexpected MQTT error: {e}', level='error', data={'error': str(e)})
            return []
        finally:
            if client:
                try:
                    client.loop_stop()
                    client.disconnect()
                except Exception:
                    pass

        events = []
        for msg in collected:
            try:
                event = self._message_to_event(msg)
                if event is not None:
                    events.append(event)
            except Exception as e:
                self.log(f'Error processing message on topic {msg.topic}: {e}', level='error')
                continue

        self.memory.set('last_sync_at', datetime.utcnow().isoformat())
        total = self.memory.get('total_messages_received', 0)
        self.memory.set('total_messages_received', total + len(events))

        if events:
            self.log(f'Collected {len(events)} message(s) from topic {self.topic}',
                     data={'count': len(events), 'broker': self.host})

        return events

    def _build_client(self) -> mqtt.Client:
        """Create a paho MQTT client compatible with both paho-mqtt 1.x and 2.x."""
        client_id = self.client_id or f'muninn-sub-{self.agent_id}'
        if _CALLBACK_API_VERSION is not None:
            return mqtt.Client(
                callback_api_version=_CALLBACK_API_VERSION,
                client_id=client_id,
            )
        return mqtt.Client(client_id=client_id)

    def _message_to_event(self, msg) -> Optional[Event]:
        """Convert a paho MQTT message object into a Muninn Event."""
        payload_str = msg.payload.decode('utf-8', errors='replace')

        if self.message_format == 'json':
            try:
                payload_data = json.loads(payload_str)
                if not isinstance(payload_data, dict):
                    payload_data = {'value': payload_data}
            except json.JSONDecodeError:
                self.log(
                    f'Skipping non-JSON message on topic {msg.topic}',
                    level='warning',
                    data={'raw': payload_str[:200]}
                )
                return None
        else:
            payload_data = {'body': payload_str}

        return self.create_event(
            payload=payload_data,
            metadata={
                'topic': msg.topic,
                'qos': msg.qos,
                'retain': bool(msg.retain),
                'broker': self.host,
                'received_at': datetime.utcnow().isoformat(),
            }
        )

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        schema = super().get_config_schema()
        schema['required_fields'] = ['host', 'topic']
        schema['optional_fields'].extend([
            {
                'name': 'host',
                'type': 'text',
                'description': 'MQTT broker hostname or IP address (e.g., localhost, 192.168.1.10)'
            },
            {
                'name': 'topic',
                'type': 'text',
                'description': (
                    'MQTT topic to subscribe to. Supports wildcards: '
                    '+ (single level), # (multi-level). '
                    'Examples: sensors/+/temperature, home/#, alerts'
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
                'description': 'MQTT username (optional; leave empty for anonymous access)'
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
                'name': 'poll_duration',
                'type': 'integer',
                'default': 5,
                'description': 'Seconds to listen for messages per scheduled run (1-300)'
            },
            {
                'name': 'max_messages',
                'type': 'integer',
                'default': 100,
                'description': 'Maximum messages to collect per run (1-10000)'
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
                'description': 'MQTT client identifier (auto-generated as muninn-sub-{id} if empty)'
            },
            {
                'name': 'message_format',
                'type': 'select',
                'default': 'json',
                'options': ['json', 'text'],
                'description': (
                    "Payload format: 'json' parses as JSON object (non-JSON messages are skipped); "
                    "'text' wraps raw payload in {\"body\": \"...\"}"
                )
            },
        ])
        return schema

    def __repr__(self):
        return f'<MqttSubscriberAgent {self.agent_id}: {self.topic}@{self.host}:{self.port}>'
