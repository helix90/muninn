import json
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
    from app.scenarios import scenarios_bp as scenarios_blueprint
    from app.webhooks import webhook_bp as webhooks_blueprint
    from app.health import health_bp as health_blueprint
    from app.template_library import template_library_bp
    from app.api import api_bp
    from app.pipeline_runs import pipeline_runs_bp

    app.register_blueprint(main_blueprint)
    app.register_blueprint(auth_blueprint)
    app.register_blueprint(agents_blueprint)
    app.register_blueprint(scheduler_blueprint)
    app.register_blueprint(events_blueprint)
    app.register_blueprint(credentials_blueprint)
    app.register_blueprint(scenarios_blueprint)
    app.register_blueprint(webhooks_blueprint)
    app.register_blueprint(health_blueprint)
    app.register_blueprint(template_library_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(pipeline_runs_bp)
    
    # Register CLI commands
    from app.cli import register_commands
    register_commands(app)
    
    # Register error handlers
    register_error_handlers(app)

    # Register context processors
    register_context_processors(app)

    # Register custom Jinja filters
    register_template_filters(app)

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

    # Suppress verbose SQLAlchemy logging - set to ERROR to block all SQL statements
    logging.getLogger('sqlalchemy').setLevel(logging.ERROR)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.ERROR)
    logging.getLogger('sqlalchemy.pool').setLevel(logging.ERROR)
    logging.getLogger('sqlalchemy.dialects').setLevel(logging.ERROR)
    logging.getLogger('sqlalchemy.orm').setLevel(logging.ERROR)

    # Also add a filter to the console handler to block SQLAlchemy messages
    class SQLAlchemyFilter(logging.Filter):
        def filter(self, record):
            # Block all SQLAlchemy logs below ERROR level
            if record.name.startswith('sqlalchemy'):
                return record.levelno >= logging.ERROR
            return True

    sqlalchemy_filter = SQLAlchemyFilter()
    console_handler.addFilter(sqlalchemy_filter)

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


def register_template_filters(app):
    """Register custom Jinja2 filters."""

    @app.template_filter('format_json')
    def format_json(value, indent=2):
        """Pretty-print a value as JSON for display in a <pre> block.

        Flask's built-in |tojson filter escapes characters such as ' < > & into
        \\u0027 \\u003c \\u003e \\u0026 for safe embedding inside <script> tags. That
        escaping is unnecessary and unreadable when displaying JSON in a <pre> block.
        This filter uses plain json.dumps with ensure_ascii=False (so apostrophes,
        curly quotes, em dashes, etc. appear as real characters), then applies normal
        HTML escaping so the result is safe to embed directly in HTML.
        """
        from markupsafe import Markup, escape
        raw = json.dumps(value, indent=indent, ensure_ascii=False, default=str)
        return Markup(escape(raw))


def register_context_processors(app):
    """Register context processors to inject variables into all templates."""
    from datetime import datetime

    @app.context_processor
    def inject_current_year():
        """Inject current year into all templates for copyright."""
        return {'current_year': datetime.now().year} 