"""
Tests for authentication functionality using Flask-Login
"""

import pytest
from flask_login import current_user
from app.models import User
from app.extensions import db


class TestAuthenticationRoutes:
    """Test authentication routes."""

    def test_login_page_accessible(self, client):
        """Test that login page is accessible."""
        response = client.get('/auth/login')
        assert response.status_code == 200

    def test_register_page_accessible(self, client):
        """Test that register page is accessible."""
        response = client.get('/auth/register')
        assert response.status_code == 200

    def test_logout_redirects_when_not_logged_in(self, client):
        """Test that logout redirects when user is not logged in."""
        response = client.get('/auth/logout', follow_redirects=False)
        # Should redirect to login page
        assert response.status_code in [302, 401]


class TestUserRegistration:
    """Test user registration functionality."""

    def test_user_can_register(self, client, app):
        """Test that a user can register successfully."""
        response = client.post('/auth/register', data={
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'password123',
            'password_confirm': 'password123'
        }, follow_redirects=True)

        # Should redirect to login page after successful registration
        assert response.status_code == 200

        # Verify user was created in database
        with app.app_context():
            user = db.session.query(User).filter_by(username='testuser').first()
            assert user is not None
            assert user.email == 'test@example.com'

    def test_duplicate_username_rejected(self, client, app):
        """Test that duplicate usernames are rejected."""
        # Create first user
        with app.app_context():
            user = User(
                username='existinguser',
                email='existing@example.com',
                password='password123'
            )
            db.session.add(user)
            db.session.commit()

        # Try to register with same username
        response = client.post('/auth/register', data={
            'username': 'existinguser',
            'email': 'different@example.com',
            'password': 'password123',
            'password_confirm': 'password123'
        })

        # Should show error
        assert response.status_code == 200
        assert b'already taken' in response.data or b'Username' in response.data

    def test_password_mismatch_rejected(self, client):
        """Test that mismatched passwords are rejected."""
        response = client.post('/auth/register', data={
            'username': 'newuser',
            'email': 'new@example.com',
            'password': 'password123',
            'password_confirm': 'different456'
        })

        # Should show error
        assert response.status_code == 200
        assert b'match' in response.data or b'password' in response.data.lower()


class TestUserLogin:
    """Test user login functionality."""

    def test_user_can_login(self, client, app):
        """Test that a user can log in successfully."""
        # Create a user
        with app.app_context():
            user = User(
                username='loginuser',
                email='login@example.com',
                password='password123'
            )
            db.session.add(user)
            db.session.commit()

        # Log in
        response = client.post('/auth/login', data={
            'username': 'loginuser',
            'password': 'password123'
        }, follow_redirects=True)

        assert response.status_code == 200

    def test_invalid_username_rejected(self, client):
        """Test that invalid username is rejected."""
        response = client.post('/auth/login', data={
            'username': 'nonexistent',
            'password': 'password123'
        })

        # Should show error or stay on login page
        assert response.status_code == 200

    def test_invalid_password_rejected(self, client, app):
        """Test that invalid password is rejected."""
        # Create a user
        with app.app_context():
            user = User(
                username='passwordtest',
                email='passwordtest@example.com',
                password='correctpassword'
            )
            db.session.add(user)
            db.session.commit()

        # Try to log in with wrong password
        response = client.post('/auth/login', data={
            'username': 'passwordtest',
            'password': 'wrongpassword'
        })

        # Should show error or stay on login page
        assert response.status_code == 200


class TestProtectedRoutes:
    """Test that routes are properly protected."""

    def test_scheduler_route_requires_authentication(self, client):
        """Test that scheduler routes require authentication."""
        response = client.get('/scheduler/', follow_redirects=False)
        # Should redirect to login
        assert response.status_code in [302, 401]


