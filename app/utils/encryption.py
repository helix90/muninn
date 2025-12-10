"""
Encryption utilities for sensitive job configuration data
"""

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2
from base64 import urlsafe_b64encode
from flask import current_app


class ConfigEncryption:
    """Handles encryption/decryption of sensitive configuration fields."""

    # Fields that should be encrypted for each job type
    # Extensible design - easy to add more sensitive fields later
    SENSITIVE_FIELDS = {
        'email_sender': ['password'],  # Only passwords for now
        'web_scraper': [],  # Future: API keys, tokens
        'rss_reader': [],  # Future: authentication credentials
        'filter': []
    }

    @staticmethod
    def get_cipher():
        """
        Get Fernet cipher from app SECRET_KEY.

        Returns:
            Fernet: Cipher instance for encryption/decryption
        """
        secret_key = current_app.config['SECRET_KEY'].encode()

        # Derive 32-byte key from SECRET_KEY using PBKDF2
        kdf = PBKDF2(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'muninn_encryption_salt',  # Fixed salt for deterministic key derivation
            iterations=100000,
        )
        key = urlsafe_b64encode(kdf.derive(secret_key))
        return Fernet(key)

    @classmethod
    def encrypt_config(cls, job_type: str, config: dict) -> dict:
        """
        Encrypt sensitive fields in job configuration.

        Args:
            job_type: Type of job
            config: Job configuration dictionary

        Returns:
            dict: Configuration with sensitive fields encrypted
        """
        if job_type not in cls.SENSITIVE_FIELDS:
            return config

        sensitive_fields = cls.SENSITIVE_FIELDS[job_type]
        if not sensitive_fields:
            return config

        encrypted_config = config.copy()
        cipher = cls.get_cipher()

        for field in sensitive_fields:
            if field in encrypted_config and encrypted_config[field]:
                value = encrypted_config[field]
                if isinstance(value, str) and not value.startswith("enc:"):
                    # Encrypt and prefix with "enc:"
                    encrypted_value = cipher.encrypt(value.encode()).decode()
                    encrypted_config[field] = f"enc:{encrypted_value}"

        return encrypted_config

    @classmethod
    def decrypt_config(cls, job_type: str, config: dict) -> dict:
        """
        Decrypt sensitive fields in job configuration.

        Args:
            job_type: Type of job
            config: Job configuration dictionary

        Returns:
            dict: Configuration with sensitive fields decrypted
        """
        if job_type not in cls.SENSITIVE_FIELDS:
            return config

        sensitive_fields = cls.SENSITIVE_FIELDS[job_type]
        if not sensitive_fields:
            return config

        decrypted_config = config.copy()
        cipher = cls.get_cipher()

        for field in sensitive_fields:
            if field in decrypted_config and decrypted_config[field]:
                value = decrypted_config[field]
                if isinstance(value, str) and value.startswith("enc:"):
                    encrypted_value = value[4:]  # Remove "enc:" prefix
                    try:
                        decrypted_value = cipher.decrypt(encrypted_value.encode()).decode()
                        decrypted_config[field] = decrypted_value
                    except Exception as e:
                        # Log error but don't crash - leave encrypted value
                        current_app.logger.error(f"Failed to decrypt field {field}: {e}")

        return decrypted_config

    @classmethod
    def is_encrypted(cls, value: str) -> bool:
        """
        Check if a value is encrypted.

        Args:
            value: Value to check

        Returns:
            bool: True if value is encrypted (has "enc:" prefix)
        """
        return isinstance(value, str) and value.startswith("enc:")
