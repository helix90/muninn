"""
Agent management views for the Muninn application

Provides web interface for managing agents (new agent system)
"""

import logging
import json
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, current_app
from flask_login import login_required, current_user

from app.extensions import db
from app.services.agent_service import AgentService
from app.agents.registry import agent_registry
from app.models import Job, AgentLink
from app.scheduler import scheduler

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
                user_id=user_id
            )

            # Set schedule and is_active as attributes (not constructor params)
            if schedule:
                agent.schedule_cron = schedule
                agent.schedule_enabled = True
            agent.is_active = True

            db.session.add(agent)
            db.session.commit()

            # Notify scheduler if schedule was set
            if schedule:
                try:
                    scheduler.schedule_job(agent.id, schedule)
                    logger.info(f"Scheduled agent {agent.id} with cron: {schedule}")
                except Exception as e:
                    logger.error(f"Failed to schedule agent {agent.id}: {e}")
                    flash('Agent created but schedule could not be registered. Please edit and save again.', 'warning')

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


@agents.route('/<int:agent_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_agent(agent_id):
    """Agent edit form."""
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

        # Get available agent types
        source_agents = agent_registry.get_source_agents()
        transform_agents = agent_registry.get_transform_agents()
        action_agents = agent_registry.get_action_agents()

        if request.method == 'POST':
            # Process form submission
            name = request.form.get('name', '').strip()
            schedule = request.form.get('schedule', '').strip()

            # Validate required fields
            if not name:
                flash('Agent name is required', 'error')
                return render_template('agents/edit.html',
                                     agent=agent,
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
            is_valid, error = agent_service.validate_agent_config(agent.job_type, config)
            if not is_valid:
                flash(f'Invalid configuration: {error}', 'error')
                return render_template('agents/edit.html',
                                     agent=agent,
                                     source_agents=source_agents,
                                     transform_agents=transform_agents,
                                     action_agents=action_agents,
                                     name=name,
                                     config=config)

            # Update agent
            agent.name = name
            agent.config = config

            # Update schedule
            if schedule:
                agent.schedule_cron = schedule
                agent.schedule_enabled = True
            else:
                agent.schedule_cron = None
                agent.schedule_enabled = False

            # Update is_active status
            agent.is_active = request.form.get('is_active') == '1'

            db.session.commit()

            # Update scheduler
            try:
                if schedule:
                    result = scheduler.schedule_job(agent.id, schedule, replace_existing=True)
                    if result:
                        logger.info(f"Updated schedule for agent {agent.id} with cron: {schedule}")
                    else:
                        logger.error(f"Failed to schedule agent {agent.id}: schedule_job returned False")
                        flash('Agent updated but schedule could not be registered. Check logs for details.', 'error')
                else:
                    result = scheduler.unschedule_job(agent.id)
                    if result:
                        logger.info(f"Removed schedule for agent {agent.id}")
                    else:
                        logger.warning(f"Failed to unschedule agent {agent.id}: agent may not have been scheduled")
            except Exception as e:
                logger.error(f"Failed to update schedule for agent {agent.id}: {e}", exc_info=True)
                flash(f'Agent updated but schedule error: {str(e)}', 'error')

            flash(f'Agent "{name}" updated successfully', 'success')
            return redirect(url_for('agents.agent_detail', agent_id=agent.id))

        # GET request - show edit form
        return render_template('agents/edit.html',
                             agent=agent,
                             source_agents=source_agents,
                             transform_agents=transform_agents,
                             action_agents=action_agents)

    except Exception as e:
        logger.error(f"Error in edit_agent: {e}", exc_info=True)
        db.session.rollback()
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('agents.agent_detail', agent_id=agent_id))


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

        # Get recent events (limit 10)
        recent_events = event_service.get_events_for_agent(agent_id, limit=10)

        # Get upstream and downstream agents
        upstream_links = db.session.query(AgentLink).filter(
            AgentLink.target_agent_id == agent_id,
            AgentLink.is_active == True
        ).all()

        downstream_links = db.session.query(AgentLink).filter(
            AgentLink.source_agent_id == agent_id,
            AgentLink.is_active == True
        ).all()

        # Get available agents for linking (only those that can receive events)
        from app.agents.registry import agent_registry

        available_agents = []
        all_agents = db.session.query(Job).filter(
            Job.user_id == user_id,
            Job.id != agent_id  # Exclude current agent
        ).all()

        for potential_target in all_agents:
            # Check if this agent can receive events
            try:
                agent_class = agent_registry.get_agent_class(potential_target.job_type)
            except ValueError:
                # Agent type not registered, skip it
                continue

            if agent_class and agent_class.can_receive_events:
                # Check if link doesn't already exist
                existing_link = db.session.query(AgentLink).filter(
                    AgentLink.source_agent_id == agent_id,
                    AgentLink.target_agent_id == potential_target.id
                ).first()

                if not existing_link:
                    available_agents.append(potential_target)

        return render_template('agents/detail.html',
                             agent=agent,
                             stats=stats,
                             runs=runs,
                             capabilities=capabilities,
                             network_stats=network_stats,
                             upstream_links=upstream_links,
                             downstream_links=downstream_links,
                             recent_events=recent_events,
                             available_agents=available_agents)

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


@agents.route('/<int:agent_id>/copy', methods=['POST'])
@login_required
def copy_agent(agent_id):
    """Copy an existing agent and redirect to edit page."""
    try:
        user_id = current_user.id

        # Get original agent
        original_agent = db.session.query(Job).filter(
            Job.id == agent_id,
            Job.user_id == user_id
        ).first()

        if not original_agent:
            flash('Agent not found', 'error')
            return redirect(url_for('agents.agent_list'))

        # Create a copy with a new name
        import json
        copy_name = f"{original_agent.name} (Copy)"

        # Deep copy the config to avoid reference issues
        config_copy = json.loads(json.dumps(original_agent.config))

        new_agent = Job(
            name=copy_name,
            job_type=original_agent.job_type,
            config=config_copy,
            user_id=user_id,
            schedule_cron=original_agent.schedule_cron,
            schedule_enabled=False  # Start with schedule disabled
        )

        # Set is_active after instantiation (not in __init__)
        new_agent.is_active = False  # Start inactive to allow user to review

        db.session.add(new_agent)
        db.session.commit()

        flash(f'Agent copied successfully as "{copy_name}"', 'success')
        return redirect(url_for('agents.edit_agent', agent_id=new_agent.id))

    except Exception as e:
        logger.error(f"Error copying agent {agent_id}: {e}", exc_info=True)
        db.session.rollback()
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('agents.agent_detail', agent_id=agent_id))


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

        # Support both JSON (API) and form data (web UI)
        if request.is_json:
            data = request.get_json()
            source_id = data.get('source_agent_id')
            target_id = data.get('target_agent_id')
        else:
            source_id = request.form.get('source_agent_id')
            target_id = request.form.get('target_agent_id')

        if not source_id or not target_id:
            if request.is_json:
                return jsonify({'success': False, 'error': 'Missing agent IDs'}), 400
            else:
                flash('Missing agent IDs', 'error')
                return redirect(url_for('agents.agent_list'))

        # Convert to int
        try:
            source_id = int(source_id)
            target_id = int(target_id)
        except (ValueError, TypeError):
            if request.is_json:
                return jsonify({'success': False, 'error': 'Invalid agent IDs'}), 400
            else:
                flash('Invalid agent IDs', 'error')
                return redirect(url_for('agents.agent_detail', agent_id=source_id))

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
            if request.is_json:
                return jsonify({'success': False, 'error': 'Agent not found'}), 404
            else:
                flash('Agent not found', 'error')
                return redirect(url_for('agents.agent_list'))

        # Create link
        result = agent_service.create_agent_link(source_id, target_id)

        if result['success']:
            if request.is_json:
                return jsonify(result)
            else:
                flash(f'Successfully linked {source.name} to {target.name}', 'success')
                return redirect(url_for('agents.agent_detail', agent_id=source_id))
        else:
            if request.is_json:
                return jsonify(result), 400
            else:
                flash(f'Error creating link: {result.get("error", "Unknown error")}', 'error')
                return redirect(url_for('agents.agent_detail', agent_id=source_id))

    except Exception as e:
        logger.error(f"Error creating link: {e}", exc_info=True)
        if request.is_json:
            return jsonify({'success': False, 'error': str(e)}), 500
        else:
            flash(f'An error occurred: {str(e)}', 'error')
            return redirect(url_for('agents.agent_list'))


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


