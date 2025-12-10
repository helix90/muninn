"""
Job management views for the Muninn application
"""

import logging
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, current_app
from flask_login import login_required, current_user

from app.extensions import db
from app.services.job_service import JobService
from app.jobs import job_registry

# Create blueprint
jobs = Blueprint('jobs', __name__, url_prefix='/jobs')
logger = logging.getLogger(__name__)


@jobs.route('/')
@login_required
def job_list():
    """Job listing page for authenticated users."""
    try:
        # Get user ID from Flask-Login
        user_id = current_user.id

        # Get pagination parameters from query string
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)

        # Get job service
        job_service = JobService(db.session)

        # Get user's jobs with pagination
        pagination_data = job_service.get_user_jobs(user_id, page=page, per_page=per_page)

        # Get job statistics
        stats = job_service.get_job_statistics(user_id)

        return render_template('jobs/list.html',
                             jobs=pagination_data['jobs'],
                             pagination=pagination_data,
                             stats=stats)

    except Exception as e:
        logger.error(f"Error in job_list: {e}")
        flash('An error occurred while loading jobs', 'error')
        return redirect(url_for('main.index'))


@jobs.route('/create', methods=['GET', 'POST'])
@login_required
def create_job():
    """Job creation form and processing."""
    try:
        # Get user ID
        user_id = current_user.id
        
        # Get available job types
        job_service = JobService(db.session)
        available_types = job_service.get_available_job_types()
        
        if request.method == 'POST':
            # Process form submission
            name = request.form.get('name', '').strip()
            job_type = request.form.get('job_type', '')
            config = {}
            
            # Validate required fields
            if not name:
                flash('Job name is required', 'error')
                return render_template('jobs/create/base.html', job_types=available_types)
            
            if not job_type:
                flash('Job type is required', 'error')
                return render_template('jobs/create/base.html', job_types=available_types)
            
            # Get job-specific configuration
            config = _get_job_config_from_form(job_type, request.form)
            logger.info(f"Form data: {dict(request.form)}")
            logger.info(f"Generated config: {config}")
            
            # Create job
            job, error = job_service.create_job(name, job_type, config, user_id)
            
            if error:
                flash(f'Failed to create job: {error}', 'error')
                return render_template('jobs/create/base.html', job_types=available_types, 
                                   form_data=request.form)
            
            flash(f'Job "{name}" created successfully', 'success')
            return redirect(url_for('jobs.job_detail', job_id=job.id))
        
        # GET request - show form
        return render_template('jobs/create/base.html', job_types=available_types)
        
    except Exception as e:
        logger.error(f"Error in create_job: {e}")
        flash('An error occurred while creating the job', 'error')
        return redirect(url_for('jobs.job_list'))


@jobs.route('/create/<job_type>')
@login_required
def get_job_type_template(job_type):
    """Get the configuration template for a specific job type."""
    try:
        # Validate job type
        job_service = JobService(db.session)
        available_types = job_service.get_available_job_types()
        valid_types = [job_type_info['type'] for job_type_info in available_types]
        
        if job_type not in valid_types:
            return jsonify({'error': 'Invalid job type'}), 400
        
        # Render the appropriate template
        template_name = f'jobs/create/{job_type}.html'
        return render_template(template_name)
        
    except Exception as e:
        logger.error(f"Error loading template for job type {job_type}: {e}")
        return jsonify({'error': 'Failed to load template'}), 500


@jobs.route('/<int:job_id>')
@login_required
def job_detail(job_id):
    """Job detail view."""
    try:
        # Get user ID
        user_id = current_user.id
        
        # Get job service
        job_service = JobService(db.session)
        
        # Get job details
        job = job_service.get_job_by_id(job_id, user_id)
        if not job:
            flash('Job not found or access denied', 'error')
            return redirect(url_for('jobs.job_list'))
        
        # Get job runs
        runs = job_service.get_job_runs(job_id, user_id, limit=50)
        
        # Get job type schema
        schema = job_registry.get_config_schema(job.job_type)
        
        return render_template('jobs/detail.html', job=job, runs=runs, schema=schema)
        
    except Exception as e:
        logger.error(f"Error in job_detail: {e}")
        flash('An error occurred while loading job details', 'error')
        return redirect(url_for('jobs.job_list'))


