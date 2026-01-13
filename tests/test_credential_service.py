"""Tests for credential service"""
import pytest
from app.services.credential_service import CredentialService
from app.models import Credential, User
from app.utils.encryption import ConfigEncryption
from app.extensions import db
from sqlalchemy.orm.exc import NoResultFound


class TestCredentialService:
    """Test credential service operations"""

    def test_create_credential(self, app, test_user):
        """Test creating an encrypted credential"""
        with app.app_context():
            service = CredentialService()

            credential = service.create_credential(
                user_id=test_user.id,
                name='test_api_key',
                value='secret_value_123',
                description='Test credential'
            )

            assert credential.id is not None
            assert credential.name == 'test_api_key'
            assert credential.description == 'Test credential'
            assert credential.encrypted_value != 'secret_value_123'  # Should be encrypted
            assert credential.salt is not None
            assert len(credential.salt) > 0
            assert credential.user_id == test_user.id

    def test_create_duplicate_credential_raises_error(self, app, test_user):
        """Test that creating duplicate credential raises ValueError"""
        with app.app_context():
            service = CredentialService()

            # Create first credential
            service.create_credential(
                user_id=test_user.id,
                name='duplicate_key',
                value='value1'
            )

            # Attempt to create duplicate
            with pytest.raises(ValueError, match="already exists"):
                service.create_credential(
                    user_id=test_user.id,
                    name='duplicate_key',
                    value='value2'
                )

    def test_get_credential(self, app, test_user):
        """Test retrieving a credential by name"""
        with app.app_context():
            service = CredentialService()

            # Create credential
            created = service.create_credential(
                user_id=test_user.id,
                name='test_key',
                value='test_value'
            )

            # Retrieve it
            retrieved = service.get_credential(test_user.id, 'test_key')

            assert retrieved is not None
            assert retrieved.id == created.id
            assert retrieved.name == 'test_key'

    def test_get_nonexistent_credential_returns_none(self, app, test_user):
        """Test that getting nonexistent credential returns None"""
        with app.app_context():
            service = CredentialService()

            credential = service.get_credential(test_user.id, 'nonexistent')

            assert credential is None

    def test_get_credentials_for_user(self, app, test_user):
        """Test getting all credentials for a user"""
        with app.app_context():
            service = CredentialService()

            # Create multiple credentials
            service.create_credential(test_user.id, 'key1', 'value1')
            service.create_credential(test_user.id, 'key2', 'value2')
            service.create_credential(test_user.id, 'key3', 'value3')

            # Retrieve all
            credentials = service.get_credentials_for_user(test_user.id)

            assert len(credentials) == 3
            names = [c.name for c in credentials]
            assert 'key1' in names
            assert 'key2' in names
            assert 'key3' in names

    def test_get_decrypted_value(self, app, test_user):
        """Test decrypting a credential value"""
        with app.app_context():
            service = CredentialService()

            # Create credential with known value
            credential = service.create_credential(
                user_id=test_user.id,
                name='test_key',
                value='my_secret_password'
            )

            # Decrypt and verify
            decrypted = service.get_decrypted_value(credential)

            assert decrypted == 'my_secret_password'

    def test_get_decrypted_value_updates_last_used(self, app, test_user):
        """Test that decrypting a credential updates last_used_at"""
        with app.app_context():
            service = CredentialService()

            credential = service.create_credential(
                user_id=test_user.id,
                name='test_key',
                value='test_value'
            )

            assert credential.last_used_at is None

            # Decrypt
            service.get_decrypted_value(credential)

            # Refresh from DB
            db.session.refresh(credential)

            assert credential.last_used_at is not None

    def test_update_credential_value(self, app, test_user):
        """Test updating credential value"""
        with app.app_context():
            service = CredentialService()

            # Create credential
            credential = service.create_credential(
                user_id=test_user.id,
                name='test_key',
                value='old_value'
            )

            original_salt = credential.salt

            # Update value
            updated = service.update_credential(
                credential_id=credential.id,
                user_id=test_user.id,
                value='new_value'
            )

            # Verify new value
            decrypted = service.get_decrypted_value(updated)
            assert decrypted == 'new_value'

            # Verify salt changed (new salt for new value)
            assert updated.salt != original_salt

    def test_update_credential_description(self, app, test_user):
        """Test updating credential description only"""
        with app.app_context():
            service = CredentialService()

            credential = service.create_credential(
                user_id=test_user.id,
                name='test_key',
                value='test_value',
                description='Old description'
            )

            original_encrypted = credential.encrypted_value
            original_salt = credential.salt

            # Update description only
            updated = service.update_credential(
                credential_id=credential.id,
                user_id=test_user.id,
                description='New description'
            )

            assert updated.description == 'New description'
            # Value should not change
            assert updated.encrypted_value == original_encrypted
            assert updated.salt == original_salt

    def test_update_nonexistent_credential_raises_error(self, app, test_user):
        """Test that updating nonexistent credential raises error"""
        with app.app_context():
            service = CredentialService()

            with pytest.raises(NoResultFound):
                service.update_credential(
                    credential_id=99999,
                    user_id=test_user.id,
                    value='new_value'
                )

    def test_delete_credential(self, app, test_user):
        """Test deleting a credential"""
        with app.app_context():
            service = CredentialService()

            credential = service.create_credential(
                user_id=test_user.id,
                name='to_delete',
                value='test_value'
            )

            credential_id = credential.id

            # Delete
            result = service.delete_credential(credential_id, test_user.id)

            assert result is True

            # Verify deleted
            deleted = service.get_credential(test_user.id, 'to_delete')
            assert deleted is None

    def test_delete_nonexistent_credential_returns_false(self, app, test_user):
        """Test that deleting nonexistent credential returns False"""
        with app.app_context():
            service = CredentialService()

            result = service.delete_credential(99999, test_user.id)

            assert result is False

    def test_resolve_credentials_in_simple_config(self, app, test_user):
        """Test resolving credential references in a simple config"""
        with app.app_context():
            service = CredentialService()

            # Create credentials
            service.create_credential(test_user.id, 'api_key', 'abc123')

            config = {
                'url': 'https://api.example.com',
                'api_key': '{{credential:api_key}}'
            }

            resolved = service.resolve_credentials_in_config(config, test_user.id)

            assert resolved['url'] == 'https://api.example.com'
            assert resolved['api_key'] == 'abc123'

    def test_resolve_credentials_in_nested_config(self, app, test_user):
        """Test resolving credential references in nested config"""
        with app.app_context():
            service = CredentialService()

            # Create credentials
            service.create_credential(test_user.id, 'api_key', 'abc123')
            service.create_credential(test_user.id, 'password', 'secret')

            config = {
                'url': 'https://api.example.com',
                'headers': {
                    'Authorization': 'Bearer {{credential:api_key}}'
                },
                'auth': {
                    'username': 'admin',
                    'password': '{{credential:password}}'
                }
            }

            resolved = service.resolve_credentials_in_config(config, test_user.id)

            assert resolved['headers']['Authorization'] == 'Bearer abc123'
            assert resolved['auth']['password'] == 'secret'
            assert resolved['auth']['username'] == 'admin'  # Non-credential value unchanged

    def test_resolve_credentials_in_list_config(self, app, test_user):
        """Test resolving credential references in config with lists"""
        with app.app_context():
            service = CredentialService()

            service.create_credential(test_user.id, 'token1', 'token_abc')
            service.create_credential(test_user.id, 'token2', 'token_xyz')

            config = {
                'tokens': [
                    '{{credential:token1}}',
                    '{{credential:token2}}',
                    'static_token'
                ]
            }

            resolved = service.resolve_credentials_in_config(config, test_user.id)

            assert resolved['tokens'][0] == 'token_abc'
            assert resolved['tokens'][1] == 'token_xyz'
            assert resolved['tokens'][2] == 'static_token'

    def test_resolve_credentials_partial_string(self, app, test_user):
        """Test resolving credential reference within a larger string"""
        with app.app_context():
            service = CredentialService()

            service.create_credential(test_user.id, 'api_key', 'abc123')

            config = {
                'auth_header': 'Bearer {{credential:api_key}}'
            }

            resolved = service.resolve_credentials_in_config(config, test_user.id)

            assert resolved['auth_header'] == 'Bearer abc123'

    def test_resolve_missing_credential_raises_error(self, app, test_user):
        """Test that missing credential reference raises ValueError"""
        with app.app_context():
            service = CredentialService()

            config = {
                'api_key': '{{credential:nonexistent}}'
            }

            with pytest.raises(ValueError, match="Credential 'nonexistent' not found"):
                service.resolve_credentials_in_config(config, test_user.id)

    def test_find_credential_references(self, app):
        """Test finding all credential references in a config"""
        with app.app_context():
            service = CredentialService()

            config = {
                'api_key': '{{credential:weather_api}}',
                'headers': {
                    'Authorization': 'Bearer {{credential:auth_token}}'
                },
                'data': {
                    'password': '{{credential:db_password}}'
                },
                'static': 'no_credential_here'
            }

            references = service.find_credential_references(config)

            assert len(references) == 3
            assert 'weather_api' in references
            assert 'auth_token' in references
            assert 'db_password' in references

    def test_find_credential_references_empty_config(self, app):
        """Test finding credential references in config without any"""
        with app.app_context():
            service = CredentialService()

            config = {
                'url': 'https://example.com',
                'timeout': 30
            }

            references = service.find_credential_references(config)

            assert len(references) == 0

    def test_user_isolation(self, app, test_user, test_user2):
        """Test that users cannot access each other's credentials"""
        with app.app_context():
            service = CredentialService()

            # User 1 creates a credential
            service.create_credential(
                user_id=test_user.id,
                name='user1_key',
                value='user1_value'
            )

            # User 2 should not be able to get it
            credential = service.get_credential(test_user2.id, 'user1_key')

            assert credential is None

    def test_credential_name_validation(self, app, test_user):
        """Test that credential names are validated properly"""
        with app.app_context():
            service = CredentialService()

            # Valid names
            valid_names = ['api_key', 'API-KEY', 'key123', 'my-api_key-2']

            for name in valid_names:
                service.create_credential(
                    user_id=test_user.id,
                    name=name,
                    value='test'
                )

            credentials = service.get_credentials_for_user(test_user.id)
            assert len(credentials) == len(valid_names)


