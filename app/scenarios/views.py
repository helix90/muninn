"""Views for scenario management"""
import json

from flask import render_template, request, redirect, url_for, flash, jsonify, Response
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError, OperationalError
from app.scenarios import scenarios_bp
from app.scenarios.export_import import (
    ImportValidationError,
    export_scenario,
    import_scenario,
    validate_import_document,
)
from app.models import Scenario, Job
from app.extensions import db
import logging

logger = logging.getLogger(__name__)


@scenarios_bp.route('/')
@login_required
def scenario_list():
    """List all scenarios for current user"""
    scenarios = db.session.query(Scenario).filter_by(
        user_id=current_user.id
    ).order_by(Scenario.name).all()

    # Note: agent_count is computed via the @property on the Scenario model

    return render_template('scenarios/list.html', scenarios=scenarios)


@scenarios_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_scenario():
    """Create a new scenario"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        color = request.form.get('color', '#3B82F6')  # Default blue

        if not name:
            flash('Scenario name is required', 'error')
            return render_template('scenarios/create.html')

        try:
            scenario = Scenario(
                user_id=current_user.id,
                name=name,
                description=description or None,
                color=color,
                is_active=True
            )
            db.session.add(scenario)
            db.session.commit()

            flash(f"Scenario '{name}' created successfully", 'success')
            return redirect(url_for('scenarios.scenario_list'))

        except IntegrityError:
            db.session.rollback()
            flash(f"Scenario '{name}' already exists", 'error')
            return render_template('scenarios/create.html', name=name, description=description, color=color)
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating scenario: {e}")
            flash('An error occurred while creating the scenario', 'error')
            return render_template('scenarios/create.html')

    return render_template('scenarios/create.html')


@scenarios_bp.route('/<int:scenario_id>')
@login_required
def scenario_detail(scenario_id):
    """View scenario details and its agents"""
    scenario = db.session.query(Scenario).filter_by(
        id=scenario_id,
        user_id=current_user.id
    ).first_or_404()

    agents = db.session.query(Job).filter_by(
        scenario_id=scenario_id,
        is_active=True
    ).order_by(Job.name).all()

    # Agents the user owns that are not in this scenario (for the add panel)
    available_agents = db.session.query(Job).filter(
        Job.user_id == current_user.id,
        Job.is_active == True,
        db.or_(Job.scenario_id.is_(None), Job.scenario_id != scenario_id)
    ).order_by(Job.name).all()

    return render_template(
        'scenarios/detail.html',
        scenario=scenario,
        agents=agents,
        available_agents=available_agents,
    )


@scenarios_bp.route('/<int:scenario_id>/add_agents', methods=['POST'])
@login_required
def add_agents_to_scenario(scenario_id):
    """Assign one or more agents to this scenario."""
    scenario = db.session.query(Scenario).filter_by(
        id=scenario_id,
        user_id=current_user.id
    ).first_or_404()

    agent_ids = request.form.getlist('agent_ids', type=int)
    if not agent_ids:
        flash('No agents selected.', 'error')
        return redirect(url_for('scenarios.scenario_detail', scenario_id=scenario_id))

    try:
        updated = db.session.query(Job).filter(
            Job.id.in_(agent_ids),
            Job.user_id == current_user.id,
        ).update({'scenario_id': scenario_id}, synchronize_session=False)
        db.session.commit()
        flash(
            f"Added {updated} agent{'s' if updated != 1 else ''} to '{scenario.name}'.",
            'success',
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error adding agents to scenario {scenario_id}: {e}")
        flash('An error occurred while adding agents.', 'error')

    return redirect(url_for('scenarios.scenario_detail', scenario_id=scenario_id))


@scenarios_bp.route('/<int:scenario_id>/remove_agent/<int:agent_id>', methods=['POST'])
@login_required
def remove_agent_from_scenario(scenario_id, agent_id):
    """Unassign an agent from this scenario."""
    # Verify the scenario belongs to the current user
    scenario = db.session.query(Scenario).filter_by(
        id=scenario_id,
        user_id=current_user.id
    ).first_or_404()

    agent = db.session.query(Job).filter_by(
        id=agent_id,
        scenario_id=scenario_id,
        user_id=current_user.id,
    ).first_or_404()

    try:
        agent.scenario_id = None
        db.session.commit()
        flash(f"'{agent.name}' removed from '{scenario.name}'.", 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error removing agent {agent_id} from scenario {scenario_id}: {e}")
        flash('An error occurred while removing the agent.', 'error')

    return redirect(url_for('scenarios.scenario_detail', scenario_id=scenario_id))


@scenarios_bp.route('/<int:scenario_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_scenario(scenario_id):
    """Edit an existing scenario"""
    scenario = db.session.query(Scenario).filter_by(
        id=scenario_id,
        user_id=current_user.id
    ).first_or_404()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        color = request.form.get('color', '#3B82F6')

        if not name:
            flash('Scenario name is required', 'error')
            return render_template('scenarios/edit.html', scenario=scenario)

        try:
            scenario.name = name
            scenario.description = description or None
            scenario.color = color
            db.session.commit()

            flash(f"Scenario '{name}' updated successfully", 'success')
            return redirect(url_for('scenarios.scenario_list'))

        except IntegrityError:
            db.session.rollback()
            flash(f"Scenario name '{name}' already exists", 'error')
            return render_template('scenarios/edit.html', scenario=scenario)
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating scenario: {e}")
            flash('An error occurred while updating the scenario', 'error')

    return render_template('scenarios/edit.html', scenario=scenario)


@scenarios_bp.route('/<int:scenario_id>/delete', methods=['POST'])
@login_required
def delete_scenario(scenario_id):
    """Delete a scenario (agents become unassigned)"""
    scenario = db.session.query(Scenario).filter_by(
        id=scenario_id,
        user_id=current_user.id
    ).first_or_404()

    try:
        name = scenario.name

        # Unassign all agents from this scenario
        db.session.query(Job).filter_by(scenario_id=scenario_id).update({'scenario_id': None})

        # Delete the scenario
        db.session.delete(scenario)
        db.session.commit()

        flash(f"Scenario '{name}' deleted successfully", 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting scenario: {e}")
        flash('An error occurred while deleting the scenario', 'error')

    return redirect(url_for('scenarios.scenario_list'))


@scenarios_bp.route('/<int:scenario_id>/export')
@login_required
def export_scenario_view(scenario_id):
    """Download a scenario and its agents as a JSON file."""
    scenario = db.session.query(Scenario).filter_by(
        id=scenario_id,
        user_id=current_user.id
    ).first_or_404()

    doc = export_scenario(scenario)
    filename = scenario.name.replace(' ', '_') + '.json'
    return Response(
        json.dumps(doc, indent=2),
        mimetype='application/json',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


@scenarios_bp.route('/import', methods=['GET', 'POST'])
@login_required
def import_scenario_view():
    """Upload a JSON export file and recreate the scenario for the current user."""
    if request.method == 'GET':
        return render_template('scenarios/import.html')

    uploaded = request.files.get('file')
    if not uploaded or not uploaded.filename:
        flash('Please select a JSON file to import.', 'error')
        return render_template('scenarios/import.html')

    raw = uploaded.read()

    try:
        doc = validate_import_document(raw)
    except ImportValidationError as exc:
        flash(str(exc), 'error')
        return render_template('scenarios/import.html')

    try:
        scenario, warnings = import_scenario(doc, current_user.id)
    except IntegrityError as exc:
        db.session.rollback()
        logger.error(f"Scenario import integrity error: {exc}")
        flash(
            'Import failed: database integrity error. '
            'If you recently reset the database, please log out and register again.',
            'error',
        )
        return render_template('scenarios/import.html')
    except OperationalError as exc:
        db.session.rollback()
        logger.error(f"Scenario import database error: {exc}")
        flash(
            'Import failed: database error — the schema on this instance may be '
            'out of date. Run "flask db upgrade" and try again.',
            'error',
        )
        return render_template('scenarios/import.html')
    except Exception as exc:
        db.session.rollback()
        logger.error(f"Scenario import failed: {exc}")
        flash('Import failed due to an unexpected error. No data was saved.', 'error')
        return render_template('scenarios/import.html')

    agent_count = len(doc['agents'])
    link_count = len(doc['links'])
    flash(
        f"Imported '{scenario.name}' — "
        f"{agent_count} agent{'s' if agent_count != 1 else ''}, "
        f"{link_count} link{'s' if link_count != 1 else ''}.",
        'success',
    )
    for warning in warnings:
        flash(warning, 'warning')

    return redirect(url_for('scenarios.scenario_detail', scenario_id=scenario.id))


@scenarios_bp.route('/api/list')
@login_required
def api_scenario_list():
    """API endpoint to get scenarios for dropdown (JSON)"""
    scenarios = db.session.query(Scenario).filter_by(
        user_id=current_user.id,
        is_active=True
    ).order_by(Scenario.name).all()

    return jsonify({
        'scenarios': [
            {
                'id': s.id,
                'name': s.name,
                'color': s.color,
                'agent_count': s.agent_count
            }
            for s in scenarios
        ]
    })
