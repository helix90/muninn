"""
Tests for WebhookAgent and webhook endpoint
"""

import pytest
import json
import hmac
import hashlib
from unittest.mock import Mock, patch
from datetime import datetime
from app.extensions import db
from app.agents.types import WebhookAgent
from app.agents import agent_registry
from app.models import Event, Job, User


@pytest.fixture
def test_job(app, test_user):
    """Create a test webhook job"""
    with app.app_context():
        job = Job(
            name='Test Webhook',
            job_type='webhook_agent',
            config={
                'secret_token': 'test_secret_token_12345678',
                'verify_signature': False,
                'allowed_ips': [],
                'include_headers': [],
                'response_status': 200,
                'response_body': {'status': 'success'}
            },
            user_id=test_user.id,
            is_active=True
        )
        db.session.add(job)
        db.session.commit()

        yield job


class TestWebhookAgentRegistration:
    """Tests for WebhookAgent registration"""

    def test_webhook_agent_registered(self):
        """Test that WebhookAgent is registered"""
        assert agent_registry.is_registered('webhook_agent')
        assert 'webhook_agent' in agent_registry.get_source_agents()

    def test_webhook_agent_capabilities(self):
        """Test webhook agent capabilities"""
        assert WebhookAgent.can_be_scheduled == False
        assert WebhookAgent.can_receive_events == False
        assert WebhookAgent.can_create_events == True
        assert WebhookAgent.requires_input == False


class TestWebhookAgentConfig:
    """Tests for WebhookAgent configuration validation"""

    def test_auto_generate_secret_token(self):
        """Test that secret token is auto-generated if not provided"""
        agent = WebhookAgent(
            agent_id=1,
            config={},
            user_id=1
        )

        assert agent.secret_token is not None
        assert len(agent.secret_token) >= 16
        assert agent.agent_type == 'webhook_agent'

    def test_explicit_secret_token(self):
        """Test using explicitly provided secret token"""
        token = 'my_custom_secret_token_1234567890'
        agent = WebhookAgent(
            agent_id=1,
            config={'secret_token': token},
            user_id=1
        )

        assert agent.secret_token == token

    def test_secret_token_too_short(self):
        """Test validation fails for short secret tokens"""
        with pytest.raises(ValueError, match="at least 16 characters"):
            WebhookAgent(
                agent_id=1,
                config={'secret_token': 'short'},
                user_id=1
            )

    def test_verify_signature_requires_secret(self):
        """Test that verify_signature=True requires signature_secret"""
        with pytest.raises(ValueError, match="signature_secret required"):
            WebhookAgent(
                agent_id=1,
                config={
                    'secret_token': 'test_secret_token_12345678',
                    'verify_signature': True,
                    'signature_secret': ''
                },
                user_id=1
            )

    def test_valid_signature_config(self):
        """Test valid signature verification configuration"""
        agent = WebhookAgent(
            agent_id=1,
            config={
                'secret_token': 'test_secret_token_12345678',
                'verify_signature': True,
                'signature_secret': 'my_hmac_secret'
            },
            user_id=1
        )

        assert agent.verify_signature == True
        assert agent.signature_secret == 'my_hmac_secret'

    def test_invalid_response_status(self):
        """Test invalid HTTP response status codes"""
        with pytest.raises(ValueError, match="between 100 and 599"):
            WebhookAgent(
                agent_id=1,
                config={
                    'secret_token': 'test_secret_token_12345678',
                    'response_status': 9999
                },
                user_id=1
            )

    def test_invalid_allowed_ips_type(self):
        """Test that allowed_ips must be a list"""
        with pytest.raises(ValueError, match="must be a list"):
            WebhookAgent(
                agent_id=1,
                config={
                    'secret_token': 'test_secret_token_12345678',
                    'allowed_ips': '192.168.1.1'
                },
                user_id=1
            )

    def test_invalid_include_headers_type(self):
        """Test that include_headers must be a list"""
        with pytest.raises(ValueError, match="must be a list"):
            WebhookAgent(
                agent_id=1,
                config={
                    'secret_token': 'test_secret_token_12345678',
                    'include_headers': 'User-Agent'
                },
                user_id=1
            )

    def test_invalid_response_body_type(self):
        """Test that response_body must be a dict or None"""
        with pytest.raises(ValueError, match="must be a dictionary"):
            WebhookAgent(
                agent_id=1,
                config={
                    'secret_token': 'test_secret_token_12345678',
                    'response_body': 'invalid'
                },
                user_id=1
            )

    def test_full_config(self):
        """Test agent with all configuration options"""
        agent = WebhookAgent(
            agent_id=1,
            config={
                'secret_token': 'test_secret_token_12345678',
                'verify_signature': True,
                'signature_secret': 'my_hmac_secret',
                'allowed_ips': ['192.168.1.1', '10.0.0.1'],
                'include_headers': ['User-Agent', 'X-Request-ID'],
                'response_status': 201,
                'response_body': {'status': 'created', 'message': 'OK'}
            },
            user_id=1
        )

        assert agent.secret_token == 'test_secret_token_12345678'
        assert agent.verify_signature == True
        assert agent.signature_secret == 'my_hmac_secret'
        assert agent.allowed_ips == ['192.168.1.1', '10.0.0.1']
        assert agent.include_headers == ['User-Agent', 'X-Request-ID']
        assert agent.response_status == 201
        assert agent.response_body == {'status': 'created', 'message': 'OK'}