class TestUserModel:
    """Test User model functionality."""

    def test_password_hashing(self, app):
        """Test that passwords are hashed."""
        with app.app_context():
            user = User(username='hashtest', email='hash@example.com', password='mypassword')

            # Password should be hashed, not stored as plaintext
            assert user.password_hash != 'mypassword'
            assert len(user.password_hash) > 20  # Hashed passwords are long

    def test_password_verification(self, app):
        """Test password verification."""
        with app.app_context():
            user = User(username='verifytest', email='verify@example.com', password='mypassword')

            # Correct password should verify
            assert user.check_password('mypassword') is True

            # Incorrect password should not verify
            assert user.check_password('wrongpassword') is False

    def test_user_is_authenticated(self, app):
        """Test UserMixin is_authenticated property."""
        with app.app_context():
            user = User(username='authtest', email='authtest@example.com', password='password')
            user.is_active = True

            # Active user should be authenticated
            assert user.is_authenticated is True

    def test_user_get_id(self, app):
        """Test that get_id returns string ID."""
        with app.app_context():
            user = User(username='idtest', email='idtest@example.com', password='password')
            db.session.add(user)
            db.session.commit()

            # get_id should return string
            user_id = user.get_id()
            assert isinstance(user_id, str)
            assert int(user_id) == user.id


class TestAuthenticationForms:
    """Test authentication forms."""

    def test_login_form_validation(self, app):
        """Test login form validation."""
        from app.auth.forms import LoginForm
        from flask import Flask
        from flask_wtf.csrf import CSRFProtect

        # Create form with app context
        with app.test_request_context():
            form = LoginForm(data={
                'username': '',
                'password': ''
            })

            # Empty form should not validate
            assert form.validate() is False

    def test_registration_form_validation(self, app):
        """Test registration form validation."""
        from app.auth.forms import RegistrationForm

        with app.test_request_context():
            form = RegistrationForm(data={
                'username': 'ab',  # Too short
                'email': 'invalid-email',
                'password': 'short',  # Too short
                'password_confirm': 'different'  # Doesn't match
            })

            # Invalid form should not validate
            assert form.validate() is False


