"""
Email sender job for sending email notifications
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Dict, Any, Optional, List
from ..base import BaseJob


class EmailSenderJob(BaseJob):
    """Job for sending email notifications."""
    
    job_type = 'email_sender'
    required_config_fields = ['smtp_server', 'smtp_port', 'username', 'password', 'to_emails', 'subject']
    optional_config_fields = ['from_email', 'body', 'html_body', 'attachments', 'cc_emails', 'bcc_emails', 'use_tls']
    
    def _validate_config_values(self):
        """Validate configuration field values."""
        # Validate SMTP settings
        smtp_port = self.config.get('smtp_port')
        if not isinstance(smtp_port, int) or smtp_port <= 0:
            raise ValueError("smtp_port must be a positive integer")
        
        # Validate email lists
        for email_field in ['to_emails', 'cc_emails', 'bcc_emails']:
            emails = self.config.get(email_field, [])
            if emails:
                if not isinstance(emails, list):
                    raise ValueError(f"{email_field} must be a list")
                if not all(self._is_valid_email(email) for email in emails):
                    raise ValueError(f"Invalid email address in {email_field}")
        
        # Validate subject
        subject = self.config.get('subject')
        if not subject or not isinstance(subject, str):
            raise ValueError("subject must be a non-empty string")
        
        # Validate body content
        body = self.config.get('body')
        html_body = self.config.get('html_body')
        if not body and not html_body:
            raise ValueError("Either body or html_body must be provided")
        
        # Validate attachments
        attachments = self.config.get('attachments', [])
        if not isinstance(attachments, list):
            raise ValueError("attachments must be a list")
        
        # Validate use_tls
        use_tls = self.config.get('use_tls', True)
        if not isinstance(use_tls, bool):
            raise ValueError("use_tls must be a boolean")
    
    def _is_valid_email(self, email: str) -> bool:
        """Check if an email address is valid."""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    def _create_message(self, to_emails: List[str], subject: str, body: str = None, 
                       html_body: str = None, cc_emails: List[str] = None, 
                       bcc_emails: List[str] = None) -> MIMEMultipart:
        """Create the email message."""
        msg = MIMEMultipart('alternative')
        
        # Set headers
        msg['Subject'] = subject
        msg['From'] = self.config.get('from_email', self.config['username'])
        msg['To'] = ', '.join(to_emails)
        
        if cc_emails:
            msg['Cc'] = ', '.join(cc_emails)
        
        # Add body parts
        if body:
            text_part = MIMEText(body, 'plain', 'utf-8')
            msg.attach(text_part)
        
        if html_body:
            html_part = MIMEText(html_body, 'html', 'utf-8')
            msg.attach(html_part)
        
        return msg
    
    def _add_attachments(self, msg: MIMEMultipart, attachments: List[Dict[str, Any]]) -> None:
        """Add attachments to the email message."""
        for attachment in attachments:
            if not isinstance(attachment, dict):
                continue
            
            file_path = attachment.get('path')
            file_name = attachment.get('name', 'attachment')
            content_type = attachment.get('content_type', 'application/octet-stream')
            
            if not file_path:
                continue
            
            try:
                with open(file_path, 'rb') as f:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(f.read())
                
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f'attachment; filename= {file_name}')
                msg.attach(part)
            except Exception as e:
                self.logger.warning(f"Failed to attach file {file_path}: {e}")
    
    def _send_email(self, msg: MIMEMultipart) -> Dict[str, Any]:
        """Send the email via SMTP."""
        smtp_server = self.config['smtp_server']
        smtp_port = self.config['smtp_port']
        username = self.config['username']
        password = self.config['password']
        use_tls = self.config.get('use_tls', True)
        
        try:
            # Create SMTP connection
            if use_tls:
                server = smtplib.SMTP(smtp_server, smtp_port)
                server.starttls()
            else:
                server = smtplib.SMTP(smtp_server, smtp_port)
            
            # Login
            server.login(username, password)
            
            # Get all recipients
            to_emails = self.config['to_emails']
            cc_emails = self.config.get('cc_emails', [])
            bcc_emails = self.config.get('bcc_emails', [])
            all_recipients = to_emails + cc_emails + bcc_emails
            
            # Send email
            server.send_message(msg, from_addr=username, to_addrs=all_recipients)
            server.quit()
            
            return {
                'status': 'sent',
                'recipients': all_recipients,
                'message_id': msg.get('Message-ID', 'unknown')
            }
            
        except smtplib.SMTPAuthenticationError as e:
            raise ValueError(f"SMTP authentication failed: {e}")
        except smtplib.SMTPRecipientsRefused as e:
            raise ValueError(f"Recipient email(s) refused: {e}")
        except smtplib.SMTPSenderRefused as e:
            raise ValueError(f"Sender email refused: {e}")
        except smtplib.SMTPDataError as e:
            raise ValueError(f"SMTP data error: {e}")
        except Exception as e:
            raise ValueError(f"SMTP error: {e}")
    
    def execute(self, input_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute the email sending job.
        
        Args:
            input_data: Optional input data that can override config values
            
        Returns:
            Dictionary containing email sending results
        """
        try:
            self.pre_execute(input_data)
            
            # Use input_data to override config if provided
            config = self.config.copy()
            if input_data:
                config.update(input_data)
            
            # Create email message
            to_emails = config['to_emails']
            subject = config['subject']
            body = config.get('body')
            html_body = config.get('html_body')
            cc_emails = config.get('cc_emails', [])
            bcc_emails = config.get('bcc_emails', [])
            attachments = config.get('attachments', [])
            
            msg = self._create_message(
                to_emails=to_emails,
                subject=subject,
                body=body,
                html_body=html_body,
                cc_emails=cc_emails,
                bcc_emails=bcc_emails
            )
            
            # Add attachments if any
            if attachments:
                self._add_attachments(msg, attachments)
            
            # Send email
            send_result = self._send_email(msg)
            
            # Prepare result
            result = {
                'email_sent': True,
                'send_result': send_result,
                'to_emails': to_emails,
                'cc_emails': cc_emails,
                'bcc_emails': bcc_emails,
                'subject': subject,
                'has_attachments': len(attachments) > 0,
                'attachment_count': len(attachments),
                'timestamp': send_result.get('timestamp')
            }
            
            self.post_execute(result, success=True)
            return result
            
        except Exception as e:
            error_result = self.handle_error(e)
            self.post_execute(error_result, success=False)
            return error_result
    
    def get_config_schema(self) -> Dict[str, Any]:
        """Get the configuration schema for email sender jobs."""
        schema = super().get_config_schema()
        schema.update({
            'description': 'Sends emails via SMTP with support for attachments and multiple recipients',
            'example_config': {
                'smtp_server': 'smtp.gmail.com',
                'smtp_port': 587,
                'username': 'user@gmail.com',
                'password': 'app_password',
                'to_emails': ['recipient@example.com'],
                'subject': 'Test Email',
                'body': 'This is a test email',
                'use_tls': True
            }
        })
        return schema
