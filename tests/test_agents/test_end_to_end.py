"""
End-to-end tests for complete agent workflows
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime
from app.models import Event, AgentLink
from app.services.agent_service import AgentService
from app.services.event_service import EventService
from app.extensions import db


class TestEndToEndScenarios:
    """End-to-end tests for complete agent workflows"""

    @patch('app.agents.types.rss_agent.feedparser.parse')
    @patch('app.agents.types.email_agent.smtplib.SMTP')
    def test_rss_to_filter_to_email(self, mock_smtp, mock_feedparser, app, test_job):
        """
        Test complete workflow: RSS → Filter → Email

        Scenario:
        1. RSS agent fetches feed
        2. Filter agent filters articles
        3. Email agent sends notifications
        """
        with app.app_context():
            from app.models import Job, User
            user = db.session.query(User).first()

            # Setup mock RSS feed
            mock_feed = MagicMock()
            mock_feed.entries = [
                MagicMock(
                    title='Python 3.12 Released',
                    link='https://example.com/python312',
                    summary='New Python version',
                    published_parsed=datetime.now().timetuple()
                ),
                MagicMock(
                    title='JavaScript Framework Update',
                    link='https://example.com/jsfw',
                    summary='Framework news',
                    published_parsed=datetime.now().timetuple()
                ),
                MagicMock(
                    title='Python Best Practices',
                    link='https://example.com/python-practices',
                    summary='Coding tips',
                    published_parsed=datetime.now().timetuple()
                )
            ]
            mock_feedparser.return_value = mock_feed

            # Setup mock SMTP
            mock_smtp_instance = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_smtp_instance

            # Create agents
            rss_agent = Job(
                name='Tech News RSS',
                job_type='rss_agent',
                config={
                    'feed_url': 'https://example.com/feed.xml',
                    'max_entries': 10
                },
                user_id=user.id,
                is_active=True
            )

            filter_agent = Job(
                name='Python Filter',
                job_type='filter_agent',
                config={
                    'rules': [
                        {'field': 'title', 'type': 'contains', 'value': 'Python', 'case_sensitive': False}
                    ]
                },
                user_id=user.id,
                is_active=True
            )

            email_agent = Job(
                name='Email Notifier',
                job_type='email_agent',
                config={
                    'smtp_server': 'smtp.example.com',
                    'smtp_port': 587,
                    'username': 'user@example.com',
                    'password': 'password',
                    'from_email': 'user@example.com',
                    'to_email': 'recipient@example.com',
                    'subject_template': 'New Article: {{ title }}',
                    'body_template': '{{ title }}\n\n{{ link }}'
                },
                user_id=user.id,
                is_active=True
            )

            db.session.add(rss_agent)
            db.session.add(filter_agent)
            db.session.add(email_agent)
            db.session.flush()

            # Create links: RSS → Filter → Email
            link1 = AgentLink(source_agent_id=rss_agent.id, target_agent_id=filter_agent.id)
            link2 = AgentLink(source_agent_id=filter_agent.id, target_agent_id=email_agent.id)
            db.session.add(link1)
            db.session.add(link2)
            db.session.commit()

            # Execute workflow
            agent_service = AgentService(db.session)
            result = agent_service.run_agent(agent_id=rss_agent.id, manual=True, propagate=True)

            # Verify
            assert result['success'] == True
            assert result['events_created'] == 3  # 3 RSS entries
            assert 'propagation_stats' in result

            # Verify propagation
            stats = result['propagation_stats']
            assert stats['agents_executed'] >= 2  # Filter and Email agents
            assert stats['events_created'] >= 2  # Filtered Python events

            # Verify emails were sent (2 Python articles)
            assert mock_smtp_instance.send_message.call_count == 2

    @patch('app.agents.types.web_fetch_agent.requests.get')
    def test_web_fetch_to_html_parser_to_dedupe(self, mock_get, app, test_job):
        """
        Test workflow: WebFetch → HTMLParser → Deduplication

        Scenario:
        1. WebFetch agent fetches HTML
        2. HTMLParser extracts data
        3. Deduplication removes duplicates
        """
        with app.app_context():
            from app.models import Job, User
            user = db.session.query(User).first()

            # Setup mock HTTP response
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = '''
            <html>
                <div class="article">
                    <h2>Article 1</h2>
                    <a href="https://example.com/1">Link 1</a>
                </div>
                <div class="article">
                    <h2>Article 2</h2>
                    <a href="https://example.com/2">Link 2</a>
                </div>
            </html>
            '''
            mock_get.return_value = mock_response

            # Create agents
            web_fetch = Job(
                name='Web Fetcher',
                job_type='web_fetch_agent',
                config={'url': 'https://example.com/articles'},
                user_id=user.id,
                is_active=True
            )

            html_parser = Job(
                name='HTML Parser',
                job_type='html_parser_agent',
                config={
                    'selectors': {
                        'title': '.article h2',
                        'link': '.article a'
                    }
                },
                user_id=user.id,
                is_active=True
            )

            dedupe = Job(
                name='Deduplicator',
                job_type='deduplication_agent',
                config={
                    'uniqueness_fields': ['link'],
                    'lookback_days': 7
                },
                user_id=user.id,
                is_active=True
            )

            db.session.add(web_fetch)
            db.session.add(html_parser)
            db.session.add(dedupe)
            db.session.flush()

            # Create links
            link1 = AgentLink(source_agent_id=web_fetch.id, target_agent_id=html_parser.id)
            link2 = AgentLink(source_agent_id=html_parser.id, target_agent_id=dedupe.id)
            db.session.add(link1)
            db.session.add(link2)
            db.session.commit()

            # Execute workflow
            agent_service = AgentService(db.session)
            result = agent_service.run_agent(agent_id=web_fetch.id, manual=True, propagate=True)

            # Verify
            assert result['success'] == True
            assert result['events_created'] == 1  # Web fetch creates 1 event
            assert 'propagation_stats' in result

            # Run again to test deduplication
            result2 = agent_service.run_agent(agent_id=web_fetch.id, manual=True, propagate=True)
            assert result2['success'] == True

    def test_template_agent_transformation(self, app, test_job):
        """
        Test workflow: Source → Template → Action

        Scenario:
        1. Source creates events
        2. Template transforms data
        3. Action consumes transformed data
        """
        with app.app_context():
            from app.models import Job, User, Event
            user = db.session.query(User).first()

            # Create source agent (we'll manually create events)
            source = Job(
                name='Source',
                job_type='rss_agent',
                config={'feed_url': 'https://example.com/feed.xml'},
                user_id=user.id,
                is_active=True
            )

            # Create template agent
            template_agent = Job(
                name='Templater',
                job_type='template_agent',
                config={
                    'template': '{{ title }} - {{ link }}',
                    'output_field': 'formatted',
                    'preserve_original': True
                },
                user_id=user.id,
                is_active=True
            )

            db.session.add(source)
            db.session.add(template_agent)
            db.session.flush()

            # Create link
            link = AgentLink(source_agent_id=source.id, target_agent_id=template_agent.id)
            db.session.add(link)
            db.session.commit()

            # Create source events manually
            source_events = [
                Event(
                    agent_id=source.id,
                    agent_type='rss_agent',
                    user_id=user.id,
                    payload={'title': 'Test Article', 'link': 'https://example.com/1'},
                    metadata={}
                )
            ]
            for event in source_events:
                db.session.add(event)
            db.session.commit()

            # Propagate events
            event_service = EventService(db.session)
            stats = event_service.propagate_events(source_events)

            # Verify template agent executed
            assert stats['agents_executed'] == 1
            assert stats['events_created'] >= 1

            # Verify transformed events exist
            transformed_events = db.session.query(Event).filter(
                Event.agent_id == template_agent.id
            ).all()
            assert len(transformed_events) >= 1

            # Check transformation
            for event in transformed_events:
                assert 'formatted' in event.payload
                assert 'Test Article - https://example.com/1' in event.payload['formatted']

    def test_digest_agent_batching(self, app, test_job):
        """
        Test workflow: Source → Digest → Action

        Scenario:
        1. Source creates multiple events
        2. Digest batches them
        3. Action receives batch
        """
        with app.app_context():
            from app.models import Job, User, Event
            user = db.session.query(User).first()

            # Create source
            source = Job(
                name='Source',
                job_type='rss_agent',
                config={'feed_url': 'https://example.com/feed.xml'},
                user_id=user.id,
                is_active=True
            )

            # Create digest agent
            digest_agent = Job(
                name='Daily Digest',
                job_type='digest_agent',
                config={
                    'batch_size': 5,
                    'batch_timeout_minutes': 60
                },
                user_id=user.id,
                is_active=True
            )

            db.session.add(source)
            db.session.add(digest_agent)
            db.session.flush()

            # Create link
            link = AgentLink(source_agent_id=source.id, target_agent_id=digest_agent.id)
            db.session.add(link)
            db.session.commit()

            # Create multiple source events
            source_events = []
            for i in range(3):
                event = Event(
                    agent_id=source.id,
                    agent_type='rss_agent',
                    user_id=user.id,
                    payload={'title': f'Article {i}', 'link': f'https://example.com/{i}'},
                    metadata={}
                )
                source_events.append(event)
                db.session.add(event)
            db.session.commit()

            # Propagate events
            event_service = EventService(db.session)
            stats = event_service.propagate_events(source_events)

            # Verify digest agent executed
            assert stats['agents_executed'] == 1

            # Verify batched events
            batched_events = db.session.query(Event).filter(
                Event.agent_id == digest_agent.id
            ).all()
            assert len(batched_events) >= 1

    def test_error_isolation(self, app, test_job):
        """
        Test that errors in one branch don't affect other branches

        Scenario:
        1. Source feeds two downstream agents
        2. One agent fails
        3. Other agent continues normally
        """
        with app.app_context():
            from app.models import Job, User, Event
            user = db.session.query(User).first()

            # Create source
            source = Job(
                name='Source',
                job_type='rss_agent',
                config={'feed_url': 'https://example.com/feed.xml'},
                user_id=user.id,
                is_active=True
            )

            # Create two downstream agents
            good_agent = Job(
                name='Good Agent',
                job_type='filter_agent',
                config={'rules': [{'field': 'title', 'type': 'contains', 'value': 'test'}]},
                user_id=user.id,
                is_active=True
            )

            # Invalid config to cause error
            bad_agent = Job(
                name='Bad Agent',
                job_type='filter_agent',
                config={},  # Missing required 'rules'
                user_id=user.id,
                is_active=True
            )

            db.session.add(source)
            db.session.add(good_agent)
            db.session.add(bad_agent)
            db.session.flush()

            # Create links to both
            link1 = AgentLink(source_agent_id=source.id, target_agent_id=good_agent.id)
            link2 = AgentLink(source_agent_id=source.id, target_agent_id=bad_agent.id)
            db.session.add(link1)
            db.session.add(link2)
            db.session.commit()

            # Create source event
            event = Event(
                agent_id=source.id,
                agent_type='rss_agent',
                user_id=user.id,
                payload={'title': 'test article', 'link': 'https://example.com/1'},
                metadata={}
            )
            db.session.add(event)
            db.session.commit()

            # Propagate - should handle error gracefully
            event_service = EventService(db.session)
            stats = event_service.propagate_events([event])

            # At least the good agent should execute
            # (bad agent may fail, but propagation continues)
            assert stats['agents_executed'] >= 1

    def test_complex_network(self, app, test_job):
        """
        Test complex network with multiple paths

        Scenario:
        Source → Transform1 → Transform2 → Action1
              → Transform3 → Action2
        """
        with app.app_context():
            from app.models import Job, User, Event
            user = db.session.query(User).first()

            # Create agents
            source = Job(
                name='Source',
                job_type='rss_agent',
                config={'feed_url': 'https://example.com/feed.xml'},
                user_id=user.id,
                is_active=True
            )

            transform1 = Job(
                name='Transform 1',
                job_type='filter_agent',
                config={'rules': [{'field': 'title', 'type': 'contains', 'value': 'test'}]},
                user_id=user.id,
                is_active=True
            )

            transform2 = Job(
                name='Transform 2',
                job_type='template_agent',
                config={'template': '{{ title }}', 'output_field': 'formatted'},
                user_id=user.id,
                is_active=True
            )

            transform3 = Job(
                name='Transform 3',
                job_type='deduplication_agent',
                config={'uniqueness_fields': ['link'], 'lookback_days': 7},
                user_id=user.id,
                is_active=True
            )

            db.session.add_all([source, transform1, transform2, transform3])
            db.session.flush()

            # Create complex network
            links = [
                AgentLink(source_agent_id=source.id, target_agent_id=transform1.id),
                AgentLink(source_agent_id=transform1.id, target_agent_id=transform2.id),
                AgentLink(source_agent_id=source.id, target_agent_id=transform3.id)
            ]
            for link in links:
                db.session.add(link)
            db.session.commit()

            # Create event
            event = Event(
                agent_id=source.id,
                agent_type='rss_agent',
                user_id=user.id,
                payload={'title': 'test article', 'link': 'https://example.com/1'},
                metadata={}
            )
            db.session.add(event)
            db.session.commit()

            # Propagate
            event_service = EventService(db.session)
            stats = event_service.propagate_events([event])

            # Should execute multiple agents across different paths
            assert stats['agents_executed'] >= 3
            assert stats['events_propagated'] >= 1
