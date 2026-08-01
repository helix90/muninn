"""Tests for the pipeline editor API (Feature: interactive canvas editor)."""

import json
import pytest

from app.extensions import db
from app.models import AgentLink, Job, Scenario


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def scenario(app, test_user):
    with app.app_context():
        s = Scenario(name='Test Scenario', user_id=test_user.id)
        db.session.add(s)
        db.session.commit()
        return s.id


@pytest.fixture
def agents(app, test_user, scenario):
    """Three agents in the test scenario: source → transform → action."""
    with app.app_context():
        src = Job(name='RSS Source', job_type='rss_agent',
                  config={'feed_url': 'https://example.com/f.xml'},
                  user_id=test_user.id, scenario_id=scenario)
        trx = Job(name='Filter', job_type='filter_agent',
                  config={'rules': [{'type': 'exists', 'field': 'title'}], 'match_all': True},
                  user_id=test_user.id, scenario_id=scenario)
        act = Job(name='Email Action', job_type='email_agent',
                  config={'to': 'a@b.com', 'subject': 'x', 'body': 'y'},
                  user_id=test_user.id, scenario_id=scenario)
        db.session.add_all([src, trx, act])
        db.session.commit()
        return src.id, trx.id, act.id


@pytest.fixture
def link(app, agents):
    """A single link from source → transform."""
    with app.app_context():
        src_id, trx_id, _ = agents
        lk = AgentLink(source_agent_id=src_id, target_agent_id=trx_id)
        db.session.add(lk)
        db.session.commit()
        return lk.id


def _put(auth_client, scenario_id, body):
    return auth_client.put(
        f'/scenarios/{scenario_id}/editor/graph',
        data=json.dumps(body),
        content_type='application/json',
    )


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class TestEditorAuth:
    def test_editor_page_requires_login(self, client, scenario):
        resp = client.get(f'/scenarios/{scenario}/editor')
        assert resp.status_code in (302, 401)

    def test_graph_get_requires_login(self, client, scenario):
        resp = client.get(f'/scenarios/{scenario}/editor/graph')
        assert resp.status_code in (302, 401)

    def test_graph_put_requires_login(self, client, scenario):
        resp = client.put(f'/scenarios/{scenario}/editor/graph',
                          data='{}', content_type='application/json')
        assert resp.status_code in (302, 401)

    def test_graph_get_wrong_user_404(self, auth_client2, scenario):
        resp = auth_client2.get(f'/scenarios/{scenario}/editor/graph')
        assert resp.status_code == 404

    def test_editor_page_wrong_user_404(self, auth_client2, scenario):
        resp = auth_client2.get(f'/scenarios/{scenario}/editor')
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Editor canvas page
# ---------------------------------------------------------------------------

class TestEditorPage:
    def test_returns_200(self, auth_client, scenario):
        resp = auth_client.get(f'/scenarios/{scenario}/editor')
        assert resp.status_code == 200

    def test_contains_react_root(self, auth_client, scenario):
        resp = auth_client.get(f'/scenarios/{scenario}/editor')
        assert b'rf-root' in resp.data

    def test_contains_scenario_name(self, auth_client, scenario):
        resp = auth_client.get(f'/scenarios/{scenario}/editor')
        assert b'Test Scenario' in resp.data

    def test_contains_reactflow_css(self, auth_client, scenario):
        resp = auth_client.get(f'/scenarios/{scenario}/editor')
        assert b'reactflow' in resp.data


# ---------------------------------------------------------------------------
# GET /editor/graph
# ---------------------------------------------------------------------------

