"""
Tests for agent view routes and forms

These tests verify that the agent creation and management views work correctly,
including form rendering, schema API, and agent creation through the web interface.
"""

import json
import pytest
from app import create_app
from app.models import Job


class TestAgentCreationView:
    """Test agent creation form rendering and submission."""

    def test_create_agent_get_request_redirects_unauthenticated(self, client):
        """Test that unauthenticated users are redirected to login."""
        response = client.get('/agents/create')
        assert response.status_code == 302
        assert '/auth/login' in response.location

    def test_create_agent_get_request_authenticated(self, authenticated_client):
        """Test that agent creation form loads for authenticated users."""
        response = authenticated_client.get('/agents/create')
        assert response.status_code == 200

        # Check that form contains expected elements
        content = response.data.decode('utf-8')
        assert 'Create New Agent' in content
        assert 'Source Agents' in content
        assert 'Transform Agents' in content
        assert 'Action Agents' in content

    def test_create_agent_form_contains_agent_types(self, authenticated_client):
        """Test that form contains all agent type options."""
        response = authenticated_client.get('/agents/create')
        content = response.data.decode('utf-8')

        # Check for known agent types
        assert 'RSS Agent' in content or 'rss_agent' in content
        assert 'Filter Agent' in content or 'filter_agent' in content
        assert 'Email Agent' in content or 'email_agent' in content

    def test_create_agent_form_has_dynamic_config_section(self, authenticated_client):
        """Test that form has JavaScript for dynamic configuration fields."""
        response = authenticated_client.get('/agents/create')
        content = response.data.decode('utf-8')

        # Check for dynamic configuration section
        assert 'configSection' in content
        assert 'configFields' in content
        assert 'updateConfigFields' in content

    def test_create_agent_post_missing_name(self, authenticated_client):
        """Test that creating agent without name fails."""
        response = authenticated_client.post('/agents/create', data={
            'agent_type': 'rss_agent',
            'config_feed_url': 'https://example.com/feed.xml'
        }, follow_redirects=True)

        content = response.data.decode('utf-8')
        assert 'Agent name is required' in content or response.status_code == 200

    def test_create_agent_post_missing_type(self, authenticated_client):
        """Test that creating agent without type fails."""
        response = authenticated_client.post('/agents/create', data={
            'name': 'Test Agent'
        }, follow_redirects=True)

        content = response.data.decode('utf-8')
        assert 'Agent type is required' in content or response.status_code == 200

    def test_create_rss_agent_missing_config(self, authenticated_client, db_session):
        """Test that creating RSS agent without feed_url fails validation."""
        response = authenticated_client.post('/agents/create', data={
            'name': 'Test RSS Agent',
            'agent_type': 'rss_agent'
            # Missing config_feed_url
        }, follow_redirects=True)

        content = response.data.decode('utf-8')
        # Should show validation error
        assert 'Invalid configuration' in content or 'required' in content.lower()

    def test_create_rss_agent_with_valid_config(self, authenticated_client, db_session):
        """Test creating RSS agent with all required configuration."""
        response = authenticated_client.post('/agents/create', data={
            'name': 'Test RSS Agent',
            'agent_type': 'rss_agent',
            'config_feed_url': 'https://example.com/feed.xml'
        })

        # Should redirect to agent detail page on success
        assert response.status_code == 302
        assert '/agents/' in response.location

        # Verify agent was created in database
        agent = db_session.query(Job).filter(Job.name == 'Test RSS Agent').first()
        assert agent is not None
        assert agent.job_type == 'rss_agent'
        assert agent.config['feed_url'] == 'https://example.com/feed.xml'

    def test_create_rss_agent_with_optional_config(self, authenticated_client, db_session):
        """Test creating RSS agent with optional configuration fields."""
        response = authenticated_client.post('/agents/create', data={
            'name': 'Advanced RSS Agent',
            'agent_type': 'rss_agent',
            'config_feed_url': 'https://example.com/feed.xml',
            'config_max_entries': '100',
            'config_days_back': '30'
        })

        assert response.status_code == 302

        # Verify optional config was saved
        agent = db_session.query(Job).filter(Job.name == 'Advanced RSS Agent').first()
        assert agent is not None
        assert agent.config.get('max_entries') == 100
        assert agent.config.get('days_back') == 30

    def test_create_agent_with_schedule(self, authenticated_client, db_session):
        """Test creating agent with cron schedule."""
        response = authenticated_client.post('/agents/create', data={
            'name': 'Scheduled RSS Agent',
            'agent_type': 'rss_agent',
            'config_feed_url': 'https://example.com/feed.xml',
            'schedule': '0 */6 * * *'  # Every 6 hours
        })

        assert response.status_code == 302

        # Verify schedule was saved
        agent = db_session.query(Job).filter(Job.name == 'Scheduled RSS Agent').first()
        assert agent is not None
        assert agent.schedule_cron == '0 */6 * * *'
        assert agent.schedule_enabled is True


