"""REST API endpoints for agents (jobs)."""

from flask import g, jsonify, request
from app.api import api_bp
from app.api.auth import require_api_auth
from app.extensions import db
from app.models import Job


def _job_to_dict(job: Job) -> dict:
    return {
        'id': job.id,
        'name': job.name,
        'job_type': job.job_type,
        'description': job.description,
        'is_active': job.is_active,
        'schedule_enabled': job.schedule_enabled,
        'schedule_cron': job.schedule_cron,
        'scenario_id': job.scenario_id,
        'priority': job.priority,
        'tags': job.tags,
        'created_at': job.created_at.isoformat() if job.created_at else None,
    }


@api_bp.route('/agents', methods=['GET'])
@require_api_auth
def list_agents():
    jobs = Job.query.filter_by(user_id=g.api_user.id).order_by(Job.id).all()
    return jsonify([_job_to_dict(j) for j in jobs])


@api_bp.route('/agents/<int:agent_id>', methods=['GET'])
@require_api_auth
def get_agent(agent_id):
    job = Job.query.filter_by(id=agent_id, user_id=g.api_user.id).first()
    if job is None:
        return jsonify({'error': 'Agent not found.'}), 404
    return jsonify(_job_to_dict(job))


@api_bp.route('/agents', methods=['POST'])
@require_api_auth
def create_agent():
    data = request.get_json(silent=True) or {}
    name = data.get('name', '').strip()
    job_type = data.get('job_type', '').strip()
    if not name:
        return jsonify({'error': "'name' is required."}), 400
    if not job_type:
        return jsonify({'error': "'job_type' is required."}), 400

    from app.agents.registry import agent_registry
    if not agent_registry.is_registered(job_type):
        return jsonify({'error': f"Unknown agent type '{job_type}'."}), 400

    job = Job(
        name=name,
        job_type=job_type,
        config=data.get('config') or {},
        user_id=g.api_user.id,
        description=data.get('description'),
        scenario_id=data.get('scenario_id'),
        priority=int(data.get('priority', 0)),
        is_active=bool(data.get('is_active', True)),
        schedule_enabled=bool(data.get('schedule_enabled', False)),
        schedule_cron=data.get('schedule_cron'),
        tags=data.get('tags'),
    )
    db.session.add(job)
    db.session.commit()
    return jsonify(_job_to_dict(job)), 201


@api_bp.route('/agents/<int:agent_id>', methods=['PATCH'])
@require_api_auth
def update_agent(agent_id):
    job = Job.query.filter_by(id=agent_id, user_id=g.api_user.id).first()
    if job is None:
        return jsonify({'error': 'Agent not found.'}), 404

    data = request.get_json(silent=True) or {}
    for field in ('name', 'description', 'config', 'priority', 'tags',
                  'is_active', 'schedule_enabled', 'schedule_cron', 'scenario_id'):
        if field in data:
            setattr(job, field, data[field])
    db.session.commit()
    return jsonify(_job_to_dict(job))


@api_bp.route('/agents/<int:agent_id>', methods=['DELETE'])
@require_api_auth
def delete_agent(agent_id):
    job = Job.query.filter_by(id=agent_id, user_id=g.api_user.id).first()
    if job is None:
        return jsonify({'error': 'Agent not found.'}), 404
    db.session.delete(job)
    db.session.commit()
    return '', 204
