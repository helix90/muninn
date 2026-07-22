from flask import Blueprint

template_library_bp = Blueprint('template_library', __name__, url_prefix='/template-library')

from app.template_library import views  # noqa: F401,E402
