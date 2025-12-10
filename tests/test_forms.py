"""
Tests for job-related forms
"""

import pytest
from app.forms import (
    JobCreationForm, WebScraperConfigForm, RSSReaderConfigForm,
    FilterConfigForm, EmailSenderConfigForm, JobEditForm, JobExecutionForm
)
from app.forms import get_job_config_form, validate_job_config, clean_job_config


class TestJobCreationForm:
    """Test the job creation form."""
    
    def test_job_creation_form_validation(self, app):
        """Test basic form validation."""
        with app.app_context():
            form = JobCreationForm()
            assert form.name is not None
            assert form.job_type is not None
    
    def test_job_creation_form_valid_data(self, app):
        """Test form with valid data."""
        with app.app_context():
            data = {
                'name': 'Test Job',
                'job_type': 'web_scraper'
            }
            form = JobCreationForm(data=data)
            assert form.validate() is True
    
    def test_job_creation_form_missing_name(self, app):
        """Test form validation with missing name."""
        with app.app_context():
            data = {
                'job_type': 'web_scraper'
            }
            form = JobCreationForm(data=data)
            assert form.validate() is False
            assert 'name' in form.errors
    
    def test_job_creation_form_missing_job_type(self, app):
        """Test form validation with missing job type."""
        with app.app_context():
            data = {
                'name': 'Test Job'
            }
            form = JobCreationForm(data=data)
            assert form.validate() is False
            assert 'job_type' in form.errors
    
    def test_job_creation_form_empty_name(self, app):
        """Test form validation with empty name."""
        with app.app_context():
            data = {
                'name': '',
                'job_type': 'web_scraper'
            }
            form = JobCreationForm(data=data)
            assert form.validate() is False
            assert 'name' in form.errors


class TestWebScraperConfigForm:
    """Test the web scraper configuration form."""
    
    def test_web_scraper_form_fields(self, app):
        """Test that all required fields are present."""
        with app.app_context():
            form = WebScraperConfigForm()
            assert hasattr(form, 'url')
            assert hasattr(form, 'selectors')
            assert hasattr(form, 'timeout')
            assert hasattr(form, 'extract_text')
            assert hasattr(form, 'extract_links')
    
    def test_web_scraper_form_validation(self, app):
        """Test form validation with valid data."""
        with app.app_context():
            data = {
                'url': 'http://example.com',
                'selectors': '{"title": "h1"}',
                'timeout': '30',
                'extract_text': True,
                'extract_links': False
            }
            form = WebScraperConfigForm(data=data)
            assert form.validate() is True
    
    def test_web_scraper_form_invalid_url(self, app):
        """Test form validation with invalid URL."""
        with app.app_context():
            data = {
                'url': 'not-a-url',
                'selectors': '{"title": "h1"}',
                'timeout': '30'
            }
            form = WebScraperConfigForm(data=data)
            assert form.validate() is False
            assert 'url' in form.errors
    
    def test_web_scraper_form_missing_selectors(self, app):
        """Test form validation with missing selectors."""
        with app.app_context():
            data = {
                'url': 'http://example.com',
                'timeout': '30'
            }
            form = WebScraperConfigForm(data=data)
            assert form.validate() is False
            assert 'selectors' in form.errors


class TestRSSReaderConfigForm:
    """Test the RSS reader configuration form."""
    
    def test_rss_reader_form_fields(self, app):
        """Test that all required fields are present."""
        with app.app_context():
            form = RSSReaderConfigForm()
            assert hasattr(form, 'feed_url')
            assert hasattr(form, 'max_entries')
            assert hasattr(form, 'include_content')
            assert hasattr(form, 'filter_keywords')
            assert hasattr(form, 'exclude_keywords')
    
    def test_rss_reader_form_validation(self, app):
        """Test form validation with valid data."""
        with app.app_context():
            data = {
                'feed_url': 'http://example.com/feed.xml',
                'max_entries': '50',
                'include_content': True,
                'filter_keywords': 'python,flask',
                'exclude_keywords': 'deprecated'
            }
            form = RSSReaderConfigForm(data=data)
            assert form.validate() is True
    
    def test_rss_reader_form_invalid_url(self, app):
        """Test form validation with invalid feed URL."""
        with app.app_context():
            data = {
                'feed_url': 'not-a-url',
                'max_entries': '50'
            }
            form = RSSReaderConfigForm(data=data)
            assert form.validate() is False
            assert 'feed_url' in form.errors


