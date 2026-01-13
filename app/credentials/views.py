"""Views for credential management"""
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.credentials import credentials_bp
from app.services.credential_service import CredentialService
from app.models import Credential
from app.extensions import db
from app.utils.encryption import ConfigEncryption
import logging
import re

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
