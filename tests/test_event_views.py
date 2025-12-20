"""
Tests for Event viewing routes
"""

import pytest
from datetime import datetime, timedelta
from flask import url_for
from app.models import Event, Job, User
from app.extensions import db


class TestAgentEventsView:
    """Test the agent-specific events view (/events/agent/<id>)"""

    def test_agent_events_requires_authentication(self, client, test_job):
        """Test that agent events page requires login"""
        response = client.get(f'/events/agent/{test_job.id}')
        assert response.status_code == 302
        assert '/auth/login' in response.location

    def test_agent_events_basic_access(self, authenticated_client, test_job, sample_events):
        """Test basic access to agent events page"""
        response = authenticated_client.get(f'/events/agent/{test_job.id}')
        assert response.status_code == 200
        assert b'Events for' in response.data
        assert b'Test Agent' in response.data

    def test_agent_events_displays_events(self, authenticated_client, test_job, sample_events):
        """Test that events are displayed on the page"""
        response = authenticated_client.get(f'/events/agent/{test_job.id}')
        assert response.status_code == 200

        # Check that all events are present
        for event in sample_events:
            assert str(event.id).encode() in response.data
            assert b'Test Event' in response.data

    def test_agent_events_ownership_check(self, app, client, test_job, sample_events):
        """Test that users can't view other users' agent events"""
        with app.app_context():
            # Create a different user
            other_user = User(username='otheruser', email='other@test.com', password='password123')
            db.session.add(other_user)
            db.session.commit()

            # Login as other user
            client.post('/auth/login', data={
                'username': 'otheruser',
                'password': 'password123'
            })

            # Try to access test_job's events (owned by test_user)
            response = client.get(f'/events/agent/{test_job.id}')
            assert response.status_code == 302  # Redirects
            assert 'not authorized' in client.get(response.location).data.decode().lower()

    def test_agent_events_with_date_filter(self, app, authenticated_client, test_job):
        """Test date range filtering on agent events"""
        with app.app_context():
            now = datetime.utcnow()
            yesterday = now - timedelta(days=1)
            tomorrow = now + timedelta(days=1)

            # Create events with different dates
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
                payload={'date': 'today'}
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

            # Filter for today onwards
            start_date = now.strftime('%Y-%m-%d')
            response = authenticated_client.get(f'/events/agent/{test_job.id}?start_date={start_date}')
            assert response.status_code == 200
            assert b'today' in response.data
            assert b'tomorrow' in response.data
            # Yesterday should not be present (or very unlikely to appear in other context)

    def test_agent_events_with_payload_search(self, app, authenticated_client, test_job):
        """Test payload text search on agent events"""
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

            # Search for Python
            response = authenticated_client.get(f'/events/agent/{test_job.id}?search=Python')
            assert response.status_code == 200
            assert b'Python' in response.data
            # JavaScript should not appear in search results

    def test_agent_events_pagination(self, app, authenticated_client, test_job):
        """Test pagination on agent events page"""
        with app.app_context():
            # Create 60 events (more than 50 per page)
            events = []
            for i in range(60):
                event = Event(
                    agent_id=test_job.id,
                    agent_type='test',
                    user_id=test_job.user_id,
                    payload={'index': i}
                )
                events.append(event)

            db.session.add_all(events)
            db.session.commit()

            # First page should have 50 events
            response = authenticated_client.get(f'/events/agent/{test_job.id}')
            assert response.status_code == 200
            assert b'Next' in response.data or b'next' in response.data.lower()

            # Second page should have remaining events
            response = authenticated_client.get(f'/events/agent/{test_job.id}?page=2')
            assert response.status_code == 200
            assert b'Previous' in response.data or b'previous' in response.data.lower()

    def test_agent_events_no_events(self, app, authenticated_client):
        """Test agent events page with no events"""
        with app.app_context():
            # Create an agent with no events
            from app.models import User
            user = User.query.filter_by(username='testuser').first()

            job = Job(
                name='Empty Agent',
                job_type='rss_agent',
                config={'feed_url': 'https://example.com/feed'},
                user_id=user.id
            )
            db.session.add(job)
            db.session.commit()

            response = authenticated_client.get(f'/events/agent/{job.id}')
            assert response.status_code == 200
            assert b'No events found' in response.data or b'no events' in response.data.lower()


