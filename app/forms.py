"""
Forms for the Muninn application
"""

from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, TextAreaField, IntegerField, BooleanField, FieldList, FormField
from wtforms.validators import DataRequired, Email, URL, Length, NumberRange, Optional, ValidationError
from wtforms.widgets import TextArea
from app.utils.validators import validate_email_list
from app.constants import JOB_TYPE_NAMES, MIN_PASSWORD_LENGTH, MIN_USERNAME_LENGTH, MAX_USERNAME_LENGTH
import json
import re


def validate_url(form, field):
    """Custom URL validator that's more lenient than WTForms' built-in validator."""
    if not field.data:
        return
    
    url = field.data.strip()
    
    # Basic URL pattern - more lenient than strict URL validation
    url_pattern = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain
        r'localhost|'  # localhost
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP address
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    if not url_pattern.match(url):
        raise ValidationError('Please enter a valid URL (e.g., https://example.com)')


class JobCreationForm(FlaskForm):
    """Form for creating new jobs."""

    name = StringField('Job Name', validators=[
        DataRequired(message='Job name is required'),
        Length(min=1, max=255, message='Job name must be between 1 and 255 characters')
    ])

    job_type = SelectField('Job Type', validators=[
        DataRequired(message='Job type is required')
    ])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Dynamically populate job types from registry
        from app.jobs import job_registry
        choices = [('', 'Select a job type')]
        for job_type in job_registry.get_registered_types():
            display_name = JOB_TYPE_NAMES.get(job_type, job_type.replace('_', ' ').title())
            choices.append((job_type, display_name))
        self.job_type.choices = choices


class WebScraperConfigForm(FlaskForm):
    """Configuration form for web scraper jobs."""
    
    url = StringField('Target URL', validators=[
        DataRequired(message='URL is required'),
        validate_url
    ])
    
    selectors = TextAreaField('CSS Selectors (JSON)', validators=[
        DataRequired(message='CSS selectors are required'),
        Length(max=2000, message='Selectors must be less than 2000 characters')
    ], widget=TextArea())
    
    timeout = IntegerField('Timeout (seconds)', validators=[
        Optional(),
        NumberRange(min=1, max=300, message='Timeout must be between 1 and 300 seconds')
    ], default=30)
    
    user_agent = StringField('User Agent', validators=[
        Optional(),
        Length(max=500, message='User agent must be less than 500 characters')
    ])
    
    extract_text = BooleanField('Extract Text Content', default=True)
    extract_links = BooleanField('Extract Links', default=False)
    
    def validate_selectors(self, field):
        """Validate that selectors contains valid JSON."""
        try:
            json.loads(field.data)
        except json.JSONDecodeError:
            raise ValidationError('Selectors must be valid JSON')


class RSSReaderConfigForm(FlaskForm):
    """Configuration form for RSS reader jobs."""
    
    feed_url = StringField('RSS Feed URL', validators=[
        DataRequired(message='Feed URL is required'),
        validate_url
    ])
    
    max_entries = IntegerField('Maximum Entries', validators=[
        Optional(),
        NumberRange(min=1, max=1000, message='Maximum entries must be between 1 and 1000')
    ], default=50)
    
    include_content = BooleanField('Include Full Content', default=False)
    
    filter_keywords = StringField('Filter Keywords', validators=[
        Optional(),
        Length(max=1000, message='Filter keywords must be less than 1000 characters')
    ])
    
    exclude_keywords = StringField('Exclude Keywords', validators=[
        Optional(),
        Length(max=1000, message='Exclude keywords must be less than 1000 characters')
    ])


class FilterConfigForm(FlaskForm):
    """Configuration form for filter jobs."""
    
    input_data = TextAreaField('Input Data (JSON)', validators=[
        DataRequired(message='Input data is required')
    ], widget=TextArea())
    
    filters = TextAreaField('Filters (JSON)', validators=[
        DataRequired(message='Filters are required'),
        Length(max=2000, message='Filters must be less than 2000 characters')
    ], widget=TextArea())
    
    output_format = SelectField('Output Format', choices=[
        ('original', 'Original'),
        ('count', 'Count Only'),
        ('summary', 'Summary')
    ], default='original')
    
    case_sensitive = BooleanField('Case Sensitive', default=True)
    regex_enabled = BooleanField('Enable Regex', default=False)
    
    def validate_input_data(self, field):
        """Validate that input_data contains valid JSON."""
        try:
            json.loads(field.data)
        except json.JSONDecodeError:
            raise ValidationError('Input data must be valid JSON')
    
    def validate_filters(self, field):
        """Validate that filters contains valid JSON."""
        try:
            json.loads(field.data)
        except json.JSONDecodeError:
            raise ValidationError('Filters must be valid JSON')


