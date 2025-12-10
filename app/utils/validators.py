"""
Validation utilities for Muninn application
"""

import re
from urllib.parse import urlparse


# Email validation regex pattern (RFC 5322 simplified)
EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')


def validate_email(email: str) -> bool:
    """
    Validate email address format.

    Args:
        email: Email address to validate

    Returns:
        bool: True if valid email format
    """
    if not email:
        return False
    return bool(EMAIL_PATTERN.match(email.strip()))


def validate_email_list(email_list: str, separator: str = ',') -> tuple[bool, list[str]]:
    """
    Validate a comma-separated list of email addresses.

    Args:
        email_list: Comma-separated email addresses
        separator: Separator character (default: comma)

    Returns:
        tuple: (is_valid, list_of_errors)
    """
    errors = []
    emails = [email.strip() for email in email_list.split(separator) if email.strip()]

    if not emails:
        return False, ['At least one email address is required']

    for email in emails:
        if not validate_email(email):
            errors.append(f'Invalid email address: {email}')

    return len(errors) == 0, errors


def validate_url(url: str) -> bool:
    """
    Validate URL format.

    Args:
        url: URL to validate

    Returns:
        bool: True if valid URL format
    """
    if not url:
        return False

    try:
        result = urlparse(url.strip())
        # Check for scheme (http/https) and netloc (domain)
        return bool(result.scheme in ('http', 'https') and result.netloc)
    except Exception:
        return False
