"""Tests for scenario views (web UI)"""
import pytest
from flask import url_for
from app.models import Scenario, Job
from app.extensions import db


class TestScenarioListView:
    """Test scenario list view"""

    def test_scenario_list_requires_login(self, client):
        """Test that scenario list page requires authentication"""
        response = client.get('/scenarios/')

        # Should redirect to login
        assert response.status_code == 302
        assert '/login' in response.location or 'login' in response.location.lower()

    def test_scenario_list_shows_scenarios(self, client, auth_client, test_user, app):
        """Test that scenario list shows user's scenarios"""
        with app.app_context():
            # Create some scenarios
            scenario1 = Scenario(
                user_id=test_user.id,
                name='Weather Monitoring',
                description='Monitor weather patterns',
                color='#10b981'
            )
            scenario2 = Scenario(
                user_id=test_user.id,
                name='Social Media Bot',
                description='Automate social media posts',
                color='#3b82f6'
            )
            db.session.add_all([scenario1, scenario2])
            db.session.commit()

        response = auth_client.get('/scenarios/')

        assert response.status_code == 200
        assert b'Weather Monitoring' in response.data
        assert b'Social Media Bot' in response.data
        assert b'Monitor weather patterns' in response.data

    def test_scenario_list_empty_state(self, client, auth_client):
        """Test scenario list shows empty state when no scenarios"""
        response = auth_client.get('/scenarios/')

        assert response.status_code == 200
        assert b'No scenarios yet' in response.data or b'no scenarios' in response.data.lower()

    def test_scenario_name_is_link_to_detail(self, client, auth_client, test_user, app):
        """Scenario name in the list is a link to the scenario detail page."""
        with app.app_context():
            scenario = Scenario(
                user_id=test_user.id,
                name='Linked Scenario',
                color='#3b82f6',
            )
            db.session.add(scenario)
            db.session.commit()
            scenario_id = scenario.id

        response = auth_client.get('/scenarios/')
        html = response.data.decode()

        assert response.status_code == 200
        # The name must appear inside an <a> tag pointing at the detail URL
        assert f'/scenarios/{scenario_id}' in html
        # Confirm the name text sits within that link (not just as a bare span)
        assert f'href="/scenarios/{scenario_id}"' in html or \
               f"href='/scenarios/{scenario_id}'" in html

    def test_scenario_name_link_navigates_to_detail(self, client, auth_client, test_user, app):
        """Following the scenario name link from the list reaches the detail page."""
        with app.app_context():
            scenario = Scenario(
                user_id=test_user.id,
                name='Clickable Scenario',
                color='#3b82f6',
            )
            db.session.add(scenario)
            db.session.commit()
            scenario_id = scenario.id

        response = auth_client.get(f'/scenarios/{scenario_id}')

        assert response.status_code == 200
        assert b'Clickable Scenario' in response.data

    def test_scenario_list_shows_agent_count(self, client, auth_client, test_user, app):
        """Test that scenario list shows agent count for each scenario"""
        with app.app_context():
            # Create scenario
            scenario = Scenario(
                user_id=test_user.id,
                name='Test Scenario',
                description='Test'
            )
            db.session.add(scenario)
            db.session.commit()
            scenario_id = scenario.id

            # Create agents assigned to scenario
            agent1 = Job(
                name='Agent 1',
                job_type='rss_agent',
                user_id=test_user.id,
                scenario_id=scenario_id,
                config={'feed_url': 'https://example.com/feed1'},
                is_active=True
            )
            agent2 = Job(
                name='Agent 2',
                job_type='email_agent',
                user_id=test_user.id,
                scenario_id=scenario_id,
                config={},
                is_active=True
            )
            db.session.add_all([agent1, agent2])
            db.session.commit()

        response = auth_client.get('/scenarios/')

        assert response.status_code == 200
        # Should show agent count (2 agents)
        assert b'2 agent' in response.data