class TestUserSettings:
    """Test user settings functionality."""

    def test_settings_route_requires_authentication(self, client):
        """Test that settings route requires authentication."""
        response = client.get('/auth/settings', follow_redirects=False)
        # Should redirect to login page
        assert response.status_code in [302, 401]

    def test_settings_page_get_request(self, client, app):
        """Test that authenticated user can access settings page."""
        # Create and log in a user
        with app.app_context():
            user = User(
                username='settingsuser',
                email='settings@example.com',
                password='password123'
            )
            db.session.add(user)
            db.session.commit()

        # Log in
        client.post('/auth/login', data={
            'username': 'settingsuser',
            'password': 'password123'
        })

        # Access settings page
        response = client.get('/auth/settings')
        assert response.status_code == 200
        assert b'User Settings' in response.data or b'Account Information' in response.data

    def test_successful_password_change(self, client, app):
        """Test successful password change with valid data."""
        # Create and log in a user
        with app.app_context():
            user = User(
                username='changepass',
                email='changepass@example.com',
                password='oldpassword123'
            )
            db.session.add(user)
            db.session.commit()
            user_id = user.id

        # Log in
        client.post('/auth/login', data={
            'username': 'changepass',
            'password': 'oldpassword123'
        })

        # Change password
        response = client.post('/auth/settings', data={
            'current_password': 'oldpassword123',
            'new_password': 'newpassword456',
            'confirm_password': 'newpassword456'
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b'Password changed successfully' in response.data

        # Verify password was actually changed in database
        with app.app_context():
            user = db.session.query(User).get(user_id)
            assert user.check_password('newpassword456') is True
            assert user.check_password('oldpassword123') is False

    def test_incorrect_current_password_rejected(self, client, app):
        """Test that incorrect current password is rejected."""
        # Create and log in a user
        with app.app_context():
            user = User(
                username='wrongpass',
                email='wrongpass@example.com',
                password='correctpassword'
            )
            db.session.add(user)
            db.session.commit()

        # Log in
        client.post('/auth/login', data={
            'username': 'wrongpass',
            'password': 'correctpassword'
        })

        # Try to change password with wrong current password
        response = client.post('/auth/settings', data={
            'current_password': 'wrongoldpassword',
            'new_password': 'newpassword456',
            'confirm_password': 'newpassword456'
        })

        assert response.status_code == 200
        assert b'Current password is incorrect' in response.data

    def test_new_password_too_short_rejected(self, client, app):
        """Test that new password shorter than minimum length is rejected."""
        from app.constants import MIN_PASSWORD_LENGTH

        # Create and log in a user
        with app.app_context():
            user = User(
                username='shortpass',
                email='shortpass@example.com',
                password='validpassword123'
            )
            db.session.add(user)
            db.session.commit()

        # Log in
        client.post('/auth/login', data={
            'username': 'shortpass',
            'password': 'validpassword123'
        })

        # Try to change password with too short new password
        response = client.post('/auth/settings', data={
            'current_password': 'validpassword123',
            'new_password': 'short',
            'confirm_password': 'short'
        })

        assert response.status_code == 200
        # Should show validation error about password length

    def test_password_confirmation_mismatch_rejected(self, client, app):
        """Test that mismatched password confirmation is rejected."""
        # Create and log in a user
        with app.app_context():
            user = User(
                username='mismatchuser',
                email='mismatch@example.com',
                password='currentpassword123'
            )
            db.session.add(user)
            db.session.commit()

        # Log in
        client.post('/auth/login', data={
            'username': 'mismatchuser',
            'password': 'currentpassword123'
        })

        # Try to change password with mismatched confirmation
        response = client.post('/auth/settings', data={
            'current_password': 'currentpassword123',
            'new_password': 'newpassword456',
            'confirm_password': 'differentpassword789'
        })

        assert response.status_code == 200
        # Should show validation error about passwords not matching

    def test_can_login_with_new_password(self, client, app):
        """Test that user can login with new password after change."""
        # Create and log in a user
        with app.app_context():
            user = User(
                username='logintest',
                email='logintest@example.com',
                password='oldpass123'
            )
            db.session.add(user)
            db.session.commit()

        # Log in
        client.post('/auth/login', data={
            'username': 'logintest',
            'password': 'oldpass123'
        })

        # Change password
        client.post('/auth/settings', data={
            'current_password': 'oldpass123',
            'new_password': 'newpass456',
            'confirm_password': 'newpass456'
        })

        # Log out
        client.get('/auth/logout')

        # Log in with new password
        response = client.post('/auth/login', data={
            'username': 'logintest',
            'password': 'newpass456'
        }, follow_redirects=True)

        assert response.status_code == 200

        # Try to log in with old password (should fail)
        client.get('/auth/logout')
        response = client.post('/auth/login', data={
            'username': 'logintest',
            'password': 'oldpass123'
        })

        assert response.status_code == 200
        assert b'Invalid username or password' in response.data

    def test_settings_shows_user_information(self, client, app):
        """Test that settings page displays user account information."""
        # Create and log in a user
        with app.app_context():
            user = User(
                username='infouser',
                email='info@example.com',
                password='password123'
            )
            db.session.add(user)
            db.session.commit()

        # Log in
        client.post('/auth/login', data={
            'username': 'infouser',
            'password': 'password123'
        })

        # Access settings page
        response = client.get('/auth/settings')

        assert response.status_code == 200
        assert b'infouser' in response.data
        assert b'info@example.com' in response.data


class TestFlaskLoginIntegration:
    """Test Flask-Login integration."""

    def test_login_manager_configured(self, app):
        """Test that login manager is configured."""
        from app.extensions import login_manager

        assert login_manager is not None
        assert login_manager.login_view == 'auth.login'

    def test_user_loader_function(self, app):
        """Test that user loader function works."""
        from app.extensions import login_manager

        with app.app_context():
            # Create a user
            user = User(username='loadertest', email='loader@example.com', password='password')
            db.session.add(user)
            db.session.commit()
            user_id = user.id

            # Test user loader
            loaded_user = login_manager._user_callback(str(user_id))
            assert loaded_user is not None
            assert loaded_user.username == 'loadertest'

    def test_user_loader_with_invalid_id(self, app):
        """Test user loader with invalid ID."""
        from app.extensions import login_manager

        with app.app_context():
            # Should return None for non-existent user
            loaded_user = login_manager._user_callback('99999')
            assert loaded_user is None