@agents.route('/pipeline')
@login_required
def pipeline():
    """Show agent pipeline visualization."""
    try:
        user_id = current_user.id

        # Get all user's agents
        agents_query = db.session.query(Job).filter(
            Job.user_id == user_id,
            Job.is_active == True
        ).all()

        # Build agent data with categories
        agents_data = []
        for agent in agents_query:
            try:
                agent_class = agent_registry.get_agent_class(agent.job_type)
            except ValueError:
                # Agent type not registered, set category as unknown
                agent_class = None

            # Determine category
            category = 'unknown'
            if agent_class:
                if hasattr(agent_class, '__bases__'):
                    from app.agents.base import SourceAgent, TransformAgent, ActionAgent
                    if issubclass(agent_class, ActionAgent):
                        category = 'action'
                    elif issubclass(agent_class, TransformAgent):
                        category = 'transform'
                    elif issubclass(agent_class, SourceAgent):
                        category = 'source'

            agents_data.append({
                'id': agent.id,
                'name': agent.name,
                'job_type': agent.job_type,
                'agent_category': category
            })

        # Get all links between user's agents
        agent_ids = [a['id'] for a in agents_data]
        links_query = db.session.query(AgentLink).filter(
            AgentLink.source_agent_id.in_(agent_ids),
            AgentLink.target_agent_id.in_(agent_ids),
            AgentLink.is_active == True
        ).all()

        links_data = [{
            'id': link.id,
            'source_agent_id': link.source_agent_id,
            'target_agent_id': link.target_agent_id
        } for link in links_query]

        return render_template('agents/pipeline.html',
                             agents=agents_data,
                             links=links_data)

    except Exception as e:
        logger.error(f"Error in pipeline view: {e}", exc_info=True)
        flash('An error occurred while loading pipeline visualization', 'error')
        return redirect(url_for('agents.agent_list'))
