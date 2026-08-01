"""
Pipeline editor API — graph read/write endpoints and the editor canvas page.

Routes (all on scenarios_bp):
  GET  /scenarios/<id>/editor          — canvas HTML page
  GET  /scenarios/<id>/editor/graph    — full graph JSON
  PUT  /scenarios/<id>/editor/graph    — save positions + link diff
"""

import logging

from flask import jsonify, render_template, request
from flask_login import current_user, login_required

from app.agents.base import ActionAgent, SourceAgent
from app.agents.registry import agent_registry
from app.extensions import db
from app.models import AgentLink, Job, Scenario
from app.scenarios import scenarios_bp
from app.scenarios.editor_layout import compute_layout

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CATEGORY_CACHE: dict = {}


def _agent_category(job_type: str) -> str:
    if job_type in _CATEGORY_CACHE:
        return _CATEGORY_CACHE[job_type]
    try:
        cls = agent_registry.get_agent_class(job_type)
        if issubclass(cls, SourceAgent):
            cat = 'source'
        elif issubclass(cls, ActionAgent):
            cat = 'action'
        else:
            cat = 'transform'
    except ValueError:
        cat = 'transform'
    _CATEGORY_CACHE[job_type] = cat
    return cat


def _agent_capabilities(job_type: str) -> dict:
    try:
        cls = agent_registry.get_agent_class(job_type)
        return {
            'can_receive_events': cls.can_receive_events,
            'can_create_events': cls.can_create_events,
        }
    except ValueError:
        return {'can_receive_events': True, 'can_create_events': True}


def _agent_to_node(agent: Job) -> dict:
    return {
        'id': agent.id,
        'name': agent.name,
        'job_type': agent.job_type,
        'category': _agent_category(agent.job_type),
        'can_receive_events': _agent_capabilities(agent.job_type)['can_receive_events'],
        'can_create_events': _agent_capabilities(agent.job_type)['can_create_events'],
        'is_active': agent.is_active,
        'schedule_enabled': agent.schedule_enabled,
        'position': agent.canvas_position or None,
    }


def _link_to_edge(link: AgentLink) -> dict:
    return {
        'id': link.id,
        'source': link.source_agent_id,
        'target': link.target_agent_id,
    }


def _get_scenario_or_404(scenario_id: int):
    return db.session.query(Scenario).filter_by(
        id=scenario_id,
        user_id=current_user.id,
    ).first_or_404()


def _get_scenario_agents(scenario_id: int):
    return db.session.query(Job).filter_by(
        scenario_id=scenario_id,
        user_id=current_user.id,
    ).all()


def _get_scenario_links(agent_ids: list) -> list:
    if not agent_ids:
        return []
    return db.session.query(AgentLink).filter(
        AgentLink.source_agent_id.in_(agent_ids),
        AgentLink.target_agent_id.in_(agent_ids),
        AgentLink.is_active == True,
    ).all()


# ---------------------------------------------------------------------------
# Canvas page
# ---------------------------------------------------------------------------

@scenarios_bp.route('/<int:scenario_id>/editor')
@login_required
def scenario_editor(scenario_id):
    scenario = _get_scenario_or_404(scenario_id)
    return render_template('scenarios/editor.html', scenario=scenario)


# ---------------------------------------------------------------------------
# Graph API
# ---------------------------------------------------------------------------

@scenarios_bp.route('/<int:scenario_id>/editor/graph')
@login_required
def editor_graph_get(scenario_id):
    scenario = _get_scenario_or_404(scenario_id)
    agents = _get_scenario_agents(scenario_id)
    agent_ids = [a.id for a in agents]
    links = _get_scenario_links(agent_ids)

    # ?reset_layout=1 wipes all positions and recomputes from scratch
    if request.args.get('reset_layout'):
        for agent in agents:
            agent.canvas_position = None

    # Auto-layout agents that have no saved position
    needs_layout = [a for a in agents if not a.canvas_position]
    if needs_layout:
        positions = compute_layout(agents, links)
        for agent in needs_layout:
            if agent.id in positions:
                agent.canvas_position = positions[agent.id]
        db.session.commit()

    return jsonify({
        'scenario': {'id': scenario.id, 'name': scenario.name},
        'agents': [_agent_to_node(a) for a in agents],
        'links': [_link_to_edge(lk) for lk in links],
    })


@scenarios_bp.route('/<int:scenario_id>/editor/graph', methods=['PUT'])
@login_required
def editor_graph_put(scenario_id):
    _get_scenario_or_404(scenario_id)
    agents = _get_scenario_agents(scenario_id)
    agent_ids = {a.id for a in agents}

    body = request.get_json(silent=True) or {}

    # --- Save positions ---
    positions: dict = body.get('positions', {})
    agent_map = {a.id: a for a in agents}
    for raw_id, pos in positions.items():
        try:
            aid = int(raw_id)
        except (ValueError, TypeError):
            continue
        if aid in agent_map and isinstance(pos, dict) and 'x' in pos and 'y' in pos:
            agent_map[aid].canvas_position = {'x': int(pos['x']), 'y': int(pos['y'])}

    # --- Add new links ---
    added = []
    errors = []
    for spec in body.get('add_links', []):
        src = spec.get('source')
        tgt = spec.get('target')
        if src is None or tgt is None:
            errors.append('Link missing source or target')
            continue
        try:
            src, tgt = int(src), int(tgt)
        except (ValueError, TypeError):
            errors.append('Link source/target must be integers')
            continue
        if src == tgt:
            errors.append(f'Self-loop not allowed (agent {src})')
            continue
        if src not in agent_ids or tgt not in agent_ids:
            errors.append(f'Agent {src} or {tgt} not in this scenario')
            continue

        # Check target can receive events
        tgt_agent = agent_map[tgt]
        caps = _agent_capabilities(tgt_agent.job_type)
        if not caps['can_receive_events']:
            errors.append(f'Agent "{tgt_agent.name}" cannot receive events')
            continue

        # Check link doesn't already exist
        existing = db.session.query(AgentLink).filter_by(
            source_agent_id=src,
            target_agent_id=tgt,
        ).first()
        if existing:
            if not existing.is_active:
                existing.is_active = True
                added.append(existing.id)
            continue

        link = AgentLink(source_agent_id=src, target_agent_id=tgt)
        db.session.add(link)
        db.session.flush()
        added.append(link.id)

    # --- Remove links ---
    removed = []
    for link_id in body.get('remove_links', []):
        try:
            link_id = int(link_id)
        except (ValueError, TypeError):
            continue
        link = db.session.query(AgentLink).filter_by(id=link_id).first()
        if link and link.source_agent_id in agent_ids and link.target_agent_id in agent_ids:
            db.session.delete(link)
            removed.append(link_id)

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.error(f'editor_graph_put commit failed: {exc}', exc_info=True)
        return jsonify({'status': 'error', 'error': str(exc)}), 500

    return jsonify({
        'status': 'ok',
        'added_links': added,
        'removed_links': removed,
        'errors': errors,
    })
