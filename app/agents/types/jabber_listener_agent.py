"""
Jabber Listener Agent - Receive XMPP messages

Source agent that listens for incoming XMPP/Jabber messages and creates events.
Supports direct messages (one-on-one) and Multi-User Chat (MUC) rooms.

Requires: slixmpp library (pip install slixmpp)
"""

import asyncio
import logging
import threading
import time
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.agents.base import SourceAgent
from app.agents.registry import register_agent
from app.models import Event

# Try to import slixmpp
try:
    import slixmpp
    XMPP_AVAILABLE = True
except ImportError:
    XMPP_AVAILABLE = False


logger = logging.getLogger(__name__)


@register_agent
class JabberListenerAgent(SourceAgent):
    """
    Listens for incoming XMPP/Jabber messages and creates events.

    Source agent that maintains a persistent XMPP connection and emits events
    for each received message. Supports direct messages and group chat rooms (MUC).

    Configuration:
        jid (str): Jabber ID (username@domain)
        password (str): XMPP account password
        listen_mode (str): 'direct', 'rooms', or 'both' (default: 'both')
        rooms (list, optional): List of room JIDs to join (e.g., ['room@conference.server'])
        room_nickname (str, optional): Nickname to use in rooms (default: agent name)
        ignore_self (bool): Ignore messages from self (default: True)
        ignore_jids (list, optional): List of JIDs to ignore
        server (str, optional): XMPP server hostname (if different from JID domain)
        port (int, optional): XMPP server port (default: 5222)
        use_tls (bool): Use TLS encryption (default: True)
        message_history_limit (int): Max messages to fetch from room history (default: 0)
    """

    agent_type = 'jabber_listener_agent'
    agent_category = 'source'

    def __init__(self, agent_id: int, config: Dict[str, Any], user_id: int, db_session=None):
        """Initialize the Jabber listener agent."""
        # Initialize XMPP client state
        self._xmpp_client = None
        self._xmpp_thread = None
        self._xmpp_loop = None
        self._stop_event = threading.Event()
        self._message_queue = []
        self._queue_lock = threading.Lock()

        super().__init__(agent_id, config, user_id, db_session)

    def validate_config(self) -> None:
        """Validate Jabber listener configuration."""
        super().validate_config()

        # Check if slixmpp is available
        if not XMPP_AVAILABLE:
            raise ValueError(
                "Jabber listener agent requires 'slixmpp' library. "
                "Install with: pip install slixmpp"
            )

        # Required JID
        if 'jid' not in self.config:
            raise ValueError("Jabber listener requires 'jid' in config")
        if not isinstance(self.config['jid'], str):
            raise ValueError("'jid' must be a string")

        # Required password
        if 'password' not in self.config:
            raise ValueError("Jabber listener requires 'password' in config")
        if not isinstance(self.config['password'], str):
            raise ValueError("'password' must be a string")

        # Listen mode
        listen_mode = self.config.get('listen_mode', 'both')
        if listen_mode not in ['direct', 'rooms', 'both']:
            raise ValueError("'listen_mode' must be 'direct', 'rooms', or 'both'")

        # Rooms list (if listening to rooms)
        if listen_mode in ['rooms', 'both']:
            rooms = self.config.get('rooms', [])
            if not isinstance(rooms, list):
                raise ValueError("'rooms' must be a list of room JIDs")
            if listen_mode == 'rooms' and not rooms:
                raise ValueError("'rooms' list cannot be empty when listen_mode is 'rooms'")

        # Optional ignore_jids
        if 'ignore_jids' in self.config:
            if not isinstance(self.config['ignore_jids'], list):
                raise ValueError("'ignore_jids' must be a list")

        # Optional port
        if 'port' in self.config:
            port = self.config['port']
            if not isinstance(port, int) or port <= 0 or port > 65535:
                raise ValueError("'port' must be a valid port number (1-65535)")

        # Optional use_tls
        if 'use_tls' in self.config:
            if not isinstance(self.config['use_tls'], bool):
                raise ValueError("'use_tls' must be a boolean")

        # Optional message_history_limit
        if 'message_history_limit' in self.config:
            limit = self.config['message_history_limit']
            if not isinstance(limit, int) or limit < 0:
                raise ValueError("'message_history_limit' must be a non-negative integer")

    def fetch(self) -> List[Event]:
        """
        Fetch received messages from the XMPP connection.

        This method is called periodically by the scheduler. It:
        1. Ensures the XMPP client is running
        2. Collects any messages received since last check
        3. Creates events from those messages

        Returns:
            List of events from received messages
        """
        # Ensure XMPP client is running
        self._ensure_client_running()

        # Collect messages from queue
        messages = []
        with self._queue_lock:
            messages = self._message_queue.copy()
            self._message_queue.clear()

        if not messages:
            self.log('No new messages', level='debug')
            return []

        # Create events from messages
        events = []
        for msg_data in messages:
            event = self.create_event(
                payload=msg_data['payload'],
                metadata=msg_data['metadata']
            )
            events.append(event)

        self.log(f'Fetched {len(events)} messages', data={
            'message_count': len(events)
        })

        return events

    def _ensure_client_running(self) -> None:
        """Ensure the XMPP client thread is running."""
        # Check if thread exists and is alive
        if self._xmpp_thread and self._xmpp_thread.is_alive():
            return

        # Start new client thread
        self.log('Starting XMPP listener thread', level='info')
        self._stop_event.clear()
        self._xmpp_thread = threading.Thread(
            target=self._run_xmpp_client,
            daemon=True,
            name=f'JabberListener-{self.agent_id}'
        )
        self._xmpp_thread.start()

    def _run_xmpp_client(self) -> None:
        """Run the XMPP client in a separate thread."""
        try:
            # Create new event loop for this thread
            self._xmpp_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._xmpp_loop)

            # Create XMPP client
            jid = self.config['jid']
            password = self.config['password']

            self._xmpp_client = XMPPListener(
                jid=jid,
                password=password,
                config=self.config,
                message_callback=self._handle_message,
                log_callback=self._log_from_client
            )

            # Configure connection
            server = self.config.get('server')
            port = self.config.get('port', 5222)

            # SSL context for self-signed certs
            import ssl
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            self._xmpp_client.ssl_context = ssl_context

            # Disable IPv6 if causing issues
            self._xmpp_client.use_ipv6 = False

            # Connect
            self.log(f'Connecting to XMPP server', level='info', data={
                'jid': jid,
                'server': server or 'DNS SRV lookup',
                'port': port
            })

            if server:
                self._xmpp_client.connect((server, port), use_ssl=False, force_starttls=True)
            else:
                self._xmpp_client.connect(use_ssl=False, force_starttls=True)

            # Process until stop event is set
            while not self._stop_event.is_set():
                self._xmpp_client.process(timeout=1)

            # Disconnect
            self.log('Disconnecting XMPP client', level='info')
            self._xmpp_client.disconnect()

        except Exception as e:
            self.log(f'XMPP client error: {e}', level='error')
        finally:
            # Clean up event loop
            try:
                pending = asyncio.all_tasks(self._xmpp_loop)
                for task in pending:
                    task.cancel()
                if pending:
                    self._xmpp_loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                if self._xmpp_loop.is_running():
                    self._xmpp_loop.stop()
                self._xmpp_loop.close()
            except Exception:
                pass

    def _handle_message(self, msg_data: Dict[str, Any]) -> None:
        """
        Handle incoming message from XMPP client.

        Called by XMPPListener when a message is received.
        Adds message to queue for processing by fetch().

        Args:
            msg_data: Message data dict with 'payload' and 'metadata'
        """
        with self._queue_lock:
            self._message_queue.append(msg_data)

    def _log_from_client(self, message: str, level: str = 'info', data: Optional[Dict] = None) -> None:
        """Log callback for XMPP client."""
        self.log(message, level=level, data=data)

    def stop(self) -> None:
        """Stop the XMPP listener."""
        self.log('Stopping XMPP listener', level='info')
        self._stop_event.set()

        # Wait for thread to finish (with timeout)
        if self._xmpp_thread and self._xmpp_thread.is_alive():
            self._xmpp_thread.join(timeout=5)

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """Get configuration schema for Jabber listener."""
        schema = super().get_config_schema()
        schema['required_fields'] = ['jid', 'password']
        schema['optional_fields'] = [
            {
                'name': 'listen_mode',
                'type': 'select',
                'options': [
                    {'value': 'both', 'label': 'Both (Direct + Rooms)'},
                    {'value': 'direct', 'label': 'Direct Messages Only'},
                    {'value': 'rooms', 'label': 'Rooms Only'}
                ],
                'default': 'both',
                'description': 'What type of messages to listen for'
            },
            {
                'name': 'rooms',
                'type': 'textarea',
                'default': '[]',
                'description': 'List of room JIDs to join (JSON array). Example: ["room@conference.server"]'
            },
            {
                'name': 'room_nickname',
                'type': 'text',
                'description': 'Nickname to use in group chat rooms'
            },
            {
                'name': 'ignore_self',
                'type': 'boolean',
                'default': True,
                'description': 'Ignore messages from self'
            },
            {
                'name': 'ignore_jids',
                'type': 'textarea',
                'default': '[]',
                'description': 'List of JIDs to ignore (JSON array). Example: ["bot@server", "spam@server"]'
            },
            {
                'name': 'server',
                'type': 'text',
                'description': 'XMPP server hostname (if different from JID domain)'
            },
            {
                'name': 'port',
                'type': 'integer',
                'default': 5222,
                'description': 'XMPP server port'
            },
            {
                'name': 'use_tls',
                'type': 'boolean',
                'default': True,
                'description': 'Use TLS encryption'
            },
            {
                'name': 'message_history_limit',
                'type': 'integer',
                'default': 0,
                'description': 'Max messages to fetch from room history (0 = none)'
            }
        ]
        schema['dependencies'] = {
            'required': ['slixmpp'],
            'install_command': 'pip install slixmpp'
        }
        return schema