class EmailSenderConfigForm(FlaskForm):
    """Configuration form for email sender jobs."""
    
    smtp_server = StringField('SMTP Server', validators=[
        DataRequired(message='SMTP server is required'),
        Length(max=255, message='SMTP server must be less than 255 characters')
    ])
    
    smtp_port = IntegerField('SMTP Port', validators=[
        DataRequired(message='SMTP port is required'),
        NumberRange(min=1, max=65535, message='SMTP port must be between 1 and 65535')
    ], default=587)
    
    username = StringField('Username', validators=[
        DataRequired(message='Username is required'),
        Email(message='Please enter a valid email address')
    ])
    
    password = StringField('Password', validators=[
        DataRequired(message='Password is required'),
        Length(min=1, message='Password cannot be empty')
    ])
    
    to_emails = StringField('To Emails', validators=[
        DataRequired(message='At least one recipient email is required')
    ])
    
    subject = StringField('Subject', validators=[
        DataRequired(message='Subject is required'),
        Length(max=255, message='Subject must be less than 255 characters')
    ])
    
    body = TextAreaField('Email Body', validators=[
        Optional()
    ], widget=TextArea())
    
    html_body = TextAreaField('HTML Body', validators=[
        Optional()
    ], widget=TextArea())
    
    cc_emails = StringField('CC Emails', validators=[
        Optional()
    ])
    
    bcc_emails = StringField('BCC Emails', validators=[
        Optional()
    ])
    
    use_tls = BooleanField('Use TLS Encryption', default=True)
    
    def validate_to_emails(self, field):
        """Validate email addresses in to_emails field."""
        is_valid, errors = validate_email_list(field.data)
        if not is_valid:
            raise ValidationError('; '.join(errors))

    def validate_cc_emails(self, field):
        """Validate email addresses in cc_emails field."""
        if field.data:
            is_valid, errors = validate_email_list(field.data)
            if not is_valid:
                raise ValidationError(f"CC emails: {'; '.join(errors)}")

    def validate_bcc_emails(self, field):
        """Validate email addresses in bcc_emails field."""
        if field.data:
            is_valid, errors = validate_email_list(field.data)
            if not is_valid:
                raise ValidationError(f"BCC emails: {'; '.join(errors)}")


class JobEditForm(FlaskForm):
    """Form for editing existing jobs."""
    
    name = StringField('Job Name', validators=[
        DataRequired(message='Job name is required'),
        Length(min=1, max=255, message='Job name must be between 1 and 255 characters')
    ])
    
    description = TextAreaField('Description', validators=[
        Optional(),
        Length(max=1000, message='Description must be less than 1000 characters')
    ], widget=TextArea())
    
    is_active = BooleanField('Active', default=True)
    
    # Configuration will be handled dynamically based on job type


class JobExecutionForm(FlaskForm):
    """Form for executing jobs with custom input data."""
    
    input_data = TextAreaField('Input Data (JSON)', validators=[
        Optional()
    ], widget=TextArea())
    
    priority = SelectField('Priority', choices=[
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent')
    ], default='normal')
    
    def validate_input_data(self, field):
        """Validate that input_data contains valid JSON if provided."""
        if field.data:
            try:
                json.loads(field.data)
            except json.JSONDecodeError:
                raise ValidationError('Input data must be valid JSON')


# Form factory for creating job-specific configuration forms
def get_job_config_form(job_type: str):
    """Get the appropriate configuration form for a job type."""
    form_map = {
        'web_scraper': WebScraperConfigForm,
        'rss_reader': RSSReaderConfigForm,
        'filter': FilterConfigForm,
        'email_sender': EmailSenderConfigForm
    }
    
    return form_map.get(job_type, None)


# Utility functions for form validation
def validate_job_config(job_type: str, config_data: dict) -> tuple[bool, list]:
    """
    Validate job configuration data.
    
    Args:
        job_type: Type of job
        config_data: Configuration data to validate
        
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    try:
        form_class = get_job_config_form(job_type)
        if form_class is None:
            errors.append(f"Unknown job type: {job_type}")
            return False, errors
        
        # Convert Python objects to string format expected by forms
        form_data = {}
        for key, value in config_data.items():
            if isinstance(value, (dict, list)):
                form_data[key] = json.dumps(value)
            else:
                form_data[key] = str(value) if value is not None else ''
        
        # Create form instance with converted data
        form = form_class(data=form_data)
        
        if not form.validate():
            for field, field_errors in form.errors.items():
                for error in field_errors:
                    errors.append(f"{field}: {error}")
        
    except Exception as e:
        errors.append(f"Configuration validation error: {str(e)}")
    
    is_valid = len(errors) == 0
    return is_valid, errors


def clean_job_config(config_data: dict) -> dict:
    """
    Clean and normalize job configuration data.
    
    Args:
        config_data: Raw configuration data
        
    Returns:
        Cleaned configuration data
    """
    cleaned = {}
    
    try:
        # Clean string values by stripping whitespace and parsing JSON if needed
        for key, value in config_data.items():
            if isinstance(value, str):
                stripped_value = value.strip()
                # Try to parse as JSON if it looks like JSON
                if stripped_value.startswith('{') or stripped_value.startswith('['):
                    try:
                        cleaned[key] = json.loads(stripped_value)
                    except json.JSONDecodeError:
                        cleaned[key] = stripped_value
                else:
                    # Try to convert to number if possible
                    try:
                        if '.' in stripped_value:
                            cleaned[key] = float(stripped_value)
                        else:
                            cleaned[key] = int(stripped_value)
                    except ValueError:
                        cleaned[key] = stripped_value
            else:
                cleaned[key] = value
        
    except Exception as e:
        # Return original data if cleaning fails
        return config_data
    
    return cleaned
