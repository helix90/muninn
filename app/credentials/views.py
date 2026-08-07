"""Views for credential management"""
import io
import json
import logging
import re
from datetime import datetime

from flask import render_template, request, redirect, url_for, flash, make_response
from flask_login import login_required, current_user

from app.credentials import credentials_bp
from app.extensions import db
from app.models import Credential
from app.services.credential_service import CredentialService
from app.utils.encryption import ConfigEncryption

logger = logging.getLogger(__name__)


@credentials_bp.route('/')
@login_required
def credential_list():
    """List all credentials for current user"""
    service = CredentialService()
    credentials = service.get_credentials_for_user(current_user.id)

    return render_template('credentials/list.html', credentials=credentials)


@credentials_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_credential():
    """Create a new credential"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        value = request.form.get('value', '')
        description = request.form.get('description', '').strip()

        # Validation
        if not name:
            flash('Credential name is required', 'error')
            return render_template('credentials/create.html')

        if not value:
            flash('Credential value is required', 'error')
            return render_template('credentials/create.html')

        # Name validation (alphanumeric, underscore, hyphen only)
        if not re.match(r'^[a-zA-Z0-9_-]+$', name):
            flash('Credential name can only contain letters, numbers, underscore, and hyphen', 'error')
            return render_template('credentials/create.html')

        try:
            service = CredentialService()
            service.create_credential(
                user_id=current_user.id,
                name=name,
                value=value,
                description=description
            )
            flash(f"Credential '{name}' created successfully", 'success')
            return redirect(url_for('credentials.credential_list'))
        except ValueError as e:
            flash(str(e), 'error')
            return render_template('credentials/create.html')
        except Exception as e:
            logger.error(f"Error creating credential: {e}")
            flash('An error occurred while creating the credential', 'error')
            return render_template('credentials/create.html')

    return render_template('credentials/create.html')


@credentials_bp.route('/<int:credential_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_credential(credential_id):
    """Edit an existing credential"""
    service = CredentialService()
    credential = db.session.query(Credential).filter_by(
        id=credential_id,
        user_id=current_user.id
    ).first()

    if not credential:
        flash('Credential not found', 'error')
        return redirect(url_for('credentials.credential_list'))

    if request.method == 'POST':
        value = request.form.get('value', '')
        description = request.form.get('description', '').strip()

        # Only update if value is provided (empty = no change)
        value_to_update = value if value else None

        try:
            service.update_credential(
                credential_id=credential_id,
                user_id=current_user.id,
                value=value_to_update,
                description=description
            )
            flash(f"Credential '{credential.name}' updated successfully", 'success')
            return redirect(url_for('credentials.credential_list'))
        except Exception as e:
            logger.error(f"Error updating credential: {e}")
            flash('An error occurred while updating the credential', 'error')

    return render_template('credentials/edit.html', credential=credential)


@credentials_bp.route('/export')
@login_required
def export_credentials():
    """Export all credentials for the current user as a JSON file.

    Values are decrypted in plaintext — the download contains secrets.
    """
    service = CredentialService()
    credentials = service.get_credentials_for_user(current_user.id)

    items = []
    for cred in credentials:
        try:
            value = service.get_decrypted_value(cred)
        except ValueError as e:
            logger.error(f"Skipping credential '{cred.name}' during export: {e}")
            continue
        items.append({
            'name': cred.name,
            'description': cred.description or '',
            'value': value,
        })

    payload = {
        'schema_version': 1,
        'exported_at': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
        'credentials': items,
    }
    body = json.dumps(payload, indent=2)
    filename = f"muninn_credentials_{datetime.utcnow().strftime('%Y-%m-%d')}.json"

    response = make_response(body)
    response.headers['Content-Type'] = 'application/json'
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


_IMPORT_MAX_BYTES = 1 * 1024 * 1024  # 1 MB


@credentials_bp.route('/import', methods=['GET', 'POST'])
@login_required
def import_credentials():
    """Import credentials from a JSON file produced by the export endpoint."""
    if request.method == 'GET':
        return render_template('credentials/import.html')

    uploaded = request.files.get('file')
    if not uploaded or not uploaded.filename:
        flash('Please select a file to import', 'error')
        return render_template('credentials/import.html')

    raw = uploaded.read(_IMPORT_MAX_BYTES + 1)
    if len(raw) > _IMPORT_MAX_BYTES:
        flash('File is too large (max 1 MB)', 'error')
        return render_template('credentials/import.html')

    try:
        data = json.loads(raw.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        flash('File is not valid JSON', 'error')
        return render_template('credentials/import.html')

    if not isinstance(data, dict) or 'credentials' not in data:
        flash('Invalid credential export file — missing "credentials" key', 'error')
        return render_template('credentials/import.html')

    entries = data['credentials']
    if not isinstance(entries, list):
        flash('Invalid credential export file — "credentials" must be a list', 'error')
        return render_template('credentials/import.html')

    service = CredentialService()
    created = skipped = errors = 0

    for entry in entries:
        if not isinstance(entry, dict):
            errors += 1
            continue

        name = entry.get('name', '').strip()
        value = entry.get('value', '')
        description = entry.get('description', '').strip()

        if not name or not value:
            errors += 1
            continue

        if not re.match(r'^[a-zA-Z0-9_-]+$', name):
            errors += 1
            continue

        try:
            service.create_credential(
                user_id=current_user.id,
                name=name,
                value=value,
                description=description or None,
            )
            created += 1
        except ValueError:
            # Duplicate name — skip silently
            skipped += 1
        except Exception as e:
            logger.error(f"Error importing credential '{name}': {e}")
            errors += 1

    parts = []
    if created:
        parts.append(f"{created} credential{'s' if created != 1 else ''} imported")
    if skipped:
        parts.append(f"{skipped} skipped (already exist)")
    if errors:
        parts.append(f"{errors} error{'s' if errors != 1 else ''}")

    if not parts:
        flash('No credentials found in the file', 'warning')
    elif errors and not created:
        flash('; '.join(parts), 'error')
    else:
        flash('; '.join(parts), 'success' if not errors else 'warning')

    return redirect(url_for('credentials.credential_list'))


@credentials_bp.route('/<int:credential_id>/delete', methods=['POST'])
@login_required
def delete_credential(credential_id):
    """Delete a credential"""
    service = CredentialService()

    try:
        success = service.delete_credential(credential_id, current_user.id)
        if success:
            flash('Credential deleted successfully', 'success')
        else:
            flash('Credential not found', 'error')
    except Exception as e:
        logger.error(f"Error deleting credential: {e}")
        flash('An error occurred while deleting the credential', 'error')

    return redirect(url_for('credentials.credential_list'))
