"""
Tests for job management views
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from app.models import User, Job, JobRun
from app.jobs import job_registry
from app.extensions import db


class TestJobViews:
    """Test job management views."""
    
    def test_job_list_route(self, client, app_context):
        """Test the job listing page."""
        with app_context.app_context():
            # Create a test user and job
            user = User(username='testuser', email='test@example.com', password='password123')
            db.session.add(user)
            db.session.commit()
            
            job = Job(
                name='Test Job',
                job_type='web_scraper',
                config={'url': 'http://example.com', 'selectors': {'title': 'h1'}},
                user_id=user.id
            )
            db.session.add(job)
            db.session.commit()
            
            # Mock get_current_user_id to return the actual user ID
            with patch('app.jobs.views.get_current_user_id', return_value=user.id):
                # Test the route
                response = client.get('/jobs/')
                assert response.status_code == 200
                assert b'Test Job' in response.data
                assert b'Web Scraper' in response.data
    
    def test_create_job_route_get(self, client):
        """Test the job creation form page."""
        response = client.get('/jobs/create')
        assert response.status_code == 200
        assert b'Create New Job' in response.data
        assert b'job_type' in response.data
    
    def test_create_job_route_post(self, client, app_context):
        """Test job creation via POST."""
        # Create test user
        user = User(username='testuser', email='test@example.com', password='password123')
        
        with app_context.app_context():
            db.session.add(user)
            db.session.commit()
            
            # Test job creation
            job_data = {
                'name': 'New Test Job',
                'job_type': 'web_scraper',
                'url': 'http://example.com',
                'selector_name': ['title'],
                'selector_value': ['h1']
            }
            
            response = client.post('/jobs/create', data=job_data, follow_redirects=True)
            assert response.status_code == 200
            
            # Verify job was created
            job = db.session.query(Job).filter_by(name='New Test Job').first()
            assert job is not None
            assert job.job_type == 'web_scraper'
    
    def test_job_detail_route(self, client, app_context):
        """Test the job detail page."""
        # Create test user and job
        user = User(username='testuser', email='test@example.com', password='password123')
        job = Job(
            name='Test Job',
            job_type='web_scraper',
            config={'url': 'http://example.com', 'selectors': {'title': 'h1'}},
            user_id=1
        )
        
        with app_context.app_context():
            db.session.add(user)
            db.session.commit()
            # Update job to use the actual user ID
            job.user_id = user.id
            db.session.add(job)
            db.session.commit()
            
            # Mock get_current_user_id to return the actual user ID
            with patch('app.jobs.views.get_current_user_id', return_value=user.id):
                # Test the route
                response = client.get(f'/jobs/{job.id}')
                assert response.status_code == 200
                assert b'Test Job' in response.data
                assert b'Web Scraper' in response.data
    
    def test_edit_job_route_get(self, client, app_context):
        """Test the job editing form page."""
        # Create test user and job
        user = User(username='testuser', email='test@example.com', password='password123')
        job = Job(
            name='Test Job',
            job_type='web_scraper',
            config={'url': 'http://example.com', 'selectors': {'title': 'h1'}},
            user_id=1
        )
        
        with app_context.app_context():
            db.session.add(user)
            db.session.commit()
            # Update job to use the actual user ID
            job.user_id = user.id
            db.session.add(job)
            db.session.commit()
            
            # Test the route
            response = client.get(f'/jobs/{job.id}/edit')
            assert response.status_code == 200
            assert b'Edit Job' in response.data
            assert b'Test Job' in response.data
    
    def test_edit_job_route_post(self, client, app_context):
        """Test job editing via POST."""
        # Create test user and job
        user = User(username='testuser', email='test@example.com', password='password123')
        job = Job(
            name='Test Job',
            job_type='web_scraper',
            config={'url': 'http://example.com', 'selectors': {'title': 'h1'}},
            user_id=1
        )
        
        with app_context.app_context():
            db.session.add(user)
            db.session.commit()
            # Update job to use the actual user ID
            job.user_id = user.id
            db.session.add(job)
            db.session.commit()
            
            # Test job editing
            updated_data = {
                'name': 'Updated Test Job',
                'url': 'http://updated.com',
                'selector_name': ['title'],
                'selector_value': ['h1']
            }
            
            response = client.post(f'/jobs/{job.id}/edit', data=updated_data, follow_redirects=True)
            assert response.status_code == 200
            
            # Verify job was updated
            updated_job = db.session.query(Job).get(job.id)
            assert updated_job.name == 'Updated Test Job'
    
    def test_delete_job_route(self, client, app_context):
        """Test job deletion."""
        # Create test user and job
        user = User(username='testuser', email='test@example.com', password='password123')
        job = Job(
            name='Test Job',
            job_type='web_scraper',
            config={'url': 'http://example.com', 'selectors': {'title': 'h1'}},
            user_id=1
        )
        
        with app_context.app_context():
            db.session.add(user)
            db.session.commit()
            # Update job to use the actual user ID
            job.user_id = user.id
            db.session.add(job)
            db.session.commit()
            
            # Test job deletion
            response = client.post(f'/jobs/{job.id}/delete', follow_redirects=True)
            assert response.status_code == 200
            
            # Verify job was deleted
            deleted_job = db.session.query(Job).get(job.id)
            assert deleted_job is None
    
    def test_execute_job_route(self, client, app_context):
        """Test job execution."""
        # Create test user and job
        user = User(username='testuser', email='test@example.com', password='password123')
        job = Job(
            name='Test Job',
            job_type='web_scraper',
            config={'url': 'http://example.com', 'selectors': {'title': 'h1'}},
            user_id=1
        )
        
        with app_context.app_context():
            db.session.add(user)
            db.session.commit()
            # Update job to use the actual user ID
            job.user_id = user.id
            db.session.add(job)
            db.session.commit()
            
            # Mock the job service execution
            with patch('app.jobs.views.JobService') as mock_service:
                mock_instance = Mock()
                mock_instance.execute_job.return_value = (Mock(id=1, status='pending'), None)
                mock_service.return_value = mock_instance
                
                # Test job execution
                response = client.post(f'/jobs/{job.id}/execute')
                assert response.status_code == 200
                
                data = json.loads(response.data)
                assert data['success'] is True
                assert 'run_id' in data
    
    def test_job_runs_route(self, client, app_context):
        """Test getting job execution history."""
        with app_context.app_context():
            # Create test user, job, and job run
            user = User(username='testuser', email='test@example.com', password='password123')
            db.session.add(user)
            db.session.commit()
            
            job = Job(
                name='Test Job',
                job_type='web_scraper',
                config={'url': 'http://example.com', 'selectors': {'title': 'h1'}},
                user_id=user.id
            )
            db.session.add(job)
            db.session.commit()
            
            job_run = JobRun(
                job_id=job.id,
                status='completed'
            )
            job_run.started_at = datetime.utcnow()
            job_run.completed_at = datetime.utcnow()
            db.session.add(job_run)
            db.session.commit()
            
            # Mock get_current_user_id to return the actual user ID
            with patch('app.jobs.views.get_current_user_id', return_value=user.id):
                # Test the route
                response = client.get(f'/jobs/{job.id}/runs')
                assert response.status_code == 200
                
                data = json.loads(response.data)
                assert data['success'] is True
                assert len(data['runs']) == 1
                assert data['runs'][0]['status'] == 'completed'
    
    def test_job_types_route(self, client):
        """Test getting available job types."""
        response = client.get('/jobs/types')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'types' in data
        # Check that the types are in the response (they're now objects with schema info)
        type_names = [t['type'] for t in data['types']]
        assert 'web_scraper' in type_names
        assert 'rss_reader' in type_names
        assert 'filter' in type_names
        assert 'email_sender' in type_names


class TestJobViewValidation:
    """Test job view validation and error handling."""
    
    def test_create_job_missing_name(self, client, app_context):
        """Test job creation with missing name."""
        response = client.post('/jobs/create', data={'job_type': 'web_scraper'}, follow_redirects=True)
        assert response.status_code == 200
        assert b'Job name is required' in response.data
    
    def test_create_job_missing_type(self, client, app_context):
        """Test job creation with missing job type."""
        response = client.post('/jobs/create', data={'name': 'Test Job'}, follow_redirects=True)
        assert response.status_code == 200
        assert b'Job type is required' in response.data
    
    def test_create_job_invalid_type(self, client, app_context):
        """Test job creation with invalid job type."""
        response = client.post('/jobs/create', data={
            'name': 'Test Job',
            'job_type': 'invalid_type'
        }, follow_redirects=True)
        assert response.status_code == 200
    
    def test_job_not_found(self, client):
        """Test accessing non-existent job."""
        response = client.get('/jobs/999')
        assert response.status_code == 302  # Redirect to job list
    
    def test_edit_nonexistent_job(self, client):
        """Test editing non-existent job."""
        response = client.get('/jobs/999/edit')
        assert response.status_code == 302  # Redirect to job list
    
    def test_delete_nonexistent_job(self, client):
        """Test deleting non-existent job."""
        response = client.post('/jobs/999/delete', follow_redirects=True)
        assert response.status_code == 200


class TestJobViewAuthentication:
    """Test job view authentication requirements."""
    
    def test_job_routes_require_auth(self, client):
        """Test that all job routes require authentication."""
        # Note: Currently using placeholder auth, so all routes should work
        # This test will need updating when real authentication is implemented
        
        routes = [
            '/jobs/',
            '/jobs/create',
            '/jobs/types'
        ]
        
        for route in routes:
            response = client.get(route)
            # Should not get 401/403 (authentication errors)
            # Currently gets 200 or 302 (redirects) due to placeholder auth
            assert response.status_code in [200, 302, 404]


class TestJobViewIntegration:
    """Test integration between job views and other components."""
    
    def test_job_creation_with_service(self, client, app_context):
        """Test that job creation uses the job service."""
        with patch('app.jobs.views.JobService') as mock_service:
            mock_instance = Mock()
            mock_instance.create_job.return_value = (Mock(id=1), None)
            mock_service.return_value = mock_instance
            
            response = client.post('/jobs/create', data={
                'name': 'Test Job',
                'job_type': 'web_scraper',
                'url': 'http://example.com'
            })
            
            mock_instance.create_job.assert_called_once()
    
    def test_job_execution_with_service(self, client, app_context):
        """Test that job execution uses the job service."""
        # Create test job
        user = User(username='testuser', email='test@example.com', password='password123')
        job = Job(
            name='Test Job',
            job_type='web_scraper',
            config={'url': 'http://example.com', 'selectors': {'title': 'h1'}},
            user_id=1
        )
        
        with app_context.app_context():
            db.session.add(user)
            db.session.commit()
            # Update job to use the actual user ID
            job.user_id = user.id
            db.session.add(job)
            db.session.commit()
            
            with patch('app.jobs.views.JobService') as mock_service:
                mock_instance = Mock()
                mock_instance.execute_job.return_value = (Mock(id=1, status='pending'), None)
                mock_service.return_value = mock_instance
                
                response = client.post(f'/jobs/{job.id}/execute')
                
                mock_instance.execute_job.assert_called_once_with(job.id, 1)