class TestFilterConfigForm:
    """Test the filter job configuration form."""
    
    def test_filter_form_fields(self, app):
        """Test that all required fields are present."""
        with app.app_context():
            form = FilterConfigForm()
            assert hasattr(form, 'input_data')
            assert hasattr(form, 'filters')
            assert hasattr(form, 'output_format')
            assert hasattr(form, 'case_sensitive')
            assert hasattr(form, 'regex_enabled')
    
    def test_filter_form_validation(self, app):
        """Test form validation with valid data."""
        with app.app_context():
            data = {
                'input_data': '{"items": [{"name": "test"}]}',
                'filters': '[{"type": "equals", "field": "name", "value": "test"}]',
                'output_format': 'original',
                'case_sensitive': False,
                'regex_enabled': False
            }
            form = FilterConfigForm(data=data)
            assert form.validate() is True
    
    def test_filter_form_invalid_json(self, app):
        """Test form validation with invalid JSON input."""
        with app.app_context():
            data = {
                'input_data': 'invalid-json',
                'filters': '[]'
            }
            form = FilterConfigForm(data=data)
            assert form.validate() is False
            assert 'input_data' in form.errors


class TestEmailSenderConfigForm:
    """Test the email sender configuration form."""
    
    def test_email_sender_form_fields(self, app):
        """Test that all required fields are present."""
        with app.app_context():
            form = EmailSenderConfigForm()
            assert hasattr(form, 'smtp_server')
            assert hasattr(form, 'smtp_port')
            assert hasattr(form, 'username')
            assert hasattr(form, 'password')
            assert hasattr(form, 'to_emails')
            assert hasattr(form, 'subject')
            assert hasattr(form, 'body')
    
    def test_email_sender_form_validation(self, app):
        """Test form validation with valid data."""
        with app.app_context():
            data = {
                'smtp_server': 'smtp.gmail.com',
                'smtp_port': '587',
                'username': 'test@gmail.com',
                'password': 'password123',
                'to_emails': 'recipient@example.com',
                'subject': 'Test Email',
                'body': 'This is a test email'
            }
            form = EmailSenderConfigForm(data=data)
            assert form.validate() is True
    
    def test_email_sender_form_invalid_port(self, app):
        """Test form validation with invalid SMTP port."""
        with app.app_context():
            data = {
                'smtp_server': 'smtp.gmail.com',
                'smtp_port': 'not-a-number',
                'username': 'test@gmail.com',
                'password': 'password123',
                'to_emails': 'recipient@example.com',
                'subject': 'Test Email',
                'body': 'This is a test email'
            }
            form = EmailSenderConfigForm(data=data)
            assert form.validate() is False
            assert 'smtp_port' in form.errors
    
    def test_email_sender_form_invalid_emails(self, app):
        """Test form validation with invalid email addresses."""
        with app.app_context():
            data = {
                'smtp_server': 'smtp.gmail.com',
                'smtp_port': '587',
                'username': 'test@gmail.com',
                'password': 'password123',
                'to_emails': 'invalid-email',
                'subject': 'Test Email',
                'body': 'This is a test email'
            }
            form = EmailSenderConfigForm(data=data)
            assert form.validate() is False
            assert 'to_emails' in form.errors


