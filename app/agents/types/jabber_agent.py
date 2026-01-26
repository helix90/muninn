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

        sent_count = 0
        failed_count = 0

        for event in events:
            try:
                # Prepare template context with event data
                context = {
                    'payload': event.payload,
                    'metadata': event.metadata,
                    'event': event
                }

                # Render templates
                recipient = self._render_template(self.config['recipient'], context)
                message = self._render_template(self.config['message_template'], context)

                # Send message
                self._send_message(jid, password, recipient, message, server, port)

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

    def test_connection(self) -> Dict[str, Any]:
        """
        Test Jabber connection by sending a test message.

        Returns:
            Dict with success status and message
        """
        if not XMPP_AVAILABLE:
            return {
                'success': False,
                'message': 'slixmpp library not available. Install with: pip install slixmpp'
            }

        # Clear previous logs before test
        self.memory.set('_logs', [])

        try:
            jid = self.config['jid']
            password = self.config['password']
            server = self.config.get('server')
            port = self.config.get('port', 5222)
            use_tls = self.config.get('use_tls', True)

            # Log the configuration being tested
            self.log(f'Testing XMPP connection with configuration', level='info', data={
                'jid': jid,
                'server': server or 'auto-discovery from JID domain',
                'port': port,
                'use_tls': use_tls
            })

            # Render recipient with test data
            test_payload = {'test': 'connection'}
            recipient = self._render_template(self.config['recipient'], test_payload)

            self.log(f'Recipient template rendered successfully: {recipient}', level='debug')

            # Send test message
            test_message = "Test message from Muninn Jabber agent. If you receive this, the connection is working!"
            self._send_message(jid, password, recipient, test_message, server, port, use_tls)

            self.log('Test message sent successfully!', level='info')

            # Get logs for detailed diagnostics
            logs = self.memory.get('_logs', [])

            return {
                'success': True,
                'message': f'Test message sent successfully to {recipient}',
                'details': {
                    'jid': jid,
                    'recipient': recipient,
                    'server': server or 'DNS SRV lookup',
                    'port': port,
                    'logs': logs[-10:]  # Last 10 log entries
                }
            }

        except Exception as e:
            import traceback
            import sys

            # Get detailed error information
            exc_type, exc_value, exc_traceback = sys.exc_info()
            tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)

            # Get logs for detailed diagnostics
            logs = self.memory.get('_logs', [])

            # Build detailed error message
            error_details = {
                'error_type': type(e).__name__,
                'error_message': str(e),
                'configuration': {
                    'jid': self.config.get('jid'),
                    'server': self.config.get('server') or 'auto-discovery from JID domain',
                    'port': self.config.get('port', 5222),
                    'use_tls': self.config.get('use_tls', True),
                    'recipient_template': self.config.get('recipient')
                },
                'logs': logs[-20:],  # Last 20 log entries for more context
                'traceback': ''.join(tb_lines[-5:])  # Last 5 lines of traceback
            }

            # Create user-friendly error message
            error_msg = f"Connection test failed: {str(e)}\n\n"
            error_msg += f"Configuration:\n"
            error_msg += f"  JID: {self.config.get('jid')}\n"
            error_msg += f"  Server: {self.config.get('server') or 'auto-discovery from JID domain'}\n"
            error_msg += f"  Port: {self.config.get('port', 5222)}\n"
            error_msg += f"  Use TLS: {self.config.get('use_tls', True)}\n\n"

            if logs:
                error_msg += f"Recent logs:\n"
                for log_entry in logs[-5:]:
                    error_msg += f"  [{log_entry.get('level', 'info').upper()}] {log_entry.get('message', '')}\n"

            self.log(f'Test connection failed: {str(e)}', level='error', data=error_details)

            return {
                'success': False,
                'message': error_msg,
                'details': error_details
            }

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
        import asyncio
        import logging

        # Enable detailed XMPP logging for diagnosis
        logging.getLogger('slixmpp').setLevel(logging.DEBUG)

        # Create a new event loop for this thread FIRST (Flask uses threads)
        # This must happen before any slixmpp operations
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Log connection attempt details
        self.log(f'Attempting XMPP connection', level='debug', data={
            'jid': jid,
            'server': server or 'auto-discovery from JID',
            'port': port,
            'recipient': recipient,
            'use_tls': use_tls
        })

        # Track error for better diagnostics
        connection_error = None

        # Create a simple XMPP client
        class SendMsgBot(slixmpp.ClientXMPP):
            def __init__(self, jid, password, recipient, message):
                slixmpp.ClientXMPP.__init__(self, jid, password)
                self.recipient = recipient
                self.msg = message
                self.message_sent = False
                self.connection_error = None

                # Register XEP plugins for better compatibility
                self.register_plugin('xep_0030')  # Service Discovery
                self.register_plugin('xep_0199')  # XMPP Ping

                # Enable specific SASL mechanisms for broader server compatibility
                # Some servers only support PLAIN, others prefer SCRAM-SHA-1
                self.register_plugin('feature_mechanisms')

                # Try to enable common SASL mechanisms
                try:
                    # Add PLAIN mechanism explicitly (most compatible but less secure over non-TLS)
                    from slixmpp.features.feature_mechanisms import stanza
                    if 'PLAIN' not in self.boundjid.bare:
                        pass  # PLAIN is usually enabled by default
                except:
                    pass  # Ignore if we can't manipulate mechanisms

                # Register event handlers
                self.add_event_handler("session_start", self.start)
                self.add_event_handler("message", self.message)
                self.add_event_handler("failed_auth", self.failed_auth)
                self.add_event_handler("no_auth", self.no_auth)
                self.add_event_handler("disconnected", self.on_disconnect)

                # Add handler to see what mechanisms are offered by server
                self.add_event_handler("stream_negotiated", self.stream_negotiated)

            async def start(self, event):
                """Send message on session start"""
                try:
                    self.send_presence()
                    await self.get_roster()

                    # Send message
                    self.send_message(mto=self.recipient, mbody=self.msg, mtype='chat')
                    self.message_sent = True

                    # Disconnect after sending
                    self.disconnect()
                except Exception as e:
                    self.connection_error = f"Error in session start: {e}"
                    self.disconnect()

            def message(self, msg):
                """Handle incoming messages (not used for sending)"""
                pass

            def failed_auth(self, event):
                """Handle authentication failure"""
                import logging
                error_msg = "Authentication failed - check username and password"
                self.connection_error = error_msg
                logging.error(f"XMPP failed_auth event: {error_msg}")
                logging.error(f"JID used: {self.boundjid}")
                self.disconnect()

            def no_auth(self, event):
                """Handle no authentication method available"""
                import logging
                error_msg = "No appropriate login method - server may require specific SASL mechanism"
                self.connection_error = error_msg
                logging.error(f"XMPP no_auth event: {error_msg}")
                self.disconnect()

            def on_disconnect(self, event):
                """Handle disconnection"""
                import logging
                logging.debug(f"XMPP disconnected. Message sent: {self.message_sent}")
                if not self.message_sent and not self.connection_error:
                    self.connection_error = "Disconnected before message could be sent"

            def stream_negotiated(self, event):
                """Log what SASL mechanisms are available"""
                import logging
                try:
                    # Try to log available SASL mechanisms
                    if hasattr(self, 'features') and self.features:
                        mechanisms = self.features.get('mechanisms', None)
                        if mechanisms:
                            logging.debug(f"SASL mechanisms available: {mechanisms}")
                except Exception as e:
                    logging.debug(f"Could not retrieve SASL mechanisms: {e}")

        try:
            # Create bot instance
            xmpp = SendMsgBot(jid, password, recipient, message)

            # Enable slixmpp debug logging temporarily for diagnostics
            import logging as py_logging
            slixmpp_logger = py_logging.getLogger('slixmpp')
            slixmpp_logger.setLevel(py_logging.DEBUG)

            # Configure SSL context for self-signed certificates
            # Many self-hosted servers like Freedombox use self-signed certs
            import ssl
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            xmpp.ssl_context = ssl_context

            # Disable IPv6 if causing issues
            xmpp.use_ipv6 = False

            # Configure connection
            # For most servers, let slixmpp figure out the connection details via DNS SRV
            # This is especially important for proper XMPP servers
            self.log(f'Initiating XMPP connection...', level='info', data={
                'explicit_server': bool(server),
                'server': server,
                'port': port,
                'jid': jid
            })

            # Test basic socket connectivity first
            if server:
                import socket
                try:
                    self.log(f'Testing TCP socket connectivity to {server}:{port}...', level='debug')
                    test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    test_sock.settimeout(5)
                    test_sock.connect((server, port))
                    test_sock.close()
                    self.log(f'TCP socket connection successful', level='debug')
                except Exception as sock_err:
                    self.log(f'TCP socket test failed: {sock_err}', level='error')
                    raise Exception(f"Cannot establish TCP connection to {server}:{port}: {sock_err}")

            # Initiate XMPP connection
            # Note: connect() just initiates the connection; the actual connection
            # and authentication happens when we call process() below via the event loop
            if server:
                # For servers with explicit host:port, use STARTTLS (standard for port 5222)
                self.log(f'Initiating XMPP connection to {server}:{port}...', level='info')
                try:
                    xmpp.connect((server, port), use_ssl=False, force_starttls=True)
                    self.log(f'Connection initiated, starting event loop...', level='debug')
                except Exception as e:
                    self.log(f'Connection initiation failed: {e}', level='error')
                    raise Exception(f"Failed to initiate XMPP connection: {e}")
            else:
                # Use DNS SRV lookup when no explicit server is provided
                self.log(f'Initiating XMPP connection via DNS SRV lookup...', level='info')
                try:
                    xmpp.connect(use_ssl=False, force_starttls=True)
                    self.log(f'Connection initiated via DNS SRV, starting event loop...', level='debug')
                except Exception as e:
                    self.log(f'Connection initiation failed: {e}', level='error')
                    raise Exception(f"Failed to initiate XMPP connection via DNS SRV: {e}")

            # Process XMPP stanzas with a timeout
            # Use process(timeout=15) to allow up to 15 seconds for connection and send
            self.log('Processing XMPP stanzas (timeout=15s)...', level='debug')
            xmpp.process(timeout=15)

            # Log final status
            self.log(f'XMPP processing complete', level='debug', data={
                'message_sent': xmpp.message_sent,
                'connection_error': xmpp.connection_error
            })

            # Check for errors
            if xmpp.connection_error:
                self.log(f'XMPP connection error detected: {xmpp.connection_error}', level='error')
                raise Exception(xmpp.connection_error)

            if not xmpp.message_sent:
                error_msg = "Failed to send XMPP message - connection may have timed out or credentials are incorrect"
                self.log(error_msg, level='error')
                raise Exception(error_msg)

            self.log('XMPP message sent successfully', level='info')
        finally:
            # Clean up event loop properly to avoid "Task was destroyed but it is pending!" warnings
            try:
                # First, try to disconnect the XMPP client cleanly
                try:
                    xmpp.disconnect()
                except Exception:
                    pass

                # Cancel all pending tasks
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()

                # Run the loop one final time to process cancellations
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))

                # Stop the loop if it's running
                if loop.is_running():
                    loop.stop()

                # Close the loop
                loop.close()
            except Exception:
                pass  # Ignore cleanup errors

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
