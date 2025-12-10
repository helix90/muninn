"""
Tests for the job execution framework
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from app.jobs import BaseJob, JobRegistry, job_registry, JobStatus
from app.jobs.types.web_scraper import WebScraperJob
from app.jobs.types.rss_reader import RSSReaderJob
from app.jobs.types.filter_job import FilterJob
from app.jobs.types.email_sender import EmailSenderJob
from app.services.job_service import JobService
from app.models import Job, JobRun, User


class TestJobStatus:
    """Test job status enumeration."""
    
    def test_job_status_values(self):
        """Test that job status values are correct."""
        assert JobStatus.PENDING.value == 'pending'
        assert JobStatus.RUNNING.value == 'running'
        assert JobStatus.COMPLETED.value == 'completed'
        assert JobStatus.FAILED.value == 'failed'
        assert JobStatus.DEAD.value == 'dead'
        assert JobStatus.CANCELLED.value == 'cancelled'
    
    def test_is_valid(self):
        """Test status validation."""
        assert JobStatus.is_valid('pending') is True
        assert JobStatus.is_valid('invalid') is False
    
    def test_get_all(self):
        """Test getting all status values."""
        all_statuses = JobStatus.get_all()
        assert 'pending' in all_statuses
        assert 'running' in all_statuses
        assert 'completed' in all_statuses
        assert 'failed' in all_statuses
        assert 'dead' in all_statuses
        assert 'cancelled' in all_statuses
    
    def test_get_active_statuses(self):
        """Test getting active statuses."""
        active_statuses = JobStatus.get_active_statuses()
        assert 'pending' in active_statuses
        assert 'running' in active_statuses
        assert 'completed' not in active_statuses
    
    def test_get_final_statuses(self):
        """Test getting final statuses."""
        final_statuses = JobStatus.get_final_statuses()
        assert 'completed' in final_statuses
        assert 'failed' in final_statuses
        assert 'dead' in final_statuses
        assert 'cancelled' in final_statuses
        assert 'pending' not in final_statuses


class TestBaseJob:
    """Test the abstract base job class."""
    
    def test_base_job_initialization(self):
        """Test base job initialization."""
        # Create a concrete implementation for testing
        class TestJob(BaseJob):
            job_type = 'test_job'
            required_config_fields = ['test_field']
            
            def execute(self, input_data=None):
                return {'result': 'success'}
        
        job = TestJob(job_id=1, config={'test_field': 'value'}, user_id=1)
        assert job.job_id == 1
        assert job.config == {'test_field': 'value'}
        assert job.user_id == 1
        assert job.status == JobStatus.PENDING
    
    def test_base_job_missing_job_type(self):
        """Test that job without job_type raises error."""
        class InvalidJob(BaseJob):
            required_config_fields = []
            
            def execute(self, input_data=None):
                return {}
        
        with pytest.raises(ValueError, match="Job type not set"):
            InvalidJob(job_id=1, config={}, user_id=1)
    
    def test_base_job_missing_required_fields(self):
        """Test that job with missing required fields raises error."""
        class TestJob(BaseJob):
            job_type = 'test_job'
            required_config_fields = ['required_field']
            
            def execute(self, input_data=None):
                return {}
        
        with pytest.raises(ValueError, match="Missing required configuration fields"):
            TestJob(job_id=1, config={}, user_id=1)
    
    def test_base_job_execution_flow(self):
        """Test complete job execution flow."""
        class TestJob(BaseJob):
            job_type = 'test_job'
            required_config_fields = ['test_field']
            
            def execute(self, input_data=None):
                return {'result': 'success'}
        
        job = TestJob(job_id=1, config={'test_field': 'value'}, user_id=1)
        
        # Test pre-execute
        job.pre_execute()
        assert job.status == JobStatus.RUNNING
        
        # Test post-execute success
        job.post_execute({'result': 'success'}, success=True)
        assert job.status == JobStatus.COMPLETED
        
        # Test post-execute failure
        job.post_execute({'error': 'test error'}, success=False)
        assert job.status == JobStatus.FAILED
    
    def test_base_job_error_handling(self):
        """Test job error handling."""
        class TestJob(BaseJob):
            job_type = 'test_job'
            required_config_fields = []
            
            def execute(self, input_data=None):
                raise ValueError("Test error")
        
        job = TestJob(job_id=1, config={}, user_id=1)
        error_result = job.handle_error(ValueError("Test error"))
        
        assert job.status == JobStatus.FAILED
        assert 'Test error' in error_result['error']
        assert error_result['error_type'] == 'ValueError'


class TestJobRegistry:
    """Test the job registry system."""
    
    def test_job_registry_initialization(self):
        """Test job registry initialization."""
        registry = JobRegistry()
        assert len(registry) == 0
        assert registry.get_registered_types() == []
    
    def test_register_job_class(self):
        """Test registering a job class."""
        registry = JobRegistry()
        
        class TestJob(BaseJob):
            job_type = 'test_job'
            required_config_fields = []
            
            def execute(self, input_data=None):
                return {}
        
        registry.register(TestJob)
        assert 'test_job' in registry
        assert len(registry) == 1
        assert registry.get_job_class('test_job') == TestJob
    
    def test_register_invalid_job_class(self):
        """Test that invalid job classes cannot be registered."""
        registry = JobRegistry()
        
        class InvalidJob:
            pass
        
        with pytest.raises(ValueError, match="Job class must inherit from BaseJob"):
            registry.register(InvalidJob)
    
    def test_register_job_without_type(self):
        """Test that jobs without job_type cannot be registered."""
        registry = JobRegistry()
        
        class InvalidJob(BaseJob):
            required_config_fields = []
            
            def execute(self, input_data=None):
                return {}
        
        with pytest.raises(ValueError, match="Job class must have a job_type"):
            registry.register(InvalidJob)
    
    def test_create_job_instance(self):
        """Test creating job instances from registry."""
        registry = JobRegistry()
        
        class TestJob(BaseJob):
            job_type = 'test_job'
            required_config_fields = ['test_field']
            
            def execute(self, input_data=None):
                return {}
        
        registry.register(TestJob)
        job_instance = registry.create_job('test_job', 1, {'test_field': 'value'}, 1)
        
        assert isinstance(job_instance, TestJob)
        assert job_instance.job_id == 1
        assert job_instance.config == {'test_field': 'value'}
    
    def test_create_unknown_job_type(self):
        """Test that creating unknown job types raises error."""
        registry = JobRegistry()
        
        with pytest.raises(ValueError, match="Unknown job type"):
            registry.create_job('unknown_type', 1, {}, 1)
    
    def test_get_config_schema(self):
        """Test getting configuration schemas."""
        registry = JobRegistry()
        
        class TestJob(BaseJob):
            job_type = 'test_job'
            required_config_fields = ['required_field']
            optional_config_fields = ['optional_field']
            
            def execute(self, input_data=None):
                return {}
        
        registry.register(TestJob)
        schema = registry.get_config_schema('test_job')
        
        assert schema['job_type'] == 'test_job'
        assert 'required_field' in schema['required_fields']
        assert 'optional_field' in schema['optional_fields']
    
    def test_unregister_job(self):
        """Test unregistering jobs."""
        registry = JobRegistry()
        
        class TestJob(BaseJob):
            job_type = 'test_job'
            required_config_fields = []
            
            def execute(self, input_data=None):
                return {}
        
        registry.register(TestJob)
        assert 'test_job' in registry
        
        success = registry.unregister('test_job')
        assert success is True
        assert 'test_job' not in registry
        
        # Test unregistering non-existent job
        success = registry.unregister('unknown')
        assert success is False


class TestWebScraperJob:
    """Test web scraper job functionality."""
    
    def test_web_scraper_initialization(self):
        """Test web scraper job initialization."""
        config = {
            'url': 'https://example.com',
            'selectors': {'title': 'h1', 'content': '.content'}
        }
        
        job = WebScraperJob(job_id=1, config=config, user_id=1)
        assert job.job_type == 'web_scraper'
        assert job.config['url'] == 'https://example.com'
        assert job.config['selectors'] == {'title': 'h1', 'content': '.content'}
    
    def test_web_scraper_missing_required_fields(self):
        """Test web scraper with missing required fields."""
        with pytest.raises(ValueError, match="Missing required configuration fields"):
            WebScraperJob(job_id=1, config={}, user_id=1)
    
    def test_web_scraper_invalid_url(self):
        """Test web scraper with invalid URL."""
        config = {
            'url': 'invalid-url',
            'selectors': {'title': 'h1'}
        }
        
        with pytest.raises(ValueError, match="Invalid URL provided"):
            WebScraperJob(job_id=1, config=config, user_id=1)
    
    def test_web_scraper_invalid_selectors(self):
        """Test web scraper with invalid selectors."""
        config = {
            'url': 'https://example.com',
            'selectors': 'invalid'
        }
        
        with pytest.raises(ValueError, match="Selectors must be a non-empty dictionary"):
            WebScraperJob(job_id=1, config=config, user_id=1)
    
    @patch('app.jobs.types.web_scraper.requests.get')
    def test_web_scraper_execution(self, mock_get):
        """Test web scraper job execution."""
        # Mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b'<html><h1>Test Title</h1><div class="content">Test Content</div></html>'
        mock_response.headers = {'content-type': 'text/html'}
        mock_get.return_value = mock_response
        
        config = {
            'url': 'https://example.com',
            'selectors': {'title': 'h1', 'content': '.content'}
        }
        
        job = WebScraperJob(job_id=1, config=config, user_id=1)
        result = job.execute()
        
        assert result['url'] == 'https://example.com'
        assert result['status_code'] == 200
        assert 'extracted_data' in result
        assert 'title' in result['extracted_data']
        assert 'content' in result['extracted_data']


class TestRSSReaderJob:
    """Test RSS reader job functionality."""
    
    def test_rss_reader_initialization(self):
        """Test RSS reader job initialization."""
        config = {
            'feed_url': 'https://example.com/feed.xml'
        }
        
        job = RSSReaderJob(job_id=1, config=config, user_id=1)
        assert job.job_type == 'rss_reader'
        assert job.config['feed_url'] == 'https://example.com/feed.xml'
    
    def test_rss_reader_missing_required_fields(self):
        """Test RSS reader with missing required fields."""
        with pytest.raises(ValueError, match="Missing required configuration fields"):
            RSSReaderJob(job_id=1, config={}, user_id=1)
    
    def test_rss_reader_invalid_url(self):
        """Test RSS reader with invalid URL."""
        config = {
            'feed_url': 'invalid-url'
        }
        
        with pytest.raises(ValueError, match="Invalid RSS feed URL provided"):
            RSSReaderJob(job_id=1, config=config, user_id=1)
    
    @patch('app.jobs.types.rss_reader.feedparser.parse')
    def test_rss_reader_execution(self, mock_parse):
        """Test RSS reader job execution."""
        # Mock feedparser response
        mock_feed = Mock()
        mock_feed.bozo = False
        mock_feed.feed = {
            'title': 'Test Feed',
            'description': 'Test Description',
            'link': 'https://example.com'
        }
        mock_feed.entries = [
            {
                'title': 'Test Entry',
                'link': 'https://example.com/entry1',
                'summary': 'Test summary',
                'published': '2024-01-01T00:00:00Z'
            }
        ]
        mock_parse.return_value = mock_feed
        
        config = {
            'feed_url': 'https://example.com/feed.xml'
        }
        
        job = RSSReaderJob(job_id=1, config=config, user_id=1)
        result = job.execute()
        
        assert result['feed_url'] == 'https://example.com/feed.xml'
        assert result['total_entries'] == 1
        assert result['filtered_entries'] == 1
        assert len(result['entries']) == 1


class TestFilterJob:
    """Test filter job functionality."""
    
    def test_filter_job_initialization(self):
        """Test filter job initialization."""
        config = {
            'input_data': {'name': 'John', 'age': 30},
            'filters': [
                {'type': 'equals', 'field': 'age', 'value': 30}
            ]
        }
        
        job = FilterJob(job_id=1, config=config, user_id=1)
        assert job.job_type == 'filter'
        assert job.config['input_data'] == {'name': 'John', 'age': 30}
        assert len(job.config['filters']) == 1
    
    def test_filter_job_missing_required_fields(self):
        """Test filter job with missing required fields."""
        with pytest.raises(ValueError, match="Missing required configuration fields"):
            FilterJob(job_id=1, config={}, user_id=1)
    
    def test_filter_job_invalid_filters(self):
        """Test filter job with invalid filters."""
        config = {
            'input_data': {'name': 'John'},
            'filters': 'invalid'
        }
        
        with pytest.raises(ValueError, match="filters must be a non-empty list"):
            FilterJob(job_id=1, config=config, user_id=1)
    
    def test_filter_job_execution(self):
        """Test filter job execution."""
        config = {
            'input_data': [
                {'name': 'John', 'age': 30, 'city': 'New York'},
                {'name': 'Jane', 'age': 25, 'city': 'Boston'},
                {'name': 'Bob', 'age': 35, 'city': 'New York'}
            ],
            'filters': [
                {'type': 'greater_than', 'field': 'age', 'value': 25},
                {'type': 'contains', 'field': 'city', 'value': 'New York'}
            ]
        }
        
        job = FilterJob(job_id=1, config=config, user_id=1)
        result = job.execute()
        
        assert result['filtering_success'] is True
        assert result['input_count'] == 3
        assert result['output_count'] == 2  # Only John and Bob match both filters


class TestEmailSenderJob:
    """Test email sender job functionality."""
    
    def test_email_sender_initialization(self):
        """Test email sender job initialization."""
        config = {
            'smtp_server': 'smtp.gmail.com',
            'smtp_port': 587,
            'username': 'test@gmail.com',
            'password': 'password',
            'to_emails': ['recipient@example.com'],
            'subject': 'Test Email',
            'body': 'Test email body'
        }
        
        job = EmailSenderJob(job_id=1, config=config, user_id=1)
        assert job.job_type == 'email_sender'
        assert job.config['smtp_server'] == 'smtp.gmail.com'
        assert job.config['smtp_port'] == 587
    
    def test_email_sender_missing_required_fields(self):
        """Test email sender with missing required fields."""
        with pytest.raises(ValueError, match="Missing required configuration fields"):
            EmailSenderJob(job_id=1, config={}, user_id=1)
    
    def test_email_sender_invalid_port(self):
        """Test email sender with invalid port."""
        config = {
            'smtp_server': 'smtp.gmail.com',
            'smtp_port': -1,
            'username': 'test@gmail.com',
            'password': 'password',
            'to_emails': ['recipient@example.com'],
            'subject': 'Test Email',
            'body': 'Test email body'
        }
        
        with pytest.raises(ValueError, match="smtp_port must be a positive integer"):
            EmailSenderJob(job_id=1, config=config, user_id=1)
    
    def test_email_sender_invalid_emails(self):
        """Test email sender with invalid email addresses."""
        config = {
            'smtp_server': 'smtp.gmail.com',
            'smtp_port': 587,
            'username': 'test@gmail.com',
            'password': 'password',
            'to_emails': ['invalid-email'],
            'subject': 'Test Email',
            'body': 'Test email body'
        }
        
        with pytest.raises(ValueError, match="Invalid email address in to_emails"):
            EmailSenderJob(job_id=1, config=config, user_id=1)


class TestJobService:
    """Test the job service functionality."""
    
    def test_job_service_initialization(self, db_session):
        """Test job service initialization."""
        service = JobService(db_session)
        assert service.db == db_session
    
    def test_create_job_success(self, db_session):
        """Test successful job creation."""
        service = JobService(db_session)
        
        # Mock job creation
        mock_job = Mock(spec=Job)
        mock_job.id = 1
        mock_job.name = 'Test Job'
        mock_job.job_type = 'web_scraper'
        
        with patch('app.services.job_service.Job', return_value=mock_job), \
             patch.object(db_session, 'add'), \
             patch.object(db_session, 'commit'), \
             patch.object(db_session, 'refresh'), \
             patch('app.services.job_service.job_registry') as mock_registry:
            
            mock_registry.is_registered.return_value = True
            mock_registry.validate_job_config.return_value = None
            
            db_session.add.return_value = None
            db_session.refresh.return_value = None
            
            job, error = service.create_job('Test Job', 'web_scraper', {'url': 'https://example.com'}, 1)
            
            assert job is not None
            assert error is None
    
    def test_create_job_unknown_type(self, db_session):
        """Test job creation with unknown type."""
        service = JobService(db_session)
        
        job, error = service.create_job('Test Job', 'unknown_type', {}, 1)
        
        assert job is None
        assert 'Unknown job type' in error
    
    def test_get_user_jobs(self, db_session):
        """Test getting user jobs with pagination."""
        service = JobService(db_session)

        # Mock query results
        mock_jobs = [Mock(spec=Job), Mock(spec=Job)]
        mock_query = Mock()

        # Mock the query chain
        filter_result = Mock()
        order_result = Mock()
        filter_result.order_by.return_value = order_result
        mock_query.filter.return_value = filter_result

        # Mock count() to return an integer
        order_result.count.return_value = 2

        # Mock limit/offset/all chain
        limit_result = Mock()
        offset_result = Mock()
        order_result.limit.return_value = limit_result
        limit_result.offset.return_value = offset_result
        offset_result.all.return_value = mock_jobs

        with patch.object(db_session, 'query', return_value=mock_query):
            result = service.get_user_jobs(1)

            # Check pagination dictionary
            assert 'jobs' in result
            assert 'page' in result
            assert 'total' in result
            assert len(result['jobs']) == 2
            assert result['total'] == 2
            assert result['page'] == 1
    
    def test_execute_job_success(self, db_session):
        """Test successful job execution."""
        service = JobService(db_session)
        
        # Mock job and execution
        mock_job = Mock(spec=Job)
        mock_job.id = 1
        mock_job.job_type = 'web_scraper'
        mock_job.config = {'url': 'https://example.com'}
        
        mock_job_run = Mock(spec=JobRun)
        mock_job_run.id = 1
        mock_job_run.status = 'completed'
        
        with patch.object(service, 'get_job_by_id', return_value=mock_job), \
             patch.object(db_session, 'add'), \
             patch.object(db_session, 'commit'), \
             patch.object(db_session, 'refresh'), \
             patch('app.services.job_service.job_registry') as mock_registry:
            
            mock_registry.create_job.return_value.execute.return_value = {'result': 'success'}
            mock_registry.create_job.return_value.status = JobStatus.COMPLETED
            
            job_run, error = service.execute_job(1, 1)
            
            assert job_run is not None
            assert error is None


class TestJobIntegration:
    """Integration tests for the job framework."""
    
    def test_job_registry_integration(self):
        """Test that all job types are properly registered."""
        # Check that all job types are registered
        assert 'web_scraper' in job_registry
        assert 'rss_reader' in job_registry
        assert 'filter' in job_registry
        assert 'email_sender' in job_registry
        
        # Check that job classes can be retrieved
        assert job_registry.get_job_class('web_scraper') == WebScraperJob
        assert job_registry.get_job_class('rss_reader') == RSSReaderJob
        assert job_registry.get_job_class('filter') == FilterJob
        assert job_registry.get_job_class('email_sender') == EmailSenderJob
    
    def test_job_config_schemas(self):
        """Test that all job types provide configuration schemas."""
        schemas = job_registry.get_all_config_schemas()
        
        assert 'web_scraper' in schemas
        assert 'rss_reader' in schemas
        assert 'filter' in schemas
        assert 'email_sender' in schemas
        
        # Check schema structure
        for job_type, schema in schemas.items():
            assert 'job_type' in schema
            assert 'required_fields' in schema
            assert 'optional_fields' in schema
            assert 'description' in schema
    
    def test_job_creation_flow(self):
        """Test complete job creation and execution flow."""
        # Test web scraper job creation
        config = {
            'url': 'https://example.com',
            'selectors': {'title': 'h1'}
        }
        
        job = WebScraperJob(job_id=1, config=config, user_id=1)
        assert job.job_type == 'web_scraper'
        assert job.is_valid_for_execution() is True
        
        # Test RSS reader job creation
        config = {
            'feed_url': 'https://example.com/feed.xml'
        }
        
        job = RSSReaderJob(job_id=2, config=config, user_id=1)
        assert job.job_type == 'rss_reader'
        assert job.is_valid_for_execution() is True
        
        # Test filter job creation
        config = {
            'input_data': {'test': 'data'},
            'filters': [{'type': 'equals', 'field': 'test', 'value': 'data'}]
        }
        
        job = FilterJob(job_id=3, config=config, user_id=1)
        assert job.job_type == 'filter'
        assert job.is_valid_for_execution() is True
        
        # Test email sender job creation
        config = {
            'smtp_server': 'smtp.gmail.com',
            'smtp_port': 587,
            'username': 'test@gmail.com',
            'password': 'password',
            'to_emails': ['recipient@example.com'],
            'subject': 'Test Email',
            'body': 'Test email body'
        }
        
        job = EmailSenderJob(job_id=4, config=config, user_id=1)
        assert job.job_type == 'email_sender'
        assert job.is_valid_for_execution() is True
