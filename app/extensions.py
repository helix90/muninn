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
            """Load user by ID for Flask-Login."""
            return db.session.query(User).get(int(user_id))

        app.logger.info("User loader registered successfully")
    except Exception as e:
        app.logger.error(f"Failed to register user loader: {e}")
        raise

    try:
        # Import models to ensure they are registered with SQLAlchemy
        from app.models import Job, JobRun, JobChain
        app.logger.info("Database models imported successfully")
    except Exception as e:
        app.logger.error(f"Failed to import database models: {e}")
        raise

    try:
        # Import jobs to ensure they are registered
        from app.jobs import job_registry
        app.logger.info(f"Job registry initialized with {len(job_registry)} job types")
    except Exception as e:
        app.logger.error(f"Failed to initialize job registry: {e}")
        raise

    try:
        # Initialize scheduler
        from app.scheduler import scheduler
        scheduler.init_app(app)
        app.logger.info("Scheduler initialized successfully")
    except Exception as e:
        app.logger.error(f"Failed to initialize scheduler: {e}")
        raise

    return db, migrate, scheduler 