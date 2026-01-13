"""Tests for credential views (web UI)"""
import pytest
from flask import url_for
from app.models import Credential
from app.services.credential_service import CredentialService
from app.extensions import db


class TestCredentialListView:
    """Test credential list view"""

    def test_credential_list_requires_login(self, client):
        """Test that credential list page requires authentication"""
        response = client.get('/credentials/')

        # Should redirect to login
        assert response.status_code == 302
        assert '/login' in response.location or 'login' in response.location.lower()

    def test_credential_list_shows_credentials(self, client, auth_client, test_user, app):
        """Test that credential list shows user's credentials"""
        with app.app_context():
            # Create some credentials
            service = CredentialService()
            service.create_credential(test_user.id, 'api_key', 'secret123', 'API Key')
            service.create_credential(test_user.id, 'password', 'pass456', 'Database Password')

        response = auth_client.get('/credentials/')

        assert response.status_code == 200
        assert b'api_key' in response.data
        assert b'password' in response.data
        assert b'API Key' in response.data
        assert b'Database Password' in response.data
        # Values should NOT be visible
        assert b'secret123' not in response.data
        assert b'pass456' not in response.data

    def test_credential_list_empty_state(self, client, auth_client):
        """Test credential list shows empty state when no credentials"""
        response = auth_client.get('/credentials/')

        assert response.status_code == 200
        assert b'No credentials yet' in response.data or b'no credentials' in response.data.lower()

    def test_credential_list_user_isolation(self, client, auth_client, auth_client2, test_user, test_user2, app):
        """Test that users only see their own credentials"""
        with app.app_context():
            service = CredentialService()
            # User 1 creates a credential
            service.create_credential(test_user.id, 'user1_key', 'secret1', 'User 1 Key')
            # User 2 creates a credential
            service.create_credential(test_user2.id, 'user2_key', 'secret2', 'User 2 Key')

        # User 1 sees only their credential
        response = auth_client.get('/credentials/')
        assert b'user1_key' in response.data
        assert b'user2_key' not in response.data

        # User 2 sees only their credential
        response = auth_client2.get('/credentials/')
        assert b'user2_key' in response.data
        assert b'user1_key' not in response.data