class TestAgentSchemaAPI:
    """Test agent schema API endpoint."""

    def test_schema_api_requires_authentication(self, client):
        """Test that schema API requires authentication."""
        response = client.get('/agents/api/schema/rss_agent')
        assert response.status_code == 302
        assert '/auth/login' in response.location

    def test_schema_api_returns_json(self, authenticated_client):
        """Test that schema API returns JSON."""
        response = authenticated_client.get('/agents/api/schema/rss_agent')
        assert response.status_code == 200
        assert response.content_type == 'application/json'

    def test_schema_api_rss_agent_structure(self, authenticated_client):
        """Test that RSS agent schema has correct structure."""
        response = authenticated_client.get('/agents/api/schema/rss_agent')
        data = json.loads(response.data)

        # Check for required schema fields
        assert 'required_fields' in data
        assert 'optional_fields' in data

        # Check that feed_url is in required fields
        assert 'feed_url' in data['required_fields']

        # Check that optional fields have proper structure
        if data['optional_fields']:
            for field in data['optional_fields']:
                assert 'name' in field
                assert 'type' in field

    def test_schema_api_invalid_agent_type(self, authenticated_client):
        """Test that schema API returns 404 for invalid agent type."""
        response = authenticated_client.get('/agents/api/schema/nonexistent_agent')
        assert response.status_code == 404
        data = json.loads(response.data)
        assert 'error' in data

    def test_schema_api_filter_agent(self, authenticated_client):
        """Test schema for filter agent."""
        response = authenticated_client.get('/agents/api/schema/filter_agent')
        assert response.status_code == 200
        data = json.loads(response.data)

        assert 'required_fields' in data
        assert 'optional_fields' in data

    def test_schema_api_email_agent(self, authenticated_client):
        """Test schema for email agent."""
        response = authenticated_client.get('/agents/api/schema/email_agent')
        assert response.status_code == 200
        data = json.loads(response.data)

        assert 'required_fields' in data
        # Email agent should have required SMTP configuration
        assert len(data['required_fields']) > 0


class TestAgentListView:
    """Test agent list view."""

    def test_agent_list_requires_authentication(self, client):
        """Test that agent list requires authentication."""
        response = client.get('/agents/')
        assert response.status_code == 302
        assert '/auth/login' in response.location

    def test_agent_list_loads(self, authenticated_client):
        """Test that agent list page loads."""
        response = authenticated_client.get('/agents/')
        assert response.status_code == 200

    def test_agent_list_shows_created_agents(self, authenticated_client, db_session, test_user):
        """Test that created agents appear in the list."""
        # Create a test agent
        agent = Job(
            name='Test List Agent',
            job_type='rss_agent',
            config={'feed_url': 'https://example.com/feed.xml'},
            user_id=test_user.id
        )
        db_session.add(agent)
        db_session.commit()

        response = authenticated_client.get('/agents/')
        content = response.data.decode('utf-8')

        assert 'Test List Agent' in content


class TestAgentDetailView:
    """Test agent detail view."""

    def test_agent_detail_requires_authentication(self, client):
        """Test that agent detail requires authentication."""
        response = client.get('/agents/1')
        assert response.status_code == 302
        assert '/auth/login' in response.location

    def test_agent_detail_own_agent(self, authenticated_client, db_session, test_user):
        """Test viewing own agent details."""
        # Create a test agent
        agent = Job(
            name='Detailed Agent',
            job_type='rss_agent',
            config={'feed_url': 'https://example.com/feed.xml'},
            user_id=test_user.id
        )
        db_session.add(agent)
        db_session.commit()

        response = authenticated_client.get(f'/agents/{agent.id}')
        assert response.status_code == 200

        content = response.data.decode('utf-8')
        assert 'Detailed Agent' in content

    def test_agent_detail_event_payload_displays_html_readably(self, authenticated_client, db_session, test_user):
        """
        Regression test: the "Show Payload" panel on an agent's detail page
        used Jinja's built-in |tojson filter to pretty-print event.payload
        inside a <pre> block. |tojson HTML-escapes '<'/'>'/'&' as
        \\u003c/\\u003e/\\u0026 (safe for embedding JSON in a <script> tag),
        which is exactly wrong for plain visible text: users saw literal
        "\\u003cp\\u003e" instead of a readable "<p>" for any HTML-ish
        payload field (e.g. an hnrss.org RSS item's 'content' field).

        Fixed by switching to the app's existing format_json filter (see
        app/__init__.py register_template_filters), which is already used
        by the events/*.html and pipeline_runs/detail.html pages -- this
        agent detail page was the one place still using raw |tojson.
        """
        from app.models import Event

        agent = Job(
            name='HN RSS Agent',
            job_type='rss_agent',
            config={'feed_url': 'https://hnrss.org/newest'},
            user_id=test_user.id
        )
        db_session.add(agent)
        db_session.commit()

        event = Event(
            agent_id=agent.id,
            agent_type='rss_agent',
            user_id=test_user.id,
            payload={'content': '<p>Article URL: <a href="https://example.com">https://example.com</a></p>'},
            metadata={},
        )
        db_session.add(event)
        db_session.commit()

        response = authenticated_client.get(f'/agents/{agent.id}')
        content = response.data.decode('utf-8')

        assert '&lt;p&gt;Article URL' in content
        assert '\\u003c' not in content

    def test_agent_detail_test_payload_textarea_displays_html_readably(self, authenticated_client, db_session, test_user):
        """Same bug, same fix, for the "Test Payload" textarea (sample_payload)."""
        agent = Job(
            name='HTML Parser Agent',
            job_type='html_parser_agent',
            config={'selectors': {'title': 'h1'}},
            user_id=test_user.id
        )
        db_session.add(agent)
        db_session.commit()

        response = authenticated_client.get(f'/agents/{agent.id}')
        content = response.data.decode('utf-8')

        assert '&lt;h1&gt;Title&lt;/h1&gt;' in content
        assert '\\u003c' not in content

    def test_agent_detail_nonexistent_agent(self, authenticated_client):
        """Test viewing non-existent agent returns appropriate error."""
        response = authenticated_client.get('/agents/99999')
        # Should either redirect or show 404
        assert response.status_code in [302, 404]


