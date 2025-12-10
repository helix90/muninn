"""
Tests for database models
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy.exc import IntegrityError
from app.models import User, Job, JobRun, JobChain
from app.extensions import db


class TestUserModel:
    """Test User model functionality."""
    
    def test_user_creation(self, app_context):
        """Test basic user creation."""
        user = User(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
        db.session.add(user)
        db.session.commit()
        
        assert user.id is not None
        assert user.username == 'testuser'
        assert user.email == 'test@example.com'
        assert user.is_active is True
        assert user.created_at is not None
        assert user.updated_at is not None
    
    def test_user_password_hashing(self, app_context):
        """Test password hashing and verification."""
        user = User(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
        
        # Password should be hashed
        assert user.password_hash != 'password123'
        assert user.password_hash.startswith('scrypt:') or user.password_hash.startswith('pbkdf2:')
        
        # Password verification should work
        assert user.check_password('password123') is True
        assert user.check_password('wrongpassword') is False
    
    def test_user_password_validation(self, app_context):
        """Test password validation rules."""
        with pytest.raises(ValueError, match="Password must be at least 8 characters long"):
            User(
                username='testuser',
                email='test@example.com',
                password='short'
            )
    
    def test_user_email_validation(self, app_context):
        """Test email validation."""
        with pytest.raises(ValueError, match="Invalid email format"):
            User(
                username='testuser',
                email='invalid-email',
                password='password123'
            )
    
    def test_user_email_normalization(self, app_context):
        """Test email is normalized to lowercase."""
        user = User(
            username='testuser',
            email='TEST@EXAMPLE.COM',
            password='password123'
        )
        assert user.email == 'test@example.com'
    
    def test_user_unique_constraints(self, app_context):
        """Test unique constraints on username and email."""
        user1 = User(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
        db.session.add(user1)
        db.session.commit()
        
        # Duplicate username should fail
        user2 = User(
            username='testuser',
            email='different@example.com',
            password='password123'
        )
        db.session.add(user2)
        with pytest.raises(IntegrityError):
            db.session.commit()
        
        db.session.rollback()
        
        # Duplicate email should fail
        user3 = User(
            username='differentuser',
            email='test@example.com',
            password='password123'
        )
        db.session.add(user3)
        with pytest.raises(IntegrityError):
            db.session.commit()
    
    def test_user_repr(self, app_context):
        """Test user string representation."""
        user = User(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
        assert repr(user) == '<User testuser>'


class TestJobModel:
    """Test Job model functionality."""
    
    def test_job_creation(self, app_context):
        """Test basic job creation."""
        # Create user first
        user = User(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
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
        
        assert job.id is not None
        assert job.name == 'Test Job'
        assert job.job_type == 'web_scraper'
        assert job.config == {'url': 'http://example.com', 'selectors': {'title': 'h1'}}
        assert job.user_id == user.id
        assert job.is_active is True
        assert job.created_at is not None
        assert job.updated_at is not None
    
    def test_job_config_validation(self, app_context):
        """Test job config validation."""
        user = User(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
        db.session.add(user)
        db.session.commit()
        
        # Config must be a dictionary
        with pytest.raises(ValueError, match="Config must be a dictionary"):
            job = Job(
                name='Test Job',
                job_type='web_scraper',
                config='not_a_dict',
                user_id=user.id
            )
            db.session.add(job)
            db.session.commit()
    
    def test_job_relationships(self, app_context):
        """Test job relationships with user and runs."""
        # Create user and job
        user = User(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
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
        
        # Test user relationship
        assert job.user == user
        assert job in user.jobs
        
        # Test runs relationship
        job_run = JobRun(job_id=job.id, status='pending')
        db.session.add(job_run)
        db.session.commit()
        
        assert job_run in job.runs
        assert job_run.job == job
    
    def test_job_repr(self, app_context):
        """Test job string representation."""
        user = User(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
        db.session.add(user)
        db.session.commit()
        
        job = Job(
            name='Test Job',
            job_type='web_scraper',
            config={'url': 'http://example.com', 'selectors': {'title': 'h1'}},
            user_id=user.id
        )
        assert repr(job) == '<Job Test Job (web_scraper)>'


class TestJobRunModel:
    """Test JobRun model functionality."""
    
    def test_job_run_creation(self, app_context):
        """Test basic job run creation."""
        # Create user and job first
        user = User(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
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
            status='pending',
            input_data={'file_path': '/data/input.csv'}
        )
        db.session.add(job_run)
        db.session.commit()
        
        assert job_run.id is not None
        assert job_run.job_id == job.id
        assert job_run.status == 'pending'
        assert job_run.input_data == {'file_path': '/data/input.csv'}
        assert job_run.output_data == {}
        assert job_run.started_at is not None
        assert job_run.completed_at is None
        assert job_run.error_message is None
    
    def test_job_run_status_validation(self, app_context):
        """Test job run status validation."""
        user = User(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
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
        
        # Invalid status should fail
        with pytest.raises(ValueError, match="Status must be one of"):
            job_run = JobRun(
                job_id=job.id,
                status='invalid_status'
            )
            db.session.add(job_run)
            db.session.commit()
    
    def test_job_run_json_validation(self, app_context):
        """Test job run JSON data validation."""
        user = User(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
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
        
        # Input data must be a dictionary
        with pytest.raises(ValueError, match="input_data must be a dictionary or None"):
            job_run = JobRun(
                job_id=job.id,
                status='pending',
                input_data='not_a_dict'
            )
            db.session.add(job_run)
            db.session.commit()
    
    def test_job_run_mark_completed(self, app_context):
        """Test marking job run as completed."""
        user = User(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
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
        
        job_run = JobRun(job_id=job.id, status='running')
        db.session.add(job_run)
        db.session.commit()
        
        # Mark as completed
        job_run.mark_completed({'result': 'success'})
        db.session.commit()
        
        assert job_run.status == 'completed'
        assert job_run.completed_at is not None
        assert job_run.output_data == {'result': 'success'}
    
    def test_job_run_mark_failed(self, app_context):
        """Test marking job run as failed."""
        user = User(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
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
        
        job_run = JobRun(job_id=job.id, status='running')
        db.session.add(job_run)
        db.session.commit()
        
        # Mark as failed
        job_run.mark_failed('Database connection failed')
        db.session.commit()
        
        assert job_run.status == 'failed'
        assert job_run.completed_at is not None
        assert job_run.error_message == 'Database connection failed'
    
    def test_job_run_duration(self, app_context):
        """Test job run duration calculation."""
        user = User(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
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
        
        job_run = JobRun(job_id=job.id, status='running')
        db.session.add(job_run)
        db.session.commit()
        
        # Duration should be None for running job
        assert job_run.get_duration() is None
        
        # Mark as completed
        job_run.mark_completed()
        db.session.commit()
        
        # Duration should be calculated
        duration = job_run.get_duration()
        assert duration is not None
        assert duration >= 0
    
    def test_job_run_repr(self, app_context):
        """Test job run string representation."""
        user = User(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
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
        
        job_run = JobRun(job_id=job.id, status='pending')
        db.session.add(job_run)
        db.session.commit()
        
        assert repr(job_run) == f'<JobRun {job_run.id} - {job.name} (pending)>'


class TestJobChainModel:
    """Test JobChain model functionality."""
    
    def test_job_chain_creation(self, app_context):
        """Test basic job chain creation."""
        # Create user and jobs first
        user = User(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
        db.session.add(user)
        db.session.commit()
        
        parent_job = Job(
            name='Parent Job',
            job_type='web_scraper',
            config={'url': 'http://example.com', 'selectors': {'title': 'h1'}},
            user_id=user.id
        )
        child_job = Job(
            name='Child Job',
            job_type='email_sender',
            config={'smtp_server': 'smtp.example.com', 'smtp_port': 587, 'username': 'user', 'password': 'pass', 'to_emails': ['test@example.com'], 'subject': 'Test', 'body': 'Test body'},
            user_id=user.id
        )
        db.session.add_all([parent_job, child_job])
        db.session.commit()
        
        job_chain = JobChain(
            parent_job_id=parent_job.id,
            child_job_id=child_job.id,
            condition_config={'trigger_on': 'success'}
        )
        db.session.add(job_chain)
        db.session.commit()
        
        assert job_chain.id is not None
        assert job_chain.parent_job_id == parent_job.id
        assert job_chain.child_job_id == child_job.id
        assert job_chain.condition_config == {'trigger_on': 'success'}
        assert job_chain.created_at is not None
    
    def test_job_chain_self_reference_prevention(self, app_context):
        """Test prevention of self-referencing job chains."""
        user = User(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
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
        
        # Self-reference should fail
        with pytest.raises(ValueError, match="Parent and child job cannot be the same"):
            job_chain = JobChain(
                parent_job_id=job.id,
                child_job_id=job.id
            )
    
    def test_job_chain_condition_config_validation(self, app_context):
        """Test job chain condition config validation."""
        user = User(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
        db.session.add(user)
        db.session.commit()
        
        parent_job = Job(
            name='Parent Job',
            job_type='web_scraper',
            config={'url': 'http://example.com', 'selectors': {'title': 'h1'}},
            user_id=user.id
        )
        child_job = Job(
            name='Child Job',
            job_type='email_sender',
            config={'smtp_server': 'smtp.example.com', 'smtp_port': 587, 'username': 'user', 'password': 'pass', 'to_emails': ['test@example.com'], 'subject': 'Test', 'body': 'Test body'},
            user_id=user.id
        )
        db.session.add_all([parent_job, child_job])
        db.session.commit()
        
        # Condition config must be a dictionary
        with pytest.raises(ValueError, match="Condition config must be a dictionary"):
            job_chain = JobChain(
                parent_job_id=parent_job.id,
                child_job_id=child_job.id,
                condition_config='not_a_dict'
            )
            db.session.add(job_chain)
            db.session.commit()
    
    def test_job_chain_relationships(self, app_context):
        """Test job chain relationships."""
        user = User(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
        db.session.add(user)
        db.session.commit()
        
        parent_job = Job(
            name='Parent Job',
            job_type='web_scraper',
            config={'url': 'http://example.com', 'selectors': {'title': 'h1'}},
            user_id=user.id
        )
        child_job = Job(
            name='Child Job',
            job_type='email_sender',
            config={'smtp_server': 'smtp.example.com', 'smtp_port': 587, 'username': 'user', 'password': 'pass', 'to_emails': ['test@example.com'], 'subject': 'Test', 'body': 'Test body'},
            user_id=user.id
        )
        db.session.add_all([parent_job, child_job])
        db.session.commit()
        
        job_chain = JobChain(
            parent_job_id=parent_job.id,
            child_job_id=child_job.id
        )
        db.session.add(job_chain)
        db.session.commit()
        
        # Test relationships
        assert job_chain.parent_job == parent_job
        assert job_chain.child_job == child_job
        assert job_chain in parent_job.parent_chains
        assert job_chain in child_job.child_chains
    
    def test_job_chain_repr(self, app_context):
        """Test job chain string representation."""
        user = User(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
        db.session.add(user)
        db.session.commit()
        
        parent_job = Job(
            name='Parent Job',
            job_type='web_scraper',
            config={'url': 'http://example.com', 'selectors': {'title': 'h1'}},
            user_id=user.id
        )
        child_job = Job(
            name='Child Job',
            job_type='email_sender',
            config={'smtp_server': 'smtp.example.com', 'smtp_port': 587, 'username': 'user', 'password': 'pass', 'to_emails': ['test@example.com'], 'subject': 'Test', 'body': 'Test body'},
            user_id=user.id
        )
        db.session.add_all([parent_job, child_job])
        db.session.commit()
        
        job_chain = JobChain(
            parent_job_id=parent_job.id,
            child_job_id=child_job.id
        )
        assert repr(job_chain) == f'<JobChain {parent_job.id} -> {child_job.id}>'


class TestModelConstraints:
    """Test model constraints and edge cases."""
    
    def test_cascade_delete(self, app_context):
        """Test cascade delete behavior."""
        user = User(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
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
        
        job_run = JobRun(job_id=job.id, status='pending')
        db.session.add(job_run)
        db.session.commit()
        
        # Delete user should cascade to job and job_run
        db.session.delete(user)
        db.session.commit()
        
        # All related records should be deleted
        assert db.session.query(User).count() == 0
        assert db.session.query(Job).count() == 0
        assert db.session.query(JobRun).count() == 0
    
    def test_soft_delete(self, app_context):
        """Test soft delete functionality with is_active flag."""
        user = User(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
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
        
        # Soft delete by setting is_active to False
        job.is_active = False
        db.session.commit()
        
        # Job should still exist but be inactive
        assert db.session.query(Job).filter_by(is_active=False).count() == 1
        assert db.session.query(Job).filter_by(is_active=True).count() == 0
    
    def test_timestamp_auto_update(self, app_context):
        """Test automatic timestamp updates."""
        user = User(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
        db.session.add(user)
        db.session.commit()
        
        original_updated_at = user.updated_at
        
        # Wait a moment to ensure timestamp difference
        import time
        time.sleep(0.1)
        
        # Update user
        user.username = 'updateduser'
        db.session.commit()
        
        # updated_at should be automatically updated
        assert user.updated_at > original_updated_at 