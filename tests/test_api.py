"""Tests for Feature 8 — REST API (/api/v1/)."""

import json
import pytest
from app.models import ApiToken, Job, Scenario


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def api_token(db_session, test_user):
    raw = ApiToken.generate()
    token = ApiToken(
        user_id=test_user.id,
        name='test-token',
        token_hash=ApiToken.hash_token(raw),
    )
    db_session.add(token)
    db_session.commit()
    return raw, token


@pytest.fixture
def bearer(client, api_token):
    """Test client that sends Bearer auth for every request."""
    raw, _ = api_token

    class BearerClient:
        def __init__(self, c, token):
            self._c = c
            self._h = {'Authorization': f'Bearer {token}'}

        def get(self, url, **kw):
            return self._c.get(url, headers=self._h, **kw)

        def post(self, url, json_data=None, **kw):
            kw.setdefault('content_type', 'application/json')
            data = json.dumps(json_data) if json_data is not None else None
            return self._c.post(url, data=data, headers=self._h, **kw)

        def patch(self, url, json_data=None, **kw):
            kw.setdefault('content_type', 'application/json')
            data = json.dumps(json_data) if json_data is not None else None
            return self._c.patch(url, data=data, headers=self._h, **kw)

        def delete(self, url, **kw):
            return self._c.delete(url, headers=self._h, **kw)

    return BearerClient(client, raw)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class TestApiAuth:
    def test_unauthenticated_returns_401(self, client):
        resp = client.get('/api/v1/agents')
        assert resp.status_code == 401

    def test_bad_token_returns_401(self, client):
        resp = client.get('/api/v1/agents', headers={'Authorization': 'Bearer badtoken'})
        assert resp.status_code == 401

    def test_valid_bearer_token_accepted(self, bearer):
        resp = bearer.get('/api/v1/agents')
        assert resp.status_code == 200

    def test_revoked_token_returns_401(self, client, db_session, api_token):
        raw, token = api_token
        token.is_active = False
        db_session.commit()
        resp = client.get('/api/v1/agents', headers={'Authorization': f'Bearer {raw}'})
        assert resp.status_code == 401

    def test_session_auth_also_works(self, auth_client):
        resp = auth_client.get('/api/v1/agents')
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Agents API
# ---------------------------------------------------------------------------

class TestAgentsApi:
    def test_list_agents_empty(self, bearer):
        resp = bearer.get('/api/v1/agents')
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_create_agent(self, bearer):
        resp = bearer.post('/api/v1/agents', {'name': 'My Agent', 'job_type': 'rss_agent', 'config': {'feed_url': 'https://example.com/feed'}})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['name'] == 'My Agent'
        assert data['job_type'] == 'rss_agent'
        assert 'id' in data

    def test_create_agent_missing_name(self, bearer):
        resp = bearer.post('/api/v1/agents', {'job_type': 'rss_agent'})
        assert resp.status_code == 400

    def test_create_agent_missing_job_type(self, bearer):
        resp = bearer.post('/api/v1/agents', {'name': 'My Agent'})
        assert resp.status_code == 400

    def test_create_agent_unknown_type(self, bearer):
        resp = bearer.post('/api/v1/agents', {'name': 'X', 'job_type': 'nonexistent_agent'})
        assert resp.status_code == 400

    def test_get_agent(self, bearer):
        create = bearer.post('/api/v1/agents', {'name': 'My Agent', 'job_type': 'rss_agent'})
        agent_id = create.get_json()['id']
        resp = bearer.get(f'/api/v1/agents/{agent_id}')
        assert resp.status_code == 200
        assert resp.get_json()['id'] == agent_id

    def test_get_agent_not_found(self, bearer):
        resp = bearer.get('/api/v1/agents/999999')
        assert resp.status_code == 404

    def test_list_agents_shows_created(self, bearer):
        bearer.post('/api/v1/agents', {'name': 'Agent A', 'job_type': 'rss_agent'})
        bearer.post('/api/v1/agents', {'name': 'Agent B', 'job_type': 'email_agent'})
        resp = bearer.get('/api/v1/agents')
        data = resp.get_json()
        assert len(data) == 2
        names = {d['name'] for d in data}
        assert names == {'Agent A', 'Agent B'}

    def test_update_agent(self, bearer):
        create = bearer.post('/api/v1/agents', {'name': 'Old Name', 'job_type': 'rss_agent'})
        agent_id = create.get_json()['id']
        resp = bearer.patch(f'/api/v1/agents/{agent_id}', {'name': 'New Name'})
        assert resp.status_code == 200
        assert resp.get_json()['name'] == 'New Name'

    def test_delete_agent(self, bearer):
        create = bearer.post('/api/v1/agents', {'name': 'To Delete', 'job_type': 'rss_agent'})
        agent_id = create.get_json()['id']
        resp = bearer.delete(f'/api/v1/agents/{agent_id}')
        assert resp.status_code == 204
        assert bearer.get(f'/api/v1/agents/{agent_id}').status_code == 404

    def test_user_isolation(self, bearer, client, db_session, test_user2):
        # Create agent as user1
        bearer.post('/api/v1/agents', {'name': 'User1 Agent', 'job_type': 'rss_agent'})

        # user2 token
        raw2 = ApiToken.generate()
        t2 = ApiToken(user_id=test_user2.id, name='t2', token_hash=ApiToken.hash_token(raw2))
        db_session.add(t2)
        db_session.commit()

        resp = client.get('/api/v1/agents', headers={'Authorization': f'Bearer {raw2}'})
        assert resp.get_json() == []


