import json
import logging

from flask import flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.scenarios.export_import import ImportValidationError, import_scenario, validate_import_document
from app.template_library import template_library_bp
from app.template_library import catalog

logger = logging.getLogger(__name__)


@template_library_bp.route('/')
@login_required
def gallery():
    templates = catalog.get_all()
    return render_template('template_library/gallery.html', templates=templates)


@template_library_bp.route('/<slug>/import', methods=['POST'])
@login_required
def import_template(slug):
    tmpl = catalog.get_by_slug(slug)
    if tmpl is None:
        flash('Template not found.', 'error')
        return redirect(url_for('template_library.gallery'))

    doc = tmpl['doc']
    # Strip the _template_meta key so the importer sees a clean export document
    clean_doc = {k: v for k, v in doc.items() if k != '_template_meta'}

    try:
        validate_import_document(json.dumps(clean_doc).encode())
    except ImportValidationError as exc:
        flash(f'Template validation failed: {exc}', 'error')
        return redirect(url_for('template_library.gallery'))

    try:
        scenario, warnings = import_scenario(clean_doc, current_user.id)
    except Exception as exc:
        db.session.rollback()
        logger.error(f'Template import failed for {slug}: {exc}')
        flash('Import failed due to an unexpected error.', 'error')
        return redirect(url_for('template_library.gallery'))

    agent_count = len(doc.get('agents', []))
    flash(
        f"Template '{tmpl['display_name']}' imported as '{scenario.name}' "
        f"({agent_count} agent{'s' if agent_count != 1 else ''}).",
        'success',
    )
    for warning in warnings:
        flash(warning, 'warning')

    return redirect(url_for('scenarios.scenario_detail', scenario_id=scenario.id))
