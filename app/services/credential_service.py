"""Service for managing credentials"""
import re
import logging
from typing import Dict, Any, Optional, List
from flask import current_app
from sqlalchemy.orm.exc import NoResultFound
from app.extensions import db
from app.models import Credential
from app.utils.encryption import ConfigEncryption

logger = logging.getLogger(__name__)

# Regex pattern to match {{credential:name}}
CREDENTIAL_PATTERN = re.compile(r'\{\{credential:([a-zA-Z0-9_-]+)\}\}')


class CredentialService:
    """Service for credential operations"""

    def __init__(self, db_session=None):
        self.db_session = db_session or db.session

    def create_credential(self, user_id: int, name: str, value: str,
                         description: str = None) -> Credential:
        """Create a new encrypted credential

        Args:
            user_id: ID of the user who owns this credential
            name: Name of the credential (used in {{credential:name}} references)
            value: The actual credential value to encrypt
            description: Optional description of the credential

        Returns:
            Credential: The created credential object

        Raises:
            ValueError: If credential name already exists for this user
        """
        # Check for duplicate
        existing = self.get_credential(user_id, name)
        if existing:
            raise ValueError(f"Credential '{name}' already exists for this user")

        # Encrypt the value
        encrypted_value, salt = ConfigEncryption.encrypt_credential(value)

        # Create credential
        credential = Credential(
            user_id=user_id,
            name=name,
            encrypted_value=encrypted_value,
            salt=salt,
            description=description
        )

        self.db_session.add(credential)
        self.db_session.commit()

        logger.info(f"Created credential '{name}' for user {user_id}")
        return credential

    def get_credential(self, user_id: int, name: str) -> Optional[Credential]:
        """Get a credential by name for a user

        Args:
            user_id: ID of the user
            name: Name of the credential

        Returns:
            Credential or None: The credential if found, None otherwise
        """
        return self.db_session.query(Credential).filter_by(
            user_id=user_id,
            name=name
        ).first()

    def get_credentials_for_user(self, user_id: int) -> List[Credential]:
        """Get all credentials for a user

        Args:
            user_id: ID of the user

        Returns:
            List[Credential]: List of all credentials owned by the user
        """
        return self.db_session.query(Credential).filter_by(
            user_id=user_id
        ).order_by(Credential.name).all()

    def update_credential(self, credential_id: int, user_id: int,
                         value: str = None, description: str = None) -> Credential:
        """Update a credential

        Args:
            credential_id: ID of the credential to update
            user_id: ID of the user (for authorization check)
            value: New credential value (if None, value is not changed)
            description: New description (if None, description is not changed)

        Returns:
            Credential: The updated credential

        Raises:
            NoResultFound: If credential not found for this user
        """
        credential = self.db_session.query(Credential).filter_by(
            id=credential_id,
            user_id=user_id
        ).first()

        if not credential:
            raise NoResultFound(f"Credential {credential_id} not found")

        if value is not None:
            # Re-encrypt with new salt
            encrypted_value, salt = ConfigEncryption.encrypt_credential(value)
            credential.encrypted_value = encrypted_value
            credential.salt = salt

        if description is not None:
            credential.description = description

        self.db_session.commit()
        logger.info(f"Updated credential '{credential.name}' for user {user_id}")
        return credential

    def delete_credential(self, credential_id: int, user_id: int) -> bool:
        """Delete a credential

        Args:
            credential_id: ID of the credential to delete
            user_id: ID of the user (for authorization check)

        Returns:
            bool: True if deleted, False if not found
        """
        credential = self.db_session.query(Credential).filter_by(
            id=credential_id,
            user_id=user_id
        ).first()

        if not credential:
            return False

        name = credential.name
        self.db_session.delete(credential)
        self.db_session.commit()

        logger.info(f"Deleted credential '{name}' for user {user_id}")
        return True

    def get_decrypted_value(self, credential: Credential) -> str:
        """Get the decrypted value of a credential

        Args:
            credential: The credential object

        Returns:
            str: The decrypted credential value

        Raises:
            ValueError: If decryption fails
        """
        try:
            value = ConfigEncryption.decrypt_credential(
                credential.encrypted_value,
                credential.salt
            )

            # Update last_used_at
            from datetime import datetime
            credential.last_used_at = datetime.utcnow()
            self.db_session.commit()

            return value
        except Exception as e:
            logger.error(f"Failed to decrypt credential '{credential.name}': {e}")
            raise ValueError(f"Failed to decrypt credential '{credential.name}'")

    def resolve_credentials_in_config(self, config: Dict[str, Any],
                                     user_id: int) -> Dict[str, Any]:
        """Resolve all {{credential:name}} references in a config dict

        Recursively searches through the config and replaces credential
        references with actual decrypted values.

        Args:
            config: Configuration dictionary (may contain nested dicts/lists)
            user_id: ID of the user who owns the credentials

        Returns:
            Dict[str, Any]: Configuration with all credential references resolved

        Raises:
            ValueError: If a referenced credential is not found
        """
        if isinstance(config, dict):
            resolved = {}
            for key, value in config.items():
                resolved[key] = self.resolve_credentials_in_config(value, user_id)
            return resolved
        elif isinstance(config, list):
            return [self.resolve_credentials_in_config(item, user_id) for item in config]
        elif isinstance(config, str):
            return self._resolve_credential_string(config, user_id)
        else:
            return config

    def _resolve_credential_string(self, value: str, user_id: int) -> str:
        """Resolve credential references in a string

        Args:
            value: String that may contain {{credential:name}} references
            user_id: ID of the user who owns the credentials

        Returns:
            str: String with all credential references replaced with actual values

        Raises:
            ValueError: If a referenced credential is not found
        """
        def replace_credential(match):
            cred_name = match.group(1)
            credential = self.get_credential(user_id, cred_name)

            if not credential:
                error_msg = f"Credential '{cred_name}' not found for user {user_id}"
                logger.error(error_msg)
                raise ValueError(error_msg)

            return self.get_decrypted_value(credential)

        return CREDENTIAL_PATTERN.sub(replace_credential, value)

    def find_credential_references(self, config: Dict[str, Any]) -> List[str]:
        """Find all credential references in a config (for validation)

        Args:
            config: Configuration dictionary to search

        Returns:
            List[str]: List of unique credential names referenced in the config
        """
        references = []

        def search(obj):
            if isinstance(obj, dict):
                for value in obj.values():
                    search(value)
            elif isinstance(obj, list):
                for item in obj:
                    search(item)
            elif isinstance(obj, str):
                matches = CREDENTIAL_PATTERN.findall(obj)
                references.extend(matches)

        search(config)
        return list(set(references))  # Return unique references
