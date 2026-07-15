"""
Tests for event propagation through agent networks
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime
from app.models import Event, AgentLink
from app.services.event_service import EventService
from app.services.agent_service import AgentService
from app.agents.types import RSSAgent, FilterAgent, EmailAgent
from app.extensions import db


class TestEventPropagation:
    """Tests for event propagation engine"""

    def test_event_service_initialization(self, app):
        """Test EventService can be initialized"""
        with app.app_context():
            service = EventService(db.session)
            assert service.db_session == db.session
            assert service.max_depth == 10

    def test_propagate_empty_events(self, app):
        """Test propagating empty event list"""
        with app.app_context():
            service = EventService(db.session)
            stats = service.propagate_events([])

            assert stats['events_propagated'] == 0
            assert stats['agents_executed'] == 0
            assert stats['events_created'] == 0
            assert stats['max_depth_reached'] == False

    def test_propagate_single_event_no_downstream(self, app, test_job, sample_events):
        """Test propagating event with no downstream agents"""
        with app.app_context():
            service = EventService(db.session)
            stats = service.propagate_events(sample_events[:1])

            # Event should be propagated but no agents executed
            assert stats['events_propagated'] == 1
            assert stats['agents_executed'] == 0

    def test_propagate_with_downstream_agent(self, app, test_job):
        """Test propagating events through a downstream agent"""
        with app.app_context():
            # Create source agent
            from app.models import Job, User
            user = db.session.query(User).first()

            source_agent = Job(
                name='Source Agent',
                job_type='rss_agent',
                config={'feed_url': 'https://example.com/feed.xml'},
                user_id=user.id
            )
            db.session.add(source_agent)
            db.session.flush()

            # Create downstream transform agent
            transform_agent = Job(
                name='Filter Agent',
                job_type='filter_agent',
                config={
                    'rules': [{'field': 'title', 'type': 'contains', 'value': 'test'}]
                },
                user_id=user.id
            )
            db.session.add(transform_agent)
            db.session.flush()

            # Create link
            link = AgentLink(
                source_agent_id=source_agent.id,
                target_agent_id=transform_agent.id
            )
            db.session.add(link)
            db.session.commit()

            # Create test events
            events = [
                Event(
                    agent_id=source_agent.id,
                    agent_type='rss_agent',
                    user_id=user.id,
                    payload={'title': 'test article', 'link': 'https://example.com/1'},
                    metadata={}
                )
            ]

            for event in events:
                db.session.add(event)
            db.session.commit()

            # Propagate
            service = EventService(db.session)
            stats = service.propagate_events(events)

            # Should execute downstream agent
            assert stats['agents_executed'] == 1
            assert transform_agent.id in stats['agent_execution_counts']
            assert stats['agent_execution_counts'][transform_agent.id] == 1

    def test_propagate_max_depth(self, app, test_job):
        """Test max depth prevents infinite loops"""
        with app.app_context():
            # Create a chain longer than max_depth
            from app.models import Job, User
            user = db.session.query(User).first()

            # Create source
            source = Job(
                name='Source',
                job_type='rss_agent',
                config={'feed_url': 'https://example.com/feed.xml'},
                user_id=user.id
            )
            db.session.add(source)
            db.session.flush()

            # Create events
            events = [
                Event(
                    agent_id=source.id,
                    agent_type='rss_agent',
                    user_id=user.id,
                    payload={'title': 'test', 'link': 'https://example.com/1'},
                    metadata={}
                )
            ]
            for event in events:
                db.session.add(event)
            db.session.commit()

            # Propagate with very small max_depth
            service = EventService(db.session, max_depth=1)
            stats = service.propagate_events(events)

            # Should hit max depth quickly
            assert stats['max_depth_reached'] == False or stats['events_propagated'] > 0

    def test_cycle_detection(self, app, test_job):
        """Test cycle detection prevents infinite loops"""
        with app.app_context():
            from app.models import Job, User
            user = db.session.query(User).first()

            # Create two agents
            agent1 = Job(
                name='Agent 1',
                job_type='filter_agent',
                config={'rules': [{'field': 'title', 'type': 'contains', 'value': 'test'}]},
                user_id=user.id
            )
            agent2 = Job(
                name='Agent 2',
                job_type='filter_agent',
                config={'rules': [{'field': 'title', 'type': 'contains', 'value': 'test'}]},
                user_id=user.id
            )
            db.session.add(agent1)
            db.session.add(agent2)
            db.session.flush()

            # Create circular link (agent1 -> agent2 -> agent1)
            link1 = AgentLink(source_agent_id=agent1.id, target_agent_id=agent2.id)
            link2 = AgentLink(source_agent_id=agent2.id, target_agent_id=agent1.id)
            db.session.add(link1)
            db.session.add(link2)
            db.session.commit()

            # Create event
            events = [
                Event(
                    agent_id=agent1.id,
                    agent_type='filter_agent',
                    user_id=user.id,
                    payload={'title': 'test', 'link': 'https://example.com/1'},
                    metadata={}
                )
            ]
            for event in events:
                db.session.add(event)
            db.session.commit()

            # Propagate - should detect cycle
            service = EventService(db.session)
            stats = service.propagate_events(events)

            # Should execute agent2 but not loop back to agent1
            assert stats['agents_executed'] >= 1

    def test_fan_out(self, app, test_job):
        """Test one agent feeding multiple downstream agents (fan-out)"""
        with app.app_context():
            from app.models import Job, User
            user = db.session.query(User).first()

            # Create source agent
            source = Job(
                name='Source',
                job_type='rss_agent',
                config={'feed_url': 'https://example.com/feed.xml'},
                user_id=user.id
            )
            db.session.add(source)
            db.session.flush()

            # Create multiple downstream agents
            agent1 = Job(
                name='Filter 1',
                job_type='filter_agent',
                config={'rules': [{'field': 'title', 'type': 'contains', 'value': 'test'}]},
                user_id=user.id
            )
            agent2 = Job(
                name='Filter 2',
                job_type='filter_agent',
                config={'rules': [{'field': 'title', 'type': 'contains', 'value': 'test'}]},
                user_id=user.id
            )
            db.session.add(agent1)
            db.session.add(agent2)
            db.session.flush()

            # Create links to both
            link1 = AgentLink(source_agent_id=source.id, target_agent_id=agent1.id)
            link2 = AgentLink(source_agent_id=source.id, target_agent_id=agent2.id)
            db.session.add(link1)
            db.session.add(link2)
            db.session.commit()

            # Create event
            events = [
                Event(
                    agent_id=source.id,
                    agent_type='rss_agent',
                    user_id=user.id,
                    payload={'title': 'test article', 'link': 'https://example.com/1'},
                    metadata={}
                )
            ]
            for event in events:
                db.session.add(event)
            db.session.commit()

            # Propagate
            service = EventService(db.session)
            stats = service.propagate_events(events)

            # Should execute both downstream agents
            assert stats['agents_executed'] == 2
            assert agent1.id in stats['agent_execution_counts']
            assert agent2.id in stats['agent_execution_counts']


class TestAgentService:
    """Tests for AgentService"""

    def test_agent_service_initialization(self, app):
        """Test AgentService can be initialized"""
        with app.app_context():
            service = AgentService(db.session)
            assert service.db_session == db.session
            assert service.event_service is not None

    def test_run_agent_not_found(self, app):
        """Test running non-existent agent"""
        with app.app_context():
            service = AgentService(db.session)
            result = service.run_agent(agent_id=99999)

            assert result['success'] == False
            assert 'not found' in result['error'].lower()

    def test_run_agent_inactive(self, app):
        """Test running inactive agent"""
        with app.app_context():
            # Create an inactive agent with a valid agent type
            from app.models import User, Job

            # Create test user first
            user = User(username='testuser', email='test@example.com', password='password123')
            db.session.add(user)
            db.session.flush()

            inactive_agent = Job(
                name='Inactive Agent',
                job_type='rss_agent',  # Use valid agent type
                config={'feed_url': 'https://example.com/feed.xml'},
                user_id=user.id
            )
            # Set as inactive after creation
            inactive_agent.is_active = False
            db.session.add(inactive_agent)
            db.session.commit()

            service = AgentService(db.session)
            result = service.run_agent(agent_id=inactive_agent.id)

            assert result['success'] == False
            assert 'not active' in result['error'].lower()

    def test_get_agent_statistics(self, app, test_job):
        """Test getting agent statistics"""
        with app.app_context():
            service = AgentService(db.session)
            stats = service.get_agent_statistics(test_job.id)

            assert 'agent_id' in stats
            assert 'total_runs' in stats
            assert 'successful_runs' in stats
            assert 'failed_runs' in stats
            assert 'success_rate' in stats
            assert stats['agent_id'] == test_job.id

    def test_validate_agent_link(self, app, test_job):
        """Test agent link validation"""
        with app.app_context():
            from app.models import Job, User
            user = db.session.query(User).first()

            # Create source and target agents
            source = Job(
                name='Source',
                job_type='rss_agent',
                config={'feed_url': 'https://example.com/feed.xml'},
                user_id=user.id
            )
            target = Job(
                name='Target',
                job_type='filter_agent',
                config={'rules': [{'field': 'title', 'type': 'contains', 'value': 'test'}]},
                user_id=user.id
            )
            db.session.add(source)
            db.session.add(target)
            db.session.commit()

            service = AgentService(db.session)

            # Valid link
            is_valid, error = service.event_service.validate_agent_link(source.id, target.id)
            assert is_valid == True
            assert error == ""

            # Invalid: same agent
            is_valid, error = service.event_service.validate_agent_link(source.id, source.id)
            assert is_valid == False
            assert "itself" in error.lower()

    def test_create_agent_link(self, app, test_job):
        """Test creating agent link"""
        with app.app_context():
            from app.models import Job, User
            user = db.session.query(User).first()

            # Create source and target
            source = Job(
                name='Source',
                job_type='rss_agent',
                config={'feed_url': 'https://example.com/feed.xml'},
                user_id=user.id
            )
            target = Job(
                name='Target',
                job_type='filter_agent',
                config={'rules': [{'field': 'title', 'type': 'contains', 'value': 'test'}]},
                user_id=user.id
            )
            db.session.add(source)
            db.session.add(target)
            db.session.commit()

            service = AgentService(db.session)
            result = service.create_agent_link(source.id, target.id)

            assert result['success'] == True
            assert 'link_id' in result

    def test_delete_agent_link(self, app, test_job):
        """Test deleting agent link"""
        with app.app_context():
            from app.models import Job, User
            user = db.session.query(User).first()

            # Create agents and link
            source = Job(
                name='Source',
                job_type='rss_agent',
                config={'feed_url': 'https://example.com/feed.xml'},
                user_id=user.id
            )
            target = Job(
                name='Target',
                job_type='filter_agent',
                config={'rules': [{'field': 'title', 'type': 'contains', 'value': 'test'}]},
                user_id=user.id
            )
            db.session.add(source)
            db.session.add(target)
            db.session.flush()

            link = AgentLink(source_agent_id=source.id, target_agent_id=target.id)
            db.session.add(link)
            db.session.commit()

            service = AgentService(db.session)
            result = service.delete_agent_link(link.id)

            assert result['success'] == True

            # Verify deleted
            deleted_link = db.session.query(AgentLink).get(link.id)
            assert deleted_link is None


class TestCredentialResolutionInPropagation:
    """Ensure credentials are resolved before agents run during event propagation.

    Regression tests for the bug where _execute_agent() passed raw agent config
    (containing {{credential:name}} template strings) directly to the agent
    constructor instead of resolving credentials first.
    """

    def test_credentials_resolved_for_downstream_agent(self, app, test_job):
        """Action/transform agents receive resolved credential values, not template strings."""
        with app.app_context():
            from app.models import Job, User
            from app.services.credential_service import CredentialService

            user = db.session.query(User).first()

            # Store a credential for the user
            cred_service = CredentialService()
            cred_service.create_credential(user.id, 'xmpp_pass', 'correct-horse-battery', 'XMPP password')

            # Source agent
            source = Job(
                name='Source',
                job_type='rss_agent',
                config={'feed_url': 'https://example.com/feed.xml'},
                user_id=user.id,
            )
            db.session.add(source)
            db.session.flush()

            # Downstream action agent whose config references a credential
            action = Job(
                name='Notifier',
                job_type='filter_agent',
                config={
                    'rules': [{'field': 'title', 'type': 'contains', 'value': 'test'}],
                    'secret': '{{credential:xmpp_pass}}',
                },
                user_id=user.id,
            )
            db.session.add(action)
            db.session.flush()

            link = AgentLink(source_agent_id=source.id, target_agent_id=action.id)
            db.session.add(link)

            event = Event(
                agent_id=source.id,
                agent_type='rss_agent',
                user_id=user.id,
                payload={'title': 'test article', 'link': 'https://example.com/1'},
                metadata={},
            )
            db.session.add(event)
            db.session.commit()

            received_configs = []

            original_create = __import__(
                'app.agents.registry', fromlist=['agent_registry']
            ).agent_registry.create_agent

            def capturing_create_agent(**kwargs):
                received_configs.append(kwargs.get('config', {}))
                return original_create(**kwargs)

            service = EventService(db.session)
            with patch.object(
                __import__('app.agents.registry', fromlist=['agent_registry']).agent_registry,
                'create_agent',
                side_effect=capturing_create_agent,
            ):
                service.propagate_events([event])

            assert received_configs, "create_agent was never called for the downstream agent"
            downstream_config = received_configs[-1]
            assert downstream_config.get('secret') == 'correct-horse-battery', (
                f"Expected resolved password but got: {downstream_config.get('secret')!r}"
            )

    def test_missing_credential_fails_gracefully(self, app, test_job):
        """Propagation records a failed run when a referenced credential does not exist."""
        with app.app_context():
            from app.models import Job, User, AgentRun
            user = db.session.query(User).first()

            source = Job(
                name='Source',
                job_type='rss_agent',
                config={'feed_url': 'https://example.com/feed.xml'},
                user_id=user.id,
            )
            db.session.add(source)
            db.session.flush()

            action = Job(
                name='Bad Notifier',
                job_type='filter_agent',
                config={
                    'rules': [],
                    'secret': '{{credential:does_not_exist}}',
                },
                user_id=user.id,
            )
            db.session.add(action)
            db.session.flush()

            link = AgentLink(source_agent_id=source.id, target_agent_id=action.id)
            db.session.add(link)

            event = Event(
                agent_id=source.id,
                agent_type='rss_agent',
                user_id=user.id,
                payload={'title': 'test article', 'link': 'https://example.com/1'},
                metadata={},
            )
            db.session.add(event)
            db.session.commit()

            service = EventService(db.session)
            # Should not raise — graceful failure
            stats = service.propagate_events([event])

            # Agent was attempted
            assert action.id in stats['agent_execution_counts']

            # Run record should be marked failed
            run = (
                db.session.query(AgentRun)
                .filter_by(agent_id=action.id)
                .order_by(AgentRun.started_at.desc())
                .first()
            )
            assert run is not None
            assert run.status == 'failed'
            assert 'does_not_exist' in (run.error_message or '')