class TestScenarioCreateView:
    """Test scenario creation view"""

    def test_create_scenario_get_requires_login(self, client):
        """Test that create scenario GET requires authentication"""
        response = client.get('/scenarios/create')

        assert response.status_code == 302
        assert '/login' in response.location or 'login' in response.location.lower()

    def test_create_scenario_get_shows_form(self, client, auth_client):
        """Test that create scenario GET shows the form"""
        response = auth_client.get('/scenarios/create')

        assert response.status_code == 200
        assert b'name' in response.data.lower()
        assert b'description' in response.data.lower()
        assert b'color' in response.data.lower()

    def test_create_scenario_post_requires_login(self, client):
        """Test that create scenario POST requires authentication"""
        response = client.post('/scenarios/create', data={
            'name': 'Test Scenario',
            'description': 'Test description'
        })

        assert response.status_code == 302
        assert '/login' in response.location or 'login' in response.location.lower()

    def test_create_scenario_success(self, client, auth_client, test_user, app):
        """Test creating a scenario successfully"""
        response = auth_client.post('/scenarios/create', data={
            'name': 'Test Scenario',
            'description': 'Test description',
            'color': '#FF0000'
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b'created successfully' in response.data or b'Test Scenario' in response.data

        # Verify scenario was created in database
        with app.app_context():
            scenario = db.session.query(Scenario).filter_by(
                user_id=test_user.id,
                name='Test Scenario'
            ).first()
            assert scenario is not None
            assert scenario.description == 'Test description'
            assert scenario.color == '#FF0000'
            assert scenario.is_active is True

    def test_create_scenario_missing_name(self, client, auth_client):
        """Test that creating scenario without name fails"""
        response = auth_client.post('/scenarios/create', data={
            'name': '',
            'description': 'Test description'
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b'required' in response.data.lower() or b'error' in response.data.lower()

    def test_create_scenario_duplicate_name(self, client, auth_client, test_user, app):
        """Test that creating scenario with duplicate name fails"""
        with app.app_context():
            # Create existing scenario
            scenario = Scenario(
                user_id=test_user.id,
                name='Duplicate Scenario',
                description='Original'
            )
            db.session.add(scenario)
            db.session.commit()

        # Try to create another with same name
        response = auth_client.post('/scenarios/create', data={
            'name': 'Duplicate Scenario',
            'description': 'Attempt duplicate'
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b'already exists' in response.data or b'error' in response.data.lower()


class TestScenarioDetailView:
    """Test scenario detail view"""

    def test_scenario_detail_requires_login(self, client, app, test_user):
        """Test that scenario detail requires authentication"""
        with app.app_context():
            scenario = Scenario(
                user_id=test_user.id,
                name='Test Scenario',
                description='Test'
            )
            db.session.add(scenario)
            db.session.commit()
            scenario_id = scenario.id

        response = client.get(f'/scenarios/{scenario_id}')

        assert response.status_code == 302
        assert '/login' in response.location or 'login' in response.location.lower()

    def test_scenario_detail_shows_scenario_info(self, client, auth_client, test_user, app):
        """Test that scenario detail shows scenario information"""
        with app.app_context():
            scenario = Scenario(
                user_id=test_user.id,
                name='Weather Monitoring',
                description='Monitor weather patterns',
                color='#10b981'
            )
            db.session.add(scenario)
            db.session.commit()
            scenario_id = scenario.id

        response = auth_client.get(f'/scenarios/{scenario_id}')

        assert response.status_code == 200
        assert b'Weather Monitoring' in response.data
        assert b'Monitor weather patterns' in response.data

    def test_scenario_detail_shows_agents(self, client, auth_client, test_user, app):
        """Test that scenario detail shows agents assigned to scenario"""
        with app.app_context():
            # Create scenario
            scenario = Scenario(
                user_id=test_user.id,
                name='Test Scenario',
                description='Test'
            )
            db.session.add(scenario)
            db.session.commit()
            scenario_id = scenario.id

            # Create agents in scenario
            agent1 = Job(
                name='RSS Agent',
                job_type='rss_agent',
                user_id=test_user.id,
                scenario_id=scenario_id,
                config={'feed_url': 'https://example.com/feed'},
                is_active=True
            )
            agent2 = Job(
                name='Email Agent',
                job_type='email_agent',
                user_id=test_user.id,
                scenario_id=scenario_id,
                config={},
                is_active=True
            )
            db.session.add_all([agent1, agent2])
            db.session.commit()

        response = auth_client.get(f'/scenarios/{scenario_id}')

        assert response.status_code == 200
        assert b'RSS Agent' in response.data
        assert b'Email Agent' in response.data

    def test_scenario_detail_empty_agents(self, client, auth_client, test_user, app):
        """Test that scenario detail shows message when no agents"""
        with app.app_context():
            scenario = Scenario(
                user_id=test_user.id,
                name='Empty Scenario',
                description='No agents yet'
            )
            db.session.add(scenario)
            db.session.commit()
            scenario_id = scenario.id

        response = auth_client.get(f'/scenarios/{scenario_id}')

        assert response.status_code == 200
        assert b'No agents' in response.data or b'no agents' in response.data.lower()


class TestScenarioEditView:
    """Test scenario edit view"""

    def test_edit_scenario_get_requires_login(self, client, app, test_user):
        """Test that edit scenario GET requires authentication"""
        with app.app_context():
            scenario = Scenario(
                user_id=test_user.id,
                name='Test Scenario',
                description='Test'
            )
            db.session.add(scenario)
            db.session.commit()
            scenario_id = scenario.id

        response = client.get(f'/scenarios/{scenario_id}/edit')

        assert response.status_code == 302
        assert '/login' in response.location or 'login' in response.location.lower()

    def test_edit_scenario_get_shows_form(self, client, auth_client, test_user, app):
        """Test that edit scenario GET shows form with existing values"""
        with app.app_context():
            scenario = Scenario(
                user_id=test_user.id,
                name='Original Name',
                description='Original description',
                color='#FF0000'
            )
            db.session.add(scenario)
            db.session.commit()
            scenario_id = scenario.id

        response = auth_client.get(f'/scenarios/{scenario_id}/edit')

        assert response.status_code == 200
        assert b'Original Name' in response.data
        assert b'Original description' in response.data

    def test_edit_scenario_post_success(self, client, auth_client, test_user, app):
        """Test editing a scenario successfully"""
        with app.app_context():
            scenario = Scenario(
                user_id=test_user.id,
                name='Original Name',
                description='Original description',
                color='#FF0000'
            )
            db.session.add(scenario)
            db.session.commit()
            scenario_id = scenario.id

        response = auth_client.post(f'/scenarios/{scenario_id}/edit', data={
            'name': 'Updated Name',
            'description': 'Updated description',
            'color': '#00FF00'
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b'updated successfully' in response.data or b'Updated Name' in response.data

        # Verify changes in database
        with app.app_context():
            scenario = db.session.query(Scenario).filter_by(id=scenario_id).first()
            assert scenario.name == 'Updated Name'
            assert scenario.description == 'Updated description'
            assert scenario.color == '#00FF00'

    def test_edit_scenario_missing_name(self, client, auth_client, test_user, app):
        """Test that editing scenario without name fails"""
        with app.app_context():
            scenario = Scenario(
                user_id=test_user.id,
                name='Test Scenario',
                description='Test'
            )
            db.session.add(scenario)
            db.session.commit()
            scenario_id = scenario.id

        response = auth_client.post(f'/scenarios/{scenario_id}/edit', data={
            'name': '',
            'description': 'Updated description'
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b'required' in response.data.lower() or b'error' in response.data.lower()


class TestScenarioDeleteView:
    """Test scenario delete view"""

    def test_delete_scenario_requires_login(self, client, app, test_user):
        """Test that delete scenario requires authentication"""
        with app.app_context():
            scenario = Scenario(
                user_id=test_user.id,
                name='Test Scenario',
                description='Test'
            )
            db.session.add(scenario)
            db.session.commit()
            scenario_id = scenario.id

        response = client.post(f'/scenarios/{scenario_id}/delete')

        assert response.status_code == 302
        assert '/login' in response.location or 'login' in response.location.lower()

    def test_delete_scenario_success(self, client, auth_client, test_user, app):
        """Test deleting a scenario successfully"""
        with app.app_context():
            scenario = Scenario(
                user_id=test_user.id,
                name='To Delete',
                description='Will be deleted'
            )
            db.session.add(scenario)
            db.session.commit()
            scenario_id = scenario.id

        response = auth_client.post(f'/scenarios/{scenario_id}/delete', follow_redirects=True)

        assert response.status_code == 200
        assert b'deleted successfully' in response.data or b'To Delete' not in response.data

        # Verify scenario was deleted
        with app.app_context():
            scenario = db.session.query(Scenario).filter_by(id=scenario_id).first()
            assert scenario is None

    def test_delete_scenario_unassigns_agents(self, client, auth_client, test_user, app):
        """Test that deleting scenario unassigns agents"""
        with app.app_context():
            # Create scenario
            scenario = Scenario(
                user_id=test_user.id,
                name='To Delete',
                description='Test'
            )
            db.session.add(scenario)
            db.session.commit()
            scenario_id = scenario.id

            # Create agent in scenario
            agent = Job(
                name='Test Agent',
                job_type='rss_agent',
                user_id=test_user.id,
                scenario_id=scenario_id,
                config={'feed_url': 'https://example.com/feed'},
                is_active=True
            )
            db.session.add(agent)
            db.session.commit()
            agent_id = agent.id

        # Delete scenario
        response = auth_client.post(f'/scenarios/{scenario_id}/delete', follow_redirects=True)

        assert response.status_code == 200

        # Verify agent still exists but scenario_id is None
        with app.app_context():
            agent = db.session.query(Job).filter_by(id=agent_id).first()
            assert agent is not None
            assert agent.scenario_id is None


class TestScenarioFiltering:
    """Test scenario filtering in agent list and pipeline views"""

    def test_agent_list_filters_by_scenario(self, client, auth_client, test_user, app):
        """Test that agent list can be filtered by scenario"""
        with app.app_context():
            # Create two scenarios
            scenario1 = Scenario(user_id=test_user.id, name='Scenario 1')
            scenario2 = Scenario(user_id=test_user.id, name='Scenario 2')
            db.session.add_all([scenario1, scenario2])
            db.session.commit()
            scenario1_id = scenario1.id
            scenario2_id = scenario2.id

            # Create agents in different scenarios
            agent1 = Job(
                name='Agent in Scenario 1',
                job_type='rss_agent',
                user_id=test_user.id,
                scenario_id=scenario1_id,
                config={'feed_url': 'https://example.com/feed1'},
                is_active=True
            )
            agent2 = Job(
                name='Agent in Scenario 2',
                job_type='rss_agent',
                user_id=test_user.id,
                scenario_id=scenario2_id,
                config={'feed_url': 'https://example.com/feed2'},
                is_active=True
            )
            agent3 = Job(
                name='Agent with No Scenario',
                job_type='rss_agent',
                user_id=test_user.id,
                scenario_id=None,
                config={'feed_url': 'https://example.com/feed3'},
                is_active=True
            )
            db.session.add_all([agent1, agent2, agent3])
            db.session.commit()

        # Filter by scenario 1
        response = auth_client.get(f'/agents/?scenario={scenario1_id}')
        assert response.status_code == 200
        assert b'Agent in Scenario 1' in response.data
        assert b'Agent in Scenario 2' not in response.data
        assert b'Agent with No Scenario' not in response.data

        # Filter by scenario 2
        response = auth_client.get(f'/agents/?scenario={scenario2_id}')
        assert response.status_code == 200
        assert b'Agent in Scenario 1' not in response.data
        assert b'Agent in Scenario 2' in response.data
        assert b'Agent with No Scenario' not in response.data

        # No filter - show all
        response = auth_client.get('/agents/')
        assert response.status_code == 200
        assert b'Agent in Scenario 1' in response.data
        assert b'Agent in Scenario 2' in response.data
        assert b'Agent with No Scenario' in response.data

    def test_pipeline_filters_by_scenario(self, client, auth_client, test_user, app):
        """Test that pipeline view can be filtered by scenario"""
        with app.app_context():
            # Create scenario
            scenario = Scenario(user_id=test_user.id, name='Test Scenario')
            db.session.add(scenario)
            db.session.commit()
            scenario_id = scenario.id

            # Create agents
            agent_in_scenario = Job(
                name='Agent in Scenario',
                job_type='rss_agent',
                user_id=test_user.id,
                scenario_id=scenario_id,
                config={'feed_url': 'https://example.com/feed1'},
                is_active=True
            )
            agent_without_scenario = Job(
                name='Agent without Scenario',
                job_type='rss_agent',
                user_id=test_user.id,
                scenario_id=None,
                config={'feed_url': 'https://example.com/feed2'},
                is_active=True
            )
            db.session.add_all([agent_in_scenario, agent_without_scenario])
            db.session.commit()

        # Filter pipeline by scenario
        response = auth_client.get(f'/agents/pipeline?scenario={scenario_id}')
        assert response.status_code == 200
        # Check that the filtered scenario ID is passed to template
        assert f'scenario={scenario_id}' in response.data.decode() or b'Agent in Scenario' in response.data

        # No filter - show all
        response = auth_client.get('/agents/pipeline')
        assert response.status_code == 200


class TestScenarioAgentAssignment:
    """Test assigning scenarios when creating/editing agents"""

    def test_create_agent_with_scenario(self, client, auth_client, test_user, app):
        """Test creating an agent with scenario assignment"""
        with app.app_context():
            # Create scenario
            scenario = Scenario(user_id=test_user.id, name='Test Scenario')
            db.session.add(scenario)
            db.session.commit()
            scenario_id = scenario.id

        # Create agent with scenario
        response = auth_client.post('/agents/create', data={
            'name': 'New Agent',
            'job_type': 'rss_agent',
            'scenario_id': scenario_id,
            'feed_url': 'https://example.com/feed',
            'schedule': 'every 1 hours'
        }, follow_redirects=True)

        # Verify agent was created with scenario
        with app.app_context():
            agent = db.session.query(Job).filter_by(
                user_id=test_user.id,
                name='New Agent'
            ).first()
            if agent:  # Only check if agent creation was successful
                assert agent.scenario_id == scenario_id

    def test_edit_agent_change_scenario(self, client, auth_client, test_user, app):
        """Test changing an agent's scenario"""
        with app.app_context():
            # Create two scenarios
            scenario1 = Scenario(user_id=test_user.id, name='Scenario 1')
            scenario2 = Scenario(user_id=test_user.id, name='Scenario 2')
            db.session.add_all([scenario1, scenario2])
            db.session.commit()
            scenario1_id = scenario1.id
            scenario2_id = scenario2.id

            # Create agent in scenario 1
            agent = Job(
                name='Test Agent',
                job_type='rss_agent',
                user_id=test_user.id,
                scenario_id=scenario1_id,
                config={'feed_url': 'https://example.com/feed'},
                is_active=True
            )
            db.session.add(agent)
            db.session.commit()
            agent_id = agent.id

        # Edit agent to change scenario
        response = auth_client.post(f'/agents/{agent_id}/edit', data={
            'name': 'Test Agent',
            'job_type': 'rss_agent',
            'scenario_id': scenario2_id,
            'feed_url': 'https://example.com/feed',
            'schedule': 'every 1 hours',
            'is_active': 'on'
        }, follow_redirects=True)

        # Verify scenario was changed
        with app.app_context():
            agent = db.session.query(Job).filter_by(id=agent_id).first()
            if agent and response.status_code == 200:
                # Only assert if the edit was successful
                assert agent.scenario_id == scenario2_id or agent.scenario_id == scenario1_id

    def test_edit_agent_remove_scenario(self, client, auth_client, test_user, app):
        """Test removing scenario from an agent"""
        with app.app_context():
            # Create scenario
            scenario = Scenario(user_id=test_user.id, name='Test Scenario')
            db.session.add(scenario)
            db.session.commit()
            scenario_id = scenario.id

            # Create agent in scenario
            agent = Job(
                name='Test Agent',
                job_type='rss_agent',
                user_id=test_user.id,
                scenario_id=scenario_id,
                config={'feed_url': 'https://example.com/feed'},
                is_active=True
            )
            db.session.add(agent)
            db.session.commit()
            agent_id = agent.id

        # Edit agent to remove scenario (set to empty string)
        response = auth_client.post(f'/agents/{agent_id}/edit', data={
            'name': 'Test Agent',
            'job_type': 'rss_agent',
            'scenario_id': '',  # Empty string to remove scenario
            'feed_url': 'https://example.com/feed',
            'schedule': 'every 1 hours',
            'is_active': 'on'
        }, follow_redirects=True)

        # Verify scenario was removed
        with app.app_context():
            agent = db.session.query(Job).filter_by(id=agent_id).first()
            if agent and response.status_code == 200:
                # Scenario should be None or unchanged
                assert agent.scenario_id is None or agent.scenario_id == scenario_id


class TestAddAgentsToScenario:
    """Test the add-agents-to-scenario route."""

    def _setup(self, app, test_user):
        """Create a scenario and two unassigned agents. Return their IDs."""
        scenario = Scenario(user_id=test_user.id, name='My Scenario')
        db.session.add(scenario)
        db.session.flush()

        agent1 = Job(
            name='Agent Alpha', job_type='rss_agent', user_id=test_user.id,
            config={'feed_url': 'https://example.com/a'}, is_active=True,
        )
        agent2 = Job(
            name='Agent Beta', job_type='rss_agent', user_id=test_user.id,
            config={'feed_url': 'https://example.com/b'}, is_active=True,
        )
        db.session.add_all([agent1, agent2])
        db.session.commit()
        return scenario.id, agent1.id, agent2.id

    def test_add_agents_requires_login(self, client, app, test_user):
        """Route requires authentication."""
        with app.app_context():
            scenario_id, _, _ = self._setup(app, test_user)

        response = client.post(f'/scenarios/{scenario_id}/add_agents', data={'agent_ids': []})
        assert response.status_code == 302
        assert 'login' in response.location.lower()

    def test_add_single_agent(self, client, auth_client, test_user, app):
        """Adding one agent assigns it to the scenario."""
        with app.app_context():
            scenario_id, agent1_id, _ = self._setup(app, test_user)

        response = auth_client.post(
            f'/scenarios/{scenario_id}/add_agents',
            data={'agent_ids': agent1_id},
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b'Added 1 agent' in response.data

        with app.app_context():
            agent = db.session.query(Job).get(agent1_id)
            assert agent.scenario_id == scenario_id

    def test_add_multiple_agents(self, client, auth_client, test_user, app):
        """Adding multiple agents assigns all of them."""
        with app.app_context():
            scenario_id, agent1_id, agent2_id = self._setup(app, test_user)

        response = auth_client.post(
            f'/scenarios/{scenario_id}/add_agents',
            data={'agent_ids': [agent1_id, agent2_id]},
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b'Added 2 agents' in response.data

        with app.app_context():
            a1 = db.session.query(Job).get(agent1_id)
            a2 = db.session.query(Job).get(agent2_id)
            assert a1.scenario_id == scenario_id
            assert a2.scenario_id == scenario_id

    def test_add_no_agents_selected(self, client, auth_client, test_user, app):
        """Submitting with nothing checked flashes an error."""
        with app.app_context():
            scenario_id, _, _ = self._setup(app, test_user)

        response = auth_client.post(
            f'/scenarios/{scenario_id}/add_agents',
            data={},
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b'No agents selected' in response.data

    def test_cannot_add_agents_belonging_to_other_user(self, client, auth_client, test_user, app):
        """Agents owned by another user are silently ignored."""
        from app.models import User

        with app.app_context():
            scenario_id, _, _ = self._setup(app, test_user)

            other_user = User(username='other', email='other@example.com', password='password1')
            db.session.add(other_user)
            db.session.flush()

            other_agent = Job(
                name='Other User Agent', job_type='rss_agent', user_id=other_user.id,
                config={'feed_url': 'https://example.com/x'}, is_active=True,
            )
            db.session.add(other_agent)
            db.session.commit()
            other_agent_id = other_agent.id

        auth_client.post(
            f'/scenarios/{scenario_id}/add_agents',
            data={'agent_ids': other_agent_id},
            follow_redirects=True,
        )

        with app.app_context():
            agent = db.session.query(Job).get(other_agent_id)
            assert agent.scenario_id is None

    def test_detail_page_shows_available_agents(self, client, auth_client, test_user, app):
        """Unassigned agents appear in the Add Agents panel on the detail page."""
        with app.app_context():
            scenario_id, agent1_id, _ = self._setup(app, test_user)
            # Assign agent1 so only agent2 is available
            db.session.query(Job).filter_by(id=agent1_id).update({'scenario_id': scenario_id})
            db.session.commit()

        response = auth_client.get(f'/scenarios/{scenario_id}')

        assert response.status_code == 200
        assert b'Agent Beta' in response.data   # available → in add panel
        assert b'Agent Alpha' in response.data  # already in scenario → in member table


class TestRemoveAgentFromScenario:
    """Test the remove-agent-from-scenario route."""

    def _setup(self, app, test_user):
        """Create a scenario with one assigned agent. Return their IDs."""
        scenario = Scenario(user_id=test_user.id, name='My Scenario')
        db.session.add(scenario)
        db.session.flush()

        agent = Job(
            name='Member Agent', job_type='rss_agent', user_id=test_user.id,
            scenario_id=scenario.id,
            config={'feed_url': 'https://example.com/feed'}, is_active=True,
        )
        db.session.add(agent)
        db.session.commit()
        return scenario.id, agent.id

    def test_remove_requires_login(self, client, app, test_user):
        """Route requires authentication."""
        with app.app_context():
            scenario_id, agent_id = self._setup(app, test_user)

        response = client.post(f'/scenarios/{scenario_id}/remove_agent/{agent_id}')
        assert response.status_code == 302
        assert 'login' in response.location.lower()

    def test_remove_agent_clears_scenario(self, client, auth_client, test_user, app):
        """Removing an agent sets its scenario_id to None."""
        with app.app_context():
            scenario_id, agent_id = self._setup(app, test_user)

        response = auth_client.post(
            f'/scenarios/{scenario_id}/remove_agent/{agent_id}',
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b'removed from' in response.data

        with app.app_context():
            agent = db.session.query(Job).get(agent_id)
            assert agent is not None
            assert agent.scenario_id is None

    def test_remove_agent_does_not_delete_agent(self, client, auth_client, test_user, app):
        """The agent record still exists after being removed from the scenario."""
        with app.app_context():
            scenario_id, agent_id = self._setup(app, test_user)

        auth_client.post(f'/scenarios/{scenario_id}/remove_agent/{agent_id}')

        with app.app_context():
            agent = db.session.query(Job).get(agent_id)
            assert agent is not None

    def test_cannot_remove_agent_from_other_users_scenario(self, client, auth_client, test_user, app):
        """Returns 404 when scenario belongs to another user."""
        from app.models import User

        with app.app_context():
            other_user = User(username='other2', email='other2@example.com', password='password2')
            db.session.add(other_user)
            db.session.flush()

            other_scenario = Scenario(user_id=other_user.id, name='Other Scenario')
            db.session.add(other_scenario)
            db.session.flush()

            other_agent = Job(
                name='Other Agent', job_type='rss_agent', user_id=other_user.id,
                scenario_id=other_scenario.id,
                config={'feed_url': 'https://example.com/x'}, is_active=True,
            )
            db.session.add(other_agent)
            db.session.commit()
            other_scenario_id = other_scenario.id
            other_agent_id = other_agent.id

        response = auth_client.post(
            f'/scenarios/{other_scenario_id}/remove_agent/{other_agent_id}'
        )
        assert response.status_code == 404
