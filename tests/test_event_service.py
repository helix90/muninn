"""
Tests for EventService query methods
"""

import pytest
from datetime import datetime, timedelta
from app.models import Event, Job, User
from app.services.event_service import EventService
from app.extensions import db


class TestEventServiceQueryMethods:
    """Test EventService query methods for event display"""

    def test_get_events_for_agent_basic(self, app, test_job, sample_events):
        """Test basic retrieval of events for an agent"""
        with app.app_context():
            service = EventService(db.session)
            events = service.get_events_for_agent(test_job.id)

            assert len(events) == 3
            assert all(e.agent_id == test_job.id for e in events)

    def test_get_events_for_agent_with_limit(self, app, test_job, sample_events):
        """Test get_events_for_agent with limit"""
        with app.app_context():
            service = EventService(db.session)
            events = service.get_events_for_agent(test_job.id, limit=2)

            assert len(events) == 2

    def test_get_events_for_agent_with_offset(self, app, test_job, sample_events):
        """Test get_events_for_agent with offset"""
        with app.app_context():
            service = EventService(db.session)
            events = service.get_events_for_agent(test_job.id, offset=1, limit=2)

            assert len(events) == 2

    def test_get_events_for_agent_date_filter(self, app, test_job):
        """Test get_events_for_agent with date filtering"""
        with app.app_context():
            # Create events with specific dates
            now = datetime.utcnow()
            yesterday = now - timedelta(days=1)
            tomorrow = now + timedelta(days=1)

            event1 = Event(
                agent_id=test_job.id,
                agent_type='test',
                user_id=test_job.user_id,
                payload={'date': 'yesterday'}
            )
            event1.created_at = yesterday

            event2 = Event(
                agent_id=test_job.id,
                agent_type='test',
                user_id=test_job.user_id,
                payload={'date': 'now'}
            )
            event2.created_at = now

            event3 = Event(
                agent_id=test_job.id,
                agent_type='test',
                user_id=test_job.user_id,
                payload={'date': 'tomorrow'}
            )
            event3.created_at = tomorrow

            db.session.add_all([event1, event2, event3])
            db.session.commit()

            service = EventService(db.session)

            # Test start_date filter
            events = service.get_events_for_agent(test_job.id, start_date=now)
            assert len(events) == 2

            # Test end_date filter
            events = service.get_events_for_agent(test_job.id, end_date=now)
            assert len(events) == 2

            # Test both filters
            events = service.get_events_for_agent(test_job.id, start_date=yesterday, end_date=now)
            assert len(events) == 2

    def test_get_events_for_agent_payload_search(self, app, test_job):
        """Test get_events_for_agent with payload search"""
        with app.app_context():
            event1 = Event(
                agent_id=test_job.id,
                agent_type='test',
                user_id=test_job.user_id,
                payload={'title': 'Python Tutorial'}
            )
            event2 = Event(
                agent_id=test_job.id,
                agent_type='test',
                user_id=test_job.user_id,
                payload={'title': 'JavaScript Guide'}
            )

            db.session.add_all([event1, event2])
            db.session.commit()

            service = EventService(db.session)

            # Search for Python
            events = service.get_events_for_agent(test_job.id, payload_search='Python')
            assert len(events) == 1
            assert 'Python' in str(events[0].payload)

    def test_count_events_for_agent(self, app, test_job, sample_events):
        """Test counting events for an agent"""
        with app.app_context():
            service = EventService(db.session)
            count = service.count_events_for_agent(test_job.id)

            assert count == 3

    def test_count_events_for_agent_with_filters(self, app, test_job):
        """Test counting events with filters"""
        with app.app_context():
            now = datetime.utcnow()
            yesterday = now - timedelta(days=1)

            event1 = Event(
                agent_id=test_job.id,
                agent_type='test',
                user_id=test_job.user_id,
                payload={'text': 'searchable'}
            )
            event1.created_at = yesterday

            event2 = Event(
                agent_id=test_job.id,
                agent_type='test',
                user_id=test_job.user_id,
                payload={'text': 'searchable'}
            )
            event2.created_at = now

            db.session.add_all([event1, event2])
            db.session.commit()

            service = EventService(db.session)

            # Count with date filter
            count = service.count_events_for_agent(test_job.id, start_date=now)
            assert count == 1

            # Count with payload search
            count = service.count_events_for_agent(test_job.id, payload_search='searchable')
            assert count == 2

    def test_get_all_events_basic(self, app, test_user, test_job, sample_events):
        """Test basic retrieval of all events for a user"""
        with app.app_context():
            service = EventService(db.session)
            events = service.get_all_events(test_user.id)

            assert len(events) == 3
            assert all(e.user_id == test_user.id for e in events)

    def test_get_all_events_with_agent_type_filter(self, app, test_user):
        """Test get_all_events with agent_type filter"""
        with app.app_context():
            # Create two jobs with different types
            job1 = Job(
                name='RSS Agent',
                job_type='rss_agent',
                config={},
                user_id=test_user.id
            )
            job2 = Job(
                name='Filter Agent',
                job_type='filter_agent',
                config={},
                user_id=test_user.id
            )
            db.session.add_all([job1, job2])
            db.session.commit()

            # Create events for each
            event1 = Event(
                agent_id=job1.id,
                agent_type='rss_agent',
                user_id=test_user.id,
                payload={}
            )
            event2 = Event(
                agent_id=job2.id,
                agent_type='filter_agent',
                user_id=test_user.id,
                payload={}
            )
            db.session.add_all([event1, event2])
            db.session.commit()

            service = EventService(db.session)

            # Filter by rss_agent
            events = service.get_all_events(test_user.id, agent_type='rss_agent')
            assert len(events) == 1
            assert events[0].agent_type == 'rss_agent'

    def test_get_all_events_with_agent_id_filter(self, app, test_user):
        """Test get_all_events with specific agent_id filter"""
        with app.app_context():
            # Create two jobs
            job1 = Job(name='Agent 1', job_type='rss_agent', config={}, user_id=test_user.id)
            job2 = Job(name='Agent 2', job_type='rss_agent', config={}, user_id=test_user.id)
            db.session.add_all([job1, job2])
            db.session.commit()

            # Create events for each
            event1 = Event(agent_id=job1.id, agent_type='rss_agent', user_id=test_user.id, payload={})
            event2 = Event(agent_id=job2.id, agent_type='rss_agent', user_id=test_user.id, payload={})
            db.session.add_all([event1, event2])
            db.session.commit()

            service = EventService(db.session)

            # Filter by specific agent
            events = service.get_all_events(test_user.id, agent_id=job1.id)
            assert len(events) == 1
            assert events[0].agent_id == job1.id

    def test_get_all_events_user_isolation(self, app):
        """Test that get_all_events only returns events for the specified user"""
        with app.app_context():
            # Create two users
            user1 = User(username='user1', email='user1@test.com', password='password123')
            user2 = User(username='user2', email='user2@test.com', password='password123')
            db.session.add_all([user1, user2])
            db.session.commit()

            # Create jobs for each
            job1 = Job(name='Job1', job_type='rss_agent', config={}, user_id=user1.id)
            job2 = Job(name='Job2', job_type='rss_agent', config={}, user_id=user2.id)
            db.session.add_all([job1, job2])
            db.session.commit()

            # Create events for each
            event1 = Event(agent_id=job1.id, agent_type='rss_agent', user_id=user1.id, payload={})
            event2 = Event(agent_id=job2.id, agent_type='rss_agent', user_id=user2.id, payload={})
            db.session.add_all([event1, event2])
            db.session.commit()

            service = EventService(db.session)

            # User 1 should only see their events
            events = service.get_all_events(user1.id)
            assert len(events) == 1
            assert events[0].user_id == user1.id

            # User 2 should only see their events
            events = service.get_all_events(user2.id)
            assert len(events) == 1
            assert events[0].user_id == user2.id

    def test_count_all_events(self, app, test_user, test_job, sample_events):
        """Test counting all events for a user"""
        with app.app_context():
            service = EventService(db.session)
            count = service.count_all_events(test_user.id)

            assert count == 3

    def test_count_all_events_with_filters(self, app, test_user):
        """Test counting all events with various filters"""
        with app.app_context():
            # Create jobs with different types
            job1 = Job(name='Job1', job_type='rss_agent', config={}, user_id=test_user.id)
            job2 = Job(name='Job2', job_type='filter_agent', config={}, user_id=test_user.id)
            db.session.add_all([job1, job2])
            db.session.commit()

            now = datetime.utcnow()
            yesterday = now - timedelta(days=1)

            # Create events
            event1 = Event(
                agent_id=job1.id,
                agent_type='rss_agent',
                user_id=test_user.id,
                payload={'text': 'test'}
            )
            event1.created_at = yesterday

            event2 = Event(
                agent_id=job2.id,
                agent_type='filter_agent',
                user_id=test_user.id,
                payload={'text': 'test'}
            )
            event2.created_at = now

            db.session.add_all([event1, event2])
            db.session.commit()

            service = EventService(db.session)

            # Count with agent_type filter
            count = service.count_all_events(test_user.id, agent_type='rss_agent')
            assert count == 1

            # Count with date filter
            count = service.count_all_events(test_user.id, start_date=now)
            assert count == 1

            # Count with payload search
            count = service.count_all_events(test_user.id, payload_search='test')
            assert count == 2

    def test_events_ordered_by_created_at_desc(self, app, test_job):
        """Test that events are returned in descending order by created_at"""
        with app.app_context():
            now = datetime.utcnow()

            # Create events with different timestamps
            event1 = Event(
                agent_id=test_job.id,
                agent_type='test',
                user_id=test_job.user_id,
                payload={'order': 1}
            )
            event1.created_at = now - timedelta(hours=2)

            event2 = Event(
                agent_id=test_job.id,
                agent_type='test',
                user_id=test_job.user_id,
                payload={'order': 2}
            )
            event2.created_at = now - timedelta(hours=1)

            event3 = Event(
                agent_id=test_job.id,
                agent_type='test',
                user_id=test_job.user_id,
                payload={'order': 3}
            )
            event3.created_at = now

            db.session.add_all([event1, event2, event3])
            db.session.commit()

            service = EventService(db.session)
            events = service.get_events_for_agent(test_job.id)

            # Should be in descending order (newest first)
            assert events[0].payload['order'] == 3
            assert events[1].payload['order'] == 2
            assert events[2].payload['order'] == 1