class TestJobEditForm:
    """Test the job editing form."""
    
    def test_job_edit_form_fields(self, app):
        """Test that all required fields are present."""
        with app.app_context():
            form = JobEditForm()
            assert hasattr(form, 'name')
            assert hasattr(form, 'description')
            assert hasattr(form, 'is_active')
    
    def test_job_edit_form_validation(self, app):
        """Test form validation with valid data."""
        with app.app_context():
            data = {
                'name': 'Updated Job Name',
                'description': 'Updated description',
                'is_active': True
            }
            form = JobEditForm(data=data)
            assert form.validate() is True


class TestJobExecutionForm:
    """Test the job execution form."""
    
    def test_job_execution_form_fields(self, app):
        """Test that all required fields are present."""
        with app.app_context():
            form = JobExecutionForm()
            assert hasattr(form, 'input_data')
            assert hasattr(form, 'priority')
    
    def test_job_execution_form_validation(self, app):
        """Test form validation with valid data."""
        with app.app_context():
            data = {
                'input_data': '{"key": "value"}',
                'priority': 'normal'
            }
            form = JobExecutionForm(data=data)
            assert form.validate() is True


class TestFormUtilities:
    """Test form utility functions."""
    
    def test_get_job_config_form_web_scraper(self, app):
        """Test getting web scraper config form."""
        with app.app_context():
            form_class = get_job_config_form('web_scraper')
            assert form_class == WebScraperConfigForm
    
    def test_get_job_config_form_rss_reader(self, app):
        """Test getting RSS reader config form."""
        with app.app_context():
            form_class = get_job_config_form('rss_reader')
            assert form_class == RSSReaderConfigForm
    
    def test_get_job_config_form_filter(self, app):
        """Test getting filter config form."""
        with app.app_context():
            form_class = get_job_config_form('filter')
            assert form_class == FilterConfigForm
    
    def test_get_job_config_form_email_sender(self, app):
        """Test getting email sender config form."""
        with app.app_context():
            form_class = get_job_config_form('email_sender')
            assert form_class == EmailSenderConfigForm
    
    def test_get_job_config_form_invalid_type(self, app):
        """Test getting config form for invalid job type."""
        with app.app_context():
            form_class = get_job_config_form('invalid_type')
            assert form_class is None
    
    def test_validate_job_config_valid(self, app):
        """Test job configuration validation with valid config."""
        with app.app_context():
            config = {
                'url': 'http://example.com',
                'selectors': {'title': 'h1'}
            }
            is_valid, errors = validate_job_config('web_scraper', config)
            assert is_valid is True
            assert len(errors) == 0
    
    def test_validate_job_config_invalid(self, app):
        """Test job configuration validation with invalid config."""
        with app.app_context():
            config = {
                'url': 'http://example.com'
                # Missing required 'selectors' field
            }
            is_valid, errors = validate_job_config('web_scraper', config)
            assert is_valid is False
            assert len(errors) > 0
    
    def test_clean_job_config(self, app):
        """Test job configuration cleaning."""
        with app.app_context():
            raw_config = {
                'url': '  http://example.com  ',
                'selectors': '{"title": "h1"}',
                'timeout': '30'
            }
            cleaned_config = clean_job_config(raw_config)
            
            assert cleaned_config['url'] == 'http://example.com'
            assert cleaned_config['selectors'] == {'title': 'h1'}
            assert cleaned_config['timeout'] == 30


class TestFormIntegration:
    """Test form integration with job types."""
    
    def test_form_job_type_mapping(self, app):
        """Test that forms correctly map to job types."""
        with app.app_context():
            job_types = ['web_scraper', 'rss_reader', 'filter', 'email_sender']
            
            for job_type in job_types:
                form_class = get_job_config_form(job_type)
                assert form_class is not None
                
                # Test that form can be instantiated
                form = form_class()
                assert form is not None
    
    def test_form_validation_consistency(self, app):
        """Test that form validation is consistent with job type requirements."""
        with app.app_context():
            # Test web scraper
            web_scraper_data = {
                'url': 'http://example.com',
                'selectors': '{"title": "h1"}'
            }
            form = WebScraperConfigForm(data=web_scraper_data)
            assert form.validate() is True
            
            # Test RSS reader
            rss_data = {
                'feed_url': 'http://example.com/feed.xml'
            }
            form = RSSReaderConfigForm(data=rss_data)
            assert form.validate() is True
            
            # Test filter
            filter_data = {
                'input_data': '{"items": []}',
                'filters': '[]'
            }
            form = FilterConfigForm(data=filter_data)
            assert form.validate() is True
            
            # Test email sender
            email_data = {
                'smtp_server': 'smtp.gmail.com',
                'smtp_port': '587',
                'username': 'test@gmail.com',
                'password': 'password123',
                'to_emails': 'recipient@example.com',
                'subject': 'Test',
                'body': 'Test body'
            }
            form = EmailSenderConfigForm(data=email_data)
            assert form.validate() is True


