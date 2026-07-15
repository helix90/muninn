"""
S3 Bucket Monitor Agent - Monitor AWS S3 buckets for file changes

This agent monitors AWS S3 buckets for file changes (create, modify, delete) by
polling the bucket and comparing object ETags with stored state.
"""

import json
import logging
from datetime import datetime
from fnmatch import fnmatch
from typing import Any, Dict, List, Optional

from jinja2 import Environment, BaseLoader, TemplateError

from app.agents.base import SourceAgent
from app.agents.registry import register_agent
from app.models import Event

logger = logging.getLogger(__name__)


@register_agent
class S3BucketMonitorAgent(SourceAgent):
    """
    Source agent that monitors AWS S3 buckets for file changes.

    Polls S3 buckets and detects file creates, modifications, and deletions
    by comparing ETags with previously stored state.

    Configuration:
        bucket_name (str): Name of the S3 bucket to monitor
        aws_access_key_id (str): AWS access key (supports credential templating)
        aws_secret_access_key (str): AWS secret key (supports credential templating)
        region (str): AWS region (e.g., us-east-1)
        prefix (str): Optional folder path filter (e.g., "logs/")
        max_keys (int): Pagination size (1-1000, default: 1000)
        file_pattern (str): Optional glob pattern filter (e.g., "*.pdf")
        exclude_pattern (str): Optional glob exclusion pattern (e.g., "*.tmp")
        detect_creates (bool): Detect new files (default: true)
        detect_modifies (bool): Detect modified files (default: true)
        detect_deletes (bool): Detect deleted files (default: true)
        endpoint_url (str): Optional custom endpoint for S3-compatible services
        use_ssl (bool): Use HTTPS connection (default: true)
    """

    agent_type = 's3_bucket_monitor_agent'
    agent_category = 'source'

    def __init__(self, agent_id: int, config: Dict[str, Any], user_id: int, db_session=None):
        """Initialize the S3 bucket monitor agent."""
        # Set instance variables BEFORE calling super().__init__()
        # because BaseAgent.__init__() calls validate_config() which needs these
        self.bucket_name = config.get('bucket_name', '')
        self.aws_access_key_id = config.get('aws_access_key_id', '')
        self.aws_secret_access_key = config.get('aws_secret_access_key', '')
        self.region = config.get('region', 'us-east-1')
        self.prefix = config.get('prefix', '')
        self.max_keys = int(config.get('max_keys', 1000))
        self.file_pattern = config.get('file_pattern', '')
        self.exclude_pattern = config.get('exclude_pattern', '')
        self.detect_creates = config.get('detect_creates', True)
        self.detect_modifies = config.get('detect_modifies', True)
        self.detect_deletes = config.get('detect_deletes', True)
        self.endpoint_url = config.get('endpoint_url', '')
        self.use_ssl = config.get('use_ssl', True)

        # Now call parent __init__ which will call validate_config()
        super().__init__(agent_id, config, user_id, db_session)

    def validate_config(self) -> None:
        """
        Validate agent configuration.

        Raises:
            ValueError: If configuration is invalid
        """
        # Call parent validation
        super().validate_config()

        # Check required fields
        if not self.bucket_name:
            raise ValueError("bucket_name is required")

        if not self.aws_access_key_id:
            raise ValueError("aws_access_key_id is required")

        if not self.aws_secret_access_key:
            raise ValueError("aws_secret_access_key is required")

        if not self.region:
            raise ValueError("region is required")

        # Validate bucket name format (basic check)
        if not 3 <= len(self.bucket_name) <= 63:
            raise ValueError("bucket_name must be between 3 and 63 characters")

        # Validate max_keys
        if not 1 <= self.max_keys <= 1000:
            raise ValueError("max_keys must be between 1 and 1000")

        # Validate boolean flags
        if not isinstance(self.detect_creates, bool):
            raise ValueError("detect_creates must be a boolean")

        if not isinstance(self.detect_modifies, bool):
            raise ValueError("detect_modifies must be a boolean")

        if not isinstance(self.detect_deletes, bool):
            raise ValueError("detect_deletes must be a boolean")

        if not isinstance(self.use_ssl, bool):
            raise ValueError("use_ssl must be a boolean")

        # At least one detection type must be enabled
        if not (self.detect_creates or self.detect_modifies or self.detect_deletes):
            raise ValueError("At least one detection type (creates/modifies/deletes) must be enabled")

    def fetch(self) -> List[Event]:
        """
        Poll S3 bucket and return events for detected changes.

        Returns:
            List of events containing file change information
        """
        try:
            # Get S3 client
            s3_client = self._get_s3_client()

            # List current bucket objects
            current_state = self._list_bucket_objects(s3_client)

            # Get stored state from memory
            stored_state = self.memory.get('object_state', {})

            # Detect changes
            changes = self._detect_changes(stored_state, current_state)

            # Create events for changes
            events = self._create_change_events(changes)

            # Update stored state in memory
            self.memory.set('object_state', current_state)
            self.memory.set('last_sync_at', datetime.utcnow().isoformat())

            if events:
                self.log(f'Detected {len(events)} change(s) in bucket {self.bucket_name}', data={
                    'changes': len(events),
                    'bucket': self.bucket_name
                })

            return events

        except Exception as e:
            # Import boto3 exceptions within the except block to handle import errors
            try:
                from botocore.exceptions import NoCredentialsError, ClientError, EndpointConnectionError

                if isinstance(e, NoCredentialsError):
                    self.log('AWS credentials not found or invalid', level='error')
                elif isinstance(e, ClientError):
                    error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                    error_msg = e.response.get('Error', {}).get('Message', str(e))

                    if error_code == 'NoSuchBucket':
                        self.log(f'Bucket not found: {self.bucket_name}', level='error')
                    elif error_code == 'AccessDenied':
                        self.log('Access denied - check IAM permissions', level='error', data={
                            'bucket': self.bucket_name,
                            'error': error_msg
                        })
                    else:
                        self.log(f'AWS client error ({error_code}): {error_msg}', level='error', data={
                            'bucket': self.bucket_name,
                            'error_code': error_code
                        })
                elif isinstance(e, EndpointConnectionError):
                    self.log('Cannot connect to S3 endpoint', level='error', data={
                        'endpoint': self.endpoint_url or f's3.{self.region}.amazonaws.com'
                    })
                else:
                    self.log(f'Unexpected error: {e}', level='error', data={'error': str(e)})
            except ImportError:
                # boto3 not installed
                self.log('boto3 library not installed - required for S3 monitoring', level='error')

            return []

    def _get_s3_client(self):
        """
        Create and return boto3 S3 client.

        Returns:
            boto3 S3 client instance

        Raises:
            ImportError: If boto3 is not installed
        """
        try:
            import boto3
        except ImportError:
            raise ImportError("boto3 is required for S3BucketMonitorAgent. Install with: pip install boto3")

        # Prepare client configuration
        client_config = {
            'aws_access_key_id': self.aws_access_key_id,
            'aws_secret_access_key': self.aws_secret_access_key,
            'region_name': self.region,
            'use_ssl': self.use_ssl
        }

        # Add endpoint URL if specified (for S3-compatible services)
        if self.endpoint_url:
            client_config['endpoint_url'] = self.endpoint_url

        return boto3.client('s3', **client_config)

    def _list_bucket_objects(self, s3_client) -> Dict[str, Dict[str, Any]]:
        """
        List all objects in the bucket with pagination.

        Args:
            s3_client: boto3 S3 client

        Returns:
            Dictionary mapping object keys to metadata
        """
        objects_state = {}
        continuation_token = None

        while True:
            # Prepare list parameters
            params = {
                'Bucket': self.bucket_name,
                'MaxKeys': self.max_keys
            }

            # Add prefix filter if specified
            if self.prefix:
                params['Prefix'] = self.prefix

            # Add continuation token for pagination
            if continuation_token:
                params['ContinuationToken'] = continuation_token

            # List objects
            response = s3_client.list_objects_v2(**params)

            # Process objects
            for obj in response.get('Contents', []):
                key = obj['Key']

                # Apply file pattern filters
                if self.file_pattern and not fnmatch(key, self.file_pattern):
                    continue

                if self.exclude_pattern and fnmatch(key, self.exclude_pattern):
                    continue

                # Store object metadata
                objects_state[key] = {
                    'etag': obj['ETag'],
                    'size': obj['Size'],
                    'last_modified': obj['LastModified'].isoformat(),
                    'storage_class': obj.get('StorageClass', 'STANDARD')
                }

            # Check if there are more objects to fetch
            if not response.get('IsTruncated', False):
                break

            continuation_token = response.get('NextContinuationToken')

        self.log(f'Listed {len(objects_state)} object(s) from bucket', level='debug', data={
            'bucket': self.bucket_name,
            'count': len(objects_state)
        })

        return objects_state

    def _detect_changes(self, stored_state: Dict[str, Dict], current_state: Dict[str, Dict]) -> List[Dict]:
        """
        Compare stored and current states to detect changes.

        Args:
            stored_state: Previously stored object state
            current_state: Current object state from S3

        Returns:
            List of change dictionaries
        """
        changes = []

        # Detect new and modified files
        for key, metadata in current_state.items():
            if key not in stored_state:
                # New file created
                if self.detect_creates:
                    changes.append({
                        'type': 'created',
                        'key': key,
                        'metadata': metadata
                    })
            elif metadata['etag'] != stored_state[key]['etag']:
                # File modified (ETag changed)
                if self.detect_modifies:
                    changes.append({
                        'type': 'modified',
                        'key': key,
                        'metadata': metadata,
                        'previous_metadata': stored_state[key]
                    })

        # Detect deleted files
        if self.detect_deletes:
            for key, metadata in stored_state.items():
                if key not in current_state:
                    changes.append({
                        'type': 'deleted',
                        'key': key,
                        'metadata': metadata
                    })

        return changes

    def _create_change_events(self, changes: List[Dict]) -> List[Event]:
        """
        Create Event objects for detected changes.

        Args:
            changes: List of change dictionaries

        Returns:
            List of Event objects
        """
        events = []
        sync_time = datetime.utcnow().isoformat()

        for change in changes:
            change_type = change['type']
            key = change['key']
            metadata = change['metadata']

            # Prepare event payload
            payload = {
                'event_type': change_type,
                'bucket': self.bucket_name,
                'key': key,
                'region': self.region
            }

            # Add metadata fields based on event type
            if change_type == 'created':
                payload['etag'] = metadata['etag']
                payload['size'] = metadata['size']
                payload['last_modified'] = metadata['last_modified']
                payload['storage_class'] = metadata['storage_class']

            elif change_type == 'modified':
                payload['etag'] = metadata['etag']
                payload['size'] = metadata['size']
                payload['last_modified'] = metadata['last_modified']
                payload['storage_class'] = metadata['storage_class']
                payload['previous_etag'] = change['previous_metadata']['etag']
                payload['previous_size'] = change['previous_metadata']['size']

            elif change_type == 'deleted':
                # For deleted files, use the stored metadata
                payload['deleted_etag'] = metadata['etag']
                payload['deleted_size'] = metadata['size']
                payload['deleted_last_modified'] = metadata['last_modified']
                payload['deleted_storage_class'] = metadata['storage_class']

            # Create event metadata
            event_metadata = {
                'sync_time': sync_time,
                'region': self.region
            }

            # Create and append event
            event = self.create_event(payload=payload, metadata=event_metadata)
            events.append(event)

            self.log(f'S3 {change_type}: {key}', level='debug', data={
                'event_type': change_type,
                'key': key,
                'bucket': self.bucket_name
            })

        return events

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """
        Get the configuration schema for this agent's configuration.

        Returns:
            Configuration schema dictionary
        """
        schema = super().get_config_schema()
        schema['required_fields'] = ['bucket_name', 'aws_access_key_id', 'aws_secret_access_key', 'region']
        schema['optional_fields'].extend([
            {
                'name': 'bucket_name',
                'type': 'text',
                'description': 'Name of the S3 bucket to monitor'
            },
            {
                'name': 'aws_access_key_id',
                'type': 'text',
                'description': 'AWS access key ID (supports credential templating: {{credential:aws_access_key}})'
            },
            {
                'name': 'aws_secret_access_key',
                'type': 'password',
                'description': 'AWS secret access key (supports credential templating: {{credential:aws_secret_key}})'
            },
            {
                'name': 'region',
                'type': 'text',
                'default': 'us-east-1',
                'description': 'AWS region (e.g., us-east-1, eu-west-1)'
            },
            {
                'name': 'prefix',
                'type': 'text',
                'default': '',
                'description': 'Optional folder path prefix filter (e.g., "logs/" to only monitor the logs folder)'
            },
            {
                'name': 'max_keys',
                'type': 'integer',
                'default': 1000,
                'description': 'Maximum number of keys to fetch per page (1-1000)'
            },
            {
                'name': 'file_pattern',
                'type': 'text',
                'default': '',
                'description': 'Optional glob pattern to match files (e.g., "*.pdf" for PDF files only)'
            },
            {
                'name': 'exclude_pattern',
                'type': 'text',
                'default': '',
                'description': 'Optional glob pattern to exclude files (e.g., "*.tmp" to ignore temporary files)'
            },
            {
                'name': 'detect_creates',
                'type': 'boolean',
                'default': True,
                'description': 'Detect new files being created'
            },
            {
                'name': 'detect_modifies',
                'type': 'boolean',
                'default': True,
                'description': 'Detect files being modified (ETag change)'
            },
            {
                'name': 'detect_deletes',
                'type': 'boolean',
                'default': True,
                'description': 'Detect files being deleted'
            },
            {
                'name': 'endpoint_url',
                'type': 'text',
                'default': '',
                'description': 'Custom endpoint URL for S3-compatible services (e.g., MinIO, DigitalOcean Spaces)'
            },
            {
                'name': 'use_ssl',
                'type': 'boolean',
                'default': True,
                'description': 'Use HTTPS connection to S3'
            }
        ])
        return schema

    def __repr__(self):
        """String representation of the agent."""
        return f'<S3BucketMonitorAgent {self.agent_id}: {self.bucket_name}>'