# ---------------------------------------------------------------------------
# Events API
# ---------------------------------------------------------------------------

class TestEventsApi:
    def test_list_events_empty(self, bearer):
        resp = bearer.get('/api/v1/events')
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_list_events_returns_created(self, bearer, db_session, test_user, test_job):
        from app.models import Event
        e = Event(
            agent_id=test_job.id,
            agent_type='rss_agent',
            user_id=test_user.id,
            payload={'title': 'Hello'},
        )
        db_session.add(e)
        db_session.commit()
        resp = bearer.get('/api/v1/events')
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]['payload']['title'] == 'Hello'

    def test_get_event(self, bearer, db_session, test_user, test_job):
        from app.models import Event
        e = Event(agent_id=test_job.id, agent_type='rss_agent', user_id=test_user.id, payload={})
        db_session.add(e)
        db_session.commit()
        resp = bearer.get(f'/api/v1/events/{e.id}')
        assert resp.status_code == 200
        assert resp.get_json()['id'] == e.id

    def test_get_event_not_found(self, bearer):
        assert bearer.get('/api/v1/events/999999').status_code == 404

    def test_events_filter_by_agent_id(self, bearer, db_session, test_user, test_job):
        from app.models import Event
        e1 = Event(agent_id=test_job.id, agent_type='rss_agent', user_id=test_user.id, payload={'n': 1})
        e2 = Event(agent_id=test_job.id, agent_type='rss_agent', user_id=test_user.id, payload={'n': 2})
        db_session.add_all([e1, e2])
        db_session.commit()
        resp = bearer.get(f'/api/v1/events?agent_id={test_job.id}')
        assert len(resp.get_json()) == 2
        resp_none = bearer.get('/api/v1/events?agent_id=999999')
        assert resp_none.get_json() == []


# ---------------------------------------------------------------------------
# Scenarios API
# ---------------------------------------------------------------------------

class TestScenariosApi:
    def test_list_scenarios_empty(self, bearer):
        assert bearer.get('/api/v1/scenarios').get_json() == []

    def test_create_scenario(self, bearer):
        resp = bearer.post('/api/v1/scenarios', {'name': 'Test Scenario'})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['name'] == 'Test Scenario'
        assert 'id' in data

    def test_create_scenario_missing_name(self, bearer):
        assert bearer.post('/api/v1/scenarios', {}).status_code == 400

    def test_get_scenario(self, bearer):
        created = bearer.post('/api/v1/scenarios', {'name': 'S1'}).get_json()
        resp = bearer.get(f'/api/v1/scenarios/{created["id"]}')
        assert resp.status_code == 200
        assert resp.get_json()['name'] == 'S1'

    def test_get_scenario_includes_agent_ids(self, bearer):
        s = bearer.post('/api/v1/scenarios', {'name': 'S1'}).get_json()
        assert 'agent_ids' in bearer.get(f'/api/v1/scenarios/{s["id"]}').get_json()

    def test_update_scenario(self, bearer):
        s = bearer.post('/api/v1/scenarios', {'name': 'Old'}).get_json()
        resp = bearer.patch(f'/api/v1/scenarios/{s["id"]}', {'name': 'New'})
        assert resp.status_code == 200
        assert resp.get_json()['name'] == 'New'

    def test_delete_scenario(self, bearer):
        s = bearer.post('/api/v1/scenarios', {'name': 'Del'}).get_json()
        resp = bearer.delete(f'/api/v1/scenarios/{s["id"]}')
        assert resp.status_code == 204
        assert bearer.get(f'/api/v1/scenarios/{s["id"]}').status_code == 404

    def test_scenario_not_found(self, bearer):
        assert bearer.get('/api/v1/scenarios/999999').status_code == 404


# ---------------------------------------------------------------------------
# Scenario import API
# ---------------------------------------------------------------------------

