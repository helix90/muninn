"""
Flask extensions for Muninn
"""

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()


def init_extensions(app):
    """Initialize all Flask extensions."""

    try:
        # Initialize SQLAlchemy
        db.init_app(app)
        app.logger.info("SQLAlchemy initialized successfully")
    except Exception as e:
        app.logger.error(f"Failed to initialize SQLAlchemy: {e}")
        raise

    try:
        # Initialize Flask-Migrate
        migrate.init_app(app, db)
        app.logger.info("Flask-Migrate initialized successfully")
    except Exception as e:
        app.logger.error(f"Failed to initialize Flask-Migrate: {e}")
        raise

    try:
        # Initialize Flask-Login
        login_manager.init_app(app)
        login_manager.login_view = 'auth.login'
        login_manager.login_message = 'Please log in to access this page.'
        login_manager.login_message_category = 'info'
        app.logger.info("Flask-Login initialized successfully")
    except Exception as e:
        app.logger.error(f"Failed to initialize Flask-Login: {e}")
        raise

    try:
        # User loader callback for Flask-Login
        from app.models import User

        @login_manager.user_loader
        def load_user(user_id):
            """Load user by ID for Flask-Login.

            Use filter().first() rather than .get() so we always hit the
            database instead of returning a potentially stale identity-map
            entry.  This matters after a DB reset where the session cookie
            still references a deleted user — .get() can return the old
            in-memory object, bypassing @login_required, and causing FK
            violations downstream.
            """
            return db.session.query(User).filter(User.id == int(user_id)).first()

        app.logger.info("User loader registered successfully")
    except Exception as e:
        app.logger.error(f"Failed to register user loader: {e}")
        raise

    try:
        # Import models to ensure they are registered with SQLAlchemy
        from app.models import Job, JobRun, JobChain, AlertLog
        app.logger.info("Database models imported successfully")
    except Exception as e:
        app.logger.error(f"Failed to import database models: {e}")
        raise

    try:
        # Import agent types to ensure they are registered
        from app.agents import agent_registry
        from app.agents import types as agent_types  # This triggers @register_agent decorators
        registered_count = len(agent_registry.get_registered_types())
        app.logger.info(f"Agent registry initialized with {registered_count} agent types")
    except Exception as e:
        app.logger.error(f"Failed to initialize agent registry: {e}")
        raise

    try:
        # Initialize scheduler — but only in the main process, not in the
        # Werkzeug reloader's monitor process (which also imports the app).
        # Without this guard, `flask run` spawns two APScheduler instances
        # that share the same database jobstore and fire every job twice.
        import os
        from app.scheduler import scheduler
        # In debug mode the Werkzeug reloader spawns a monitor process AND a
        # worker process. Both import the app, so without this guard two
        # APScheduler instances start and every job fires twice.
        # WERKZEUG_RUN_MAIN is 'true' only in the worker; it is unset in the
        # monitor. In production (no reloader) it is also unset, so we check
        # app.debug to distinguish the two cases.
        if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
            scheduler.init_app(app)
            app.logger.info("Scheduler initialized successfully")
        else:
            app.logger.info("Scheduler skipped (Werkzeug reloader monitor process)")
    except Exception as e:
        app.logger.error(f"Failed to initialize scheduler: {e}")
        raise

    return db, migrate, scheduler 