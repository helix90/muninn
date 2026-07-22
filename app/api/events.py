"""REST API endpoints for events."""

from flask import g, jsonify, request
from app.api import api_bp
from app.api.auth import require_api_auth
from app.models import Event


def _event_to_dict(e: Event) -> dict:
    return {
        'id': e.id,
        'agent_id': e.agent_id,
        'agent_type': e.agent_type,
        'payload': e.payload,
        'event_metadata': e.event_metadata,
        'created_at': e.created_at.isoformat() if e.created_at else None,
    }


@api_bp.route('/events', methods=['GET'])
@require_api_auth
def list_events():
    limit = min(int(request.args.get('limit', 50)), 200)
    offset = int(request.args.get('offset', 0))
    agent_id = request.args.get('agent_id', type=int)

    q = Event.query.filter_by(user_id=g.api_user.id)
    if agent_id is not None:
        q = q.filter_by(agent_id=agent_id)
    events = q.order_by(Event.id.desc()).limit(limit).offset(offset).all()
    return jsonify([_event_to_dict(e) for e in events])


@api_bp.route('/events/<int:event_id>', methods=['GET'])
@require_api_auth
def get_event(event_id):
    e = Event.query.filter_by(id=event_id, user_id=g.api_user.id).first()
    if e is None:
        return jsonify({'error': 'Event not found.'}), 404
    return jsonify(_event_to_dict(e))