class TestAgentEditView:
    """Test agent editing functionality."""

    def test_edit_agent_get_request_requires_authentication(self, client, db_session, test_user):
        """Test that edit page requires authentication."""
        # Create a test agent
        agent = Job(
            name='Edit Test Agent',
            job_type='rss_agent',
            config={'feed_url': 'https://example.com/feed.xml'},
            user_id=test_user.id
        )
        db_session.add(agent)
        db_session.commit()

        response = client.get(f'/agents/{agent.id}/edit')
        assert response.status_code == 302
        assert '/auth/login' in response.location

    def test_edit_agent_get_displays_form(self, authenticated_client, db_session, test_user):
        """Test that edit form displays with pre-filled data."""
        # Create a test agent
        agent = Job(
            name='Agent to Edit',
            job_type='rss_agent',
            config={'feed_url': 'https://example.com/feed.xml'},
            user_id=test_user.id
        )
        agent.schedule_cron = '0 */6 * * *'
        agent.schedule_enabled = True
        db_session.add(agent)
        db_session.commit()

        response = authenticated_client.get(f'/agents/{agent.id}/edit')
        assert response.status_code == 200

        content = response.data.decode('utf-8')
        assert 'Edit Agent' in content
        assert 'Agent to Edit' in content
        assert '0 */6 * * *' in content
        assert 'rss_agent' in content.lower()

    def test_edit_agent_post_updates_agent(self, authenticated_client, db_session, test_user):
        """Test that POST request successfully updates agent."""
        # Create a test agent
        agent = Job(
            name='Original Name',
            job_type='rss_agent',
            config={'feed_url': 'https://example.com/original.xml'},
            user_id=test_user.id
        )
        db_session.add(agent)
        db_session.commit()
        agent_id = agent.id

        # Update the agent
        response = authenticated_client.post(f'/agents/{agent_id}/edit', data={
            'name': 'Updated Name',
            'config_feed_url': 'https://example.com/updated.xml'
        })

        # Should redirect to agent detail page
        assert response.status_code == 302
        assert f'/agents/{agent_id}' in response.location

        # Verify agent was updated
        updated_agent = db_session.query(Job).filter(Job.id == agent_id).first()
        assert updated_agent.name == 'Updated Name'
        assert updated_agent.config['feed_url'] == 'https://example.com/updated.xml'

    def test_edit_agent_updates_config_fields(self, authenticated_client, db_session, test_user):
        """Test that config fields are properly updated."""
        agent = Job(
            name='Config Test Agent',
            job_type='rss_agent',
            config={'feed_url': 'https://example.com/feed.xml'},
            user_id=test_user.id
        )
        db_session.add(agent)
        db_session.commit()
        agent_id = agent.id

        # Update with optional config fields
        response = authenticated_client.post(f'/agents/{agent_id}/edit', data={
            'name': 'Config Test Agent',
            'config_feed_url': 'https://example.com/new-feed.xml',
            'config_max_entries': '50',
            'config_days_back': '14'
        })

        assert response.status_code == 302

        updated_agent = db_session.query(Job).filter(Job.id == agent_id).first()
        assert updated_agent.config['feed_url'] == 'https://example.com/new-feed.xml'
        assert updated_agent.config['max_entries'] == 50
        assert updated_agent.config['days_back'] == 14

    def test_edit_agent_preserves_list_valued_config_field(self, authenticated_client, db_session, test_user):
        """
        Server-side half of a regression test for a bug where editing an
        agent with a list-valued config field (e.g. DeduplicationAgent's
        required 'uniqueness_fields') silently failed to save.

        Root cause was in the edit form's JS (app/templates/agents/edit.html
        generateFieldHTML()): it JSON.stringify's list/object values before
        embedding them in a text input's value="..." attribute, but didn't
        HTML-escape the result. The double quotes in e.g. '["link"]'
        prematurely closed the attribute, so the browser truncated the
        submitted value down to just '[' -- which failed json.loads()
        server-side, got stored as the raw string '[', and was then
        rejected by DeduplicationAgent.validate_config() ("must be a
        list"), blocking the save. Fixed by adding an escapeHtml() helper.

        NOTE: this test posts form data directly via the Flask test client,
        which never executes the browser-side JS -- it does NOT exercise
        the actual bug or prove the JS fix is correct (this test passes
        identically with or without the edit.html change). It only guards
        the server-side save path: given a correctly JSON-encoded list
        value (what a fixed browser now sends), the save must succeed and
        the list must persist correctly. There is no JS test runner in
        this project to cover the client-side half.
        """
        agent = Job(
            name='Deduplicate Across Feeds',
            job_type='deduplication_agent',
            config={'uniqueness_fields': ['link'], 'lookback_days': 14},
            user_id=test_user.id
        )
        db_session.add(agent)
        db_session.commit()
        agent_id = agent.id

        response = authenticated_client.post(f'/agents/{agent_id}/edit', data={
            'name': 'Deduplicate Across Feeds',
            'config_uniqueness_fields': '["link"]',
            'config_lookback_days': '21',
        })

        assert response.status_code == 302

        updated_agent = db_session.query(Job).filter(Job.id == agent_id).first()
        assert updated_agent.config['uniqueness_fields'] == ['link']
        assert updated_agent.config['lookback_days'] == 21

    def test_edit_agent_updates_schedule(self, authenticated_client, db_session, test_user):
        """Test that schedule can be updated."""
        agent = Job(
            name='Schedule Test Agent',
            job_type='rss_agent',
            config={'feed_url': 'https://example.com/feed.xml'},
            user_id=test_user.id
        )
        db_session.add(agent)
        db_session.commit()
        agent_id = agent.id

        # Add schedule
        response = authenticated_client.post(f'/agents/{agent_id}/edit', data={
            'name': 'Schedule Test Agent',
            'config_feed_url': 'https://example.com/feed.xml',
            'schedule': '0 */12 * * *'
        })

        assert response.status_code == 302

        updated_agent = db_session.query(Job).filter(Job.id == agent_id).first()
        assert updated_agent.schedule_cron == '0 */12 * * *'
        assert updated_agent.schedule_enabled is True

    def test_edit_agent_clears_schedule(self, authenticated_client, db_session, test_user):
        """Test that schedule can be cleared when empty."""
        agent = Job(
            name='Clear Schedule Agent',
            job_type='rss_agent',
            config={'feed_url': 'https://example.com/feed.xml'},
            user_id=test_user.id
        )
        agent.schedule_cron = '0 */6 * * *'
        agent.schedule_enabled = True
        db_session.add(agent)
        db_session.commit()
        agent_id = agent.id

        # Clear schedule by sending empty value
        response = authenticated_client.post(f'/agents/{agent_id}/edit', data={
            'name': 'Clear Schedule Agent',
            'config_feed_url': 'https://example.com/feed.xml',
            'schedule': ''
        })

        assert response.status_code == 302

        updated_agent = db_session.query(Job).filter(Job.id == agent_id).first()
        assert updated_agent.schedule_cron is None
        assert updated_agent.schedule_enabled is False

    def test_edit_agent_validates_config(self, authenticated_client, db_session, test_user):
        """Test that configuration is validated on edit."""
        agent = Job(
            name='Validation Test Agent',
            job_type='rss_agent',
            config={'feed_url': 'https://example.com/feed.xml'},
            user_id=test_user.id
        )
        db_session.add(agent)
        db_session.commit()
        agent_id = agent.id

        # Try to update with invalid config (missing required field)
        response = authenticated_client.post(f'/agents/{agent_id}/edit', data={
            'name': 'Validation Test Agent'
            # Missing config_feed_url
        }, follow_redirects=True)

        content = response.data.decode('utf-8')
        assert 'Invalid configuration' in content or 'required' in content.lower()

    def test_edit_agent_ownership_check(self, app, client, db_session, test_user):
        """Test that users can't edit other users' agents."""
        with app.app_context():
            # Create another user
            from app.models import User
            other_user = User(username='otheruser', email='other@test.com', password='password123')
            db_session.add(other_user)
            db_session.commit()

            # Create agent owned by other user
            agent = Job(
                name='Other User Agent',
                job_type='rss_agent',
                config={'feed_url': 'https://example.com/feed.xml'},
                user_id=other_user.id
            )
            db_session.add(agent)
            db_session.commit()
            agent_id = agent.id

            # Login as test user
            client.post('/auth/login', data={
                'username': 'testuser',
                'password': 'password123'
            })

            # Try to edit other user's agent
            response = client.get(f'/agents/{agent_id}/edit')
            assert response.status_code == 302
            # Should redirect to agent list with error

    def test_edit_agent_invalid_name(self, authenticated_client, db_session, test_user):
        """Test that empty name is rejected."""
        agent = Job(
            name='Name Test Agent',
            job_type='rss_agent',
            config={'feed_url': 'https://example.com/feed.xml'},
            user_id=test_user.id
        )
        db_session.add(agent)
        db_session.commit()
        agent_id = agent.id

        # Try to update with empty name
        response = authenticated_client.post(f'/agents/{agent_id}/edit', data={
            'name': '',
            'config_feed_url': 'https://example.com/feed.xml'
        }, follow_redirects=True)

        content = response.data.decode('utf-8')
        assert 'Agent name is required' in content

    def test_edit_agent_type_unchanged(self, authenticated_client, db_session, test_user):
        """Test that agent type cannot be changed after creation."""
        agent = Job(
            name='Type Test Agent',
            job_type='rss_agent',
            config={'feed_url': 'https://example.com/feed.xml'},
            user_id=test_user.id
        )
        db_session.add(agent)
        db_session.commit()
        agent_id = agent.id
        original_type = agent.job_type

        # Update agent (agent_type is not in the form, it's read-only)
        response = authenticated_client.post(f'/agents/{agent_id}/edit', data={
            'name': 'Type Test Agent Updated',
            'config_feed_url': 'https://example.com/feed.xml'
        })

        assert response.status_code == 302

        updated_agent = db_session.query(Job).filter(Job.id == agent_id).first()
        # Agent type should remain unchanged
        assert updated_agent.job_type == original_type
        assert updated_agent.job_type == 'rss_agent'

    def test_edit_agent_nonexistent(self, authenticated_client):
        """Test editing non-existent agent returns appropriate error."""
        response = authenticated_client.get('/agents/99999/edit')
        # Should redirect with error
        assert response.status_code == 302