class TestWebhookAgentFetch:
    """Tests for WebhookAgent fetch method"""

    def test_fetch_returns_empty_list(self, app):
        """Test that fetch() returns empty list (webhooks are push-based)"""
        agent = WebhookAgent(
            agent_id=1,
            config={'secret_token': 'test_secret_token_12345678'},
            user_id=1
        )

        events = agent.fetch()

        assert events == []
        assert isinstance(events, list)

    def test_fetch_updates_memory(self, app, db_session, test_job):
        """Test that fetch() updates last_check_at in memory"""
        agent = WebhookAgent(
            agent_id=test_job.id,
            config={'secret_token': 'test_secret_token_12345678'},
            user_id=test_job.user_id,
            db_session=db_session
        )

        before = datetime.utcnow().isoformat()
        agent.fetch()
        after = datetime.utcnow().isoformat()

        last_check = agent.memory.get('last_check_at')
        assert last_check is not None
        assert before <= last_check <= after


class TestWebhookAgentHelpers:
    """Tests for WebhookAgent helper methods"""

    def test_get_webhook_url_with_base_url(self):
        """Test webhook URL generation with base URL"""
        agent = WebhookAgent(
            agent_id=123,
            config={'secret_token': 'test_secret_token_12345678'},
            user_id=1
        )

        url = agent.get_webhook_url('https://muninn.example.com')

        assert url == 'https://muninn.example.com/webhooks/123/test_secret_token_12345678'

    def test_get_webhook_url_without_base_url(self):
        """Test webhook URL generation without base URL (uses placeholder)"""
        agent = WebhookAgent(
            agent_id=456,
            config={'secret_token': 'another_secret_token_98765'},
            user_id=1
        )

        url = agent.get_webhook_url()

        assert url == 'https://your-muninn-instance.com/webhooks/456/another_secret_token_98765'

    def test_agent_repr(self):
        """Test string representation masks token"""
        agent = WebhookAgent(
            agent_id=789,
            config={'secret_token': 'very_long_secret_token_should_be_masked'},
            user_id=1
        )

        repr_str = repr(agent)

        assert '789' in repr_str
        assert 'very_lon***' in repr_str
        assert 'should_be_masked' not in repr_str


