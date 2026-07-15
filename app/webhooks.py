"""
Webhook Blueprint - HTTP endpoints for receiving webhooks from external services

This module provides Flask routes for webhook reception. External services POST to
/webhooks/<agent_id>/<secret_token> to trigger events in Muninn workflows.
"""

from flask import Blueprint, request, jsonify, current_app
from datetime import datetime
import hmac
import hashlib

webhook_bp = Blueprint('webhooks', __name__)


@webhook_bp.route('/webhooks/<int:agent_id>/<secret_token>', methods=['POST'])
def receive_webhook(agent_id: int, secret_token: str):
    """
    Receive webhook POST request and create event.

    URL: /webhooks/<agent_id>/<secret_token>
    Method: POST
    Content-Type: application/json (or form-encoded)

    Headers (optional):
    - X-Hub-Signature-256: HMAC signature for verification
    - X-Forwarded-For: Client IP (for whitelisting)

    Returns:
        JSON response with status and event_id (200)
        or error message (403, 404, 500)
    """
    try:
        # Import here to avoid circular imports
        from app.models import Job, Event
        from app.extensions import db

        # Load agent configuration
        job = Job.query.filter_by(id=agent_id, is_active=True).first()
        if not job:
            current_app.logger.warning(f'Webhook not found or disabled: agent_id={agent_id}')
            return jsonify({'error': 'Webhook not found or disabled'}), 404

        agent_config = job.config or {}

        # Verify secret token (constant-time comparison)
        expected_token = agent_config.get('secret_token', '')
        if not expected_token or not hmac.compare_digest(secret_token, expected_token):
            current_app.logger.warning(f'Invalid webhook token for agent {agent_id}')
            return jsonify({'error': 'Invalid token'}), 403

        # Verify HMAC signature (if configured)
        if agent_config.get('verify_signature', False):
            signature = request.headers.get('X-Hub-Signature-256', '')
            secret = agent_config.get('signature_secret', '')

            if not _verify_signature(request.data, secret, signature):
                current_app.logger.warning(f'Invalid signature for agent {agent_id}')
                return jsonify({'error': 'Invalid signature'}), 403

        # IP whitelisting (if configured)
        allowed_ips = agent_config.get('allowed_ips', [])
        if allowed_ips:
            client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
            # Handle X-Forwarded-For with multiple IPs (get the first one)
            if ',' in client_ip:
                client_ip = client_ip.split(',')[0].strip()

            if client_ip not in allowed_ips:
                current_app.logger.warning(f'IP not allowed for agent {agent_id}: {client_ip}')
                return jsonify({'error': 'IP not allowed'}), 403

        # Parse payload
        if request.is_json:
            payload = request.get_json()
        elif request.form:
            payload = dict(request.form)
        else:
            # Raw data (try to decode as text)
            try:
                payload = {'raw': request.data.decode('utf-8')}
            except UnicodeDecodeError:
                payload = {'raw': request.data.hex()}

        # Extract headers (if configured)
        include_headers = agent_config.get('include_headers', [])
        headers = {h: request.headers.get(h, '') for h in include_headers}

        # Create event immediately
        event = Event(
            agent_id=agent_id,
            agent_type=job.job_type,
            user_id=job.user_id,
            payload=payload,
            metadata={
                'source': 'webhook',
                'client_ip': request.remote_addr,
                'headers': headers,
                'received_at': datetime.utcnow().isoformat(),
                'content_type': request.content_type or 'unknown'
            }
        )
        db.session.add(event)
        db.session.commit()

        current_app.logger.info(f'Webhook received for agent {agent_id}, event {event.id}')

        # Get custom response (if configured)
        response_status = agent_config.get('response_status', 200)
        response_body = agent_config.get('response_body', {
            'status': 'success',
            'event_id': event.id,
            'message': 'Webhook received'
        })

        # Ensure event_id is in response
        if isinstance(response_body, dict) and 'event_id' not in response_body:
            response_body['event_id'] = event.id

        return jsonify(response_body), response_status

    except Exception as e:
        current_app.logger.error(f'Webhook error for agent {agent_id}: {e}', exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


def _verify_signature(payload: bytes, secret: str, signature: str) -> bool:
    """
    Verify HMAC-SHA256 signature (GitHub/Stripe style).

    Args:
        payload: Raw request payload bytes
        secret: Secret key for HMAC
        signature: Signature from request header (format: 'sha256=<hex>')

    Returns:
        True if signature is valid, False otherwise
    """
    if not signature or not secret:
        return False

    # Signature should be in format: sha256=<hex>
    if not signature.startswith('sha256='):
        return False

    # Compute expected signature
    expected_sig = 'sha256=' + hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()

    # Constant-time comparison
    return hmac.compare_digest(signature, expected_sig)
