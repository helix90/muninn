"""REST API endpoints for scenarios."""

from flask import g, jsonify, request
from app.api import api_bp
from app.api.auth import require_api_auth
from app.extensions import db
from app.models import Job, Scenario


def _scenario_to_dict(s: Scenario) -> dict:
    return {
        'id': s.id,
        'name': s.name,
        'description': s.description,
        'color': s.color,
        'is_active': s.is_active,
        'created_at': s.created_at.isoformat() if s.created_at else None,
    }


@api_bp.route('/scenarios', methods=['GET'])
@require_api_auth
def list_scenarios():
    scenarios = Scenario.query.filter_by(user_id=g.api_user.id).order_by(Scenario.id).all()
    return jsonify([_scenario_to_dict(s) for s in scenarios])


@api_bp.route('/scenarios/<int:scenario_id>', methods=['GET'])
@require_api_auth
def get_scenario(scenario_id):
    s = Scenario.query.filter_by(id=scenario_id, user_id=g.api_user.id).first()
    if s is None:
        return jsonify({'error': 'Scenario not found.'}), 404
    agents = Job.query.filter_by(scenario_id=s.id).order_by(Job.id).all()
    d = _scenario_to_dict(s)
    d['agent_ids'] = [j.id for j in agents]
    return jsonify(d)


@api_bp.route('/scenarios', methods=['POST'])
@require_api_auth
def create_scenario():
    data = request.get_json(silent=True) or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': "'name' is required."}), 400
    s = Scenario(
        user_id=g.api_user.id,
        name=name,
        description=data.get('description'),
        color=data.get('color') or '#3B82F6',
        is_active=bool(data.get('is_active', True)),
    )
    db.session.add(s)
    db.session.commit()
    return jsonify(_scenario_to_dict(s)), 201


@api_bp.route('/scenarios/<int:scenario_id>', methods=['PATCH'])
@require_api_auth
def update_scenario(scenario_id):
    s = Scenario.query.filter_by(id=scenario_id, user_id=g.api_user.id).first()
    if s is None:
        return jsonify({'error': 'Scenario not found.'}), 404
    data = request.get_json(silent=True) or {}
    for field in ('name', 'description', 'color', 'is_active'):
        if field in data:
            setattr(s, field, data[field])
    db.session.commit()
    return jsonify(_scenario_to_dict(s))


@api_bp.route('/scenarios/<int:scenario_id>', methods=['DELETE'])
@require_api_auth
def delete_scenario(scenario_id):
    s = Scenario.query.filter_by(id=scenario_id, user_id=g.api_user.id).first()
    if s is None:
        return jsonify({'error': 'Scenario not found.'}), 404
    db.session.delete(s)
    db.session.commit()
    return '', 204