class TestWebhookEndpoint:
    """Tests for webhook HTTP endpoint"""

    def test_receive_json_webhook(self, client, test_job):
        """Test receiving JSON webhook successfully"""
        response = client.post(
            f'/webhooks/{test_job.id}/test_secret_token_12345678',
            json={'message': 'Hello', 'count': 42},
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'success'
        assert 'event_id' in data

        # Verify event was created
        event = Event.query.filter_by(agent_id=test_job.id).first()
        assert event is not None
        assert event.payload['message'] == 'Hello'
        assert event.payload['count'] == 42
        assert event.event_metadata['source'] == 'webhook'

    def test_receive_form_webhook(self, client, test_job):
        """Test receiving form-encoded webhook"""
        response = client.post(
            f'/webhooks/{test_job.id}/test_secret_token_12345678',
            data={'field1': 'value1', 'field2': 'value2'},
            content_type='application/x-www-form-urlencoded'
        )

        assert response.status_code == 200

        # Verify event was created with form data
        event = Event.query.filter_by(agent_id=test_job.id).first()
        assert event is not None
        assert event.payload['field1'] == 'value1'
        assert event.payload['field2'] == 'value2'

    def test_receive_raw_text_webhook(self, client, test_job):
        """Test receiving raw text webhook"""
        response = client.post(
            f'/webhooks/{test_job.id}/test_secret_token_12345678',
            data='Plain text payload',
            content_type='text/plain'
        )

        assert response.status_code == 200

        # Verify event was created with raw text
        event = Event.query.filter_by(agent_id=test_job.id).first()
        assert event is not None
        assert event.payload['raw'] == 'Plain text payload'

    def test_invalid_token(self, client, test_job):
        """Test webhook with invalid secret token"""
        response = client.post(
            f'/webhooks/{test_job.id}/wrong_token',
            json={'message': 'test'}
        )

        assert response.status_code == 403
        data = response.get_json()
        assert data['error'] == 'Invalid token'

        # Verify no event was created
        event_count = Event.query.filter_by(agent_id=test_job.id).count()
        assert event_count == 0

    def test_webhook_not_found(self, client):
        """Test webhook with non-existent agent ID"""
        response = client.post(
            '/webhooks/99999/some_token',
            json={'message': 'test'}
        )

        assert response.status_code == 404
        data = response.get_json()
        assert data['error'] == 'Webhook not found or disabled'

    def test_disabled_webhook(self, client, test_job):
        """Test webhook for disabled agent"""
        test_job.is_active = False
        db.session.commit()

        response = client.post(
            f'/webhooks/{test_job.id}/test_secret_token_12345678',
            json={'message': 'test'}
        )

        assert response.status_code == 404
        data = response.get_json()
        assert data['error'] == 'Webhook not found or disabled'

    def test_custom_response_status(self, client, test_user):
        """Test custom HTTP response status"""
        job = Job(
            name='Custom Response Webhook',
            job_type='webhook_agent',
            config={
                'secret_token': 'custom_token_1234567890',
                'response_status': 201,
                'response_body': {'status': 'created'}
            },
            user_id=test_user.id,
            is_active=True
        )
        db.session.add(job)
        db.session.commit()

        response = client.post(
            f'/webhooks/{job.id}/custom_token_1234567890',
            json={'data': 'test'}
        )

        assert response.status_code == 201
        data = response.get_json()
        assert data['status'] == 'created'
        assert 'event_id' in data


class TestWebhookSignatureVerification:
    """Tests for HMAC signature verification"""

    def test_valid_signature(self, client, test_user):
        """Test webhook with valid HMAC signature"""
        secret = 'my_hmac_secret'
        job = Job(
            name='Signed Webhook',
            job_type='webhook_agent',
            config={
                'secret_token': 'signed_token_1234567890',
                'verify_signature': True,
                'signature_secret': secret
            },
            user_id=test_user.id,
            is_active=True
        )
        db.session.add(job)
        db.session.commit()

        payload = json.dumps({'message': 'test'}).encode('utf-8')
        signature = 'sha256=' + hmac.new(
            secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()

        response = client.post(
            f'/webhooks/{job.id}/signed_token_1234567890',
            data=payload,
            content_type='application/json',
            headers={'X-Hub-Signature-256': signature}
        )

        assert response.status_code == 200

        # Verify event was created
        event = Event.query.filter_by(agent_id=job.id).first()
        assert event is not None

    def test_invalid_signature(self, client, test_user):
        """Test webhook with invalid HMAC signature"""
        job = Job(
            name='Signed Webhook',
            job_type='webhook_agent',
            config={
                'secret_token': 'signed_token_1234567890',
                'verify_signature': True,
                'signature_secret': 'my_hmac_secret'
            },
            user_id=test_user.id,
            is_active=True
        )
        db.session.add(job)
        db.session.commit()

        payload = json.dumps({'message': 'test'}).encode('utf-8')

        response = client.post(
            f'/webhooks/{job.id}/signed_token_1234567890',
            data=payload,
            content_type='application/json',
            headers={'X-Hub-Signature-256': 'sha256=invalid_signature'}
        )

        assert response.status_code == 403
        data = response.get_json()
        assert data['error'] == 'Invalid signature'

        # Verify no event was created
        event_count = Event.query.filter_by(agent_id=job.id).count()
        assert event_count == 0

    def test_missing_signature(self, client, test_user):
        """Test webhook with signature verification enabled but no signature provided"""
        job = Job(
            name='Signed Webhook',
            job_type='webhook_agent',
            config={
                'secret_token': 'signed_token_1234567890',
                'verify_signature': True,
                'signature_secret': 'my_hmac_secret'
            },
            user_id=test_user.id,
            is_active=True
        )
        db.session.add(job)
        db.session.commit()

        response = client.post(
            f'/webhooks/{job.id}/signed_token_1234567890',
            json={'message': 'test'}
        )

        assert response.status_code == 403


class TestWebhookIPWhitelisting:
    """Tests for IP whitelisting"""

    def test_allowed_ip(self, client, test_user):
        """Test webhook from allowed IP address"""
        job = Job(
            name='IP Restricted Webhook',
            job_type='webhook_agent',
            config={
                'secret_token': 'ip_restricted_token_1234567890',
                'allowed_ips': ['127.0.0.1']
            },
            user_id=test_user.id,
            is_active=True
        )
        db.session.add(job)
        db.session.commit()

        response = client.post(
            f'/webhooks/{job.id}/ip_restricted_token_1234567890',
            json={'message': 'test'}
        )

        assert response.status_code == 200

        # Verify event was created
        event = Event.query.filter_by(agent_id=job.id).first()
        assert event is not None

    def test_blocked_ip(self, client, test_user):
        """Test webhook from non-whitelisted IP address"""
        job = Job(
            name='IP Restricted Webhook',
            job_type='webhook_agent',
            config={
                'secret_token': 'ip_restricted_token_1234567890',
                'allowed_ips': ['192.168.1.1', '10.0.0.1']
            },
            user_id=test_user.id,
            is_active=True
        )
        db.session.add(job)
        db.session.commit()

        response = client.post(
            f'/webhooks/{job.id}/ip_restricted_token_1234567890',
            json={'message': 'test'},
            environ_base={'REMOTE_ADDR': '1.2.3.4'}
        )

        assert response.status_code == 403
        data = response.get_json()
        assert data['error'] == 'IP not allowed'

        # Verify no event was created
        event_count = Event.query.filter_by(agent_id=job.id).count()
        assert event_count == 0


class TestWebhookHeaders:
    """Tests for header capture"""

    def test_capture_headers(self, client, test_user):
        """Test capturing specified headers in event metadata"""
        job = Job(
            name='Header Capture Webhook',
            job_type='webhook_agent',
            config={
                'secret_token': 'header_capture_token_1234567890',
                'include_headers': ['User-Agent', 'X-Request-ID', 'X-Custom-Header']
            },
            user_id=test_user.id,
            is_active=True
        )
        db.session.add(job)
        db.session.commit()

        response = client.post(
            f'/webhooks/{job.id}/header_capture_token_1234567890',
            json={'message': 'test'},
            headers={
                'User-Agent': 'TestClient/1.0',
                'X-Request-ID': 'req-123',
                'X-Custom-Header': 'custom-value',
                'X-Ignored-Header': 'should-not-appear'
            }
        )

        assert response.status_code == 200

        # Verify headers were captured
        event = Event.query.filter_by(agent_id=job.id).first()
        assert event is not None
        assert event.event_metadata['headers']['User-Agent'] == 'TestClient/1.0'
        assert event.event_metadata['headers']['X-Request-ID'] == 'req-123'
        assert event.event_metadata['headers']['X-Custom-Header'] == 'custom-value'
        assert 'X-Ignored-Header' not in event.event_metadata['headers']

    def test_missing_headers(self, client, test_user):
        """Test that missing headers are captured as empty strings"""
        job = Job(
            name='Header Capture Webhook',
            job_type='webhook_agent',
            config={
                'secret_token': 'header_capture_token_1234567890',
                'include_headers': ['X-Missing-Header']
            },
            user_id=test_user.id,
            is_active=True
        )
        db.session.add(job)
        db.session.commit()

        response = client.post(
            f'/webhooks/{job.id}/header_capture_token_1234567890',
            json={'message': 'test'}
        )

        assert response.status_code == 200

        # Verify missing header is empty string
        event = Event.query.filter_by(agent_id=job.id).first()
        assert event is not None
        assert event.event_metadata['headers']['X-Missing-Header'] == ''


class TestWebhookEventMetadata:
    """Tests for webhook event metadata"""

    def test_event_metadata_structure(self, client, test_job):
        """Test that events have correct metadata structure"""
        response = client.post(
            f'/webhooks/{test_job.id}/test_secret_token_12345678',
            json={'message': 'test'},
            headers={'User-Agent': 'TestClient/1.0'}
        )

        assert response.status_code == 200

        event = Event.query.filter_by(agent_id=test_job.id).first()
        assert event is not None

        # Check metadata fields
        assert event.event_metadata['source'] == 'webhook'
        assert 'client_ip' in event.event_metadata
        assert 'received_at' in event.event_metadata
        assert 'content_type' in event.event_metadata
        assert 'headers' in event.event_metadata

    def test_event_user_assignment(self, client, test_job, test_user):
        """Test that events are assigned to correct user"""
        response = client.post(
            f'/webhooks/{test_job.id}/test_secret_token_12345678',
            json={'message': 'test'}
        )

        assert response.status_code == 200

        event = Event.query.filter_by(agent_id=test_job.id).first()
        assert event is not None
        assert event.user_id == test_user.id
        assert event.agent_id == test_job.id


class TestWebhookConfigSchema:
    """Tests for webhook agent configuration schema"""

    def test_config_schema_structure(self):
        """Test that config schema has correct structure"""
        schema = WebhookAgent.get_config_schema()

        assert 'required_fields' in schema
        assert 'optional_fields' in schema
        assert len(schema['required_fields']) == 0  # All fields are optional

        # Check that key fields are present
        field_names = [f['name'] for f in schema['optional_fields']]
        assert 'secret_token' in field_names
        assert 'verify_signature' in field_names
        assert 'signature_secret' in field_names
        assert 'allowed_ips' in field_names
        assert 'include_headers' in field_names
        assert 'response_status' in field_names
        assert 'response_body' in field_names

    def test_secret_token_auto_generate_flag(self):
        """Test that secret_token field has auto_generate flag"""
        schema = WebhookAgent.get_config_schema()

        secret_token_field = next(
            f for f in schema['optional_fields'] if f['name'] == 'secret_token'
        )

        assert secret_token_field['auto_generate'] == True