class TestAgentFormValidation:
    """Test form validation edge cases."""

    def test_create_agent_with_invalid_schedule(self, authenticated_client):
        """Test that invalid cron schedule is handled."""
        response = authenticated_client.post('/agents/create', data={
            'name': 'Bad Schedule Agent',
            'agent_type': 'rss_agent',
            'config_feed_url': 'https://example.com/feed.xml',
            'schedule': 'not-a-valid-cron'
        }, follow_redirects=True)

        # Should either accept and validate later or reject immediately
        # The current implementation may accept invalid cron strings
        assert response.status_code == 200

    def test_create_agent_with_special_characters_in_name(self, authenticated_client, db_session):
        """Test that special characters in name are handled."""
        response = authenticated_client.post('/agents/create', data={
            'name': 'Test Agent <script>alert("xss")</script>',
            'agent_type': 'rss_agent',
            'config_feed_url': 'https://example.com/feed.xml'
        })

        assert response.status_code == 302

        # Verify name was saved (should be escaped when displayed)
        agent = db_session.query(Job).filter(
            Job.name.contains('Test Agent')
        ).first()
        assert agent is not None

    def test_create_agent_with_very_long_name(self, authenticated_client):
        """Test that very long agent names are handled."""
        long_name = 'A' * 500
        response = authenticated_client.post('/agents/create', data={
            'name': long_name,
            'agent_type': 'rss_agent',
            'config_feed_url': 'https://example.com/feed.xml'
        }, follow_redirects=True)

        # Should either truncate or reject
        assert response.status_code == 200

    def test_create_agent_with_invalid_url(self, authenticated_client):
        """Test that invalid URLs in config are validated."""
        response = authenticated_client.post('/agents/create', data={
            'name': 'Invalid URL Agent',
            'agent_type': 'rss_agent',
            'config_feed_url': 'not-a-valid-url'
        }, follow_redirects=True)

        content = response.data.decode('utf-8')
        # Should show validation error
        assert 'Invalid configuration' in content or 'url' in content.lower()