@jobs.route('/<int:job_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_job(job_id):
    """Edit job form and processing."""
    try:
        # Get user ID
        user_id = current_user.id
        
        # Get job service
        job_service = JobService(db.session)
        
        # Get job details
        job = job_service.get_job_by_id(job_id, user_id)
        if not job:
            flash('Job not found or access denied', 'error')
            return redirect(url_for('jobs.job_list'))
        
        if request.method == 'POST':
            # Process form submission
            name = request.form.get('name', '').strip()
            config = _get_job_config_from_form(job.job_type, request.form)
            
            # Validate required fields
            if not name:
                flash('Job name is required', 'error')
                return render_template('jobs/edit.html', job=job)
            
            # Update job
            updated_job, error = job_service.update_job(job_id, user_id, name=name, config=config)
            
            if error:
                flash(f'Failed to update job: {error}', 'error')
                return render_template('jobs/edit.html', job=job)
            
            flash(f'Job "{name}" updated successfully', 'success')
            return redirect(url_for('jobs.job_detail', job_id=job.id))
        
        # GET request - show form
        return render_template('jobs/edit.html', job=job)
        
    except Exception as e:
        logger.error(f"Error in edit_job: {e}")
        flash('An error occurred while editing the job', 'error')
        return redirect(url_for('jobs.job_list'))


@jobs.route('/<int:job_id>/delete', methods=['POST'])
@login_required
def delete_job(job_id):
    """Delete a job."""
    try:
        # Get user ID
        user_id = current_user.id
        
        # Get job service
        job_service = JobService(db.session)
        
        # Delete job
        success, error = job_service.delete_job(job_id, user_id)
        
        if not success:
            flash(f'Failed to delete job: {error}', 'error')
        else:
            flash('Job deleted successfully', 'success')
        
        return redirect(url_for('jobs.job_list'))
        
    except Exception as e:
        logger.error(f"Error in delete_job: {e}")
        flash('An error occurred while deleting the job', 'error')
        return redirect(url_for('jobs.job_list'))


@jobs.route('/<int:job_id>/execute', methods=['POST'])
@login_required
def execute_job(job_id):
    """Execute a job."""
    try:
        # Get user ID
        user_id = current_user.id
        
        # Get job service
        job_service = JobService(db.session)
        
        # Execute job
        job_run, error = job_service.execute_job(job_id, user_id)
        
        if error:
            return jsonify({'success': False, 'error': error}), 400
        
        return jsonify({
            'success': True,
            'run_id': job_run.id,
            'status': job_run.status,
            'message': f'Job execution started (Run ID: {job_run.id})'
        })
        
    except Exception as e:
        logger.error(f"Error in execute_job: {e}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@jobs.route('/<int:job_id>/runs')
@login_required
def job_runs(job_id):
    """Get job execution history."""
    try:
        # Get user ID
        user_id = current_user.id
        
        # Get job service
        job_service = JobService(db.session)
        
        # Get job runs
        runs = job_service.get_job_runs(job_id, user_id, limit=100)
        
        # Format runs for JSON response
        runs_data = []
        for run in runs:
            runs_data.append({
                'id': run.id,
                'status': run.status,
                'started_at': run.started_at.isoformat() if run.started_at else None,
                'completed_at': run.completed_at.isoformat() if run.completed_at else None,
                'error_message': run.error_message,
                'duration': run.get_duration()
            })
        
        return jsonify({'success': True, 'runs': runs_data})
        
    except Exception as e:
        logger.error(f"Error in job_runs: {e}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@jobs.route('/types')
@login_required
def job_types():
    """Get available job types and their schemas."""
    try:
        # Get available job types
        job_service = JobService(db.session)
        available_types = job_service.get_available_job_types()
        
        return jsonify({'success': True, 'types': available_types})
        
    except Exception as e:
        logger.error(f"Error in job_types: {e}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


def _get_job_config_from_form(job_type: str, form_data: dict) -> dict:
    """Extract job configuration from form data based on job type."""
    config = {}
    
    if job_type == 'web_scraper':
        config = {
            'url': form_data.get('url', ''),
            'selectors': _parse_selectors_from_form(form_data),
            'timeout': int(form_data.get('timeout', 30)),
            'extract_text': form_data.get('extract_text') == 'on',
            'extract_links': form_data.get('extract_links') == 'on'
        }
        
        # Add headers if provided
        headers = {}
        if form_data.get('user_agent'):
            headers['User-Agent'] = form_data.get('user_agent')
        if headers:
            config['headers'] = headers
    
    elif job_type == 'rss_reader':
        config = {
            'feed_url': form_data.get('feed_url', ''),
            'max_entries': int(form_data.get('max_entries', 50)) if form_data.get('max_entries') else 50,
            'timeout': int(form_data.get('timeout', 30)),
            'title_filter': form_data.get('title_filter', ''),
            'content_filter': form_data.get('content_filter', ''),
            'include_content': form_data.get('include_content') == 'on',
            'include_summary': form_data.get('include_summary') == 'on'
        }
    
    elif job_type == 'filter':
        config = {
            'input_source': form_data.get('input_source', ''),
            'input_data': form_data.get('input_data', ''),
            'source_job_id': form_data.get('source_job_id', ''),
            'filters': _parse_filters_from_form(form_data),
            'output_format': form_data.get('output_format', 'json'),
            'max_results': int(form_data.get('max_results', 100)) if form_data.get('max_results') else 100
        }
    
    elif job_type == 'email_sender':
        config = {
            'smtp_server': form_data.get('smtp_server', ''),
            'smtp_port': int(form_data.get('smtp_port', 587)),
            'username': form_data.get('username', ''),
            'password': form_data.get('password', ''),
            'use_tls': form_data.get('use_tls') == 'on',
            'to_emails': form_data.get('to_emails', ''),
            'subject': form_data.get('subject', ''),
            'body_template': form_data.get('body_template', ''),
            'data_source': form_data.get('data_source', ''),
            'source_job_id': form_data.get('source_job_id', ''),
            'manual_data_content': form_data.get('manual_data_content', ''),
            'send_as_html': form_data.get('send_as_html') == 'on',
            'include_attachments': form_data.get('include_attachments') == 'on'
        }
    
    return config


def _parse_selectors_from_form(form_data: dict) -> dict:
    """Parse CSS selectors from form data."""
    selectors = {}
    selector_names = form_data.getlist('selector_name')
    selector_values = form_data.getlist('selector_value')
    
    for name, value in zip(selector_names, selector_values):
        if name and value:
            selectors[name] = value
    
    return selectors


def _parse_filters_from_form(form_data: dict) -> list[dict]:
    """Parse filters from form data."""
    filters = []
    filter_fields = form_data.getlist('filter_field')
    filter_operators = form_data.getlist('filter_operator')
    filter_values = form_data.getlist('filter_value')
    
    for field, operator, value in zip(filter_fields, filter_operators, filter_values):
        if field and operator and value:
            filters.append({
                'field': field,
                'operator': operator,
                'value': value
            })
    
    return filters


def _parse_list_from_form(value: str) -> list[str]:
    """Parse comma-separated list from form value."""
    if not value:
        return []
    return [item.strip() for item in value.split(',') if item.strip()]


def _parse_json_from_form(value: str) -> dict:
    """Parse JSON from form value."""
    import json
    try:
        return json.loads(value) if value else {}
    except json.JSONDecodeError:
        return {}