class XMPPListener(slixmpp.ClientXMPP):
    """XMPP client for listening to messages."""

    def __init__(self, jid: str, password: str, config: Dict[str, Any],
                 message_callback, log_callback):
        """
        Initialize XMPP listener.

        Args:
            jid: Jabber ID
            password: XMPP password
            config: Agent configuration
            message_callback: Callback for received messages
            log_callback: Callback for logging
        """
        super().__init__(jid, password)

        self.config = config
        self.message_callback = message_callback
        self.log_callback = log_callback

        # Register plugins
        self.register_plugin('xep_0030')  # Service Discovery
        self.register_plugin('xep_0045')  # Multi-User Chat (MUC)
        self.register_plugin('xep_0199')  # XMPP Ping

        # Register event handlers
        self.add_event_handler("session_start", self.on_session_start)
        self.add_event_handler("message", self.on_message)
        self.add_event_handler("groupchat_message", self.on_groupchat_message)
        self.add_event_handler("failed_auth", self.on_failed_auth)
        self.add_event_handler("disconnected", self.on_disconnected)

    async def on_session_start(self, event):
        """Handle session start."""
        try:
            self.send_presence()
            await self.get_roster()
            self.log_callback('XMPP session started', level='info')

            # Join rooms if configured
            listen_mode = self.config.get('listen_mode', 'both')
            if listen_mode in ['rooms', 'both']:
                rooms = self.config.get('rooms', [])
                nickname = self.config.get('room_nickname', 'Muninn')
                history_limit = self.config.get('message_history_limit', 0)

                for room_jid in rooms:
                    self.log_callback(f'Joining room: {room_jid}', level='info')
                    # Configure room history
                    mhistory = None
                    if history_limit > 0:
                        mhistory = self.plugin['xep_0045'].makeHistory(maxchars=None, maxstanzas=history_limit)

                    self.plugin['xep_0045'].join_muc(
                        room_jid,
                        nickname,
                        wait=True,
                        mhistory=mhistory
                    )
                    self.log_callback(f'Joined room: {room_jid}', level='info')

        except Exception as e:
            self.log_callback(f'Error in session start: {e}', level='error')

    def on_message(self, msg):
        """Handle direct messages."""
        # Ignore empty messages and non-chat messages
        if msg['type'] not in ('chat', 'normal'):
            return

        if not msg['body']:
            return

        # Check listen mode
        listen_mode = self.config.get('listen_mode', 'both')
        if listen_mode == 'rooms':
            return  # Only listening to rooms

        # Apply filters
        if self._should_ignore_message(msg):
            return

        # Create message data
        msg_data = {
            'payload': {
                'body': msg['body'],
                'from': str(msg['from'].bare),
                'from_resource': str(msg['from'].resource) if msg['from'].resource else None,
                'type': msg['type'],
                'subject': msg['subject'] if msg['subject'] else None
            },
            'metadata': {
                'received_at': datetime.utcnow().isoformat(),
                'message_type': 'direct',
                'agent_jid': str(self.boundjid.bare)
            }
        }

        # Add to queue via callback
        self.message_callback(msg_data)
        self.log_callback(f'Received direct message from {msg["from"].bare}', level='debug')

    def on_groupchat_message(self, msg):
        """Handle group chat messages."""
        # Ignore empty messages
        if not msg['body']:
            return

        # Check listen mode
        listen_mode = self.config.get('listen_mode', 'both')
        if listen_mode == 'direct':
            return  # Only listening to direct messages

        # Apply filters
        if self._should_ignore_message(msg):
            return

        # Create message data
        msg_data = {
            'payload': {
                'body': msg['body'],
                'from': str(msg['from'].bare),  # Room JID
                'from_nick': str(msg['from'].resource) if msg['from'].resource else None,  # Sender nickname
                'type': 'groupchat',
                'subject': msg['subject'] if msg['subject'] else None
            },
            'metadata': {
                'received_at': datetime.utcnow().isoformat(),
                'message_type': 'groupchat',
                'room': str(msg['from'].bare),
                'agent_jid': str(self.boundjid.bare)
            }
        }

        # Add to queue via callback
        self.message_callback(msg_data)
        self.log_callback(
            f'Received room message from {msg["from"].resource} in {msg["from"].bare}',
            level='debug'
        )

    def _should_ignore_message(self, msg) -> bool:
        """
        Check if message should be ignored based on filters.

        Args:
            msg: Message stanza

        Returns:
            True if message should be ignored
        """
        # Ignore messages from self
        if self.config.get('ignore_self', True):
            # For direct messages, check sender
            if msg['type'] in ('chat', 'normal'):
                if msg['from'].bare == self.boundjid.bare:
                    return True
            # For groupchat, check nickname
            elif msg['type'] == 'groupchat':
                our_nick = self.config.get('room_nickname', 'Muninn')
                if msg['from'].resource == our_nick:
                    return True

        # Ignore specific JIDs
        ignore_jids = self.config.get('ignore_jids', [])
        if msg['from'].bare in ignore_jids:
            return True

        # For groupchat, also check if sender nick is in ignore list
        if msg['type'] == 'groupchat' and msg['from'].resource in ignore_jids:
            return True

        return False

    def on_failed_auth(self, event):
        """Handle authentication failure."""
        self.log_callback('XMPP authentication failed', level='error')

    def on_disconnected(self, event):
        """Handle disconnection."""
        self.log_callback('XMPP disconnected', level='warning')
