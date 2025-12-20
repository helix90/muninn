"""
Tests for Agent Pipeline UI features

Tests the UI components for:
- Creating and managing links between agents
- Pipeline visualization
- Agent categorization
- Link validation
"""

import pytest
import json
from app.models import Job, AgentLink
from app.extensions import db


class TestAgentLinkCreation:
    """Tests for creating agent links through the UI."""

    def test_available_agents_excludes_current(self, authenticated_client, test_user):
        """Current agent should not appear in available agents list."""
        # Create RSS agent (source - can create events)
        rss_agent = Job(
            name='RSS Agent',
            job_type='rss_agent',
            config={'feed_url': 'https://example.com/feed'},
            user_id=test_user.id
        )
        db.session.add(rss_agent)

        # Create filter agent (transform - can receive events)
        filter_agent = Job(
            name='Filter Agent',
            job_type='filter_agent',
            config={'rules': []},
            user_id=test_user.id
        )
        db.session.add(filter_agent)
        db.session.commit()

        # Get RSS agent detail page
        response = authenticated_client.get(f'/agents/{rss_agent.id}')
        assert response.status_code == 200

        # RSS agent should not appear in its own available agents list
        html = response.data.decode('utf-8')
        assert 'RSS Agent' not in html.split('target_agent_id')[1].split('</select>')[0]

    def test_available_agents_only_shows_receivers(self, authenticated_client, test_user):
        """Only agents that can receive events should be available for linking."""
        # Create RSS agent (source - can create events)
        rss_agent = Job(
            name='RSS Agent',
            job_type='rss_agent',
            config={'feed_url': 'https://example.com/feed'},
            user_id=test_user.id
        )
        db.session.add(rss_agent)

        # Create another RSS agent (source - cannot receive events)
        rss_agent2 = Job(
            name='RSS Agent 2',
            job_type='rss_agent',
            config={'feed_url': 'https://example.com/feed2'},
            user_id=test_user.id
        )
        db.session.add(rss_agent2)

        # Create filter agent (transform - can receive events)
        filter_agent = Job(
            name='Filter Agent',
            job_type='filter_agent',
            config={'rules': []},
            user_id=test_user.id
        )
        db.session.add(filter_agent)
        db.session.commit()

        # Get first RSS agent detail page
        response = authenticated_client.get(f'/agents/{rss_agent.id}')
        assert response.status_code == 200

        html = response.data.decode('utf-8')

        # Filter agent should be available (can receive events)
        assert 'Filter Agent' in html

        # Second RSS agent should NOT be available (cannot receive events)
        # The available agents section should exist
        if 'target_agent_id' in html:
            available_section = html.split('target_agent_id')[1].split('</select>')[0]
            assert 'RSS Agent 2' not in available_section

    def test_available_agents_excludes_existing_links(self, authenticated_client, test_user):
        """Agents that already have a link should not appear in available agents."""
        # Create RSS agent (source)
        rss_agent = Job(
            name='RSS Agent',
            job_type='rss_agent',
            config={'feed_url': 'https://example.com/feed'},
            user_id=test_user.id
        )
        db.session.add(rss_agent)

        # Create two filter agents
        filter_agent1 = Job(
            name='Filter Agent 1',
            job_type='filter_agent',
            config={'rules': []},
            user_id=test_user.id
        )
        db.session.add(filter_agent1)

        filter_agent2 = Job(
            name='Filter Agent 2',
            job_type='filter_agent',
            config={'rules': []},
            user_id=test_user.id
        )
        db.session.add(filter_agent2)
        db.session.commit()

        # Create link from RSS to Filter Agent 1
        link = AgentLink(
            source_agent_id=rss_agent.id,
            target_agent_id=filter_agent1.id
        )
        db.session.add(link)
        db.session.commit()

        # Get RSS agent detail page
        response = authenticated_client.get(f'/agents/{rss_agent.id}')
        assert response.status_code == 200

        html = response.data.decode('utf-8')

        # Filter Agent 2 should be available
        assert 'Filter Agent 2' in html

        # Filter Agent 1 should NOT be available (already linked)
        if 'target_agent_id' in html:
            available_section = html.split('target_agent_id')[1].split('</select>')[0]
            assert 'Filter Agent 1' not in available_section

    def test_create_link_from_detail_page(self, authenticated_client, test_user):
        """Should be able to create a link via POST to create_link endpoint."""
        # Create RSS agent (source)
        rss_agent = Job(
            name='RSS Agent',
            job_type='rss_agent',
            config={'feed_url': 'https://example.com/feed'},
            user_id=test_user.id
        )
        db.session.add(rss_agent)

        # Create filter agent (transform)
        filter_agent = Job(
            name='Filter Agent',
            job_type='filter_agent',
            config={'rules': []},
            user_id=test_user.id
        )
        db.session.add(filter_agent)
        db.session.commit()

        # Create link via POST
        response = authenticated_client.post(
            '/agents/link',
            json={
                'source_agent_id': rss_agent.id,
                'target_agent_id': filter_agent.id
            }
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

        # Verify link was created in database
        link = db.session.query(AgentLink).filter(
            AgentLink.source_agent_id == rss_agent.id,
            AgentLink.target_agent_id == filter_agent.id
        ).first()
        assert link is not None
        assert link.is_active is True


class TestAgentLinkDeletion:
    """Tests for deleting agent links."""

    def test_delete_link_from_detail_page(self, authenticated_client, test_user):
        """Should be able to delete a link via POST to delete_link endpoint."""
        # Create agents
        rss_agent = Job(
            name='RSS Agent',
            job_type='rss_agent',
            config={'feed_url': 'https://example.com/feed'},
            user_id=test_user.id
        )
        db.session.add(rss_agent)

        filter_agent = Job(
            name='Filter Agent',
            job_type='filter_agent',
            config={'rules': []},
            user_id=test_user.id
        )
        db.session.add(filter_agent)
        db.session.commit()

        # Create link
        link = AgentLink(
            source_agent_id=rss_agent.id,
            target_agent_id=filter_agent.id
        )
        db.session.add(link)
        db.session.commit()
        link_id = link.id

        # Delete link via POST
        response = authenticated_client.post(f'/agents/link/{link_id}/delete')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

        # Verify link was deleted from database
        deleted_link = db.session.query(AgentLink).filter(
            AgentLink.id == link_id
        ).first()
        assert deleted_link is None


class TestPipelineVisualization:
    """Tests for the pipeline visualization page."""

    def test_pipeline_page_loads(self, authenticated_client, test_user):
        """Pipeline page should load successfully."""
        response = authenticated_client.get('/agents/pipeline')
        assert response.status_code == 200
        assert b'Agent Pipeline Visualization' in response.data

    def test_pipeline_includes_all_agents(self, authenticated_client, test_user):
        """Pipeline should include all user's active agents in JSON."""
        # Create multiple agents
        rss_agent = Job(
            name='RSS Agent',
            job_type='rss_agent',
            config={'feed_url': 'https://example.com/feed'},
            user_id=test_user.id
        )
        db.session.add(rss_agent)

        filter_agent = Job(
            name='Filter Agent',
            job_type='filter_agent',
            config={'rules': []},
            user_id=test_user.id
        )
        db.session.add(filter_agent)

        email_agent = Job(
            name='Email Agent',
            job_type='email_agent',
            config={'to': 'test@example.com'},
            user_id=test_user.id
        )
        db.session.add(email_agent)
        db.session.commit()

        # Get pipeline page
        response = authenticated_client.get('/agents/pipeline')
        assert response.status_code == 200

        html = response.data.decode('utf-8')

        # Check that agents are included in the JavaScript data
        assert 'RSS Agent' in html
        assert 'Filter Agent' in html
        assert 'Email Agent' in html

    def test_pipeline_includes_all_links(self, authenticated_client, test_user):
        """Pipeline should include all links between user's agents."""
        # Create agents
        rss_agent = Job(
            name='RSS Agent',
            job_type='rss_agent',
            config={'feed_url': 'https://example.com/feed'},
            user_id=test_user.id
        )
        db.session.add(rss_agent)

        filter_agent = Job(
            name='Filter Agent',
            job_type='filter_agent',
            config={'rules': []},
            user_id=test_user.id
        )
        db.session.add(filter_agent)

        email_agent = Job(
            name='Email Agent',
            job_type='email_agent',
            config={'to': 'test@example.com'},
            user_id=test_user.id
        )
        db.session.add(email_agent)
        db.session.commit()

        # Create links
        link1 = AgentLink(
            source_agent_id=rss_agent.id,
            target_agent_id=filter_agent.id
        )
        db.session.add(link1)

        link2 = AgentLink(
            source_agent_id=filter_agent.id,
            target_agent_id=email_agent.id
        )
        db.session.add(link2)
        db.session.commit()

        # Get pipeline page
        response = authenticated_client.get('/agents/pipeline')
        assert response.status_code == 200

        html = response.data.decode('utf-8')

        # Links should be in the JavaScript data
        assert f'"source_agent_id": {rss_agent.id}' in html
        assert f'"target_agent_id": {filter_agent.id}' in html
        assert f'"source_agent_id": {filter_agent.id}' in html
        assert f'"target_agent_id": {email_agent.id}' in html

    def test_pipeline_agent_categories(self, authenticated_client, test_user):
        """Agents should be categorized correctly (source/transform/action)."""
        # Create one of each category
        rss_agent = Job(
            name='RSS Agent',
            job_type='rss_agent',
            config={'feed_url': 'https://example.com/feed'},
            user_id=test_user.id
        )
        db.session.add(rss_agent)

        filter_agent = Job(
            name='Filter Agent',
            job_type='filter_agent',
            config={'rules': []},
            user_id=test_user.id
        )
        db.session.add(filter_agent)

        email_agent = Job(
            name='Email Agent',
            job_type='email_agent',
            config={'to': 'test@example.com'},
            user_id=test_user.id
        )
        db.session.add(email_agent)
        db.session.commit()

        # Get pipeline page
        response = authenticated_client.get('/agents/pipeline')
        assert response.status_code == 200

        html = response.data.decode('utf-8')

        # Check categories in JSON data
        # RSS should be categorized as 'source'
        assert '"agent_category": "source"' in html

        # Filter should be categorized as 'transform'
        assert '"agent_category": "transform"' in html

        # Email should be categorized as 'action'
        assert '"agent_category": "action"' in html

    def test_pipeline_excludes_other_users(self, authenticated_client, test_user, app):
        """Pipeline should not show agents from other users."""
        # Create agent for test user
        user_agent = Job(
            name='Test User Agent',
            job_type='rss_agent',
            config={'feed_url': 'https://example.com/feed'},
            user_id=test_user.id
        )
        db.session.add(user_agent)

        # Create another user
        from app.models import User
        other_user = User(
            username='otheruser',
            email='other@example.com',
            password='password123'
        )
        db.session.add(other_user)
        db.session.commit()

        # Create agent for other user
        other_agent = Job(
            name='Other User Agent',
            job_type='rss_agent',
            config={'feed_url': 'https://example.com/other'},
            user_id=other_user.id
        )
        db.session.add(other_agent)
        db.session.commit()

        # Get pipeline page as test user
        response = authenticated_client.get('/agents/pipeline')
        assert response.status_code == 200

        html = response.data.decode('utf-8')

        # Test user's agent should be present
        assert 'Test User Agent' in html

        # Other user's agent should NOT be present
        assert 'Other User Agent' not in html


class TestLinkValidation:
    """Tests for link validation rules."""

    def test_cannot_link_to_source_agent(self, authenticated_client, test_user):
        """Should not be able to create link to an agent that cannot receive events."""
        # Create two RSS agents (both are source agents - cannot receive events)
        rss_agent1 = Job(
            name='RSS Agent 1',
            job_type='rss_agent',
            config={'feed_url': 'https://example.com/feed1'},
            user_id=test_user.id
        )
        db.session.add(rss_agent1)

        rss_agent2 = Job(
            name='RSS Agent 2',
            job_type='rss_agent',
            config={'feed_url': 'https://example.com/feed2'},
            user_id=test_user.id
        )
        db.session.add(rss_agent2)
        db.session.commit()

        # Try to create link from RSS 1 to RSS 2 (should fail)
        response = authenticated_client.post(
            '/agents/link',
            json={
                'source_agent_id': rss_agent1.id,
                'target_agent_id': rss_agent2.id
            }
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'cannot receive events' in data['error'].lower()

    def test_cannot_link_from_action_agent(self, authenticated_client, test_user):
        """Should not be able to create link from an agent that cannot create events."""
        # Create email agent (action - cannot create events)
        email_agent = Job(
            name='Email Agent',
            job_type='email_agent',
            config={'to': 'test@example.com'},
            user_id=test_user.id
        )
        db.session.add(email_agent)

        # Create filter agent (transform - can receive events)
        filter_agent = Job(
            name='Filter Agent',
            job_type='filter_agent',
            config={'rules': []},
            user_id=test_user.id
        )
        db.session.add(filter_agent)
        db.session.commit()

        # Try to create link from Email to Filter (should fail)
        response = authenticated_client.post(
            '/agents/link',
            json={
                'source_agent_id': email_agent.id,
                'target_agent_id': filter_agent.id
            }
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'cannot create events' in data['error'].lower()

    def test_can_link_source_to_transform(self, authenticated_client, test_user):
        """Should be able to create valid link from source to transform agent."""
        # Create RSS agent (source - can create events)
        rss_agent = Job(
            name='RSS Agent',
            job_type='rss_agent',
            config={'feed_url': 'https://example.com/feed'},
            user_id=test_user.id
        )
        db.session.add(rss_agent)

        # Create filter agent (transform - can receive and create events)
        filter_agent = Job(
            name='Filter Agent',
            job_type='filter_agent',
            config={'rules': []},
            user_id=test_user.id
        )
        db.session.add(filter_agent)
        db.session.commit()

        # Create link (should succeed)
        response = authenticated_client.post(
            '/agents/link',
            json={
                'source_agent_id': rss_agent.id,
                'target_agent_id': filter_agent.id
            }
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

        # Verify link exists
        link = db.session.query(AgentLink).filter(
            AgentLink.source_agent_id == rss_agent.id,
            AgentLink.target_agent_id == filter_agent.id
        ).first()
        assert link is not None

    def test_can_link_transform_to_action(self, authenticated_client, test_user):
        """Should be able to create valid link from transform to action agent."""
        # Create filter agent (transform - can create events)
        filter_agent = Job(
            name='Filter Agent',
            job_type='filter_agent',
            config={'rules': []},
            user_id=test_user.id
        )
        db.session.add(filter_agent)

        # Create email agent (action - can receive events)
        email_agent = Job(
            name='Email Agent',
            job_type='email_agent',
            config={'to': 'test@example.com'},
            user_id=test_user.id
        )
        db.session.add(email_agent)
        db.session.commit()

        # Create link (should succeed)
        response = authenticated_client.post(
            '/agents/link',
            json={
                'source_agent_id': filter_agent.id,
                'target_agent_id': email_agent.id
            }
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

        # Verify link exists
        link = db.session.query(AgentLink).filter(
            AgentLink.source_agent_id == filter_agent.id,
            AgentLink.target_agent_id == email_agent.id
        ).first()
        assert link is not None