class TestCredentialCreateView:
    """Test credential creation view"""

    def test_create_credential_get_requires_login(self, client):
        """Test that create credential GET requires authentication"""
        response = client.get('/credentials/create')

        assert response.status_code == 302
        assert '/login' in response.location or 'login' in response.location.lower()

    def test_create_credential_get_shows_form(self, client, auth_client):
        """Test that create credential GET shows the form"""
        response = auth_client.get('/credentials/create')

        assert response.status_code == 200
        assert b'name' in response.data.lower()
        assert b'value' in response.data.lower()
        assert b'description' in response.data.lower()

    def test_create_credential_post_requires_login(self, client):
        """Test that create credential POST requires authentication"""
        response = client.post('/credentials/create', data={
            'name': 'test_key',
            'value': 'test_value'
        })

        assert response.status_code == 302
        assert '/login' in response.location or 'login' in response.location.lower()

    def test_create_credential_post_valid_data(self, client, auth_client, test_user, app):
        """Test creating a credential with valid data"""
        response = auth_client.post('/credentials/create', data={
            'name': 'new_api_key',
            'value': 'secret_value_123',
            'description': 'My API Key'
        }, follow_redirects=True)

        assert response.status_code == 200

        # Verify credential was created
        with app.app_context():
            service = CredentialService()
            credential = service.get_credential(test_user.id, 'new_api_key')

            assert credential is not None
            assert credential.name == 'new_api_key'
            assert credential.description == 'My API Key'

            # Verify value can be decrypted
            decrypted = service.get_decrypted_value(credential)
            assert decrypted == 'secret_value_123'

    def test_create_credential_post_without_description(self, client, auth_client, test_user, app):
        """Test creating a credential without description"""
        response = auth_client.post('/credentials/create', data={
            'name': 'no_desc_key',
            'value': 'secret_value'
        }, follow_redirects=True)

        assert response.status_code == 200

        with app.app_context():
            service = CredentialService()
            credential = service.get_credential(test_user.id, 'no_desc_key')

            assert credential is not None
            assert credential.description is None or credential.description == ''

    def test_create_credential_post_missing_name(self, client, auth_client):
        """Test creating a credential without name fails"""
        response = auth_client.post('/credentials/create', data={
            'value': 'secret_value'
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b'required' in response.data.lower() or b'error' in response.data.lower()

    def test_create_credential_post_missing_value(self, client, auth_client):
        """Test creating a credential without value fails"""
        response = auth_client.post('/credentials/create', data={
            'name': 'test_key'
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b'required' in response.data.lower() or b'error' in response.data.lower()

    def test_create_credential_post_invalid_name(self, client, auth_client):
        """Test creating a credential with invalid name fails"""
        response = auth_client.post('/credentials/create', data={
            'name': 'invalid name with spaces!',
            'value': 'secret_value'
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b'letter' in response.data.lower() or b'invalid' in response.data.lower()

    def test_create_credential_post_duplicate_name(self, client, auth_client, test_user, app):
        """Test creating a credential with duplicate name fails"""
        with app.app_context():
            service = CredentialService()
            service.create_credential(test_user.id, 'existing_key', 'value1')

        response = auth_client.post('/credentials/create', data={
            'name': 'existing_key',
            'value': 'value2'
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b'already exists' in response.data.lower() or b'duplicate' in response.data.lower()


class TestCredentialEditView:
    """Test credential editing view"""

    def test_edit_credential_get_requires_login(self, client, test_user, app):
        """Test that edit credential GET requires authentication"""
        with app.app_context():
            service = CredentialService()
            credential = service.create_credential(test_user.id, 'test_key', 'value')

        response = client.get(f'/credentials/{credential.id}/edit')

        assert response.status_code == 302
        assert '/login' in response.location or 'login' in response.location.lower()

    def test_edit_credential_get_shows_form(self, client, auth_client, test_user, app):
        """Test that edit credential GET shows the form with current data"""
        with app.app_context():
            service = CredentialService()
            credential = service.create_credential(
                test_user.id,
                'test_key',
                'secret_value',
                'Test Description'
            )
            credential_id = credential.id

        response = auth_client.get(f'/credentials/{credential_id}/edit')

        assert response.status_code == 200
        assert b'test_key' in response.data
        assert b'Test Description' in response.data
        # Value should NOT be visible
        assert b'secret_value' not in response.data

    def test_edit_credential_get_nonexistent(self, client, auth_client):
        """Test editing nonexistent credential returns 404 or redirects"""
        response = auth_client.get('/credentials/99999/edit')

        # Should either be 404 or redirect with error
        assert response.status_code in [302, 404]

    def test_edit_credential_post_requires_login(self, client, test_user, app):
        """Test that edit credential POST requires authentication"""
        with app.app_context():
            service = CredentialService()
            credential = service.create_credential(test_user.id, 'test_key', 'value')

        response = client.post(f'/credentials/{credential.id}/edit', data={
            'description': 'New description'
        })

        assert response.status_code == 302
        assert '/login' in response.location or 'login' in response.location.lower()

    def test_edit_credential_post_update_value(self, client, auth_client, test_user, app):
        """Test updating credential value"""
        with app.app_context():
            service = CredentialService()
            credential = service.create_credential(test_user.id, 'test_key', 'old_value')
            credential_id = credential.id

        response = auth_client.post(f'/credentials/{credential_id}/edit', data={
            'value': 'new_value',
            'description': 'Updated'
        }, follow_redirects=True)

        assert response.status_code == 200

        # Verify value was updated
        with app.app_context():
            service = CredentialService()
            credential = db.session.query(Credential).get(credential_id)
            decrypted = service.get_decrypted_value(credential)

            assert decrypted == 'new_value'
            assert credential.description == 'Updated'

    def test_edit_credential_post_update_description_only(self, client, auth_client, test_user, app):
        """Test updating only description keeps value unchanged"""
        with app.app_context():
            service = CredentialService()
            credential = service.create_credential(
                test_user.id,
                'test_key',
                'original_value',
                'Old description'
            )
            credential_id = credential.id
            original_encrypted = credential.encrypted_value

        response = auth_client.post(f'/credentials/{credential_id}/edit', data={
            'description': 'New description'
            # No value provided
        }, follow_redirects=True)

        assert response.status_code == 200

        with app.app_context():
            service = CredentialService()
            credential = db.session.query(Credential).get(credential_id)

            assert credential.description == 'New description'
            # Value should be unchanged
            decrypted = service.get_decrypted_value(credential)
            assert decrypted == 'original_value'

    def test_edit_credential_user_isolation(self, client, auth_client, auth_client2, test_user, test_user2, app):
        """Test that users cannot edit other users' credentials"""
        with app.app_context():
            service = CredentialService()
            # User 1 creates a credential
            credential = service.create_credential(test_user.id, 'user1_key', 'secret')
            credential_id = credential.id

        # User 2 tries to edit User 1's credential
        response = auth_client2.get(f'/credentials/{credential_id}/edit')

        # Should either be 404 or redirect with error
        assert response.status_code in [302, 404]


class TestCredentialDeleteView:
    """Test credential deletion view"""

    def test_delete_credential_requires_login(self, client, test_user, app):
        """Test that delete credential requires authentication"""
        with app.app_context():
            service = CredentialService()
            credential = service.create_credential(test_user.id, 'test_key', 'value')

        response = client.post(f'/credentials/{credential.id}/delete')

        assert response.status_code == 302
        assert '/login' in response.location or 'login' in response.location.lower()

    def test_delete_credential_success(self, client, auth_client, test_user, app):
        """Test successfully deleting a credential"""
        with app.app_context():
            service = CredentialService()
            credential = service.create_credential(test_user.id, 'to_delete', 'value')
            credential_id = credential.id

        response = auth_client.post(f'/credentials/{credential_id}/delete', follow_redirects=True)

        assert response.status_code == 200

        # Verify credential was deleted
        with app.app_context():
            service = CredentialService()
            deleted = service.get_credential(test_user.id, 'to_delete')

            assert deleted is None

    def test_delete_nonexistent_credential(self, client, auth_client):
        """Test deleting nonexistent credential"""
        response = auth_client.post('/credentials/99999/delete', follow_redirects=True)

        # Should redirect with error message
        assert response.status_code == 200

    def test_delete_credential_user_isolation(self, client, auth_client, auth_client2, test_user, test_user2, app):
        """Test that users cannot delete other users' credentials"""
        with app.app_context():
            service = CredentialService()
            # User 1 creates a credential
            credential = service.create_credential(test_user.id, 'user1_key', 'secret')
            credential_id = credential.id

        # User 2 tries to delete User 1's credential
        response = auth_client2.post(f'/credentials/{credential_id}/delete', follow_redirects=True)

        # Verify credential still exists
        with app.app_context():
            service = CredentialService()
            credential = service.get_credential(test_user.id, 'user1_key')

            assert credential is not None


class TestCredentialIntegration:
    """Integration tests for credentials with agents"""

    def test_agent_uses_credential(self, client, auth_client, test_user, app):
        """Test that agents can use credentials in their config"""
        with app.app_context():
            from app.models import Job
            from app.services.agent_service import AgentService

            # Create a credential
            credential_service = CredentialService()
            credential_service.create_credential(
                test_user.id,
                'test_api_key',
                'secret_api_key_123'
            )

            # Create an agent that uses the credential
            agent = Job(
                name='Test Agent',
                job_type='rss',
                user_id=test_user.id,
                config={
                    'url': 'https://example.com/feed',
                    'api_key': '{{credential:test_api_key}}'
                },
                enabled=False
            )
            db.session.add(agent)
            db.session.commit()

            agent_id = agent.id

        # Verify the agent config has credential reference
        with app.app_context():
            agent = db.session.query(Job).get(agent_id)
            assert agent.config['api_key'] == '{{credential:test_api_key}}'

            # Resolve credentials
            credential_service = CredentialService()
            resolved_config = credential_service.resolve_credentials_in_config(
                agent.config,
                test_user.id
            )

            # Verify credential was resolved
            assert resolved_config['api_key'] == 'secret_api_key_123'

    def test_agent_with_missing_credential_fails(self, client, auth_client, test_user, app):
        """Test that agent with missing credential raises error"""
        with app.app_context():
            from app.models import Job
            from app.services.credential_service import CredentialService

            # Create an agent that references nonexistent credential
            agent = Job(
                name='Test Agent',
                job_type='rss',
                user_id=test_user.id,
                config={
                    'url': 'https://example.com/feed',
                    'api_key': '{{credential:nonexistent}}'
                },
                enabled=False
            )
            db.session.add(agent)
            db.session.commit()

            # Try to resolve credentials
            credential_service = CredentialService()

            with pytest.raises(ValueError, match="not found"):
                credential_service.resolve_credentials_in_config(
                    agent.config,
                    test_user.id
                )