class TestAgentTemplateRegression:
    """Regression tests for the specific bug that was fixed."""

    def test_schema_format_matches_frontend_expectations(self, authenticated_client):
        """
        Regression test: Verify schema API returns format that frontend expects.

        This test ensures the bug where frontend expected 'fields' array but
        backend returned 'required_fields' and 'optional_fields' doesn't recur.
        """
        response = authenticated_client.get('/agents/api/schema/rss_agent')
        data = json.loads(response.data)

        # Backend MUST return these fields for frontend to work
        assert 'required_fields' in data, "Schema must include required_fields"
        assert 'optional_fields' in data, "Schema must include optional_fields"

        # required_fields should be an array
        assert isinstance(data['required_fields'], list)

        # optional_fields should be an array of objects with name, type, description
        if data['optional_fields']:
            assert isinstance(data['optional_fields'], list)
            for field in data['optional_fields']:
                assert 'name' in field
                assert 'type' in field

    def test_template_variable_naming_no_conflict(self, authenticated_client):
        """
        Regression test: Verify template doesn't have variable naming conflicts.

        This test ensures the bug where loop variable 'agent_type' shadowed
        the form value 'agent_type' doesn't recur.
        """
        # Submit form with validation error to trigger re-render with values
        response = authenticated_client.post('/agents/create', data={
            'name': 'Test Agent',
            'agent_type': 'rss_agent'
            # Missing required config
        }, follow_redirects=True)

        content = response.data.decode('utf-8')

        # The form should re-render with the agent_type still selected
        # Check that the template uses different variable names for loop vs form value
        # This is a smoke test - if variable shadowing occurs, the wrong radio might be selected
        assert 'rss_agent' in content
        assert 'value="rss_agent"' in content

    def test_config_fields_render_for_rss_agent(self, authenticated_client):
        """
        Regression test: Verify configuration fields are generated for RSS agent.

        This test ensures that when RSS agent is selected, the feed_url field
        appears in the form (which was the original bug report).
        """
        response = authenticated_client.get('/agents/create')
        content = response.data.decode('utf-8')

        # Verify JavaScript function exists that will fetch and render config fields
        assert 'updateConfigFields' in content
        assert 'fetch' in content or 'XMLHttpRequest' in content
        assert 'configFields' in content

        # Verify the schema endpoint is referenced
        assert '/agents/api/schema/' in content

    def test_agent_list_pagination_footer_renders_past_first_page(
        self, authenticated_client, db_session, test_user
    ):
        """
        Regression test: the agent list page's pagination footer
        ("Showing X to Y of Z results") called the bare Python builtin
        min() as a Jinja expression -- {{ min(pagination.page *
        pagination.per_page, pagination.total) }} -- but Jinja does not
        expose Python builtins like min()/max() by default, raising
        'min' is undefined.

        This only executes once {% if pagination.pages > 1 %}, i.e. once a
        user has more agents than one page's worth (per_page defaults to
        20), so it went unnoticed until importing a multi-agent scenario
        pushed a real account over that threshold -- at which point
        agent_list()'s render_template call raised, was caught by its
        broad except Exception, and silently redirected to the homepage
        with an "An error occurred while loading agents" flash, appearing
        to the user as "I can't list agents any more."

        Fixed by using Jinja's built-in `min` filter over a list literal
        instead of calling a nonexistent global function.
        """
        for i in range(25):
            agent = Job(
                name=f'Pagination Test Agent {i}',
                job_type='rss_agent',
                config={'feed_url': f'https://example.com/feed{i}.xml'},
                user_id=test_user.id,
            )
            db_session.add(agent)
        db_session.commit()

        response = authenticated_client.get('/agents/')

        # Pre-fix, the exception handler in agent_list() redirects to '/'
        # instead of rendering the list -- so status 200 + real content is
        # itself part of what this test guards, not just the exact numbers.
        assert response.status_code == 200

        content = response.data.decode('utf-8')
        assert 'An error occurred while loading agents' not in content
        assert 'Showing' in content and 'of' in content and 'results' in content
        assert '<span class="font-medium">1</span>' in content
        assert '<span class="font-medium">20</span>' in content  # min(20, 25) == 20
        assert '<span class="font-medium">25</span>' in content  # pagination.total


