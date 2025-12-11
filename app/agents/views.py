"""
Agent management views for the Muninn application

Provides web interface for managing agents (new agent system)
"""

import logging
import json
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user

from app.extensions import db
from app.services.agent_service import AgentService
from app.agents.registry import agent_registry
from app.models import Job, AgentLink

# Create blueprint
agents = Blueprint('agents', __name__, url_prefix='/agents')
logger = logging.getLogger(__name__)


@agents.route('/')
@login_required
def agent_list():
    """Agent listing page."""
    try:
        user_id = current_user.id

        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)

        # Get agent service
        agent_service = AgentService(db.session)

        # Get user's agents (using Job table)
        query = db.session.query(Job).filter(Job.user_id == user_id)

        # Filter for agent types only
        agent_types = agent_registry.get_registered_types()
        query = query.filter(Job.job_type.in_(agent_types))

        # Pagination
        pagination = query.order_by(Job.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

        # Get statistics for each agent
        agents_with_stats = []
        for agent in pagination.items:
            stats = agent_service.get_agent_statistics(agent.id)
            agents_with_stats.append({
                'agent': agent,
                'stats': stats
            })

        return render_template('agents/list.html',
                             agents=agents_with_stats,
                             pagination=pagination,
                             agent_types=agent_registry.get_registered_types())

    except Exception as e:
        logger.error(f"Error in agent_list: {e}", exc_info=True)
        flash('An error occurred while loading agents', 'error')
        return redirect(url_for('main.index'))


@agents.route('/create', methods=['GET', 'POST'])
@login_required
def create_agent():
    """Agent creation form."""
    try:
        user_id = current_user.id
        agent_service = AgentService(db.session)

        # Get available agent types
        available_types = agent_registry.get_registered_types()

        # Get agent types organized by category
        source_agents = agent_registry.get_source_agents()
        transform_agents = agent_registry.get_transform_agents()
        action_agents = agent_registry.get_action_agents()

        if request.method == 'POST':
            # Process form submission
            name = request.form.get('name', '').strip()
            agent_type = request.form.get('agent_type', '')
            schedule = request.form.get('schedule', '').strip()

            # Validate required fields
            if not name:
                flash('Agent name is required', 'error')
                return render_template('agents/create.html',
                                     source_agents=source_agents,
                                     transform_agents=transform_agents,
                                     action_agents=action_agents)

            if not agent_type:
                flash('Agent type is required', 'error')
                return render_template('agents/create.html',
                                     source_agents=source_agents,
                                     transform_agents=transform_agents,
                                     action_agents=action_agents)

            # Get agent-specific configuration from form
            config = {}
            for key in request.form:
                if key.startswith('config_'):
                    config_key = key[7:]  # Remove 'config_' prefix
                    value = request.form.get(key, '').strip()
                    if value:
                        # Try to parse as JSON for complex values
                        try:
                            config[config_key] = json.loads(value)
                        except:
                            config[config_key] = value

            # Validate configuration
            is_valid, error = agent_service.validate_agent_config(agent_type, config)
            if not is_valid:
                flash(f'Invalid configuration: {error}', 'error')
                return render_template('agents/create.html',
                                     source_agents=source_agents,
                                     transform_agents=transform_agents,
                                     action_agents=action_agents,
                                     name=name,
                                     agent_type=agent_type,
                                     config=config)

            # Create agent
            agent = Job(
                name=name,
                job_type=agent_type,
                config=config,
                schedule=schedule if schedule else None,
                user_id=user_id,
                is_active=True
            )

            db.session.add(agent)
            db.session.commit()

            flash(f'Agent "{name}" created successfully', 'success')
            return redirect(url_for('agents.agent_detail', agent_id=agent.id))

        # GET request
        return render_template('agents/create.html',
                             source_agents=source_agents,
                             transform_agents=transform_agents,
                             action_agents=action_agents)

    except Exception as e:
        logger.error(f"Error in create_agent: {e}", exc_info=True)
        db.session.rollback()
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('agents.agent_list'))


