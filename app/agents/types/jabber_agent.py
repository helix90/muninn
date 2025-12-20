"""
Jabber Agent - Send XMPP messages

Single responsibility: ONLY sends XMPP/Jabber messages.
Does NOT create new events (terminal agent).

Requires: slixmpp library (pip install slixmpp)
"""

from typing import List, Dict, Any
from jinja2 import Template, TemplateSyntaxError, UndefinedError
from app.agents.base import ActionAgent
from app.agents.registry import register_agent
from app.models import Event

# Try to import slixmpp
try:
    import slixmpp
    import asyncio
    XMPP_AVAILABLE = True
except ImportError:
    XMPP_AVAILABLE = False


@register_agent
class JabberAgent(ActionAgent):
    """
    Sends XMPP/Jabber messages.

    Terminal agent: consumes events but does not create new ones.
    Useful for sending notifications via XMPP/Jabber protocol.

    Requires slixmpp library: pip install slixmpp

    Configuration:
        jid (str): Jabber ID (username@domain)
        password (str): XMPP account password
        recipient (str): Recipient JID, can use Jinja2 template
        message_template (str): Jinja2 template for message text
        server (str, optional): XMPP server hostname (if different from JID domain)
        port (int, optional): XMPP server port (default: 5222)
        use_tls (bool): Use TLS encryption (default: True)
    """

    agent_type = 'jabber_agent'

    def validate_config(self) -> None:
        """Validate Jabber agent configuration."""
        super().validate_config()

        # Check if slixmpp is available
        if not XMPP_AVAILABLE:
            raise ValueError(
                "Jabber agent requires 'slixmpp' library. "
                "Install with: pip install slixmpp"
            )

        # Required JID
        if 'jid' not in self.config:
            raise ValueError("Jabber agent requires 'jid' in config")

        if not isinstance(self.config['jid'], str):
            raise ValueError("'jid' must be a string")

        # Required password
        if 'password' not in self.config:
            raise ValueError("Jabber agent requires 'password' in config")

        if not isinstance(self.config['password'], str):
            raise ValueError("'password' must be a string")

        # Required recipient
        if 'recipient' not in self.config:
            raise ValueError("Jabber agent requires 'recipient' in config")

        if not isinstance(self.config['recipient'], str):
            raise ValueError("'recipient' must be a string")

        # Test recipient template
        try:
            Template(self.config['recipient'])
        except TemplateSyntaxError as e:
            raise ValueError(f"Invalid Jinja2 syntax in 'recipient': {e}")

        # Required message template
        if 'message_template' not in self.config:
            raise ValueError("Jabber agent requires 'message_template' in config")

        if not isinstance(self.config['message_template'], str):
            raise ValueError("'message_template' must be a string")

        # Test message template
        try:
            Template(self.config['message_template'])
        except TemplateSyntaxError as e:
            raise ValueError(f"Invalid Jinja2 syntax in 'message_template': {e}")

        # Optional server
        if 'server' in self.config:
            if not isinstance(self.config['server'], str):
                raise ValueError("'server' must be a string")

        # Optional port
        if 'port' in self.config:
            port = self.config['port']
            if not isinstance(port, int) or port <= 0 or port > 65535:
                raise ValueError("'port' must be a valid port number (1-65535)")

        # Optional use_tls
        if 'use_tls' in self.config:
            if not isinstance(self.config['use_tls'], bool):
                raise ValueError("'use_tls' must be a boolean")

    def act(self, events: List[Event]) -> None:
        """
        Send XMPP messages for each event.

        Args:
            events: Events to process
        """
        if not XMPP_AVAILABLE:
            self.log('slixmpp library not available, skipping messages', level='error')
            return

        jid = self.config['jid']
        password = self.config['password']
        server = self.config.get('server')
        port = self.config.get('port', 5222)
        use_tls = self.config.get('use_tls', True)

        sent_count = 0
        failed_count = 0

        for event in events:
            try:
                # Render templates
                recipient = self._render_template(self.config['recipient'], event.payload)
                message = self._render_template(self.config['message_template'], event.payload)

                # Send message
                self._send_message(jid, password, recipient, message, server, port, use_tls)

                sent_count += 1
                self.log(f'XMPP message sent successfully', level='info', data={
                    'event_id': event.id,
                    'recipient': recipient
                })

            except Exception as e:
                failed_count += 1
                self.log(f'Failed to send XMPP message: {e}', level='error', data={
                    'event_id': event.id,
                    'error': str(e)
                })

        self.log(f'Processed {len(events)} events', data={
            'sent_count': sent_count,
            'failed_count': failed_count
        })

    def _render_template(self, template_str: str, data: Dict[str, Any]) -> str:
        """
        Render Jinja2 template with event data.

        Args:
            template_str: Template string
            data: Event payload data

        Returns:
            Rendered string
        """
        try:
            template = Template(template_str)
            return template.render(**data)
        except UndefinedError as e:
            self.log(f'Undefined variable in template: {e}', level='warning')
            return f'[Template Error: {e}]'
        except Exception as e:
            self.log(f'Template rendering error: {e}', level='error')
            return f'[Render Error: {e}]'

    def _send_message(self, jid: str, password: str, recipient: str,
                     message: str, server: str = None, port: int = 5222,
                     use_tls: bool = True) -> None:
        """
        Send XMPP message.

        Args:
            jid: Sender Jabber ID
            password: XMPP password
            recipient: Recipient JID
            message: Message text
            server: Optional server hostname
            port: Server port
            use_tls: Use TLS encryption
        """
        # Create a simple XMPP client
        class SendMsgBot(slixmpp.ClientXMPP):
            def __init__(self, jid, password, recipient, message):
                slixmpp.ClientXMPP.__init__(self, jid, password)
                self.recipient = recipient
                self.msg = message
                self.message_sent = False

                # Register event handlers
                self.add_event_handler("session_start", self.start)
                self.add_event_handler("message", self.message)

            async def start(self, event):
                """Send message on session start"""
                self.send_presence()
                await self.get_roster()

                # Send message
                self.send_message(mto=self.recipient, mbody=self.msg, mtype='chat')
                self.message_sent = True

                # Disconnect after sending
                self.disconnect()

            def message(self, msg):
                """Handle incoming messages (not used for sending)"""
                pass

        # Create bot instance
        xmpp = SendMsgBot(jid, password, recipient, message)

        # Configure connection
        if server:
            xmpp.connect((server, port), use_ssl=False, use_tls=use_tls)
        else:
            xmpp.connect(None, use_ssl=False, use_tls=use_tls)

        # Process XMPP stanzas
        xmpp.process(forever=False)

        if not xmpp.message_sent:
            raise Exception("Failed to send XMPP message")

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """Get configuration schema for Jabber agent."""
        schema = super().get_config_schema()
        schema['required_fields'] = [
            'jid',
            'password',
            'recipient',
            'message_template'
        ]
        schema['optional_fields'] = [
            {
                'name': 'server',
                'type': 'string',
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
            }
        ]
        schema['template_context'] = {
            'description': 'Templates have access to all event payload fields',
            'example_recipient': '{{ notify_user }}@jabber.example.com',
            'example_message': 'Alert: {{ title }}\\n\\nDetails: {{ description }}'
        }
        schema['dependencies'] = {
            'required': ['slixmpp'],
            'install_command': 'pip install slixmpp'
        }
        return schema