class TestConfigEncryption:
    """Test encryption utility functions"""

    def test_generate_salt(self, app):
        """Test salt generation"""
        with app.app_context():
            salt1 = ConfigEncryption.generate_salt()
            salt2 = ConfigEncryption.generate_salt()

            assert salt1 != salt2  # Salts should be unique
            assert len(salt1) > 0
            assert len(salt2) > 0

    def test_encrypt_decrypt_credential(self, app):
        """Test encrypting and decrypting a credential"""
        with app.app_context():
            original_value = 'my_secret_password'

            # Encrypt
            encrypted, salt = ConfigEncryption.encrypt_credential(original_value)

            assert encrypted != original_value
            assert salt is not None

            # Decrypt
            decrypted = ConfigEncryption.decrypt_credential(encrypted, salt)

            assert decrypted == original_value

    def test_different_salts_produce_different_ciphertexts(self, app):
        """Test that same value with different salts produces different ciphertext"""
        with app.app_context():
            value = 'same_password'

            encrypted1, salt1 = ConfigEncryption.encrypt_credential(value)
            encrypted2, salt2 = ConfigEncryption.encrypt_credential(value)

            assert salt1 != salt2
            assert encrypted1 != encrypted2

            # But both should decrypt to same value
            assert ConfigEncryption.decrypt_credential(encrypted1, salt1) == value
            assert ConfigEncryption.decrypt_credential(encrypted2, salt2) == value

    def test_mask_credential_value(self, app):
        """Test masking credential values for display"""
        with app.app_context():
            # Long value
            masked = ConfigEncryption.mask_credential_value('abcdefghijklmnop')
            assert masked.startswith('ab')
            assert masked.endswith('op')
            assert '*' in masked
            assert 'cdefghijklmn' not in masked

            # Short value
            masked_short = ConfigEncryption.mask_credential_value('abc')
            assert masked_short == '***'

            # Empty value
            masked_empty = ConfigEncryption.mask_credential_value('')
            assert masked_empty == ''
