"""
Authentication views for Muninn application
"""

import logging
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user, login_required
from app.auth import auth
from app.auth.forms import LoginForm, RegistrationForm
from app.extensions import db
from app.models import User

logger = logging.getLogger(__name__)


@auth.route('/login', methods=['GET', 'POST'])
def login():
    """User login route."""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    form = LoginForm()
    if form.validate_on_submit():
        # Find user by username
        user = db.session.query(User).filter_by(username=form.username.data).first()

        if user and user.check_password(form.password.data):
            # Check if account is active
            if not user.is_active:
                flash('Your account is inactive. Please contact an administrator.', 'error')
                return render_template('auth/login.html', form=form)

            # Log the user in
            login_user(user, remember=form.remember_me.data)
            logger.info(f'User {user.username} logged in successfully')

            # Redirect to next page or index
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            return redirect(url_for('main.index'))

        flash('Invalid username or password', 'error')

    return render_template('auth/login.html', form=form)


@auth.route('/register', methods=['GET', 'POST'])
def register():
    """User registration route."""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    form = RegistrationForm()
    if form.validate_on_submit():
        try:
            # Create new user
            user = User(
                username=form.username.data,
                email=form.email.data,
                password=form.password.data
            )
            db.session.add(user)
            db.session.commit()

            logger.info(f'New user registered: {user.username}')
            flash(f'Registration successful! Welcome, {user.username}. Please log in.', 'success')
            return redirect(url_for('auth.login'))

        except Exception as e:
            db.session.rollback()
            logger.error(f'Error during registration: {e}')
            flash('An error occurred during registration. Please try again.', 'error')

    return render_template('auth/register.html', form=form)


@auth.route('/logout')
@login_required
def logout():
    """User logout route."""
    username = current_user.username
    logout_user()
    logger.info(f'User {username} logged out')
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.login'))