class TestGraphGet:
    def test_returns_scenario_info(self, auth_client, scenario):
        resp = auth_client.get(f'/scenarios/{scenario}/editor/graph')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['scenario']['id'] == scenario
        assert data['scenario']['name'] == 'Test Scenario'

    def test_returns_agents(self, auth_client, scenario, agents):
        resp = auth_client.get(f'/scenarios/{scenario}/editor/graph')
        data = resp.get_json()
        assert len(data['agents']) == 3

    def test_agent_has_required_fields(self, auth_client, scenario, agents):
        resp = auth_client.get(f'/scenarios/{scenario}/editor/graph')
        data = resp.get_json()
        agent = data['agents'][0]
        for field in ('id', 'name', 'job_type', 'category', 'position',
                      'can_receive_events', 'can_create_events', 'is_active'):
            assert field in agent, f'Missing field: {field}'

    def test_source_agent_category(self, auth_client, scenario, agents):
        resp = auth_client.get(f'/scenarios/{scenario}/editor/graph')
        data = resp.get_json()
        src = next(a for a in data['agents'] if a['job_type'] == 'rss_agent')
        assert src['category'] == 'source'
        assert src['can_receive_events'] is False
        assert src['can_create_events'] is True

    def test_transform_agent_category(self, auth_client, scenario, agents):
        resp = auth_client.get(f'/scenarios/{scenario}/editor/graph')
        data = resp.get_json()
        trx = next(a for a in data['agents'] if a['job_type'] == 'filter_agent')
        assert trx['category'] == 'transform'

    def test_action_agent_category(self, auth_client, scenario, agents):
        resp = auth_client.get(f'/scenarios/{scenario}/editor/graph')
        data = resp.get_json()
        act = next(a for a in data['agents'] if a['job_type'] == 'email_agent')
        assert act['category'] == 'action'
        assert act['can_receive_events'] is True
        assert act['can_create_events'] is False

    def test_returns_links(self, auth_client, scenario, agents, link):
        resp = auth_client.get(f'/scenarios/{scenario}/editor/graph')
        data = resp.get_json()
        assert len(data['links']) == 1
        lk = data['links'][0]
        assert 'id' in lk and 'source' in lk and 'target' in lk

    def test_auto_layout_assigns_positions(self, auth_client, app, scenario, agents):
        resp = auth_client.get(f'/scenarios/{scenario}/editor/graph')
        data = resp.get_json()
        for agent in data['agents']:
            pos = agent['position']
            assert pos is not None, f"Agent {agent['id']} has no position"
            assert 'x' in pos and 'y' in pos

    def test_positions_persisted_after_auto_layout(self, auth_client, app, db_session,
                                                    scenario, agents):
        auth_client.get(f'/scenarios/{scenario}/editor/graph')
        src_id = agents[0]
        db_session.expire_all()
        job = db_session.query(Job).get(src_id)
        assert job.canvas_position is not None
        assert 'x' in job.canvas_position

    def test_reset_layout_recomputes_positions(self, auth_client, app, db_session,
                                               scenario, agents):
        # Set a fixed position
        with app.app_context():
            db_session.query(Job).filter_by(id=agents[0]).update(
                {'canvas_position': {'x': 9999, 'y': 9999}}
            )
            db_session.commit()

        resp = auth_client.get(f'/scenarios/{scenario}/editor/graph?reset_layout=1')
        data = resp.get_json()
        src = next(a for a in data['agents'] if a['id'] == agents[0])
        assert src['position']['x'] != 9999

    def test_empty_scenario_returns_empty_lists(self, auth_client, scenario):
        resp = auth_client.get(f'/scenarios/{scenario}/editor/graph')
        data = resp.get_json()
        assert data['agents'] == []
        assert data['links'] == []


# ---------------------------------------------------------------------------
# PUT /editor/graph — positions
# ---------------------------------------------------------------------------

class TestGraphPutPositions:
    def test_save_positions(self, auth_client, app, db_session, scenario, agents):
        src_id, trx_id, act_id = agents
        body = {
            'positions': {
                str(src_id): {'x': 100, 'y': 200},
                str(trx_id): {'x': 400, 'y': 200},
                str(act_id): {'x': 700, 'y': 200},
            },
            'add_links': [],
            'remove_links': [],
        }
        resp = _put(auth_client, scenario, body)
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'ok'

        db_session.expire_all()
        job = db_session.query(Job).get(src_id)
        assert job.canvas_position == {'x': 100, 'y': 200}

    def test_ignores_positions_for_wrong_user_agents(self, auth_client, app, test_user2,
                                                      scenario, agents, db_session):
        with app.app_context():
            other_job = Job(name='Other', job_type='rss_agent',
                            config={'feed_url': 'x'}, user_id=test_user2.id)
            db_session.add(other_job)
            db_session.commit()
            other_id = other_job.id

        body = {'positions': {str(other_id): {'x': 50, 'y': 50}},
                'add_links': [], 'remove_links': []}
        resp = _put(auth_client, scenario, body)
        assert resp.status_code == 200
        # No error, just ignored
        db_session.expire_all()
        job = db_session.query(Job).get(other_id)
        assert job.canvas_position is None