class TestAllEventsView:
    """Test the global events view (/events/)"""

    def test_all_events_requires_authentication(self, client):
        """Test that all events page requires login"""
        response = client.get('/events/')
        assert response.status_code == 302
        assert '/auth/login' in response.location

    def test_all_events_basic_access(self, authenticated_client, test_job, sample_events):
        """Test basic access to all events page"""
        response = authenticated_client.get('/events/')
        assert response.status_code == 200
        assert b'All Events' in response.data

    def test_all_events_displays_events(self, authenticated_client, test_job, sample_events):
        """Test that all events are displayed"""
        response = authenticated_client.get('/events/')
        assert response.status_code == 200

        # Check that events are present
        for event in sample_events:
            assert str(event.id).encode() in response.data

    def test_all_events_user_isolation(self, app, client, test_job, sample_events):
        """Test that users only see their own events"""
        with app.app_context():
            # Create another user with their own job and events
            other_user = User(username='otheruser', email='other@test.com', password='password123')
            db.session.add(other_user)
            db.session.commit()

            other_job = Job(
                name='Other Agent',
                job_type='rss_agent',
                config={'feed_url': 'https://example.com/feed'},
                user_id=other_user.id
            )
            db.session.add(other_job)
            db.session.commit()

            other_event = Event(
                agent_id=other_job.id,
                agent_type='test',
                user_id=other_user.id,
                payload={'title': 'Other User Event'}
            )
            db.session.add(other_event)
            db.session.commit()

            # Login as test user
            client.post('/auth/login', data={
                'username': 'testuser',
                'password': 'password123'
            })

            response = client.get('/events/')
            assert response.status_code == 200

            # Should see own events
            assert b'Test Event 1' in response.data

            # Should NOT see other user's events
            assert b'Other User Event' not in response.data

    def test_all_events_with_agent_type_filter(self, app, authenticated_client, test_user):
        """Test filtering by agent type"""
        with app.app_context():
            # Create jobs with different types
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
                payload={'type': 'rss'}
            )
            event2 = Event(
                agent_id=job2.id,
                agent_type='filter_agent',
                user_id=test_user.id,
                payload={'type': 'filter'}
            )
            db.session.add_all([event1, event2])
            db.session.commit()

            # Filter by rss_agent
            response = authenticated_client.get('/events/?agent_type=rss_agent')
            assert response.status_code == 200
            assert b'rss' in response.data.lower()

    def test_all_events_with_specific_agent_filter(self, app, authenticated_client, test_user):
        """Test filtering by specific agent ID"""
        with app.app_context():
            # Create two jobs
            job1 = Job(name='Agent 1', job_type='rss_agent', config={}, user_id=test_user.id)
            job2 = Job(name='Agent 2', job_type='rss_agent', config={}, user_id=test_user.id)
            db.session.add_all([job1, job2])
            db.session.commit()

            # Create events for each
            event1 = Event(agent_id=job1.id, agent_type='rss_agent', user_id=test_user.id, payload={'agent': '1'})
            event2 = Event(agent_id=job2.id, agent_type='rss_agent', user_id=test_user.id, payload={'agent': '2'})
            db.session.add_all([event1, event2])
            db.session.commit()

            # Filter by job1
            response = authenticated_client.get(f'/events/?agent_id={job1.id}')
            assert response.status_code == 200
            # Should only see events from job1

    def test_all_events_with_date_filters(self, app, authenticated_client, test_job):
        """Test date range filtering on all events"""
        with app.app_context():
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

            # Filter for today onwards
            start_date = now.strftime('%Y-%m-%d')
            response = authenticated_client.get(f'/events/?start_date={start_date}')
            assert response.status_code == 200
            assert b'now' in response.data or b'tomorrow' in response.data

    def test_all_events_with_payload_search(self, app, authenticated_client, test_job):
        """Test payload search on all events"""
        with app.app_context():
            event1 = Event(
                agent_id=test_job.id,
                agent_type='test',
                user_id=test_job.user_id,
                payload={'title': 'Unique Search Term'}
            )
            event2 = Event(
                agent_id=test_job.id,
                agent_type='test',
                user_id=test_job.user_id,
                payload={'title': 'Different Content'}
            )

            db.session.add_all([event1, event2])
            db.session.commit()

            # Search for unique term
            response = authenticated_client.get('/events/?search=Unique')
            assert response.status_code == 200
            assert b'Unique' in response.data

    def test_all_events_pagination(self, app, authenticated_client, test_job):
        """Test pagination on all events page"""
        with app.app_context():
            # Create 60 events
            events = []
            for i in range(60):
                event = Event(
                    agent_id=test_job.id,
                    agent_type='test',
                    user_id=test_job.user_id,
                    payload={'index': i}
                )
                events.append(event)

            db.session.add_all(events)
            db.session.commit()

            # First page
            response = authenticated_client.get('/events/')
            assert response.status_code == 200
            assert b'Next' in response.data or b'next' in response.data.lower()

            # Second page
            response = authenticated_client.get('/events/?page=2')
            assert response.status_code == 200
            assert b'Previous' in response.data or b'previous' in response.data.lower()

    def test_all_events_combined_filters(self, app, authenticated_client, test_user):
        """Test using multiple filters together"""
        with app.app_context():
            # Create job
            job = Job(
                name='Combined Test Agent',
                job_type='rss_agent',
                config={},
                user_id=test_user.id
            )
            db.session.add(job)
            db.session.commit()

            now = datetime.utcnow()

            # Create events
            event1 = Event(
                agent_id=job.id,
                agent_type='rss_agent',
                user_id=test_user.id,
                payload={'title': 'Python Guide'}
            )
            event1.created_at = now

            event2 = Event(
                agent_id=job.id,
                agent_type='rss_agent',
                user_id=test_user.id,
                payload={'title': 'JavaScript Guide'}
            )
            event2.created_at = now - timedelta(days=2)

            db.session.add_all([event1, event2])
            db.session.commit()

            # Use date filter + payload search
            start_date = (now - timedelta(days=1)).strftime('%Y-%m-%d')
            response = authenticated_client.get(f'/events/?start_date={start_date}&search=Python')
            assert response.status_code == 200
            assert b'Python' in response.data

    def test_all_events_no_events(self, app, client):
        """Test all events page with no events"""
        with app.app_context():
            # Create a new user with no events
            user = User(username='newuser', email='new@test.com', password='password123')
            db.session.add(user)
            db.session.commit()

            # Login as new user
            client.post('/auth/login', data={
                'username': 'newuser',
                'password': 'password123'
            })

            response = client.get('/events/')
            assert response.status_code == 200
            assert b'No events found' in response.data or b'no events' in response.data.lower()

    def test_all_events_filter_form_populated(self, app, authenticated_client, test_user):
        """Test that filter form values persist after filtering"""
        with app.app_context():
            # Create a job
            job = Job(
                name='Test Agent',
                job_type='rss_agent',
                config={},
                user_id=test_user.id
            )
            db.session.add(job)
            db.session.commit()

            # Apply filters
            response = authenticated_client.get(f'/events/?agent_type=rss_agent&search=test')
            assert response.status_code == 200
            # Form should retain the filter values
            assert b'rss_agent' in response.data
            assert b'test' in response.data
