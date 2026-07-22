from flask import Blueprint

api_bp = Blueprint('api', __name__, url_prefix='/api/v1')

from app.api import agents, events, scenarios, tokens  # noqa: F401,E402
