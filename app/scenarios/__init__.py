"""Scenarios blueprint for agent grouping"""
from flask import Blueprint

scenarios_bp = Blueprint('scenarios', __name__, url_prefix='/scenarios')

from app.scenarios import views  # noqa
from app.scenarios import editor_api  # noqa
