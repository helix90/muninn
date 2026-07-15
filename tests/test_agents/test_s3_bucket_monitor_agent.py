"""
Tests for S3BucketMonitorAgent
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from app.extensions import db
from app.agents.types import S3BucketMonitorAgent
from app.agents import agent_registry
from app.models import Event


@pytest.fixture
def test_job(app, test_user):
    """Create a test job for agent tests"""
    from app.models import Job

    with app.app_context():
        job = Job(
            name='Test S3 Monitor',
            job_type='s3_bucket_monitor_agent',
            config={
                'bucket_name': 'test-bucket',
                'aws_access_key_id': 'test_access_key',
                'aws_secret_access_key': 'test_secret_key',
                'region': 'us-east-1'
            },
            user_id=test_user.id
        )
        db.session.add(job)
        db.session.commit()

        yield job


class TestS3BucketMonitorAgentRegistration:
    """Tests for S3BucketMonitorAgent registration"""

    def test_s3_agent_registered(self):
        """Test that S3BucketMonitorAgent is registered"""
        assert agent_registry.is_registered('s3_bucket_monitor_agent')
        assert 's3_bucket_monitor_agent' in agent_registry.get_source_agents()

    def test_s3_agent_capabilities(self):
        """Test S3BucketMonitorAgent capabilities"""
        assert S3BucketMonitorAgent.can_be_scheduled == True
        assert S3BucketMonitorAgent.can_receive_events == False
        assert S3BucketMonitorAgent.can_create_events == True
        assert S3BucketMonitorAgent.requires_input == False


class TestS3BucketMonitorAgentConfig:
    """Tests for S3BucketMonitorAgent configuration validation"""

    def test_valid_minimal_config(self):
        """Test S3 agent with minimal valid configuration"""
        agent = S3BucketMonitorAgent(
            agent_id=1,
            config={
                'bucket_name': 'test-bucket',
                'aws_access_key_id': 'AKIAIOSFODNN7EXAMPLE',
                'aws_secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                'region': 'us-east-1'
            },
            user_id=1
        )
        assert agent.agent_type == 's3_bucket_monitor_agent'
        assert agent.bucket_name == 'test-bucket'
        assert agent.region == 'us-east-1'

    def test_valid_config_with_all_options(self):
        """Test S3 agent with all configuration options"""
        agent = S3BucketMonitorAgent(
            agent_id=1,
            config={
                'bucket_name': 'my-data-bucket',
                'aws_access_key_id': 'AKIAIOSFODNN7EXAMPLE',
                'aws_secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                'region': 'us-west-2',
                'prefix': 'uploads/',
                'max_keys': 500,
                'file_pattern': '*.pdf',
                'exclude_pattern': '*.tmp',
                'detect_creates': True,
                'detect_modifies': False,
                'detect_deletes': True,
                'endpoint_url': 'https://s3.example.com',
                'use_ssl': False
            },
            user_id=1
        )
        assert agent.bucket_name == 'my-data-bucket'
        assert agent.prefix == 'uploads/'
        assert agent.max_keys == 500
        assert agent.file_pattern == '*.pdf'
        assert agent.exclude_pattern == '*.tmp'
        assert agent.detect_creates == True
        assert agent.detect_modifies == False
        assert agent.detect_deletes == True
        assert agent.endpoint_url == 'https://s3.example.com'
        assert agent.use_ssl == False

    def test_missing_bucket_name(self):
        """Test that missing bucket_name raises error"""
        with pytest.raises(ValueError, match="bucket_name is required"):
            S3BucketMonitorAgent(
                agent_id=1,
                config={
                    'aws_access_key_id': 'AKIAIOSFODNN7EXAMPLE',
                    'aws_secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                    'region': 'us-east-1'
                },
                user_id=1
            )

    def test_missing_aws_access_key(self):
        """Test that missing aws_access_key_id raises error"""
        with pytest.raises(ValueError, match="aws_access_key_id is required"):
            S3BucketMonitorAgent(
                agent_id=1,
                config={
                    'bucket_name': 'test-bucket',
                    'aws_secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                    'region': 'us-east-1'
                },
                user_id=1
            )

    def test_missing_aws_secret_key(self):
        """Test that missing aws_secret_access_key raises error"""
        with pytest.raises(ValueError, match="aws_secret_access_key is required"):
            S3BucketMonitorAgent(
                agent_id=1,
                config={
                    'bucket_name': 'test-bucket',
                    'aws_access_key_id': 'AKIAIOSFODNN7EXAMPLE',
                    'region': 'us-east-1'
                },
                user_id=1
            )

    def test_missing_region(self):
        """Test that missing region raises error"""
        with pytest.raises(ValueError, match="region is required"):
            S3BucketMonitorAgent(
                agent_id=1,
                config={
                    'bucket_name': 'test-bucket',
                    'aws_access_key_id': 'AKIAIOSFODNN7EXAMPLE',
                    'aws_secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                    'region': ''
                },
                user_id=1
            )

    def test_invalid_bucket_name_too_short(self):
        """Test that bucket name must be at least 3 characters"""
        with pytest.raises(ValueError, match="bucket_name must be between 3 and 63 characters"):
            S3BucketMonitorAgent(
                agent_id=1,
                config={
                    'bucket_name': 'ab',
                    'aws_access_key_id': 'AKIAIOSFODNN7EXAMPLE',
                    'aws_secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                    'region': 'us-east-1'
                },
                user_id=1
            )

    def test_invalid_bucket_name_too_long(self):
        """Test that bucket name must be at most 63 characters"""
        with pytest.raises(ValueError, match="bucket_name must be between 3 and 63 characters"):
            S3BucketMonitorAgent(
                agent_id=1,
                config={
                    'bucket_name': 'a' * 64,
                    'aws_access_key_id': 'AKIAIOSFODNN7EXAMPLE',
                    'aws_secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                    'region': 'us-east-1'
                },
                user_id=1
            )

    def test_invalid_max_keys_too_low(self):
        """Test that max_keys must be at least 1"""
        with pytest.raises(ValueError, match="max_keys must be between 1 and 1000"):
            S3BucketMonitorAgent(
                agent_id=1,
                config={
                    'bucket_name': 'test-bucket',
                    'aws_access_key_id': 'AKIAIOSFODNN7EXAMPLE',
                    'aws_secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                    'region': 'us-east-1',
                    'max_keys': 0
                },
                user_id=1
            )

    def test_invalid_max_keys_too_high(self):
        """Test that max_keys must be at most 1000"""
        with pytest.raises(ValueError, match="max_keys must be between 1 and 1000"):
            S3BucketMonitorAgent(
                agent_id=1,
                config={
                    'bucket_name': 'test-bucket',
                    'aws_access_key_id': 'AKIAIOSFODNN7EXAMPLE',
                    'aws_secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                    'region': 'us-east-1',
                    'max_keys': 1001
                },
                user_id=1
            )

    def test_invalid_detect_creates_not_boolean(self):
        """Test that detect_creates must be boolean"""
        with pytest.raises(ValueError, match="detect_creates must be a boolean"):
            S3BucketMonitorAgent(
                agent_id=1,
                config={
                    'bucket_name': 'test-bucket',
                    'aws_access_key_id': 'AKIAIOSFODNN7EXAMPLE',
                    'aws_secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                    'region': 'us-east-1',
                    'detect_creates': 'yes'
                },
                user_id=1
            )

    def test_invalid_all_detection_types_disabled(self):
        """Test that at least one detection type must be enabled"""
        with pytest.raises(ValueError, match="At least one detection type"):
            S3BucketMonitorAgent(
                agent_id=1,
                config={
                    'bucket_name': 'test-bucket',
                    'aws_access_key_id': 'AKIAIOSFODNN7EXAMPLE',
                    'aws_secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                    'region': 'us-east-1',
                    'detect_creates': False,
                    'detect_modifies': False,
                    'detect_deletes': False
                },
                user_id=1
            )


class TestS3BucketMonitorAgentFetch:
    """Tests for S3BucketMonitorAgent fetch logic"""

    @patch('boto3.client')
    def test_first_run_all_created(self, mock_boto_client, test_job):
        """Test first run detects all objects as created"""
        # Mock S3 client
        mock_s3 = Mock()
        mock_boto_client.return_value = mock_s3

        # Mock list_objects_v2 response
        mock_s3.list_objects_v2.return_value = {
            'Contents': [
                {
                    'Key': 'file1.txt',
                    'ETag': '"abc123"',
                    'Size': 1024,
                    'LastModified': datetime(2025, 1, 15, 10, 30, 0),
                    'StorageClass': 'STANDARD'
                },
                {
                    'Key': 'file2.txt',
                    'ETag': '"def456"',
                    'Size': 2048,
                    'LastModified': datetime(2025, 1, 15, 11, 0, 0),
                    'StorageClass': 'STANDARD'
                }
            ],
            'IsTruncated': False
        }

        # Create agent and fetch
        agent = S3BucketMonitorAgent(
            agent_id=test_job.id,
            config={
                'bucket_name': 'test-bucket',
                'aws_access_key_id': 'AKIAIOSFODNN7EXAMPLE',
                'aws_secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                'region': 'us-east-1'
            },
            user_id=test_job.user_id,
            db_session=db.session
        )

        events = agent.fetch()
        db.session.commit()

        # Verify results
        assert len(events) == 2
        assert all(isinstance(e, Event) for e in events)
        assert events[0].payload['event_type'] == 'created'
        assert events[0].payload['key'] == 'file1.txt'
        assert events[0].payload['bucket'] == 'test-bucket'
        assert events[0].payload['etag'] == '"abc123"'
        assert events[0].payload['size'] == 1024

        assert events[1].payload['event_type'] == 'created'
        assert events[1].payload['key'] == 'file2.txt'

    @patch('boto3.client')
    def test_no_changes_no_events(self, mock_boto_client, test_job):
        """Test no events when no changes detected"""
        # Mock S3 client
        mock_s3 = Mock()
        mock_boto_client.return_value = mock_s3

        # Mock list_objects_v2 response
        mock_s3.list_objects_v2.return_value = {
            'Contents': [
                {
                    'Key': 'file1.txt',
                    'ETag': '"abc123"',
                    'Size': 1024,
                    'LastModified': datetime(2025, 1, 15, 10, 30, 0),
                    'StorageClass': 'STANDARD'
                }
            ],
            'IsTruncated': False
        }

        # Create agent
        agent = S3BucketMonitorAgent(
            agent_id=test_job.id,
            config={
                'bucket_name': 'test-bucket',
                'aws_access_key_id': 'AKIAIOSFODNN7EXAMPLE',
                'aws_secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                'region': 'us-east-1'
            },
            user_id=test_job.user_id,
            db_session=db.session
        )

        # First fetch - creates events
        events = agent.fetch()
        assert len(events) == 1

        # Second fetch with same data - no events
        events = agent.fetch()
        assert len(events) == 0

    @patch('boto3.client')
    def test_new_file_created_event(self, mock_boto_client, test_job):
        """Test detection of new file"""
        # Mock S3 client
        mock_s3 = Mock()
        mock_boto_client.return_value = mock_s3

        # First call - one file
        mock_s3.list_objects_v2.side_effect = [
            {
                'Contents': [
                    {
                        'Key': 'file1.txt',
                        'ETag': '"abc123"',
                        'Size': 1024,
                        'LastModified': datetime(2025, 1, 15, 10, 30, 0),
                        'StorageClass': 'STANDARD'
                    }
                ],
                'IsTruncated': False
            },
            # Second call - two files
            {
                'Contents': [
                    {
                        'Key': 'file1.txt',
                        'ETag': '"abc123"',
                        'Size': 1024,
                        'LastModified': datetime(2025, 1, 15, 10, 30, 0),
                        'StorageClass': 'STANDARD'
                    },
                    {
                        'Key': 'file2.txt',
                        'ETag': '"def456"',
                        'Size': 2048,
                        'LastModified': datetime(2025, 1, 15, 11, 0, 0),
                        'StorageClass': 'STANDARD'
                    }
                ],
                'IsTruncated': False
            }
        ]

        # Create agent
        agent = S3BucketMonitorAgent(
            agent_id=test_job.id,
            config={
                'bucket_name': 'test-bucket',
                'aws_access_key_id': 'AKIAIOSFODNN7EXAMPLE',
                'aws_secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                'region': 'us-east-1'
            },
            user_id=test_job.user_id,
            db_session=db.session
        )

        # First fetch
        events = agent.fetch()
        assert len(events) == 1
        assert events[0].payload['event_type'] == 'created'
        assert events[0].payload['key'] == 'file1.txt'

        # Second fetch - should detect new file
        events = agent.fetch()
        assert len(events) == 1
        assert events[0].payload['event_type'] == 'created'
        assert events[0].payload['key'] == 'file2.txt'

    @patch('boto3.client')
    def test_modified_file_modified_event(self, mock_boto_client, test_job):
        """Test detection of modified file via ETag change"""
        # Mock S3 client
        mock_s3 = Mock()
        mock_boto_client.return_value = mock_s3

        # First call - original file
        mock_s3.list_objects_v2.side_effect = [
            {
                'Contents': [
                    {
                        'Key': 'file1.txt',
                        'ETag': '"abc123"',
                        'Size': 1024,
                        'LastModified': datetime(2025, 1, 15, 10, 30, 0),
                        'StorageClass': 'STANDARD'
                    }
                ],
                'IsTruncated': False
            },
            # Second call - modified file (different ETag and size)
            {
                'Contents': [
                    {
                        'Key': 'file1.txt',
                        'ETag': '"xyz789"',
                        'Size': 2048,
                        'LastModified': datetime(2025, 1, 15, 12, 0, 0),
                        'StorageClass': 'STANDARD'
                    }
                ],
                'IsTruncated': False
            }
        ]

        # Create agent
        agent = S3BucketMonitorAgent(
            agent_id=test_job.id,
            config={
                'bucket_name': 'test-bucket',
                'aws_access_key_id': 'AKIAIOSFODNN7EXAMPLE',
                'aws_secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                'region': 'us-east-1'
            },
            user_id=test_job.user_id,
            db_session=db.session
        )

        # First fetch
        events = agent.fetch()
        assert len(events) == 1
        assert events[0].payload['event_type'] == 'created'

        # Second fetch - should detect modification
        events = agent.fetch()
        assert len(events) == 1
        assert events[0].payload['event_type'] == 'modified'
        assert events[0].payload['key'] == 'file1.txt'
        assert events[0].payload['etag'] == '"xyz789"'
        assert events[0].payload['size'] == 2048
        assert events[0].payload['previous_etag'] == '"abc123"'
        assert events[0].payload['previous_size'] == 1024

    @patch('boto3.client')
    def test_deleted_file_deleted_event(self, mock_boto_client, test_job):
        """Test detection of deleted file"""
        # Mock S3 client
        mock_s3 = Mock()
        mock_boto_client.return_value = mock_s3

        # First call - two files
        mock_s3.list_objects_v2.side_effect = [
            {
                'Contents': [
                    {
                        'Key': 'file1.txt',
                        'ETag': '"abc123"',
                        'Size': 1024,
                        'LastModified': datetime(2025, 1, 15, 10, 30, 0),
                        'StorageClass': 'STANDARD'
                    },
                    {
                        'Key': 'file2.txt',
                        'ETag': '"def456"',
                        'Size': 2048,
                        'LastModified': datetime(2025, 1, 15, 11, 0, 0),
                        'StorageClass': 'STANDARD'
                    }
                ],
                'IsTruncated': False
            },
            # Second call - one file deleted
            {
                'Contents': [
                    {
                        'Key': 'file1.txt',
                        'ETag': '"abc123"',
                        'Size': 1024,
                        'LastModified': datetime(2025, 1, 15, 10, 30, 0),
                        'StorageClass': 'STANDARD'
                    }
                ],
                'IsTruncated': False
            }
        ]

        # Create agent
        agent = S3BucketMonitorAgent(
            agent_id=test_job.id,
            config={
                'bucket_name': 'test-bucket',
                'aws_access_key_id': 'AKIAIOSFODNN7EXAMPLE',
                'aws_secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                'region': 'us-east-1'
            },
            user_id=test_job.user_id,
            db_session=db.session
        )

        # First fetch
        events = agent.fetch()
        assert len(events) == 2

        # Second fetch - should detect deletion
        events = agent.fetch()
        assert len(events) == 1
        assert events[0].payload['event_type'] == 'deleted'
        assert events[0].payload['key'] == 'file2.txt'
        assert events[0].payload['deleted_etag'] == '"def456"'
        assert events[0].payload['deleted_size'] == 2048

    @patch('boto3.client')
    def test_multiple_changes_single_sync(self, mock_boto_client, test_job):
        """Test detection of multiple change types in single sync"""
        # Mock S3 client
        mock_s3 = Mock()
        mock_boto_client.return_value = mock_s3

        # First call - initial state
        mock_s3.list_objects_v2.side_effect = [
            {
                'Contents': [
                    {
                        'Key': 'file1.txt',
                        'ETag': '"abc123"',
                        'Size': 1024,
                        'LastModified': datetime(2025, 1, 15, 10, 30, 0),
                        'StorageClass': 'STANDARD'
                    },
                    {
                        'Key': 'file2.txt',
                        'ETag': '"def456"',
                        'Size': 2048,
                        'LastModified': datetime(2025, 1, 15, 11, 0, 0),
                        'StorageClass': 'STANDARD'
                    }
                ],
                'IsTruncated': False
            },
            # Second call - new file, modified file, deleted file
            {
                'Contents': [
                    {
                        'Key': 'file1.txt',
                        'ETag': '"xyz789"',  # Modified
                        'Size': 3072,
                        'LastModified': datetime(2025, 1, 15, 12, 0, 0),
                        'StorageClass': 'STANDARD'
                    },
                    # file2.txt deleted
                    {
                        'Key': 'file3.txt',  # New file
                        'ETag': '"ghi012"',
                        'Size': 4096,
                        'LastModified': datetime(2025, 1, 15, 12, 30, 0),
                        'StorageClass': 'STANDARD'
                    }
                ],
                'IsTruncated': False
            }
        ]

        # Create agent
        agent = S3BucketMonitorAgent(
            agent_id=test_job.id,
            config={
                'bucket_name': 'test-bucket',
                'aws_access_key_id': 'AKIAIOSFODNN7EXAMPLE',
                'aws_secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                'region': 'us-east-1'
            },
            user_id=test_job.user_id,
            db_session=db.session
        )

        # First fetch
        events = agent.fetch()
        assert len(events) == 2

        # Second fetch - should detect all changes
        events = agent.fetch()
        assert len(events) == 3

        # Find events by type
        event_types = {e.payload['event_type']: e for e in events}

        assert 'modified' in event_types
        assert event_types['modified'].payload['key'] == 'file1.txt'

        assert 'created' in event_types
        assert event_types['created'].payload['key'] == 'file3.txt'

        assert 'deleted' in event_types
        assert event_types['deleted'].payload['key'] == 'file2.txt'


class TestS3BucketMonitorAgentPagination:
    """Tests for S3BucketMonitorAgent pagination"""

    @patch('boto3.client')
    def test_small_bucket_single_page(self, mock_boto_client, test_job):
        """Test listing small bucket (no pagination needed)"""
        # Mock S3 client
        mock_s3 = Mock()
        mock_boto_client.return_value = mock_s3

        # Mock single-page response
        mock_s3.list_objects_v2.return_value = {
            'Contents': [
                {
                    'Key': f'file{i}.txt',
                    'ETag': f'"etag{i}"',
                    'Size': 1024 * i,
                    'LastModified': datetime(2025, 1, 15, 10, 30, 0),
                    'StorageClass': 'STANDARD'
                }
                for i in range(1, 11)  # 10 files
            ],
            'IsTruncated': False
        }

        # Create agent
        agent = S3BucketMonitorAgent(
            agent_id=test_job.id,
            config={
                'bucket_name': 'test-bucket',
                'aws_access_key_id': 'AKIAIOSFODNN7EXAMPLE',
                'aws_secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                'region': 'us-east-1'
            },
            user_id=test_job.user_id,
            db_session=db.session
        )

        events = agent.fetch()

        # Should have 10 events (all created on first run)
        assert len(events) == 10
        # Should have called list_objects_v2 only once
        assert mock_s3.list_objects_v2.call_count == 1

    @patch('boto3.client')
    def test_large_bucket_multiple_pages(self, mock_boto_client, test_job):
        """Test listing large bucket with pagination"""
        # Mock S3 client
        mock_s3 = Mock()
        mock_boto_client.return_value = mock_s3

        # Mock paginated responses
        mock_s3.list_objects_v2.side_effect = [
            # First page
            {
                'Contents': [
                    {
                        'Key': f'file{i}.txt',
                        'ETag': f'"etag{i}"',
                        'Size': 1024 * i,
                        'LastModified': datetime(2025, 1, 15, 10, 30, 0),
                        'StorageClass': 'STANDARD'
                    }
                    for i in range(1, 6)  # 5 files
                ],
                'IsTruncated': True,
                'NextContinuationToken': 'token1'
            },
            # Second page
            {
                'Contents': [
                    {
                        'Key': f'file{i}.txt',
                        'ETag': f'"etag{i}"',
                        'Size': 1024 * i,
                        'LastModified': datetime(2025, 1, 15, 10, 30, 0),
                        'StorageClass': 'STANDARD'
                    }
                    for i in range(6, 11)  # 5 more files
                ],
                'IsTruncated': False
            }
        ]

        # Create agent with small max_keys to force pagination
        agent = S3BucketMonitorAgent(
            agent_id=test_job.id,
            config={
                'bucket_name': 'test-bucket',
                'aws_access_key_id': 'AKIAIOSFODNN7EXAMPLE',
                'aws_secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                'region': 'us-east-1',
                'max_keys': 5
            },
            user_id=test_job.user_id,
            db_session=db.session
        )

        events = agent.fetch()

        # Should have 10 events total (all created on first run)
        assert len(events) == 10
        # Should have called list_objects_v2 twice (two pages)
        assert mock_s3.list_objects_v2.call_count == 2

        # Verify continuation token was used
        second_call_args = mock_s3.list_objects_v2.call_args_list[1][1]
        assert second_call_args['ContinuationToken'] == 'token1'

    @patch('boto3.client')
    def test_empty_bucket_no_events(self, mock_boto_client, test_job):
        """Test listing empty bucket"""
        # Mock S3 client
        mock_s3 = Mock()
        mock_boto_client.return_value = mock_s3

        # Mock empty response
        mock_s3.list_objects_v2.return_value = {
            'Contents': [],
            'IsTruncated': False
        }

        # Create agent
        agent = S3BucketMonitorAgent(
            agent_id=test_job.id,
            config={
                'bucket_name': 'test-bucket',
                'aws_access_key_id': 'AKIAIOSFODNN7EXAMPLE',
                'aws_secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                'region': 'us-east-1'
            },
            user_id=test_job.user_id,
            db_session=db.session
        )

        events = agent.fetch()

        # Should have no events
        assert len(events) == 0


class TestS3BucketMonitorAgentFilters:
    """Tests for S3BucketMonitorAgent filtering"""

    @patch('boto3.client')
    def test_prefix_filter(self, mock_boto_client, test_job):
        """Test filtering by prefix"""
        # Mock S3 client
        mock_s3 = Mock()
        mock_boto_client.return_value = mock_s3

        # Mock response
        mock_s3.list_objects_v2.return_value = {
            'Contents': [
                {
                    'Key': 'logs/app.log',
                    'ETag': '"abc123"',
                    'Size': 1024,
                    'LastModified': datetime(2025, 1, 15, 10, 30, 0),
                    'StorageClass': 'STANDARD'
                }
            ],
            'IsTruncated': False
        }

        # Create agent with prefix
        agent = S3BucketMonitorAgent(
            agent_id=test_job.id,
            config={
                'bucket_name': 'test-bucket',
                'aws_access_key_id': 'AKIAIOSFODNN7EXAMPLE',
                'aws_secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                'region': 'us-east-1',
                'prefix': 'logs/'
            },
            user_id=test_job.user_id,
            db_session=db.session
        )

        agent.fetch()

        # Verify prefix was passed to S3 API
        call_args = mock_s3.list_objects_v2.call_args[1]
        assert call_args['Prefix'] == 'logs/'

    @patch('boto3.client')
    def test_file_pattern_filter(self, mock_boto_client, test_job):
        """Test filtering by file pattern"""
        # Mock S3 client
        mock_s3 = Mock()
        mock_boto_client.return_value = mock_s3

        # Mock response with mixed file types
        mock_s3.list_objects_v2.return_value = {
            'Contents': [
                {
                    'Key': 'document1.pdf',
                    'ETag': '"abc123"',
                    'Size': 1024,
                    'LastModified': datetime(2025, 1, 15, 10, 30, 0),
                    'StorageClass': 'STANDARD'
                },
                {
                    'Key': 'document2.txt',
                    'ETag': '"def456"',
                    'Size': 2048,
                    'LastModified': datetime(2025, 1, 15, 11, 0, 0),
                    'StorageClass': 'STANDARD'
                },
                {
                    'Key': 'document3.pdf',
                    'ETag': '"ghi789"',
                    'Size': 3072,
                    'LastModified': datetime(2025, 1, 15, 12, 0, 0),
                    'StorageClass': 'STANDARD'
                }
            ],
            'IsTruncated': False
        }

        # Create agent with file pattern filter
        agent = S3BucketMonitorAgent(
            agent_id=test_job.id,
            config={
                'bucket_name': 'test-bucket',
                'aws_access_key_id': 'AKIAIOSFODNN7EXAMPLE',
                'aws_secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                'region': 'us-east-1',
                'file_pattern': '*.pdf'
            },
            user_id=test_job.user_id,
            db_session=db.session
        )

        events = agent.fetch()

        # Should only have events for PDF files
        assert len(events) == 2
        assert all('.pdf' in e.payload['key'] for e in events)

    @patch('boto3.client')
    def test_exclude_pattern_filter(self, mock_boto_client, test_job):
        """Test excluding files by pattern"""
        # Mock S3 client
        mock_s3 = Mock()
        mock_boto_client.return_value = mock_s3

        # Mock response with temporary files
        mock_s3.list_objects_v2.return_value = {
            'Contents': [
                {
                    'Key': 'document.txt',
                    'ETag': '"abc123"',
                    'Size': 1024,
                    'LastModified': datetime(2025, 1, 15, 10, 30, 0),
                    'StorageClass': 'STANDARD'
                },
                {
                    'Key': 'temp.tmp',
                    'ETag': '"def456"',
                    'Size': 2048,
                    'LastModified': datetime(2025, 1, 15, 11, 0, 0),
                    'StorageClass': 'STANDARD'
                }
            ],
            'IsTruncated': False
        }

        # Create agent with exclude pattern
        agent = S3BucketMonitorAgent(
            agent_id=test_job.id,
            config={
                'bucket_name': 'test-bucket',
                'aws_access_key_id': 'AKIAIOSFODNN7EXAMPLE',
                'aws_secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                'region': 'us-east-1',
                'exclude_pattern': '*.tmp'
            },
            user_id=test_job.user_id,
            db_session=db.session
        )

        events = agent.fetch()

        # Should only have event for non-tmp file
        assert len(events) == 1
        assert events[0].payload['key'] == 'document.txt'

    @patch('boto3.client')
    def test_combined_filters(self, mock_boto_client, test_job):
        """Test combining prefix, pattern, and exclude filters"""
        # Mock S3 client
        mock_s3 = Mock()
        mock_boto_client.return_value = mock_s3

        # Mock response
        mock_s3.list_objects_v2.return_value = {
            'Contents': [
                {
                    'Key': 'uploads/report.pdf',
                    'ETag': '"abc123"',
                    'Size': 1024,
                    'LastModified': datetime(2025, 1, 15, 10, 30, 0),
                    'StorageClass': 'STANDARD'
                },
                {
                    'Key': 'uploads/temp.pdf',
                    'ETag': '"def456"',
                    'Size': 2048,
                    'LastModified': datetime(2025, 1, 15, 11, 0, 0),
                    'StorageClass': 'STANDARD'
                },
                {
                    'Key': 'uploads/data.txt',
                    'ETag': '"ghi789"',
                    'Size': 3072,
                    'LastModified': datetime(2025, 1, 15, 12, 0, 0),
                    'StorageClass': 'STANDARD'
                }
            ],
            'IsTruncated': False
        }

        # Create agent with combined filters
        # Note: Patterns are matched against the full S3 key path
        agent = S3BucketMonitorAgent(
            agent_id=test_job.id,
            config={
                'bucket_name': 'test-bucket',
                'aws_access_key_id': 'AKIAIOSFODNN7EXAMPLE',
                'aws_secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                'region': 'us-east-1',
                'prefix': 'uploads/',
                'file_pattern': '*.pdf',
                'exclude_pattern': '*temp.*'
            },
            user_id=test_job.user_id,
            db_session=db.session
        )

        events = agent.fetch()

        # Should only have event for report.pdf (temp.pdf excluded, data.txt filtered by pattern)
        assert len(events) == 1
        assert events[0].payload['key'] == 'uploads/report.pdf'


class TestS3BucketMonitorAgentToggles:
    """Tests for S3BucketMonitorAgent detection toggles"""

    @patch('boto3.client')
    def test_detect_creates_false(self, mock_boto_client, test_job):
        """Test disabling create detection"""
        # Mock S3 client
        mock_s3 = Mock()
        mock_boto_client.return_value = mock_s3

        # Mock response
        mock_s3.list_objects_v2.return_value = {
            'Contents': [
                {
                    'Key': 'file1.txt',
                    'ETag': '"abc123"',
                    'Size': 1024,
                    'LastModified': datetime(2025, 1, 15, 10, 30, 0),
                    'StorageClass': 'STANDARD'
                }
            ],
            'IsTruncated': False
        }

        # Create agent with create detection disabled
        agent = S3BucketMonitorAgent(
            agent_id=test_job.id,
            config={
                'bucket_name': 'test-bucket',
                'aws_access_key_id': 'AKIAIOSFODNN7EXAMPLE',
                'aws_secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                'region': 'us-east-1',
                'detect_creates': False,
                'detect_modifies': True,
                'detect_deletes': True
            },
            user_id=test_job.user_id,
            db_session=db.session
        )

        events = agent.fetch()

        # Should have no events (new files not detected)
        assert len(events) == 0

    @patch('boto3.client')
    def test_detect_modifies_false(self, mock_boto_client, test_job):
        """Test disabling modify detection"""
        # Mock S3 client
        mock_s3 = Mock()
        mock_boto_client.return_value = mock_s3

        # First call - original file
        mock_s3.list_objects_v2.side_effect = [
            {
                'Contents': [
                    {
                        'Key': 'file1.txt',
                        'ETag': '"abc123"',
                        'Size': 1024,
                        'LastModified': datetime(2025, 1, 15, 10, 30, 0),
                        'StorageClass': 'STANDARD'
                    }
                ],
                'IsTruncated': False
            },
            # Second call - modified file
            {
                'Contents': [
                    {
                        'Key': 'file1.txt',
                        'ETag': '"xyz789"',
                        'Size': 2048,
                        'LastModified': datetime(2025, 1, 15, 12, 0, 0),
                        'StorageClass': 'STANDARD'
                    }
                ],
                'IsTruncated': False
            }
        ]

        # Create agent with modify detection disabled
        agent = S3BucketMonitorAgent(
            agent_id=test_job.id,
            config={
                'bucket_name': 'test-bucket',
                'aws_access_key_id': 'AKIAIOSFODNN7EXAMPLE',
                'aws_secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                'region': 'us-east-1',
                'detect_creates': True,
                'detect_modifies': False,
                'detect_deletes': True
            },
            user_id=test_job.user_id,
            db_session=db.session
        )

        # First fetch
        events = agent.fetch()
        assert len(events) == 1
        assert events[0].payload['event_type'] == 'created'

        # Second fetch - modification should not be detected
        events = agent.fetch()
        assert len(events) == 0

    @patch('boto3.client')
    def test_detect_deletes_false(self, mock_boto_client, test_job):
        """Test disabling delete detection"""
        # Mock S3 client
        mock_s3 = Mock()
        mock_boto_client.return_value = mock_s3

        # First call - two files
        mock_s3.list_objects_v2.side_effect = [
            {
                'Contents': [
                    {
                        'Key': 'file1.txt',
                        'ETag': '"abc123"',
                        'Size': 1024,
                        'LastModified': datetime(2025, 1, 15, 10, 30, 0),
                        'StorageClass': 'STANDARD'
                    },
                    {
                        'Key': 'file2.txt',
                        'ETag': '"def456"',
                        'Size': 2048,
                        'LastModified': datetime(2025, 1, 15, 11, 0, 0),
                        'StorageClass': 'STANDARD'
                    }
                ],
                'IsTruncated': False
            },
            # Second call - one file deleted
            {
                'Contents': [
                    {
                        'Key': 'file1.txt',
                        'ETag': '"abc123"',
                        'Size': 1024,
                        'LastModified': datetime(2025, 1, 15, 10, 30, 0),
                        'StorageClass': 'STANDARD'
                    }
                ],
                'IsTruncated': False
            }
        ]

        # Create agent with delete detection disabled
        agent = S3BucketMonitorAgent(
            agent_id=test_job.id,
            config={
                'bucket_name': 'test-bucket',
                'aws_access_key_id': 'AKIAIOSFODNN7EXAMPLE',
                'aws_secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                'region': 'us-east-1',
                'detect_creates': True,
                'detect_modifies': True,
                'detect_deletes': False
            },
            user_id=test_job.user_id,
            db_session=db.session
        )

        # First fetch
        events = agent.fetch()
        assert len(events) == 2

        # Second fetch - deletion should not be detected
        events = agent.fetch()
        assert len(events) == 0


class TestS3BucketMonitorAgentErrors:
    """Tests for S3BucketMonitorAgent error handling"""

    @patch('boto3.client')
    def test_no_credentials_error(self, mock_boto_client, test_job):
        """Test handling of missing AWS credentials"""
        from botocore.exceptions import NoCredentialsError

        # Mock S3 client to raise NoCredentialsError
        mock_s3 = Mock()
        mock_boto_client.return_value = mock_s3
        mock_s3.list_objects_v2.side_effect = NoCredentialsError()

        # Create agent
        agent = S3BucketMonitorAgent(
            agent_id=test_job.id,
            config={
                'bucket_name': 'test-bucket',
                'aws_access_key_id': 'AKIAIOSFODNN7EXAMPLE',
                'aws_secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                'region': 'us-east-1'
            },
            user_id=test_job.user_id,
            db_session=db.session
        )

        # Fetch should return empty list and not raise exception
        events = agent.fetch()
        assert events == []

    @patch('boto3.client')
    def test_no_such_bucket_error(self, mock_boto_client, test_job):
        """Test handling of non-existent bucket"""
        from botocore.exceptions import ClientError

        # Mock S3 client to raise NoSuchBucket error
        mock_s3 = Mock()
        mock_boto_client.return_value = mock_s3
        error_response = {
            'Error': {
                'Code': 'NoSuchBucket',
                'Message': 'The specified bucket does not exist'
            }
        }
        mock_s3.list_objects_v2.side_effect = ClientError(error_response, 'ListObjectsV2')

        # Create agent
        agent = S3BucketMonitorAgent(
            agent_id=test_job.id,
            config={
                'bucket_name': 'nonexistent-bucket',
                'aws_access_key_id': 'AKIAIOSFODNN7EXAMPLE',
                'aws_secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                'region': 'us-east-1'
            },
            user_id=test_job.user_id,
            db_session=db.session
        )

        # Fetch should return empty list and not raise exception
        events = agent.fetch()
        assert events == []

    @patch('boto3.client')
    def test_access_denied_error(self, mock_boto_client, test_job):
        """Test handling of access denied errors"""
        from botocore.exceptions import ClientError

        # Mock S3 client to raise AccessDenied error
        mock_s3 = Mock()
        mock_boto_client.return_value = mock_s3
        error_response = {
            'Error': {
                'Code': 'AccessDenied',
                'Message': 'Access Denied'
            }
        }
        mock_s3.list_objects_v2.side_effect = ClientError(error_response, 'ListObjectsV2')

        # Create agent
        agent = S3BucketMonitorAgent(
            agent_id=test_job.id,
            config={
                'bucket_name': 'restricted-bucket',
                'aws_access_key_id': 'AKIAIOSFODNN7EXAMPLE',
                'aws_secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                'region': 'us-east-1'
            },
            user_id=test_job.user_id,
            db_session=db.session
        )

        # Fetch should return empty list and not raise exception
        events = agent.fetch()
        assert events == []

    @patch('boto3.client')
    def test_endpoint_connection_error(self, mock_boto_client, test_job):
        """Test handling of endpoint connection errors"""
        from botocore.exceptions import EndpointConnectionError

        # Mock S3 client to raise EndpointConnectionError
        mock_s3 = Mock()
        mock_boto_client.return_value = mock_s3
        mock_s3.list_objects_v2.side_effect = EndpointConnectionError(endpoint_url='https://s3.us-east-1.amazonaws.com')

        # Create agent
        agent = S3BucketMonitorAgent(
            agent_id=test_job.id,
            config={
                'bucket_name': 'test-bucket',
                'aws_access_key_id': 'AKIAIOSFODNN7EXAMPLE',
                'aws_secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                'region': 'us-east-1'
            },
            user_id=test_job.user_id,
            db_session=db.session
        )

        # Fetch should return empty list and not raise exception
        events = agent.fetch()
        assert events == []

    @patch('boto3.client')
    def test_generic_client_error(self, mock_boto_client, test_job):
        """Test handling of generic client errors"""
        from botocore.exceptions import ClientError

        # Mock S3 client to raise generic error
        mock_s3 = Mock()
        mock_boto_client.return_value = mock_s3
        error_response = {
            'Error': {
                'Code': 'InternalError',
                'Message': 'Internal server error'
            }
        }
        mock_s3.list_objects_v2.side_effect = ClientError(error_response, 'ListObjectsV2')

        # Create agent
        agent = S3BucketMonitorAgent(
            agent_id=test_job.id,
            config={
                'bucket_name': 'test-bucket',
                'aws_access_key_id': 'AKIAIOSFODNN7EXAMPLE',
                'aws_secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                'region': 'us-east-1'
            },
            user_id=test_job.user_id,
            db_session=db.session
        )

        # Fetch should return empty list and not raise exception
        events = agent.fetch()
        assert events == []


class TestS3BucketMonitorAgentConfigSchema:
    """Tests for S3BucketMonitorAgent configuration schema"""

    def test_get_config_schema(self):
        """Test that get_config_schema returns proper schema"""
        schema = S3BucketMonitorAgent.get_config_schema()

        # Check required fields
        assert 'required_fields' in schema
        assert 'bucket_name' in schema['required_fields']
        assert 'aws_access_key_id' in schema['required_fields']
        assert 'aws_secret_access_key' in schema['required_fields']
        assert 'region' in schema['required_fields']

        # Check optional fields
        assert 'optional_fields' in schema
        field_names = [f['name'] for f in schema['optional_fields']]
        assert 'prefix' in field_names
        assert 'max_keys' in field_names
        assert 'file_pattern' in field_names
        assert 'exclude_pattern' in field_names
        assert 'detect_creates' in field_names
        assert 'detect_modifies' in field_names
        assert 'detect_deletes' in field_names
        assert 'endpoint_url' in field_names
        assert 'use_ssl' in field_names
