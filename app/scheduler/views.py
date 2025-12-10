"""
Scheduler management views for the Muninn application
"""

import logging
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from datetime import datetime

from app.extensions import db
from app.services.scheduler_service import SchedulerService
from app.models import Job

# Create blueprint
scheduler_bp = Blueprint('scheduler', __name__, url_prefix='/scheduler')
logger = logging.getLogger(__name__)


@scheduler_bp.route('/')
@login_required
def scheduler_dashboard():
    """Scheduler dashboard page."""
    try:
        user_id = current_user.id
        scheduler_service = SchedulerService(db.session)
        
        # Get scheduled jobs
        scheduled_jobs = scheduler_service.get_scheduled_jobs(user_id)
        
        # Get scheduler status
        scheduler_status = scheduler_service.get_scheduler_status()
        
        return render_template('scheduler/dashboard.html', 
                             scheduled_jobs=scheduled_jobs,
                             scheduler_status=scheduler_status)
        
    except Exception as e:
        logger.error(f"Error in scheduler_dashboard: {e}")
        flash('An error occurred while loading the scheduler dashboard', 'error')
        return redirect(url_for('main.index'))


@scheduler_bp.route('/jobs')
@login_required
def scheduled_jobs():
    """List of scheduled jobs."""
    try:
        user_id = current_user.id
        scheduler_service = SchedulerService(db.session)
        
        # Get scheduled jobs
        scheduled_jobs = scheduler_service.get_scheduled_jobs(user_id)
        
        return render_template('scheduler/jobs.html', 
                             scheduled_jobs=scheduled_jobs)
        
    except Exception as e:
        logger.error(f"Error in scheduled_jobs: {e}")
        flash('An error occurred while loading scheduled jobs', 'error')
        return redirect(url_for('scheduler.scheduler_dashboard'))


@scheduler_bp.route('/schedule/<int:job_id>', methods=['GET', 'POST'])
@login_required
def schedule_job(job_id):
    """Schedule a job."""
    try:
        user_id = current_user.id
        scheduler_service = SchedulerService(db.session)
        
        # Get job details
        job = db.session.query(Job).filter(
            Job.id == job_id,
            Job.user_id == user_id
        ).first()
        
        if not job:
            flash('Job not found or access denied', 'error')
            return redirect(url_for('jobs.job_list'))
        
        if request.method == 'POST':
            # Get form data
            cron_expression = request.form.get('cron_expression', '').strip()
            schedule_type = request.form.get('schedule_type', 'cron')
            interval_minutes = request.form.get('interval_minutes', type=int)
            
            if schedule_type == 'cron':
                if not cron_expression:
                    flash('Cron expression is required', 'error')
                    return render_template('scheduler/schedule.html', job=job)
                
                # Schedule with cron expression
                success, error = scheduler_service.schedule_job(
                    job_id, cron_expression, user_id
                )
            else:
                if not interval_minutes or interval_minutes <= 0:
                    flash('Interval must be a positive number', 'error')
                    return render_template('scheduler/schedule.html', job=job)
                
                # Schedule with interval
                success, error = scheduler_service.schedule_interval_job(
                    job_id, interval_minutes, user_id
                )
            
            if success:
                flash(f'Job "{job.name}" scheduled successfully', 'success')
                return redirect(url_for('scheduler.scheduled_jobs'))
            else:
                flash(f'Failed to schedule job: {error}', 'error')
        
        # GET request - show form
        return render_template('scheduler/schedule.html', job=job)
        
    except Exception as e:
        logger.error(f"Error in schedule_job: {e}")
        flash('An error occurred while scheduling the job', 'error')
        return redirect(url_for('jobs.job_list'))


@scheduler_bp.route('/unschedule/<int:job_id>', methods=['POST'])
@login_required
def unschedule_job(job_id):
    """Unschedule a job."""
    try:
        user_id = current_user.id
        scheduler_service = SchedulerService(db.session)
        
        # Get job details
        job = db.session.query(Job).filter(
            Job.id == job_id,
            Job.user_id == user_id
        ).first()
        
        if not job:
            return jsonify({'success': False, 'error': 'Job not found or access denied'}), 404
        
        # Unschedule the job
        success, error = scheduler_service.unschedule_job(job_id, user_id)
        
        if success:
            return jsonify({
                'success': True, 
                'message': f'Job "{job.name}" unscheduled successfully'
            })
        else:
            return jsonify({'success': False, 'error': error}), 400
            
    except Exception as e:
        logger.error(f"Error in unschedule_job: {e}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@scheduler_bp.route('/status/<int:job_id>')
@login_required
def job_schedule_status(job_id):
    """Get schedule status for a job."""
    try:
        user_id = current_user.id
        scheduler_service = SchedulerService(db.session)
        
        status = scheduler_service.get_job_schedule_status(job_id, user_id)
        
        if not status:
            return jsonify({'success': False, 'error': 'Job not found or access denied'}), 404
        
        return jsonify({'success': True, 'status': status})
        
    except Exception as e:
        logger.error(f"Error in job_schedule_status: {e}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@scheduler_bp.route('/status')
@login_required
def scheduler_status():
    """Get overall scheduler status."""
    try:
        scheduler_service = SchedulerService(db.session)
        status = scheduler_service.get_scheduler_status()
        
        return jsonify({'success': True, 'status': status})
        
    except Exception as e:
        logger.error(f"Error in scheduler_status: {e}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@scheduler_bp.route('/cron-help')
@login_required
def cron_help():
    """Cron expression help page."""
    return render_template('scheduler/cron_help.html')
