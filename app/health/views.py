"""Health dashboard views"""
from datetime import datetime, timedelta
from flask import render_template, jsonify
from flask_login import login_required, current_user
from app.health import health_bp
from app.extensions import db
from app.models import Job, AgentRun, AlertLog
from app.services.health_service import compute_health, get_fleet_summary, sweep_all_agents
import logging

logger = logging.getLogger(__name__)


@health_bp.route('/')
@login_required
def dashboard():
    """Health dashboard — fleet overview and per-agent status."""
    agents = (
        db.session.query(Job)
        .filter(Job.user_id == current_user.id, Job.is_active == True)
        .order_by(Job.name)
        .all()
    )

    # Recompute health for all agents on page load so statuses are current
    for agent in agents:
        try:
            compute_health(agent, db.session)
        except Exception as e:
            logger.error(f"Health check error for agent {agent.id}: {e}")
    db.session.commit()

    summary = get_fleet_summary(current_user.id, db.session)

    # Attach recent run counts for display
    window = datetime.utcnow() - timedelta(days=7)
    for agent in agents:
        recent_runs = (
            db.session.query(AgentRun)
            .filter(AgentRun.agent_id == agent.id, AgentRun.started_at >= window)
            .order_by(AgentRun.started_at.desc())
            .limit(10)
            .all()
        )
        agent._recent_runs = recent_runs
        agent._last_run = recent_runs[0] if recent_runs else None

    return render_template('health/dashboard.html', agents=agents, summary=summary)


@health_bp.route('/api/summary')
@login_required
def api_summary():
    """JSON fleet health summary — used for nav badge."""
    summary = get_fleet_summary(current_user.id, db.session)
    return jsonify(summary)


@health_bp.route('/api/agent/<int:agent_id>')
@login_required
def api_agent_health(agent_id):
    """JSON health detail for a single agent."""
    agent = (
        db.session.query(Job)
        .filter(Job.id == agent_id, Job.user_id == current_user.id, Job.is_active == True)
        .first_or_404()
    )
    compute_health(agent, db.session)
    db.session.commit()
    return jsonify({
        'id': agent.id,
        'name': agent.name,
        'health_status': agent.health_status,
        'consecutive_failures': agent.consecutive_failures,
        'health_checked_at': agent.health_checked_at.isoformat() if agent.health_checked_at else None,
        'last_alerted_at': agent.last_alerted_at.isoformat() if agent.last_alerted_at else None,
        'alert_enabled': agent.alert_enabled,
    })