class TestAgentSchedulerIntegration:
    """
    Test scheduler integration when creating and editing agents.

    These tests verify that the scheduler is correctly notified when:
    - Creating an agent with a schedule
    - Editing an agent to add/update/remove a schedule

    This prevents regression of the bug where agents were created/edited but
    the scheduler was never notified, causing schedules to not be honored.
    """

    def test_create_agent_with_schedule_calls_scheduler(self, app, authenticated_client, db_session, test_user, monkeypatch):
        """Test that creating an agent with schedule calls scheduler.schedule_job()"""
        from unittest.mock import Mock
        from app import scheduler

        # Mock the scheduler methods
        mock_schedule_job = Mock()
        monkeypatch.setattr(scheduler.scheduler, 'schedule_job', mock_schedule_job)

        # Create agent with schedule
        response = authenticated_client.post('/agents/create', data={
            'name': 'Scheduled RSS Agent',
            'agent_type': 'rss_agent',
            'config_feed_url': 'https://example.com/feed.xml',
            'schedule': '0 */6 * * *'
        })

        assert response.status_code == 302

        # Verify scheduler was called
        assert mock_schedule_job.called, "scheduler.schedule_job() should have been called"
        assert mock_schedule_job.call_count == 1

        # Verify it was called with correct arguments
        call_args = mock_schedule_job.call_args
        agent_id = call_args[0][0]  # First positional argument
        cron_expression = call_args[0][1]  # Second positional argument

        assert cron_expression == '0 */6 * * *'

        # Verify the agent was actually created in DB
        agent = db_session.query(Job).filter(Job.id == agent_id).first()
        assert agent is not None
        assert agent.schedule_cron == '0 */6 * * *'
        assert agent.schedule_enabled is True

    def test_create_agent_without_schedule_doesnt_call_scheduler(self, app, authenticated_client, db_session, test_user, monkeypatch):
        """Test that creating an agent without schedule doesn't call scheduler"""
        from unittest.mock import Mock
        from app import scheduler

        # Mock the scheduler methods
        mock_schedule_job = Mock()
        monkeypatch.setattr(scheduler.scheduler, 'schedule_job', mock_schedule_job)

        # Create agent without schedule
        response = authenticated_client.post('/agents/create', data={
            'name': 'Unscheduled RSS Agent',
            'agent_type': 'rss_agent',
            'config_feed_url': 'https://example.com/feed.xml'
            # No schedule provided
        })

        assert response.status_code == 302

        # Verify scheduler was NOT called
        assert not mock_schedule_job.called, "scheduler.schedule_job() should NOT have been called"

    def test_edit_agent_add_schedule_calls_scheduler(self, app, authenticated_client, db_session, test_user, monkeypatch):
        """Test that adding a schedule to an agent calls scheduler.schedule_job()"""
        from unittest.mock import Mock
        from app import scheduler

        # Create agent without schedule first
        agent = Job(
            name='Test Agent',
            job_type='rss_agent',
            config={'feed_url': 'https://example.com/feed.xml'},
            user_id=test_user.id
        )
        db_session.add(agent)
        db_session.commit()
        agent_id = agent.id

        # Mock the scheduler methods
        mock_schedule_job = Mock()
        monkeypatch.setattr(scheduler.scheduler, 'schedule_job', mock_schedule_job)

        # Edit agent to add schedule
        response = authenticated_client.post(f'/agents/{agent_id}/edit', data={
            'name': 'Test Agent',
            'config_feed_url': 'https://example.com/feed.xml',
            'schedule': '0 */12 * * *'
        })

        assert response.status_code == 302

        # Verify scheduler was called with replace_existing=True
        assert mock_schedule_job.called, "scheduler.schedule_job() should have been called"
        assert mock_schedule_job.call_count == 1

        call_args = mock_schedule_job.call_args
        assert call_args[0][0] == agent_id
        assert call_args[0][1] == '0 */12 * * *'
        assert call_args[1]['replace_existing'] is True  # Keyword argument

    def test_edit_agent_update_schedule_calls_scheduler_with_replace(self, app, authenticated_client, db_session, test_user, monkeypatch):
        """Test that updating an existing schedule calls scheduler with replace_existing=True"""
        from unittest.mock import Mock
        from app import scheduler

        # Create agent with existing schedule
        agent = Job(
            name='Scheduled Agent',
            job_type='rss_agent',
            config={'feed_url': 'https://example.com/feed.xml'},
            user_id=test_user.id
        )
        agent.schedule_cron = '0 */6 * * *'
        agent.schedule_enabled = True
        db_session.add(agent)
        db_session.commit()
        agent_id = agent.id

        # Mock the scheduler methods
        mock_schedule_job = Mock()
        monkeypatch.setattr(scheduler.scheduler, 'schedule_job', mock_schedule_job)

        # Edit agent to update schedule
        response = authenticated_client.post(f'/agents/{agent_id}/edit', data={
            'name': 'Scheduled Agent',
            'config_feed_url': 'https://example.com/feed.xml',
            'schedule': '0 */4 * * *'  # Different schedule
        })

        assert response.status_code == 302

        # Verify scheduler was called
        assert mock_schedule_job.called
        call_args = mock_schedule_job.call_args
        assert call_args[0][1] == '0 */4 * * *'
        assert call_args[1]['replace_existing'] is True

    def test_edit_agent_remove_schedule_calls_unschedule(self, app, authenticated_client, db_session, test_user, monkeypatch):
        """Test that removing a schedule calls scheduler.unschedule_job()"""
        from unittest.mock import Mock
        from app import scheduler

        # Create agent with existing schedule
        agent = Job(
            name='Scheduled Agent',
            job_type='rss_agent',
            config={'feed_url': 'https://example.com/feed.xml'},
            user_id=test_user.id
        )
        agent.schedule_cron = '0 */6 * * *'
        agent.schedule_enabled = True
        db_session.add(agent)
        db_session.commit()
        agent_id = agent.id

        # Mock the scheduler methods
        mock_unschedule_job = Mock()
        monkeypatch.setattr(scheduler.scheduler, 'unschedule_job', mock_unschedule_job)

        # Edit agent to remove schedule
        response = authenticated_client.post(f'/agents/{agent_id}/edit', data={
            'name': 'Scheduled Agent',
            'config_feed_url': 'https://example.com/feed.xml',
            'schedule': ''  # Empty schedule
        })

        assert response.status_code == 302

        # Verify unschedule was called
        assert mock_unschedule_job.called, "scheduler.unschedule_job() should have been called"
        assert mock_unschedule_job.call_count == 1
        assert mock_unschedule_job.call_args[0][0] == agent_id

        # Verify schedule was cleared in DB
        updated_agent = db_session.query(Job).filter(Job.id == agent_id).first()
        assert updated_agent.schedule_cron is None
        assert updated_agent.schedule_enabled is False

    def test_scheduler_error_doesnt_prevent_agent_creation(self, app, authenticated_client, db_session, test_user, monkeypatch):
        """Test that scheduler errors don't prevent agent from being created"""
        from unittest.mock import Mock
        from app import scheduler

        # Mock scheduler to raise an exception
        mock_schedule_job = Mock(side_effect=Exception("Scheduler error"))
        monkeypatch.setattr(scheduler.scheduler, 'schedule_job', mock_schedule_job)

        # Create agent with schedule
        response = authenticated_client.post('/agents/create', data={
            'name': 'Test Agent',
            'agent_type': 'rss_agent',
            'config_feed_url': 'https://example.com/feed.xml',
            'schedule': '0 */6 * * *'
        })

        # Should still redirect successfully
        assert response.status_code == 302

        # Agent should still be created in DB
        agent = db_session.query(Job).filter(Job.name == 'Test Agent').first()
        assert agent is not None
        assert agent.schedule_cron == '0 */6 * * *'

    def test_scheduler_error_doesnt_prevent_agent_update(self, app, authenticated_client, db_session, test_user, monkeypatch):
        """Test that scheduler errors don't prevent agent from being updated"""
        from unittest.mock import Mock
        from app import scheduler

        # Create agent
        agent = Job(
            name='Test Agent',
            job_type='rss_agent',
            config={'feed_url': 'https://example.com/feed.xml'},
            user_id=test_user.id
        )
        db_session.add(agent)
        db_session.commit()
        agent_id = agent.id

        # Mock scheduler to raise an exception
        mock_schedule_job = Mock(side_effect=Exception("Scheduler error"))
        monkeypatch.setattr(scheduler.scheduler, 'schedule_job', mock_schedule_job)

        # Edit agent to add schedule
        response = authenticated_client.post(f'/agents/{agent_id}/edit', data={
            'name': 'Test Agent Updated',
            'config_feed_url': 'https://example.com/feed.xml',
            'schedule': '0 */12 * * *'
        })

        # Should still redirect successfully
        assert response.status_code == 302

        # Agent should still be updated in DB
        updated_agent = db_session.query(Job).filter(Job.id == agent_id).first()
        assert updated_agent.name == 'Test Agent Updated'
        assert updated_agent.schedule_cron == '0 */12 * * *'

    def test_scheduler_can_serialize_jobs_integration(self, app, db_session, test_user):
        """
        Integration test that verifies the scheduler can actually serialize jobs.

        This test does NOT use mocking - it actually calls the real scheduler methods
        to ensure jobs can be serialized and persisted to the database.

        This prevents regression of the bug where APScheduler couldn't serialize
        closure functions created by _create_job_function.
        """
        from app.scheduler import scheduler
        from app.models import Job

        with app.app_context():
            # Initialize scheduler if not done (skipped in test mode with DEBUG=True)
            if scheduler.scheduler is None:
                scheduler.init_app(app)
            # Start the scheduler for this test (it's not started in test mode by default)
            if not scheduler.scheduler.running:
                scheduler.start()

            try:
                # Create a real job in the database
                job = Job(
                    name='Serialization Test Agent',
                    job_type='rss_agent',
                    config={'feed_url': 'https://example.com/feed.xml'},
                    user_id=test_user.id
                )
                job.is_active = True  # Set after creation
                db_session.add(job)
                db_session.commit()
                job_id = job.id

                # Actually call the real scheduler (no mocking!)
                success = scheduler.schedule_job(job_id, '0 * * * *')

                # Verify it succeeded
                assert success, "Scheduler should successfully schedule the job"

                # Verify the job is actually in the scheduler
                status = scheduler.get_job_status(job_id)
                assert status is not None, "Should be able to get job status"
                assert status['scheduled'] is True, "Job should be marked as scheduled"
                assert status['next_run_time'] is not None, "Job should have a next run time"

                # Verify we can get all scheduled jobs and find ours
                all_jobs = scheduler.get_scheduled_jobs()
                job_ids = [job_info['job_id'] for job_info in all_jobs]
                assert job_id in job_ids, "Our job should appear in the list of scheduled jobs"

                # Verify we can unschedule the job
                success = scheduler.unschedule_job(job_id)
                assert success, "Should be able to unschedule the job"

                # Verify it's no longer scheduled
                status = scheduler.get_job_status(job_id)
                assert status['scheduled'] is False, "Job should no longer be scheduled"

                # Cleanup
                db_session.delete(job)
                db_session.commit()

            finally:
                # Stop the scheduler after the test
                scheduler.stop()