class TestFormEdgeCases:
    """Test form edge cases and error conditions."""
    
    def test_form_with_none_data(self, app):
        """Test forms with None data."""
        with app.app_context():
            form = JobCreationForm(data=None)
            assert form.validate() is False
    
    def test_form_with_empty_dict(self, app):
        """Test forms with empty dictionary."""
        with app.app_context():
            form = JobCreationForm(data={})
            assert form.validate() is False
    
    def test_form_with_whitespace_only(self, app):
        """Test forms with whitespace-only values."""
        with app.app_context():
            data = {
                'name': '   ',
                'job_type': 'web_scraper'
            }
            form = JobCreationForm(data=data)
            assert form.validate() is False
            assert 'name' in form.errors
    
    def test_form_with_very_long_values(self, app):
        """Test forms with extremely long values."""
        with app.app_context():
            long_name = 'a' * 1000
            data = {
                'name': long_name,
                'job_type': 'web_scraper'
            }
            form = JobCreationForm(data=data)
            # Should fail validation due to length restrictions
            assert form.validate() is False
            assert 'name' in form.errors
    
    def test_form_with_special_characters(self, app):
        """Test forms with special characters."""
        with app.app_context():
            data = {
                'name': 'Test Job with @#$%^&*()',
                'job_type': 'web_scraper'
            }
            form = JobCreationForm(data=data)
            assert form.validate() is True


class TestFormFieldTypes:
    """Test form field types and constraints."""
    
    def test_job_type_field_choices(self, app):
        """Test that job type field has correct choices."""
        with app.app_context():
            form = JobCreationForm()
            job_type_field = form.job_type
            
            # Check that all expected job types are available
            expected_types = ['web_scraper', 'rss_reader', 'filter', 'email_sender']
            for job_type in expected_types:
                assert job_type in [choice[0] for choice in job_type_field.choices]
    
    def test_boolean_fields(self, app):
        """Test boolean form fields."""
        with app.app_context():
            form = WebScraperConfigForm()
            
            # Test boolean fields
            assert hasattr(form, 'extract_text')
            assert hasattr(form, 'extract_links')
            
            # Test with boolean values
            data = {
                'url': 'http://example.com',
                'selectors': '{"title": "h1"}',
                'extract_text': True,
                'extract_links': False
            }
            form = WebScraperConfigForm(data=data)
            assert form.validate() is True
    
    def test_integer_fields(self, app):
        """Test integer form fields."""
        with app.app_context():
            form = WebScraperConfigForm()
            
            # Test integer fields
            assert hasattr(form, 'url')
            assert hasattr(form, 'selectors')
            assert hasattr(form, 'timeout')
            assert hasattr(form, 'extract_text')
            assert hasattr(form, 'extract_links')
            
            # Test with integer values
            data = {
                'url': 'http://example.com',
                'selectors': '{"title": "h1"}',
                'timeout': 30
            }
            form = WebScraperConfigForm(data=data)
            assert form.validate() is True
            
            # Test with string integer values
            data = {
                'url': 'http://example.com',
                'selectors': '{"title": "h1"}',
                'timeout': '30'
            }
            form = WebScraperConfigForm(data=data)
            assert form.validate() is True