# ---------------------------------------------------------------------------
# PUT /editor/graph — add links
# ---------------------------------------------------------------------------

class TestGraphPutAddLinks:
    def test_add_link(self, auth_client, app, db_session, scenario, agents):
        src_id, trx_id, _ = agents
        body = {'positions': {}, 'add_links': [{'source': src_id, 'target': trx_id}],
                'remove_links': []}
        resp = _put(auth_client, scenario, body)
        data = resp.get_json()
        assert data['status'] == 'ok'
        assert len(data['added_links']) == 1

        db_session.expire_all()
        lk = db_session.query(AgentLink).filter_by(
            source_agent_id=src_id, target_agent_id=trx_id).first()
        assert lk is not None

    def test_duplicate_link_is_silently_ignored(self, auth_client, scenario, agents, link):
        src_id, trx_id, _ = agents
        body = {'positions': {}, 'add_links': [{'source': src_id, 'target': trx_id}],
                'remove_links': []}
        resp = _put(auth_client, scenario, body)
        assert resp.status_code == 200
        # No error — idempotent

    def test_self_loop_returns_error(self, auth_client, scenario, agents):
        src_id = agents[0]
        body = {'positions': {}, 'add_links': [{'source': src_id, 'target': src_id}],
                'remove_links': []}
        resp = _put(auth_client, scenario, body)
        data = resp.get_json()
        assert data['status'] == 'ok'  # request succeeds
        assert len(data['errors']) > 0  # but error noted

    def test_link_to_non_receiving_agent_returns_error(self, auth_client, scenario, agents):
        _, trx_id, act_id = agents
        # rss_agent (source) cannot receive events
        src_id = agents[0]
        body = {'positions': {}, 'add_links': [{'source': trx_id, 'target': src_id}],
                'remove_links': []}
        resp = _put(auth_client, scenario, body)
        data = resp.get_json()
        assert len(data['errors']) > 0

    def test_link_to_agent_in_other_scenario_rejected(self, auth_client, app,
                                                       test_user, scenario, agents):
        src_id = agents[0]
        with app.app_context():
            other_job = Job(name='Outside', job_type='filter_agent',
                            config={'rules': [{'type': 'exists', 'field': 'x'}], 'match_all': True},
                            user_id=test_user.id)
            db.session.add(other_job)
            db.session.commit()
            outside_id = other_job.id

        body = {'positions': {}, 'add_links': [{'source': src_id, 'target': outside_id}],
                'remove_links': []}
        resp = _put(auth_client, scenario, body)
        data = resp.get_json()
        assert len(data['errors']) > 0


# ---------------------------------------------------------------------------
# PUT /editor/graph — remove links
# ---------------------------------------------------------------------------

class TestGraphPutRemoveLinks:
    def test_remove_link(self, auth_client, app, db_session, scenario, agents, link):
        body = {'positions': {}, 'add_links': [], 'remove_links': [link]}
        resp = _put(auth_client, scenario, body)
        data = resp.get_json()
        assert data['status'] == 'ok'
        assert link in data['removed_links']

        db_session.expire_all()
        lk = db_session.query(AgentLink).get(link)
        assert lk is None

    def test_remove_nonexistent_link_is_ignored(self, auth_client, scenario):
        body = {'positions': {}, 'add_links': [], 'remove_links': [999999]}
        resp = _put(auth_client, scenario, body)
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'ok'


# ---------------------------------------------------------------------------
# Auto-layout algorithm
# ---------------------------------------------------------------------------

class TestAutoLayout:
    def test_layout_assigns_different_x_for_different_layers(
            self, auth_client, scenario, agents, link):
        # src → trx are linked; src should be at smaller x than trx
        resp = auth_client.get(f'/scenarios/{scenario}/editor/graph?reset_layout=1')
        data = resp.get_json()
        src_id, trx_id, _ = agents
        src = next(a for a in data['agents'] if a['id'] == src_id)
        trx = next(a for a in data['agents'] if a['id'] == trx_id)
        assert src['position']['x'] < trx['position']['x']

    def test_layout_with_no_links(self, auth_client, scenario, agents):
        resp = auth_client.get(f'/scenarios/{scenario}/editor/graph?reset_layout=1')
        data = resp.get_json()
        # All agents end up in layer 0 — same x, different y
        positions = [a['position'] for a in data['agents']]
        assert all(p is not None for p in positions)