@agents.route('/<int:agent_id>')
@login_required
def agent_detail(agent_id):
    """Agent detail page."""
    try:
        user_id = current_user.id
        agent_service = AgentService(db.session)

        # Get agent
        agent = db.session.query(Job).filter(
            Job.id == agent_id,
            Job.user_id == user_id
        ).first()

        if not agent:
            flash('Agent not found', 'error')
            return redirect(url_for('agents.agent_list'))

        # Get statistics
        stats = agent_service.get_agent_statistics(agent_id)

        # Get execution history
        runs = agent_service.get_agent_run_history(agent_id, limit=20)

        # Get agent capabilities
        capabilities = agent_service.get_agent_capabilities(agent.job_type)

        # Get network stats
        from app.services.event_service import EventService
        event_service = EventService(db.session)
        network_stats = event_service.get_agent_network_stats(agent_id)

        # Get upstream and downstream agents
        upstream_links = db.session.query(AgentLink).filter(
            AgentLink.target_agent_id == agent_id,
            AgentLink.is_active == True
        ).all()

        downstream_links = db.session.query(AgentLink).filter(
            AgentLink.source_agent_id == agent_id,
            AgentLink.is_active == True
        ).all()

        return render_template('agents/detail.html',
                             agent=agent,
                             stats=stats,
                             runs=runs,
                             capabilities=capabilities,
                             network_stats=network_stats,
                             upstream_links=upstream_links,
                             downstream_links=downstream_links)

    except Exception as e:
        logger.error(f"Error in agent_detail: {e}", exc_info=True)
        flash('An error occurred while loading agent details', 'error')
        return redirect(url_for('agents.agent_list'))


@agents.route('/<int:agent_id>/run', methods=['POST'])
@login_required
def run_agent(agent_id):
    """Manually run an agent."""
    try:
        user_id = current_user.id
        agent_service = AgentService(db.session)

        # Verify ownership
        agent = db.session.query(Job).filter(
            Job.id == agent_id,
            Job.user_id == user_id
        ).first()

        if not agent:
            return jsonify({'success': False, 'error': 'Agent not found'}), 404

        # Run the agent
        result = agent_service.run_agent(
            agent_id=agent_id,
            manual=True,
            propagate=True
        )

        if result['success']:
            return jsonify({
                'success': True,
                'events_created': result.get('events_created', 0),
                'propagation_stats': result.get('propagation_stats', {})
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', 'Unknown error')
            }), 400

    except Exception as e:
        logger.error(f"Error running agent {agent_id}: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@agents.route('/<int:agent_id>/delete', methods=['POST'])
@login_required
def delete_agent(agent_id):
    """Delete an agent."""
    try:
        user_id = current_user.id

        # Get agent
        agent = db.session.query(Job).filter(
            Job.id == agent_id,
            Job.user_id == user_id
        ).first()

        if not agent:
            flash('Agent not found', 'error')
            return redirect(url_for('agents.agent_list'))

        agent_name = agent.name
        db.session.delete(agent)
        db.session.commit()

        flash(f'Agent "{agent_name}" deleted successfully', 'success')
        return redirect(url_for('agents.agent_list'))

    except Exception as e:
        logger.error(f"Error deleting agent {agent_id}: {e}", exc_info=True)
        db.session.rollback()
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('agents.agent_detail', agent_id=agent_id))


@agents.route('/link', methods=['POST'])
@login_required
def create_link():
    """Create a link between two agents."""
    try:
        user_id = current_user.id
        agent_service = AgentService(db.session)

        data = request.get_json()
        source_id = data.get('source_agent_id')
        target_id = data.get('target_agent_id')

        if not source_id or not target_id:
            return jsonify({'success': False, 'error': 'Missing agent IDs'}), 400

        # Verify ownership of both agents
        source = db.session.query(Job).filter(
            Job.id == source_id,
            Job.user_id == user_id
        ).first()

        target = db.session.query(Job).filter(
            Job.id == target_id,
            Job.user_id == user_id
        ).first()

        if not source or not target:
            return jsonify({'success': False, 'error': 'Agent not found'}), 404

        # Create link
        result = agent_service.create_agent_link(source_id, target_id)

        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400

    except Exception as e:
        logger.error(f"Error creating link: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@agents.route('/link/<int:link_id>/delete', methods=['POST'])
@login_required
def delete_link(link_id):
    """Delete an agent link."""
    try:
        user_id = current_user.id
        agent_service = AgentService(db.session)

        # Get link
        link = db.session.query(AgentLink).filter(AgentLink.id == link_id).first()

        if not link:
            return jsonify({'success': False, 'error': 'Link not found'}), 404

        # Verify ownership of both agents
        source = db.session.query(Job).filter(
            Job.id == link.source_agent_id,
            Job.user_id == user_id
        ).first()

        if not source:
            return jsonify({'success': False, 'error': 'Access denied'}), 403

        # Delete link
        result = agent_service.delete_agent_link(link_id)

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error deleting link {link_id}: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@agents.route('/api/schema/<agent_type>')
@login_required
def get_agent_schema(agent_type):
    """Get configuration schema for an agent type."""
    try:
        schema = agent_registry.get_config_schema(agent_type)
        return jsonify(schema)
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logger.error(f"Error getting schema for {agent_type}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500
