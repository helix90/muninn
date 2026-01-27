import logging
from datetime import datetime
from flask import Blueprint, render_template, jsonify, current_app
from app.main import main
from app.extensions import db
from sqlalchemy import text


@main.route('/')
def index():
    """Home page route."""
    current_app.logger.info('Home page accessed')
    return render_template('main/index.html')


@main.route('/health')
def health_check():
    """Health check endpoint for monitoring."""
    current_app.logger.debug('Health check requested')
    
    # Check database connectivity
    db_status = 'healthy'
    try:
        # Simple database connectivity test
        db.session.execute(text('SELECT 1'))
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f'Database health check failed: {e}')
        db_status = 'unhealthy'
    
    health_status = {
        'status': 'healthy' if db_status == 'healthy' else 'degraded',
        'service': 'Muninn',
        'version': '1.0.0',
        'environment': current_app.config.get('ENV', 'development'),
        'database': db_status,
        'timestamp': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    # Set appropriate HTTP status code
    status_code = 200 if db_status == 'healthy' else 503
    
    return jsonify(health_status), status_code 