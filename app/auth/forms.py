"""
Authentication forms for Muninn application
"""

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, Length, EqualTo, ValidationError
from app.models import User
from app.extensions import db
from app.constants import MIN_PASSWORD_LENGTH, MIN_USERNAME_LENGTH, MAX_USERNAME_LENGTH


class LoginForm(FlaskForm):
    """Form for user login."""

    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Log In')


class RegistrationForm(FlaskForm):
    """Form for user registration."""

    username = StringField('Username', validators=[
        DataRequired(),
        Length(min=MIN_USERNAME_LENGTH, max=MAX_USERNAME_LENGTH,
               message=f'Username must be between {MIN_USERNAME_LENGTH} and {MAX_USERNAME_LENGTH} characters')
    ])
    email = StringField('Email', validators=[
        DataRequired(),
        Email(message='Please enter a valid email address')
    ])
    password = PasswordField('Password', validators=[
        DataRequired(),
        Length(min=MIN_PASSWORD_LENGTH, message=f'Password must be at least {MIN_PASSWORD_LENGTH} characters')
    ])
    password_confirm = PasswordField('Confirm Password', validators=[
        DataRequired(),
        EqualTo('password', message='Passwords must match')
    ])
    submit = SubmitField('Register')

    def validate_username(self, field):
        """Check if username is already taken."""
        if db.session.query(User).filter_by(username=field.data).first():
            raise ValidationError('Username already taken. Please choose a different one.')

    def validate_email(self, field):
        """Check if email is already registered."""
        if db.session.query(User).filter_by(email=field.data.lower()).first():
            raise ValidationError('Email already registered. Please use a different email.')


class ChangePasswordForm(FlaskForm):
    """Form for changing user password."""

    current_password = PasswordField('Current Password', validators=[
        DataRequired(message='Please enter your current password')
    ])
    new_password = PasswordField('New Password', validators=[
        DataRequired(),
        Length(min=MIN_PASSWORD_LENGTH, message=f'Password must be at least {MIN_PASSWORD_LENGTH} characters')
    ])
    confirm_password = PasswordField('Confirm New Password', validators=[
        DataRequired(),
        EqualTo('new_password', message='Passwords must match')
    ])
    submit = SubmitField('Change Password')
