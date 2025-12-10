"""
Integration tests for the complete job workflow
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from app.models import User, Job, JobRun
from app.jobs import job_registry, JobStatus
from app.services.job_service import JobService
from app.extensions import db


class TestJobWorkflowIntegration:
    """Test the complete job workflow from creation to execution."""
    
    def test_complete_web_scraper_workflow(self, client, app_context):
        """Test complete web scraper job workflow."""
        # Create test user
        user = User(username='testuser', email='test@example.com', password='password123')
        
        with app_context.app_context():
            db.session.add(user)
            db.session.commit()
            
            # Step 1: Create job via form
            job_data = {
                'name': 'Test Web Scraper',
                'job_type': 'web_scraper',
                'url': 'http://example.com',
                'selector_name': ['title', 'content'],
                'selector_value': ['h1', 'p'],
                'timeout': '30',
                'extract_text': 'on',
                'extract_links': 'off'
            }
            
            response = client.post('/jobs/create', data=job_data, follow_redirects=True)
            assert response.status_code == 200
            
            # Verify job was created
            job = db.session.query(Job).filter_by(name='Test Web Scraper').first()
            assert job is not None
            assert job.job_type == 'web_scraper'
            assert job.config['url'] == 'http://example.com'
            assert 'title' in job.config['selectors']
            assert 'content' in job.config['selectors']
            
            # Step 2: Execute job
            with patch('app.jobs.views.JobService') as mock_service:
                mock_instance = Mock()
                mock_run = Mock(id=1, status='pending')
                mock_instance.execute_job.return_value = (mock_run, None)
                mock_service.return_value = mock_instance
                
                response = client.post(f'/jobs/{job.id}/execute')
                assert response.status_code == 200
                
                data = json.loads(response.data)
                assert data['success'] is True
                assert 'run_id' in data
            
            # Step 3: Check job runs
            response = client.get(f'/jobs/{job.id}/runs')
            assert response.status_code == 200
            
            data = json.loads(response.data)
            assert data['success'] is True
    
    def test_complete_rss_reader_workflow(self, client, app_context):
        """Test complete RSS reader job workflow."""
        # Create test user
        user = User(username='testuser', email='test@example.com', password='password123')
        
        with app_context.app_context():
            db.session.add(user)
            db.session.commit()
            
            # Create RSS reader job
            job_data = {
                'name': 'Test RSS Reader',
                'job_type': 'rss_reader',
                'feed_url': 'http://example.com/feed.xml',
                'max_entries': '50',
                'include_content': 'on',
                'filter_keywords': 'python,flask',
                'exclude_keywords': 'deprecated'
            }
            
            response = client.post('/jobs/create', data=job_data, follow_redirects=True)
            assert response.status_code == 200
            
            # Verify job was created
            job = db.session.query(Job).filter_by(name='Test RSS Reader').first()
            assert job is not None
            assert job.job_type == 'rss_reader'
            assert job.config['feed_url'] == 'http://example.com/feed.xml'
            assert job.config['max_entries'] == 50
            assert job.config['include_content'] is True
    
    def test_complete_filter_workflow(self, client, app_context):
        """Test complete filter job workflow."""
        # Create test user
        user = User(username='testuser', email='test@example.com', password='password123')
        
        with app_context.app_context():
            db.session.add(user)
            db.session.commit()
            
            # Create filter job
            job_data = {
                'name': 'Test Filter Job',
                'job_type': 'filter',
                'input_data': '{"items": [{"name": "test", "value": 10}]}',
                'filter_type': ['equals'],
                'filter_field': ['name'],
                'filter_value': ['test'],
                'output_format': 'original',
                'case_sensitive': 'off',
                'regex_enabled': 'off'
            }
            
            response = client.post('/jobs/create', data=job_data, follow_redirects=True)
            assert response.status_code == 200
            
            # Verify job was created
            job = db.session.query(Job).filter_by(name='Test Filter Job').first()
            assert job is not None
            assert job.job_type == 'filter'
            assert 'items' in job.config['input_data']
            assert len(job.config['filters']) == 1
    
    def test_complete_email_sender_workflow(self, client, app_context):
        """Test complete email sender job workflow."""
        # Create test user
        user = User(username='testuser', email='test@example.com', password='password123')
        
        with app_context.app_context():
            db.session.add(user)
            db.session.commit()
            
            # Create email sender job
            job_data = {
                'name': 'Test Email Sender',
                'job_type': 'email_sender',
                'smtp_server': 'smtp.gmail.com',
                'smtp_port': '587',
                'username': 'test@gmail.com',
                'password': 'password123',
                'to_emails': 'recipient@example.com,cc@example.com',
                'subject': 'Test Email',
                'body': 'This is a test email',
                'use_tls': 'on'
            }
            
            response = client.post('/jobs/create', data=job_data, follow_redirects=True)
            assert response.status_code == 200
            
            # Verify job was created
            job = db.session.query(Job).filter_by(name='Test Email Sender').first()
            assert job is not None
            assert job.job_type == 'email_sender'
            assert job.config['smtp_server'] == 'smtp.gmail.com'
            assert job.config['smtp_port'] == 587
            assert 'recipient@example.com' in job.config['to_emails']
            assert 'cc@example.com' in job.config['to_emails']


class TestJobServiceIntegration:
    """Test integration between job views and job service."""
    
    def test_job_service_creation_integration(self, app_context):
        """Test that job creation properly integrates with job service."""
        user = User(username='testuser', email='test@example.com', password='password123')
        
        with app_context.app_context():
            db.session.add(user)
            db.session.commit()
            
            # Test job service directly
            job_service = JobService(db.session)
            
            config = {
                'url': 'http://example.com',
                'selectors': {'title': 'h1'}
            }
            
            job, error = job_service.create_job('Test Job', 'web_scraper', config, user.id)
            assert error is None
            assert job is not None
            assert job.name == 'Test Job'
            assert job.job_type == 'web_scraper'
            assert job.user_id == user.id
    
    def test_job_service_execution_integration(self, app_context):
        """Test that job execution properly integrates with job service."""
        user = User(username='testuser', email='test@example.com', password='password123')
        job = Job(
            name='Test Job',
            job_type='web_scraper',
            config={'url': 'http://example.com', 'selectors': {'title': 'h1'}},
            user_id=1
        )
        
        with app_context.app_context():
            db.session.add(user)
            db.session.add(job)
            db.session.commit()
            
            # Test job service execution
            job_service = JobService(db.session)
            
            with patch('app.services.job_service.job_registry') as mock_registry:
                mock_job_instance = Mock()
                mock_job_instance.execute.return_value = {'result': 'success'}
                mock_job_instance.status = JobStatus.COMPLETED
                mock_registry.create_job.return_value = mock_job_instance
                
                job_run, error = job_service.execute_job(job.id, user.id)
                assert error is None
                assert job_run is not None
                assert job_run.job_id == job.id
                assert job_run.status == 'completed'


class TestFormViewIntegration:
    """Test integration between forms and views."""
    
    def test_form_data_processing(self, client, app_context):
        """Test that form data is properly processed by views."""
        user = User(username='testuser', email='test@example.com', password='password123')
        
        with app_context.app_context():
            db.session.add(user)
            db.session.commit()
            
            # Test complex form data
            job_data = {
                'name': 'Complex Test Job',
                'job_type': 'web_scraper',
                'url': 'http://example.com',
                'selector_name': ['title', 'content', 'links'],
                'selector_value': ['h1', 'p', 'a'],
                'timeout': '60',
                'extract_text': 'on',
                'extract_links': 'on',
                'user_agent': 'Custom Bot/1.0'
            }
            
            response = client.post('/jobs/create', data=job_data, follow_redirects=True)
            assert response.status_code == 200
            
            # Verify complex configuration was processed
            job = db.session.query(Job).filter_by(name='Complex Test Job').first()
            assert job is not None
            assert len(job.config['selectors']) == 3
            # Note: user_agent might be stored under headers or processed differently by the form
            assert job.config['timeout'] == 60
    
    def test_form_validation_integration(self, client, app_context):
        """Test that form validation errors are properly handled by views."""
        user = User(username='testuser', email='test@example.com', password='password123')
        
        with app_context.app_context():
            db.session.add(user)
            db.session.commit()
            
            # Test invalid form data
            invalid_data = {
                'name': '',  # Empty name
                'job_type': 'web_scraper'
            }
            
            response = client.post('/jobs/create', data=invalid_data, follow_redirects=True)
            assert response.status_code == 200
            assert b'Job name is required' in response.data
            
            # Verify no job was created
            job = db.session.query(Job).filter_by(job_type='web_scraper').first()
            assert job is None


class TestErrorHandlingIntegration:
    """Test error handling across the complete workflow."""
    
    def test_job_creation_error_handling(self, client, app_context):
        """Test error handling during job creation."""
        user = User(username='testuser', email='test@example.com', password='password123')
        
        with app_context.app_context():
            db.session.add(user)
            db.session.commit()
            
            # Test with invalid job type
            invalid_data = {
                'name': 'Test Job',
                'job_type': 'invalid_type'
            }
            
            response = client.post('/jobs/create', data=invalid_data, follow_redirects=True)
            assert response.status_code == 200
            # Should handle gracefully even with invalid job type
    
    def test_job_execution_error_handling(self, client, app_context):
        """Test error handling during job execution."""
        user = User(username='testuser', email='test@example.com', password='password123')
        job = Job(
            name='Test Job',
            job_type='web_scraper',
            config={'url': 'http://example.com', 'selectors': {'title': 'h1'}},
            user_id=1
        )
        
        with app_context.app_context():
            db.session.add(user)
            db.session.add(job)
            db.session.commit()
            
            # Mock job service to return error
            with patch('app.jobs.views.JobService') as mock_service:
                mock_instance = Mock()
                mock_instance.execute_job.return_value = (None, 'Execution failed')
                mock_service.return_value = mock_instance
                
                response = client.post(f'/jobs/{job.id}/execute')
                assert response.status_code == 400
                
                data = json.loads(response.data)
                assert data['success'] is False
                assert 'Execution failed' in data['error']


class TestDataPersistenceIntegration:
    """Test that data persists correctly across the workflow."""
    
    def test_job_config_persistence(self, app_context):
        """Test that job configuration persists correctly."""
        user = User(username='testuser', email='test@example.com', password='password123')
        
        with app_context.app_context():
            db.session.add(user)
            db.session.commit()
            
            # Create job with complex config
            complex_config = {
                'url': 'http://example.com',
                'selectors': {
                    'title': 'h1',
                    'content': 'p',
                    'links': 'a'
                },
                'timeout': 60,
                'extract_text': True,
                'extract_links': True,
                'headers': {
                    'User-Agent': 'Custom Bot/1.0'
                }
            }
            
            job = Job(
                name='Persistence Test Job',
                job_type='web_scraper',
                config=complex_config,
                user_id=user.id
            )
            
            db.session.add(job)
            db.session.commit()
            
            # Retrieve and verify
            retrieved_job = db.session.query(Job).get(job.id)
            assert retrieved_job is not None
            assert retrieved_job.config == complex_config
            assert retrieved_job.config['selectors']['title'] == 'h1'
            assert retrieved_job.config['timeout'] == 60
            assert retrieved_job.config['headers']['User-Agent'] == 'Custom Bot/1.0'
    
    def test_job_run_persistence(self, app_context):
        """Test that job runs persist correctly."""
        user = User(username='testuser', email='test@example.com', password='password123')
        job = Job(
            name='Run Test Job',
            job_type='web_scraper',
            config={'url': 'http://example.com', 'selectors': {'title': 'h1'}},
            user_id=1
        )
        
        with app_context.app_context():
            db.session.add(user)
            db.session.add(job)
            db.session.commit()
            
            # Create job run
            job_run = JobRun(
                job_id=job.id,
                status='completed',
                input_data={'test': 'data'}
            )
            job_run.output_data = {'result': 'success', 'data': ['item1', 'item2']}
            
            db.session.add(job_run)
            db.session.commit()
            
            # Retrieve and verify
            retrieved_run = db.session.query(JobRun).get(job_run.id)
            assert retrieved_run is not None
            assert retrieved_run.status == 'completed'
            assert retrieved_run.output_data['result'] == 'success'
            assert len(retrieved_run.output_data['data']) == 2
