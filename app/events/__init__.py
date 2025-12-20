"""
Events blueprint for displaying and managing events.
"""

from flask import Blueprint

events = Blueprint('events', __name__, url_prefix='/events')

from app.events import views
