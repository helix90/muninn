"""
IMAP Agent - Monitor email inbox via IMAP

This agent polls email inboxes for new messages by connecting via IMAP protocol,
fetches emails with headers and body text, and creates events for downstream processing.
Uses Message-ID based deduplication to prevent duplicate processing.
"""

import imaplib
import email
import email.utils
import socket
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

from app.agents.base import SourceAgent
from app.agents.registry import register_agent
from app.models import Event

logger = logging.getLogger(__name__)


@register_agent
class IMAPAgent(SourceAgent):
    """
    Source agent that monitors email inboxes via IMAP.

    Polls IMAP servers and fetches new emails with headers and body content.
    Uses Message-ID based deduplication to prevent processing duplicate messages.

    Configuration:
        host (str): IMAP server hostname (e.g., imap.gmail.com)
        username (str): Email account username
        password (str): Email account password (supports credential templating)
        port (int): IMAP port (default: 993 for SSL, 143 for non-SSL)
        use_ssl (bool): Use SSL/TLS connection (default: True)
        search_criteria (str): IMAP SEARCH criteria (default: UNSEEN)
        max_emails (int): Maximum emails to fetch per run (default: 50)
        mark_as_read (bool): Mark fetched emails as read on server (default: False)
        lookback_days (int): On first run, only check emails from last N days (default: 7)
    """

    agent_type = 'imap_agent'
    agent_category = 'source'

    def __init__(self, agent_id: int, config: Dict[str, Any], user_id: int, db_session=None):
        """Initialize the IMAP agent."""
        # Set instance variables BEFORE calling super().__init__()
        # because BaseAgent.__init__() calls validate_config() which needs these
        self.host = config.get('host', '')
        self.username = config.get('username', '')
        self.password = config.get('password', '')  # Resolved from credentials
        self.port = int(config.get('port', 993))
        self.use_ssl = config.get('use_ssl', True)
        self.search_criteria = config.get('search_criteria', 'UNSEEN')
        self.max_emails = int(config.get('max_emails', 50))
        self.mark_as_read = config.get('mark_as_read', False)
        self.lookback_days = int(config.get('lookback_days', 7))

        # Now call parent __init__ which will call validate_config()
        super().__init__(agent_id, config, user_id, db_session)

    def validate_config(self) -> None:
        """
        Validate agent configuration.

        Raises:
            ValueError: If configuration is invalid
        """
        # Call parent validation
        super().validate_config()

        # Check required fields
        if not self.host:
            raise ValueError("host is required")

        if not self.username:
            raise ValueError("username is required")

        if not self.password:
            raise ValueError("password is required")

        # Validate port
        if not 1 <= self.port <= 65535:
            raise ValueError("port must be between 1 and 65535")

        # Validate boolean flags
        if not isinstance(self.use_ssl, bool):
            raise ValueError("use_ssl must be a boolean")

        if not isinstance(self.mark_as_read, bool):
            raise ValueError("mark_as_read must be a boolean")

        # Validate max_emails
        if not 1 <= self.max_emails <= 1000:
            raise ValueError("max_emails must be between 1 and 1000")

        # Validate lookback_days
        if not 1 <= self.lookback_days <= 365:
            raise ValueError("lookback_days must be between 1 and 365")

    def fetch(self) -> List[Event]:
        """
        Poll IMAP inbox and return events for new emails.

        Returns:
            List of events containing email information
        """
        try:
            # Connect to IMAP server
            imap = self._connect_imap()

            # Build search criteria (with lookback on first run)
            search_criteria = self._build_search_criteria()

            # Search for matching emails
            status, data = imap.search(None, search_criteria)
            if status != 'OK':
                self.log('IMAP search failed', level='error', data={'status': status})
                imap.logout()
                return []

            # Get email UIDs
            email_uids = data[0].split() if data[0] else []

            # Limit number of emails
            if len(email_uids) > self.max_emails:
                email_uids = email_uids[:self.max_emails]

            # Fetch and parse emails
            events = []
            seen_message_ids = self.memory.get('seen_message_ids', [])

            for uid in email_uids:
                try:
                    # Fetch raw email
                    status, data = imap.fetch(uid, '(RFC822)')
                    if status != 'OK':
                        self.log(f'Failed to fetch email UID {uid.decode()}', level='warning')
                        continue

                    raw_email = data[0][1]
                    email_data = self._parse_email(raw_email)

                    # Deduplication check
                    message_id = email_data['message_id']
                    if message_id and message_id in seen_message_ids:
                        self.log(f'Skipping duplicate email: {message_id}', level='debug')
                        continue

                    # Add UID to email data
                    email_data['uid'] = uid.decode()

                    # Create event
                    event = self.create_event(
                        payload=email_data,
                        metadata={
                            'server': self.host,
                            'folder': 'INBOX',
                            'fetched_at': datetime.utcnow().isoformat(),
                            'search_criteria': search_criteria
                        }
                    )
                    events.append(event)

                    # Mark as seen in memory
                    if message_id:
                        self.memory.append_to_list(
                            'seen_message_ids',
                            message_id,
                            max_length=10000,  # Prevent unbounded growth
                            ttl=30 * 24 * 3600  # 30 days TTL
                        )

                    # Optionally mark as read on server
                    if self.mark_as_read:
                        imap.store(uid, '+FLAGS', '\\Seen')

                except Exception as e:
                    self.log(f'Error processing email UID {uid.decode()}: {e}', level='error')
                    continue

            # Update metrics
            self.memory.set('last_sync_at', datetime.utcnow().isoformat())
            total_fetched = self.memory.get('total_emails_fetched', 0)
            self.memory.set('total_emails_fetched', total_fetched + len(events))

            # Logout
            imap.logout()

            if events:
                self.log(f'Fetched {len(events)} new email(s)', data={
                    'count': len(events),
                    'server': self.host
                })

            return events

        except imaplib.IMAP4.error as e:
            self.log(f'IMAP protocol error: {e}', level='error', data={'error': str(e)})
            return []
        except socket.gaierror as e:
            self.log(f'Cannot resolve hostname: {self.host}', level='error', data={'error': str(e)})
            return []
        except socket.timeout as e:
            self.log(f'Connection timeout: {e}', level='error', data={'error': str(e)})
            return []
        except ConnectionRefusedError as e:
            self.log(f'Connection refused (check host/port): {self.host}:{self.port}', level='error', data={'error': str(e)})
            return []
        except Exception as e:
            self.log(f'Unexpected error: {e}', level='error', data={'error': str(e)})
            return []

    def _connect_imap(self):
        """
        Connect to IMAP server with SSL/TLS.

        Returns:
            IMAP4 client instance

        Raises:
            imaplib.IMAP4.error: If login fails
            socket errors: If connection fails
        """
        # Create IMAP connection
        if self.use_ssl:
            imap = imaplib.IMAP4_SSL(self.host, self.port)
        else:
            imap = imaplib.IMAP4(self.host, self.port)

        # Login
        imap.login(self.username, self.password)

        # Select INBOX folder
        status, data = imap.select('INBOX')
        if status != 'OK':
            raise imaplib.IMAP4.error(f'Failed to select INBOX: {data}')

        return imap

    def _build_search_criteria(self) -> str:
        """
        Build IMAP search criteria with first-run lookback.

        Returns:
            IMAP SEARCH criteria string
        """
        search_criteria = self.search_criteria

        # On first run, apply lookback_days to prevent flooding
        if not self.memory.get('last_sync_at'):
            lookback_date = datetime.utcnow() - timedelta(days=self.lookback_days)
            since_date = lookback_date.strftime('%d-%b-%Y')

            # Combine with existing criteria
            if search_criteria:
                search_criteria = f'{search_criteria} SINCE {since_date}'
            else:
                search_criteria = f'SINCE {since_date}'

            self.log(f'First run: applying lookback filter (SINCE {since_date})', level='debug')

        return search_criteria

    def _parse_email(self, raw_email: bytes) -> Dict[str, Any]:
        """
        Parse raw email bytes into structured data.

        Args:
            raw_email: Raw email bytes

        Returns:
            Dictionary containing parsed email data
        """
        try:
            msg = email.message_from_bytes(raw_email)

            # Extract headers
            message_id = msg.get('Message-ID', '')
            from_addr = email.utils.parseaddr(msg.get('From', ''))[1] if msg.get('From') else ''
            to_addr = email.utils.parseaddr(msg.get('To', ''))[1] if msg.get('To') else ''
            subject = msg.get('Subject', '')
            date_str = msg.get('Date', '')

            # Parse date to ISO format
            date_iso = ''
            if date_str:
                try:
                    date_tuple = email.utils.parsedate_to_datetime(date_str)
                    if date_tuple:
                        date_iso = date_tuple.isoformat()
                except Exception as e:
                    self.log(f'Failed to parse date: {date_str}', level='warning')

            # Extract body (text and html)
            body_text = ''
            body_html = ''

            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get('Content-Disposition', ''))

                    # Skip attachments
                    if 'attachment' in content_disposition:
                        continue

                    try:
                        if content_type == 'text/plain' and not body_text:
                            payload = part.get_payload(decode=True)
                            if payload:
                                body_text = payload.decode('utf-8', errors='replace')
                        elif content_type == 'text/html' and not body_html:
                            payload = part.get_payload(decode=True)
                            if payload:
                                body_html = payload.decode('utf-8', errors='replace')
                    except Exception as e:
                        self.log(f'Failed to decode email part: {e}', level='warning')
            else:
                content_type = msg.get_content_type()
                try:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        decoded = payload.decode('utf-8', errors='replace')
                        if content_type == 'text/plain':
                            body_text = decoded
                        elif content_type == 'text/html':
                            body_html = decoded
                except Exception as e:
                    self.log(f'Failed to decode email body: {e}', level='warning')

            # Extract additional headers
            headers = {
                'reply_to': msg.get('Reply-To', ''),
                'in_reply_to': msg.get('In-Reply-To', ''),
                'references': msg.get('References', ''),
                'content_type': msg.get_content_type()
            }

            return {
                'message_id': message_id,
                'from': from_addr,
                'to': to_addr,
                'subject': subject,
                'date': date_iso,
                'body_text': body_text,
                'body_html': body_html,
                'headers': headers
            }

        except Exception as e:
            self.log(f'Failed to parse email: {e}', level='error')
            return {
                'message_id': '',
                'from': '',
                'to': '',
                'subject': '',
                'date': '',
                'body_text': '',
                'body_html': '',
                'headers': {},
                'parse_error': str(e)
            }

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """
        Get the configuration schema for this agent's configuration.

        Returns:
            Configuration schema dictionary
        """
        schema = super().get_config_schema()
        schema['required_fields'] = ['host', 'username', 'password']
        schema['optional_fields'].extend([
            {
                'name': 'host',
                'type': 'text',
                'description': 'IMAP server hostname (e.g., imap.gmail.com, imap.outlook.com)'
            },
            {
                'name': 'username',
                'type': 'text',
                'description': 'Email account username (usually your email address)'
            },
            {
                'name': 'password',
                'type': 'password',
                'description': 'Email account password (supports credential templating: {{credential:email_password}})'
            },
            {
                'name': 'port',
                'type': 'integer',
                'default': 993,
                'description': 'IMAP port (993 for SSL, 143 for non-SSL)'
            },
            {
                'name': 'use_ssl',
                'type': 'boolean',
                'default': True,
                'description': 'Use SSL/TLS connection'
            },
            {
                'name': 'search_criteria',
                'type': 'text',
                'default': 'UNSEEN',
                'description': 'IMAP SEARCH criteria (e.g., UNSEEN, ALL, FROM "email@example.com", SUBJECT "urgent")'
            },
            {
                'name': 'max_emails',
                'type': 'integer',
                'default': 50,
                'description': 'Maximum number of emails to fetch per run (1-1000)'
            },
            {
                'name': 'mark_as_read',
                'type': 'boolean',
                'default': False,
                'description': 'Mark fetched emails as read on the server'
            },
            {
                'name': 'lookback_days',
                'type': 'integer',
                'default': 7,
                'description': 'On first run, only check emails from the last N days (1-365)'
            }
        ])
        return schema

    def __repr__(self):
        """String representation of the agent."""
        return f'<IMAPAgent {self.agent_id}: {self.username}@{self.host}>'
