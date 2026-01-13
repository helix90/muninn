"""Credentials blueprint"""
from flask import Blueprint

credentials_bp = Blueprint('credentials', __name__, url_prefix='/credentials')

from app.credentials import views
