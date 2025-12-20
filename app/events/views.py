"""
Event viewing routes for Muninn
"""

import logging
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from math import ceil

from app.events import events
from app.extensions import db
from app.services.event_service import EventService
from app.models import Job
from app.agents.registry import agent_registry

logger = logging.getLogger(__name__)

# Pagination settings
EVENTS_PER_PAGE = 50


@events.route('/agent/<int:agent_id>')
@login_required
def agent_events(agent_id):
    """
    Display all events for a specific agent with filtering and pagination.
    """
    try:
        user_id = current_user.id

        # Verify agent ownership
        agent = db.session.query(Job).filter(
            Job.id == agent_id,
            Job.user_id == user_id
        ).first()

        if not agent:
            flash('You are not authorized to view this agent', 'error')
            return redirect(url_for('agents.agent_list'))

        # Get filter parameters
        page = request.args.get('page', 1, type=int)
        start_date_str = request.args.get('start_date', '').strip()
        end_date_str = request.args.get('end_date', '').strip()
        search = request.args.get('search', '').strip()

        # Parse dates
        start_date = None
        end_date = None

        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            except ValueError:
                flash('Invalid start date format. Use YYYY-MM-DD.', 'error')

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
                # Set to end of day
                end_date = end_date.replace(hour=23, minute=59, second=59)
            except ValueError:
                flash('Invalid end date format. Use YYYY-MM-DD.', 'error')

        # Get events
        event_service = EventService(db.session)

        # Calculate offset
        offset = (page - 1) * EVENTS_PER_PAGE

        # Query events with filters
        event_list = event_service.get_events_for_agent(
            agent_id=agent_id,
            limit=EVENTS_PER_PAGE,
            offset=offset,
            start_date=start_date,
            end_date=end_date,
            payload_search=search if search else None
        )

        # Get total count for pagination
        total_count = event_service.count_events_for_agent(
            agent_id=agent_id,
            start_date=start_date,
            end_date=end_date,
            payload_search=search if search else None
        )

        total_pages = ceil(total_count / EVENTS_PER_PAGE) if total_count > 0 else 1

        return render_template('events/agent_events.html',
                             agent=agent,
                             events=event_list,
                             page=page,
                             total_pages=total_pages,
                             total_count=total_count,
                             start_date=start_date_str,
                             end_date=end_date_str,
                             search=search)

    except Exception as e:
        logger.error(f"Error in agent_events: {e}", exc_info=True)
        flash('An error occurred while loading events', 'error')
        return redirect(url_for('agents.agent_detail', agent_id=agent_id))


@events.route('/')
@login_required
def all_events():
    """
    Display all events across all agents for the current user with filtering.
    """
    try:
        user_id = current_user.id

        # Get filter parameters
        page = request.args.get('page', 1, type=int)
        start_date_str = request.args.get('start_date', '').strip()
        end_date_str = request.args.get('end_date', '').strip()
        agent_type_filter = request.args.get('agent_type', '').strip()
        agent_id_filter = request.args.get('agent_id', None, type=int)
        search = request.args.get('search', '').strip()

        # Parse dates
        start_date = None
        end_date = None

        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            except ValueError:
                flash('Invalid start date format. Use YYYY-MM-DD.', 'error')

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
                # Set to end of day
                end_date = end_date.replace(hour=23, minute=59, second=59)
            except ValueError:
                flash('Invalid end date format. Use YYYY-MM-DD.', 'error')

        # Get user's agents for dropdown
        user_agents = db.session.query(Job).filter(
            Job.user_id == user_id
        ).order_by(Job.name).all()

        # Get available agent types
        agent_types = agent_registry.get_all_types()

        # Get events
        event_service = EventService(db.session)

        # Calculate offset
        offset = (page - 1) * EVENTS_PER_PAGE

        # Query events with filters
        event_list = event_service.get_all_events(
            user_id=user_id,
            limit=EVENTS_PER_PAGE,
            offset=offset,
            start_date=start_date,
            end_date=end_date,
            agent_type=agent_type_filter if agent_type_filter else None,
            agent_id=agent_id_filter,
            payload_search=search if search else None
        )

        # Get total count for pagination
        total_count = event_service.count_all_events(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            agent_type=agent_type_filter if agent_type_filter else None,
            agent_id=agent_id_filter,
            payload_search=search if search else None
        )

        total_pages = ceil(total_count / EVENTS_PER_PAGE) if total_count > 0 else 1

        # Get agent details for events
        # Create a map of agent_id -> agent for quick lookup
        agent_map = {agent.id: agent for agent in user_agents}

        return render_template('events/all_events.html',
                             events=event_list,
                             agent_map=agent_map,
                             page=page,
                             total_pages=total_pages,
                             total_count=total_count,
                             start_date=start_date_str,
                             end_date=end_date_str,
                             agent_type_filter=agent_type_filter,
                             agent_id_filter=agent_id_filter,
                             search=search,
                             user_agents=user_agents,
                             agent_types=sorted(agent_types))

    except Exception as e:
        logger.error(f"Error in all_events: {e}", exc_info=True)
        flash('An error occurred while loading events', 'error')
        return redirect(url_for('main.index'))
