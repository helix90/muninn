from flask import Blueprint

pipeline_runs_bp = Blueprint('pipeline_runs', __name__, url_prefix='/pipeline-runs')

from app.pipeline_runs import views  # noqa: F401,E402
