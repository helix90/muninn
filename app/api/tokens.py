"""REST API endpoints for managing API tokens (requires session auth)."""

from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.api import api_bp
from app.api.auth import require_api_auth
from app.extensions import db
from app.models import ApiToken


# --- Web UI routes for token management ---

@api_bp.route('/tokens/manage', methods=['GET'])
@login_required
def manage_tokens():
    tokens = (
        ApiToken.query
        .filter_by(user_id=current_user.id, is_active=True)
        .order_by(ApiToken.created_at.desc())
        .all()
    )
    return render_template('api/tokens.html', tokens=tokens)


@api_bp.route('/tokens/create', methods=['POST'])
@login_required
def create_token_ui():
    name = (request.form.get('name') or '').strip()
    if not name:
        flash('Token name is required.', 'error')
        return redirect(url_for('api.manage_tokens'))

    raw = ApiToken.generate()
    token = ApiToken(
        user_id=current_user.id,
        name=name,
        token_hash=ApiToken.hash_token(raw),
    )
    db.session.add(token)
    db.session.commit()
    flash(
        f'Token created. Copy it now — it will not be shown again: {raw}',
        'token_reveal',
    )
    return redirect(url_for('api.manage_tokens'))


@api_bp.route('/tokens/<int:token_id>/revoke', methods=['POST'])
@login_required
def revoke_token(token_id):
    token = ApiToken.query.filter_by(id=token_id, user_id=current_user.id).first()
    if token:
        token.is_active = False
        db.session.commit()
        flash('Token revoked.', 'success')
    return redirect(url_for('api.manage_tokens'))


# --- REST API endpoint: list tokens (no raw values) ---

@api_bp.route('/tokens', methods=['GET'])
@require_api_auth
def list_tokens():
    from flask import g
    tokens = ApiToken.query.filter_by(user_id=g.api_user.id, is_active=True).all()
    return jsonify([{
        'id': t.id,
        'name': t.name,
        'created_at': t.created_at.isoformat() if t.created_at else None,
        'last_used_at': t.last_used_at.isoformat() if t.last_used_at else None,
    } for t in tokens])