def _valid_import_doc(name="Imported"):
    return {
        "schema_version": 1,
        "scenario": {"name": name, "description": "", "color": "#3B82F6", "is_active": True},
        "agents": [
            {
                "export_id": 0,
                "name": "RSS Feed",
                "job_type": "rss_agent",
                "config": {"feed_url": "https://example.com/feed"},
                "schedule_cron": None,
                "schedule_enabled": False,
                "is_active": True,
                "priority": 0,
            },
            {
                "export_id": 1,
                "name": "Email Alert",
                "job_type": "email_agent",
                "config": {"to_email": "a@b.com", "subject": "x", "body": "y"},
                "schedule_cron": None,
                "schedule_enabled": False,
                "is_active": True,
                "priority": 0,
            },
        ],
        "links": [{"source": 0, "target": 1}],
    }


class TestScenarioImportApi:
    def test_import_creates_scenario(self, bearer):
        resp = bearer.post('/api/v1/scenarios/import', _valid_import_doc())
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['name'] == 'Imported'
        assert data['scenario_id'] is not None

    def test_import_creates_agents(self, bearer):
        resp = bearer.post('/api/v1/scenarios/import', _valid_import_doc())
        assert resp.get_json()['agent_count'] == 2

    def test_import_creates_correct_links(self, bearer, db_session):
        from app.models import AgentLink
        resp = bearer.post('/api/v1/scenarios/import', _valid_import_doc())
        sid = resp.get_json()['scenario_id']
        jobs = sorted(
            db_session.query(Job).filter_by(scenario_id=sid).all(),
            key=lambda j: j.id,
        )
        assert len(jobs) == 2
        link = db_session.query(AgentLink).filter_by(
            source_agent_id=jobs[0].id, target_agent_id=jobs[1].id,
        ).first()
        assert link is not None

    def test_import_bad_json_returns_400(self, bearer, client, api_token):
        raw, _ = api_token
        resp = client.post(
            '/api/v1/scenarios/import',
            data='not json',
            headers={'Authorization': f'Bearer {raw}', 'Content-Type': 'application/json'},
        )
        assert resp.status_code == 400

    def test_import_unknown_agent_type_returns_400(self, bearer):
        doc = _valid_import_doc()
        doc['agents'][0]['job_type'] = 'nonexistent_agent_xyz'
        resp = bearer.post('/api/v1/scenarios/import', doc)
        assert resp.status_code == 400
        assert 'Unknown' in resp.get_json()['error']

    def test_import_wrong_schema_version_returns_400(self, bearer):
        doc = _valid_import_doc()
        doc['schema_version'] = 99
        resp = bearer.post('/api/v1/scenarios/import', doc)
        assert resp.status_code == 400

    def test_import_requires_auth(self, client):
        resp = client.post(
            '/api/v1/scenarios/import',
            data=json.dumps(_valid_import_doc()),
            content_type='application/json',
        )
        assert resp.status_code == 401

    def test_import_returns_warnings_for_missing_credentials(self, bearer):
        doc = _valid_import_doc()
        doc['agents'][0]['config']['api_key'] = '{{credential:my_secret}}'
        resp = bearer.post('/api/v1/scenarios/import', doc)
        assert resp.status_code == 201
        data = resp.get_json()
        assert isinstance(data['warnings'], list)


# ---------------------------------------------------------------------------
# Token management UI
# ---------------------------------------------------------------------------

class TestTokenManagementUI:
    def test_manage_page_requires_login(self, client):
        resp = client.get('/api/v1/tokens/manage')
        assert resp.status_code in (302, 401)

    def test_manage_page_accessible(self, auth_client):
        resp = auth_client.get('/api/v1/tokens/manage')
        assert resp.status_code == 200
        assert b'API Tokens' in resp.data

    def test_create_token_via_form(self, auth_client, db_session, test_user):
        resp = auth_client.post(
            '/api/v1/tokens/create',
            data={'name': 'My Script'},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert db_session.query(ApiToken).filter_by(user_id=test_user.id).count() == 1

    def test_create_token_name_required(self, auth_client):
        resp = auth_client.post(
            '/api/v1/tokens/create',
            data={'name': ''},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        # Should flash error and not create token

    def test_revoke_token_via_form(self, auth_client, db_session, test_user):
        raw = ApiToken.generate()
        t = ApiToken(user_id=test_user.id, name='revoke-me', token_hash=ApiToken.hash_token(raw))
        db_session.add(t)
        db_session.commit()
        resp = auth_client.post(
            f'/api/v1/tokens/{t.id}/revoke',
            follow_redirects=True,
        )
        assert resp.status_code == 200
        db_session.refresh(t)
        assert t.is_active is False

    def test_token_list_via_api(self, bearer, db_session, test_user):
        raw2 = ApiToken.generate()
        t2 = ApiToken(user_id=test_user.id, name='second', token_hash=ApiToken.hash_token(raw2))
        db_session.add(t2)
        db_session.commit()
        resp = bearer.get('/api/v1/tokens')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 2
        names = {d['name'] for d in data}
        assert 'test-token' in names
        assert 'second' in names
