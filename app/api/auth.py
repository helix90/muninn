"""Bearer token authentication for the REST API.

Falls back to Flask-Login session auth so the browsable API works when
the user is already logged in to the web UI.
"""

import functools
from flask import g, jsonify, request
from flask_login import current_user

from app.models import ApiToken


def _token_from_header() -> str | None:
    auth = request.headers.get('Authorization', '')
    if auth.lower().startswith('bearer '):
        return auth[7:].strip()
    return None


def require_api_auth(f):
    """Decorator: authenticate via Bearer token or active session."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        raw = _token_from_header()
        if raw:
            token = ApiToken.verify(raw)
            if token is None:
                return jsonify({'error': 'Invalid or revoked API token.'}), 401
            token.touch()
            from app.extensions import db
            db.session.commit()
            g.api_user = token.user
        elif current_user.is_authenticated:
            g.api_user = current_user._get_current_object()
        else:
            return jsonify({'error': 'Authentication required.'}), 401
        return f(*args, **kwargs)
    return decorated
