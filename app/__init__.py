import logging
import os
import re
from flask import Flask, render_template, request
from config import config
from app.extensions import init_extensions


class CredentialMaskingFilter(logging.Filter):
    """Filter to mask credential values and references in logs"""
    # Pattern to match {{credential:name}}
    CREDENTIAL_PATTERN = re.compile(r'\{\{credential:([a-zA-Z0-9_-]+)\}\}')
    # Pattern to match common credential-like values (long alphanumeric strings that might be API keys)
    API_KEY_PATTERN = re.compile(r'(["\']?)([a-zA-Z0-9]{20,})(["\']?)')

    def filter(self, record):
        """Filter log records to mask credential references and values"""
        if isinstance(record.msg, str):
            # Mask {{credential:name}} references
            record.msg = self.CREDENTIAL_PATTERN.sub(r'***CREDENTIAL:\1***', record.msg)

        # Also mask in args if present
        if record.args:
            try:
                if isinstance(record.args, dict):
                    record.args = {
                        k: self._mask_value(v) for k, v in record.args.items()
                    }
                elif isinstance(record.args, tuple):
                    record.args = tuple(self._mask_value(arg) for arg in record.args)
            except Exception:
                # If we can't mask args, leave them as is
                pass

        return True

    def _mask_value(self, value):
        """Mask a single value if it looks like a credential"""
        if isinstance(value, str):
            # Mask credential references
            value = self.CREDENTIAL_PATTERN.sub(r'***CREDENTIAL:\1***', value)
        return value


def create_app(config_name=None):
    """Application factory for creating Flask app instances."""
    
    # Determine configuration
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'default')
    
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)
    
    # Initialize extensions (database, migrations, scheduler, etc.)
    db, migrate, scheduler = init_extensions(app)
    
    # Setup logging
    setup_logging(app)
    
    # Register blueprints
    from app.main import main as main_blueprint
    from app.agents.views import agents as agents_blueprint
    from app.scheduler import scheduler_bp as scheduler_blueprint
    from app.auth import auth as auth_blueprint
    from app.events import events as events_blueprint
    from app.credentials import credentials_bp as credentials_blueprint

    app.register_blueprint(main_blueprint)
    app.register_blueprint(auth_blueprint)
    app.register_blueprint(agents_blueprint)
    app.register_blueprint(scheduler_blueprint)
    app.register_blueprint(events_blueprint)
    app.register_blueprint(credentials_blueprint)
    
    # Register CLI commands
    from app.cli import register_commands
    register_commands(app)
    
    # Register error handlers
    register_error_handlers(app)
    
    # Log application startup
    app.logger.info(f'Muninn application started with {config_name} configuration')
    
    return app


def setup_logging(app):
    """Setup application logging."""

    # Remove default Flask logger handlers
    for handler in app.logger.handlers:
        app.logger.removeHandler(handler)

    # Set log level
    app.logger.setLevel(app.config['LOG_LEVEL'])

    # Create formatter
    formatter = logging.Formatter(app.config['LOG_FORMAT'])

    # Create credential masking filter
    credential_filter = CredentialMaskingFilter()

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(app.config['LOG_LEVEL'])
    console_handler.setFormatter(formatter)
    console_handler.addFilter(credential_filter)
    app.logger.addHandler(console_handler)

    # File handler for development
    if app.debug and not app.testing:
        if not os.path.exists('logs'):
            os.mkdir('logs')

        file_handler = logging.FileHandler('logs/muninn-dev.log')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(credential_filter)
        app.logger.addHandler(file_handler)

    app.logger.info('Logging setup completed')


def register_error_handlers(app):
    """Register application error handlers."""

    @app.errorhandler(404)
    def not_found_error(error):
        """Handle 404 errors."""
        app.logger.warning(f'Page not found: {request.url}')
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 errors."""
        from app.extensions import db
        app.logger.error(f'Server Error: {error}')
        try:
            db.session.rollback()
        except:
            pass
        return render_template('errors/500.html'), 500

    @app.errorhandler(Exception)
    def handle_exception(e):
        """Handle unhandled exceptions."""
        from app.extensions import db
        app.logger.error(f'Unhandled exception: {e}')
        try:
            db.session.rollback()
        except:
            pass
        return render_template('errors/500.html'), 500

    @app.teardown_appcontext
    def shutdown_session(exception=None):
        """Cleanup database session after each request."""
        from app.extensions import db
        if exception:
            try:
                db.session.rollback()
            except:
                pass
        try:
            db.session.remove()
        except:
            pass 