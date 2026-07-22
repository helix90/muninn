"""Pipeline run history and trace views."""

from collections import defaultdict

from flask import render_template
from flask_login import current_user, login_required
from sqlalchemy import distinct, func

from app.extensions import db
from app.models import AgentRun, Event, Job
from app.pipeline_runs import pipeline_runs_bp


@pipeline_runs_bp.route('/')
@login_required
def list_runs():
    """List distinct pipeline runs (grouped by propagation_id) for this user."""
    # Find all distinct propagation_ids that belong to this user's agents
    # (via AgentRun.agent_id → jobs.user_id)
    rows = (
        db.session.query(
            AgentRun.propagation_id,
            func.min(AgentRun.started_at).label('started_at'),
            func.max(AgentRun.completed_at).label('completed_at'),
            func.count(AgentRun.id).label('agent_run_count'),
        )
        .join(Job, AgentRun.agent_id == Job.id)
        .filter(
            Job.user_id == current_user.id,
            AgentRun.propagation_id.isnot(None),
        )
        .group_by(AgentRun.propagation_id)
        .order_by(func.min(AgentRun.started_at).desc())
        .limit(100)
        .all()
    )

    runs = []
    for row in rows:
        runs.append({
            'propagation_id': row.propagation_id,
            'started_at': row.started_at,
            'completed_at': row.completed_at,
            'agent_run_count': row.agent_run_count,
        })

    return render_template('pipeline_runs/list.html', runs=runs)


@pipeline_runs_bp.route('/<propagation_id>')
@login_required
def run_detail(propagation_id):
    """Show all AgentRuns and Events for a given propagation_id."""
    # Security: only show runs that belong to this user's agents
    agent_runs = (
        db.session.query(AgentRun)
        .join(Job, AgentRun.agent_id == Job.id)
        .filter(
            AgentRun.propagation_id == propagation_id,
            Job.user_id == current_user.id,
        )
        .order_by(AgentRun.started_at)
        .all()
    )

    if not agent_runs:
        return render_template('pipeline_runs/detail.html',
                               propagation_id=propagation_id,
                               agent_runs=[],
                               events=[],
                               event_map={})

    events = (
        db.session.query(Event)
        .filter(
            Event.propagation_id == propagation_id,
            Event.user_id == current_user.id,
        )
        .order_by(Event.created_at)
        .all()
    )

    # Build a mapping from event_id → event for template use
    event_map = {e.id: e for e in events}

    return render_template(
        'pipeline_runs/detail.html',
        propagation_id=propagation_id,
        agent_runs=agent_runs,
        events=events,
        event_map=event_map,
    )
