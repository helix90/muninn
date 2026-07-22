"""Health dashboard blueprint"""
from flask import Blueprint

health_bp = Blueprint('health', __name__, url_prefix='/health')

from app.health import views  # noqa: F401, E402
