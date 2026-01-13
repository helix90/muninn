"""
Encryption utilities for sensitive job configuration data
"""

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
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

        # Derive 32-byte key from SECRET_KEY using PBKDF2HMAC
        kdf = PBKDF2HMAC(
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

    # New methods for per-credential encryption with unique salts

    @staticmethod
    def generate_salt() -> str:
        """
        Generate a random salt for each credential.

        Returns:
            str: Base64-encoded random salt
        """
        import secrets
        from base64 import urlsafe_b64encode
        return urlsafe_b64encode(secrets.token_bytes(16)).decode('utf-8')

    @classmethod
    def get_cipher_with_salt(cls, salt: str):
        """
        Get Fernet cipher with a specific salt.

        Args:
            salt: Salt string to use for key derivation

        Returns:
            Fernet: Cipher instance for encryption/decryption
        """
        secret_key = current_app.config['SECRET_KEY'].encode()

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt.encode('utf-8'),
            iterations=100000,
        )
        key = urlsafe_b64encode(kdf.derive(secret_key))
        return Fernet(key)

    @classmethod
    def encrypt_credential(cls, value: str, salt: str = None) -> tuple:
        """
        Encrypt a credential value with optional salt.

        Args:
            value: The credential value to encrypt
            salt: Optional salt (if None, generates a new one)

        Returns:
            tuple: (encrypted_value, salt)
        """
        if salt is None:
            salt = cls.generate_salt()

        cipher = cls.get_cipher_with_salt(salt)
        encrypted = cipher.encrypt(value.encode('utf-8'))
        return encrypted.decode('utf-8'), salt

    @classmethod
    def decrypt_credential(cls, encrypted_value: str, salt: str) -> str:
        """
        Decrypt a credential value using its salt.

        Args:
            encrypted_value: The encrypted credential value
            salt: The salt used for encryption

        Returns:
            str: Decrypted credential value
        """
        cipher = cls.get_cipher_with_salt(salt)
        decrypted = cipher.decrypt(encrypted_value.encode('utf-8'))
        return decrypted.decode('utf-8')

    @staticmethod
    def mask_credential_value(value: str) -> str:
        """
        Mask credential value for display/logging.

        Args:
            value: The credential value to mask

        Returns:
            str: Masked value showing only first 2 and last 2 characters
        """
        if not value:
            return ''
        if len(value) <= 4:
            return '*' * len(value)
        return value[:2] + '*' * (len(value) - 4) + value[-2:]
