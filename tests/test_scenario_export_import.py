"""
Tests for scenario export / import (service layer + HTTP routes).
"""

import io
import json
import pytest

from app.extensions import db
from app.models import AgentLink, Job, Scenario
from app.scenarios.export_import import (
    MAX_FILE_BYTES,
    SCHEMA_VERSION,
    ImportValidationError,
    check_missing_credentials,
    export_scenario,
    import_scenario,
    validate_import_document,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def scenario(app, test_user):
    with app.app_context():
        s = Scenario(
            user_id=test_user.id,
            name='Daily Newspaper',
            description='Morning email pipeline',
            color='#3B82F6',
            is_active=True,
        )
        db.session.add(s)
        db.session.commit()
        yield s


@pytest.fixture
def agents_and_links(app, test_user, scenario):
    """Three agents in the scenario with two internal links."""
    with app.app_context():
        source = Job(
            name='World RSS',
            job_type='rss_agent',
            config={'feed_url': 'https://example.com/feed', 'max_entries': 20},
            user_id=test_user.id,
            scenario_id=scenario.id,
            schedule_cron='0 */2 * * *',
            schedule_enabled=True,
            is_active=True,
        )
        transform = Job(
            name='Broadsheet Formatter',
            job_type='template_agent',
            config={'template': '<html>{{ title }}</html>', 'output_field': 'formatted'},
            user_id=test_user.id,
            scenario_id=scenario.id,
            is_active=True,
        )
        action = Job(
            name='Morning Email',
            job_type='email_agent',
            config={'to': 'user@example.com', 'subject': 'Daily News',
                    'password': '{{credential:smtp_pass}}'},
            user_id=test_user.id,
            scenario_id=scenario.id,
            is_active=True,
        )
        db.session.add_all([source, transform, action])
        db.session.flush()

        link1 = AgentLink(source_agent_id=source.id, target_agent_id=transform.id)
        link2 = AgentLink(source_agent_id=transform.id, target_agent_id=action.id)
        db.session.add_all([link1, link2])
        db.session.commit()

        yield source, transform, action


# ---------------------------------------------------------------------------
# Export — service layer
# ---------------------------------------------------------------------------

class TestExportScenario:

    def test_export_schema_version(self, app, scenario, agents_and_links):
        with app.app_context():
            s = db.session.get(Scenario, scenario.id)
            doc = export_scenario(s)
        assert doc['schema_version'] == SCHEMA_VERSION

    def test_export_scenario_metadata(self, app, scenario, agents_and_links):
        with app.app_context():
            s = db.session.get(Scenario, scenario.id)
            doc = export_scenario(s)
        assert doc['scenario']['name'] == 'Daily Newspaper'
        assert doc['scenario']['description'] == 'Morning email pipeline'
        assert doc['scenario']['color'] == '#3B82F6'
        assert doc['scenario']['is_active'] is True

    def test_export_includes_all_scenario_agents(self, app, scenario, agents_and_links):
        with app.app_context():
            s = db.session.get(Scenario, scenario.id)
            doc = export_scenario(s)
        assert len(doc['agents']) == 3
        names = {a['name'] for a in doc['agents']}
        assert names == {'World RSS', 'Broadsheet Formatter', 'Morning Email'}

    def test_export_agents_have_sequential_export_ids(self, app, scenario, agents_and_links):
        with app.app_context():
            s = db.session.get(Scenario, scenario.id)
            doc = export_scenario(s)
        ids = sorted(a['export_id'] for a in doc['agents'])
        assert ids == list(range(len(doc['agents'])))

    def test_export_agent_fields_present(self, app, scenario, agents_and_links):
        with app.app_context():
            s = db.session.get(Scenario, scenario.id)
            doc = export_scenario(s)
        agent = next(a for a in doc['agents'] if a['name'] == 'World RSS')
        assert agent['job_type'] == 'rss_agent'
        assert agent['config']['feed_url'] == 'https://example.com/feed'
        assert agent['schedule_cron'] == '0 */2 * * *'
        assert agent['schedule_enabled'] is True

    def test_export_includes_internal_links(self, app, scenario, agents_and_links):
        with app.app_context():
            s = db.session.get(Scenario, scenario.id)
            doc = export_scenario(s)
        assert len(doc['links']) == 2

    def test_export_links_reference_valid_export_ids(self, app, scenario, agents_and_links):
        with app.app_context():
            s = db.session.get(Scenario, scenario.id)
            doc = export_scenario(s)
        valid_ids = {a['export_id'] for a in doc['agents']}
        for lnk in doc['links']:
            assert lnk['source'] in valid_ids
            assert lnk['target'] in valid_ids

    def test_export_preserves_credential_reference(self, app, scenario, agents_and_links):
        with app.app_context():
            s = db.session.get(Scenario, scenario.id)
            doc = export_scenario(s)
        action = next(a for a in doc['agents'] if a['name'] == 'Morning Email')
        assert action['config']['password'] == '{{credential:smtp_pass}}'

    def test_export_omits_cross_scenario_links(self, app, test_user, scenario, agents_and_links):
        """A link whose target is outside the scenario is not exported."""
        with app.app_context():
            # Agent outside the scenario
            outside = Job(
                name='Outside Agent',
                job_type='email_agent',
                config={},
                user_id=test_user.id,
                scenario_id=None,
                is_active=True,
            )
            db.session.add(outside)
            db.session.flush()
            source_agent = agents_and_links[0]
            cross_link = AgentLink(
                source_agent_id=source_agent.id,
                target_agent_id=outside.id,
            )
            db.session.add(cross_link)
            db.session.commit()

            s = db.session.get(Scenario, scenario.id)
            doc = export_scenario(s)

        # Still only the two internal links, not the cross-scenario one
        assert len(doc['links']) == 2

    def test_export_empty_scenario(self, app, scenario):
        with app.app_context():
            s = db.session.get(Scenario, scenario.id)
            doc = export_scenario(s)
        assert doc['agents'] == []
        assert doc['links'] == []

    def test_export_contains_exported_at(self, app, scenario):
        with app.app_context():
            s = db.session.get(Scenario, scenario.id)
            doc = export_scenario(s)
        assert 'exported_at' in doc
        assert 'T' in doc['exported_at']  # ISO format

    def test_export_does_not_include_db_ids(self, app, scenario, agents_and_links):
        with app.app_context():
            s = db.session.get(Scenario, scenario.id)
            doc = export_scenario(s)
        for agent in doc['agents']:
            assert 'id' not in agent
            assert 'scenario_id' not in agent
            assert 'user_id' not in agent


# ---------------------------------------------------------------------------
# validate_import_document
# ---------------------------------------------------------------------------

class TestValidateImportDocument:

    def _valid_doc(self):
        return {
            'schema_version': SCHEMA_VERSION,
            'scenario': {'name': 'Test', 'description': None, 'color': '#000', 'is_active': True},
            'agents': [
                {
                    'export_id': 0,
                    'name': 'Feed',
                    'job_type': 'rss_agent',
                    'description': None,
                    'config': {},
                    'schedule_cron': None,
                    'schedule_enabled': False,
                    'is_active': True,
                    'priority': 0,
                    'tags': None,
                }
            ],
            'links': [],
        }

    def _encode(self, doc):
        return json.dumps(doc).encode()

    def test_valid_document_passes(self):
        doc = validate_import_document(self._encode(self._valid_doc()))
        assert doc['schema_version'] == SCHEMA_VERSION

    def test_rejects_file_exceeding_size_limit(self):
        big = b'x' * (MAX_FILE_BYTES + 1)
        with pytest.raises(ImportValidationError, match='size limit'):
            validate_import_document(big)

    def test_rejects_malformed_json(self):
        with pytest.raises(ImportValidationError, match='Invalid JSON'):
            validate_import_document(b'{not valid json')

    def test_rejects_wrong_schema_version(self):
        doc = self._valid_doc()
        doc['schema_version'] = 99
        with pytest.raises(ImportValidationError, match='schema_version'):
            validate_import_document(self._encode(doc))

    def test_rejects_missing_scenario_key(self):
        doc = self._valid_doc()
        del doc['scenario']
        with pytest.raises(ImportValidationError, match="'scenario'"):
            validate_import_document(self._encode(doc))

    def test_rejects_missing_agents_key(self):
        doc = self._valid_doc()
        del doc['agents']
        with pytest.raises(ImportValidationError, match="'agents'"):
            validate_import_document(self._encode(doc))

    def test_rejects_missing_links_key(self):
        doc = self._valid_doc()
        del doc['links']
        with pytest.raises(ImportValidationError, match="'links'"):
            validate_import_document(self._encode(doc))

    def test_rejects_unknown_agent_type(self):
        doc = self._valid_doc()
        doc['agents'][0]['job_type'] = 'nonexistent_agent_9000'
        with pytest.raises(ImportValidationError, match='Unknown agent type'):
            validate_import_document(self._encode(doc))

    def test_rejects_link_with_out_of_range_source(self):
        doc = self._valid_doc()
        doc['links'] = [{'source': 5, 'target': 0}]
        with pytest.raises(ImportValidationError, match='out-of-range'):
            validate_import_document(self._encode(doc))

    def test_rejects_link_with_non_integer_index(self):
        doc = self._valid_doc()
        doc['links'] = [{'source': 'a', 'target': 0}]
        with pytest.raises(ImportValidationError, match='non-integer'):
            validate_import_document(self._encode(doc))

    def test_accepts_empty_agents_list(self):
        doc = self._valid_doc()
        doc['agents'] = []
        doc['links'] = []
        result = validate_import_document(self._encode(doc))
        assert result['agents'] == []


# ---------------------------------------------------------------------------
# check_missing_credentials
# ---------------------------------------------------------------------------

class TestCheckMissingCredentials:

    def _doc_with_creds(self, *names):
        refs = {f'secret_{n}': f'{{{{credential:{n}}}}}' for n in names}
        return {
            'agents': [{'config': refs}],
        }

    def test_no_refs_returns_empty(self, app, test_user):
        with app.app_context():
            result = check_missing_credentials({'agents': [{'config': {}}]}, test_user.id)
        assert result == []

    def test_missing_credential_reported(self, app, test_user):
        with app.app_context():
            result = check_missing_credentials(
                self._doc_with_creds('smtp_pass'), test_user.id
            )
        assert 'smtp_pass' in result

    def test_existing_credential_not_reported(self, app, test_user):
        from app.models import Credential
        from app.utils.encryption import ConfigEncryption
        with app.app_context():
            enc, salt = ConfigEncryption.encrypt_credential('secret')
            cred = Credential(
                user_id=test_user.id,
                name='smtp_pass',
                encrypted_value=enc,
                salt=salt,
            )
            db.session.add(cred)
            db.session.commit()
            result = check_missing_credentials(
                self._doc_with_creds('smtp_pass'), test_user.id
            )
        assert 'smtp_pass' not in result

    def test_nested_credential_refs_found(self, app, test_user):
        doc = {
            'agents': [{
                'config': {
                    'nested': {'deep': '{{credential:deep_secret}}'},
                    'list': ['{{credential:list_secret}}'],
                }
            }]
        }
        with app.app_context():
            result = check_missing_credentials(doc, test_user.id)
        assert 'deep_secret' in result
        assert 'list_secret' in result


# ---------------------------------------------------------------------------
# import_scenario — service layer
# ---------------------------------------------------------------------------

class TestImportScenario:

    def _minimal_doc(self, name='Imported'):
        return {
            'schema_version': SCHEMA_VERSION,
            'exported_at': '2026-05-27T09:00:00+00:00',
            'exported_by': 'alice',
            'scenario': {
                'name': name,
                'description': 'Imported scenario',
                'color': '#10B981',
                'is_active': True,
            },
            'agents': [
                {
                    'export_id': 0,
                    'name': 'Source',
                    'job_type': 'rss_agent',
                    'description': None,
                    'config': {'feed_url': 'https://example.com/feed'},
                    'schedule_cron': '0 * * * *',
                    'schedule_enabled': True,
                    'is_active': True,
                    'priority': 0,
                    'tags': None,
                },
                {
                    'export_id': 1,
                    'name': 'Action',
                    'job_type': 'email_agent',
                    'description': None,
                    'config': {'to': 'user@example.com'},
                    'schedule_cron': None,
                    'schedule_enabled': False,
                    'is_active': True,
                    'priority': 0,
                    'tags': None,
                },
            ],
            'links': [{'source': 0, 'target': 1}],
        }

    def test_creates_scenario(self, app, test_user):
        with app.app_context():
            scenario, _ = import_scenario(self._minimal_doc(), test_user.id)
            created = db.session.get(Scenario, scenario.id)
        assert created is not None
        assert created.name == 'Imported'
        assert created.user_id == test_user.id

    def test_creates_agents(self, app, test_user):
        with app.app_context():
            scenario, _ = import_scenario(self._minimal_doc(), test_user.id)
            jobs = db.session.query(Job).filter_by(scenario_id=scenario.id).all()
        assert len(jobs) == 2
        names = {j.name for j in jobs}
        assert names == {'Source', 'Action'}

    def test_creates_links(self, app, test_user):
        with app.app_context():
            scenario, _ = import_scenario(self._minimal_doc(), test_user.id)
            jobs = db.session.query(Job).filter_by(scenario_id=scenario.id).order_by(Job.name).all()
            job_ids = {j.id for j in jobs}
            links = db.session.query(AgentLink).filter(
                AgentLink.source_agent_id.in_(job_ids)
            ).all()
        assert len(links) == 1

    def test_agent_config_preserved(self, app, test_user):
        with app.app_context():
            scenario, _ = import_scenario(self._minimal_doc(), test_user.id)
            source = db.session.query(Job).filter_by(
                scenario_id=scenario.id, name='Source'
            ).first()
        assert source.config['feed_url'] == 'https://example.com/feed'

    def test_scheduling_fields_preserved(self, app, test_user):
        with app.app_context():
            scenario, _ = import_scenario(self._minimal_doc(), test_user.id)
            source = db.session.query(Job).filter_by(
                scenario_id=scenario.id, name='Source'
            ).first()
        assert source.schedule_cron == '0 * * * *'
        assert source.schedule_enabled is True

    def test_last_scheduled_run_not_imported(self, app, test_user):
        with app.app_context():
            scenario, _ = import_scenario(self._minimal_doc(), test_user.id)
            for job in db.session.query(Job).filter_by(scenario_id=scenario.id).all():
                assert job.last_scheduled_run is None

    def test_name_collision_appends_counter(self, app, test_user):
        with app.app_context():
            import_scenario(self._minimal_doc('Collision'), test_user.id)
            s2, _ = import_scenario(self._minimal_doc('Collision'), test_user.id)
            s3, _ = import_scenario(self._minimal_doc('Collision'), test_user.id)
            assert s2.name == 'Collision (2)'
            assert s3.name == 'Collision (3)'

    def test_missing_credential_produces_warning(self, app, test_user):
        doc = self._minimal_doc()
        doc['agents'][0]['config']['password'] = '{{credential:missing_cred}}'
        with app.app_context():
            _, warnings = import_scenario(doc, test_user.id)
        assert any('missing_cred' in w for w in warnings)

    def test_no_warning_when_credentials_exist(self, app, test_user):
        from app.models import Credential
        from app.utils.encryption import ConfigEncryption
        with app.app_context():
            enc, salt = ConfigEncryption.encrypt_credential('s')
            db.session.add(Credential(
                user_id=test_user.id, name='known_cred',
                encrypted_value=enc, salt=salt,
            ))
            db.session.commit()

            doc = self._minimal_doc()
            doc['agents'][0]['config']['password'] = '{{credential:known_cred}}'
            _, warnings = import_scenario(doc, test_user.id)
        assert not any('known_cred' in w for w in warnings)

    def test_empty_scenario_imports_cleanly(self, app, test_user):
        doc = self._minimal_doc()
        doc['agents'] = []
        doc['links'] = []
        with app.app_context():
            scenario, warnings = import_scenario(doc, test_user.id)
            count = db.session.query(Job).filter_by(scenario_id=scenario.id).count()
        assert count == 0
        assert warnings == []

    def test_scenario_color_preserved(self, app, test_user):
        with app.app_context():
            scenario, _ = import_scenario(self._minimal_doc(), test_user.id)
            assert scenario.color == '#10B981'


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------

class TestRoundTrip:

    def test_export_then_import_equivalent_graph(self, app, test_user, scenario, agents_and_links):
        """Export a scenario, import it, re-export, and verify the agent/link graph matches."""
        with app.app_context():
            s = db.session.get(Scenario, scenario.id)
            original_doc = export_scenario(s)

        with app.app_context():
            imported_scenario, _ = import_scenario(original_doc, test_user.id)
            reimported_doc = export_scenario(
                db.session.get(Scenario, imported_scenario.id)
            )

        # Same number of agents and links
        assert len(reimported_doc['agents']) == len(original_doc['agents'])
        assert len(reimported_doc['links']) == len(original_doc['links'])

        # Same agent names and types (order may differ by DB id, so use sets of tuples)
        orig_agents = {(a['name'], a['job_type']) for a in original_doc['agents']}
        new_agents = {(a['name'], a['job_type']) for a in reimported_doc['agents']}
        assert orig_agents == new_agents

        # Same link structure expressed as (source_name, target_name) pairs
        def link_names(doc):
            by_id = {a['export_id']: a['name'] for a in doc['agents']}
            return {(by_id[lnk['source']], by_id[lnk['target']]) for lnk in doc['links']}

        assert link_names(original_doc) == link_names(reimported_doc)

    def test_cross_user_import(self, app, test_user, test_user2, scenario, agents_and_links):
        """Any user can import a scenario exported by a different user.

        The resulting scenario and agents must be owned by the *importing* user,
        not the original exporter.
        """
        # Export as test_user (scenario owner)
        with app.app_context():
            s = db.session.get(Scenario, scenario.id)
            doc = export_scenario(s)

        assert doc['exported_by'] == test_user.username

        # Import as test_user2 (completely different user)
        with app.app_context():
            imported, warnings = import_scenario(doc, test_user2.id)

            # Scenario owned by the importer
            assert imported.user_id == test_user2.id
            assert imported.user_id != test_user.id

            # All agents owned by the importer
            jobs = db.session.query(Job).filter_by(scenario_id=imported.id).all()
            assert len(jobs) == 3
            assert all(j.user_id == test_user2.id for j in jobs)

            # Original scenario still owned by test_user
            original = db.session.get(Scenario, scenario.id)
            assert original.user_id == test_user.id


# ---------------------------------------------------------------------------
# HTTP routes
# ---------------------------------------------------------------------------

class TestExportRoute:

    def test_export_requires_login(self, client, scenario):
        response = client.get(f'/scenarios/{scenario.id}/export')
        assert response.status_code == 302
        assert 'login' in response.location.lower()

    def test_export_returns_json_file(self, auth_client, app, test_user, scenario, agents_and_links):
        response = auth_client.get(f'/scenarios/{scenario.id}/export')
        assert response.status_code == 200
        assert response.content_type == 'application/json'
        assert 'attachment' in response.headers['Content-Disposition']
        assert '.json' in response.headers['Content-Disposition']

    def test_export_returns_valid_json(self, auth_client, scenario, agents_and_links):
        response = auth_client.get(f'/scenarios/{scenario.id}/export')
        doc = json.loads(response.data)
        assert doc['schema_version'] == SCHEMA_VERSION
        assert doc['scenario']['name'] == scenario.name

    def test_export_404_for_other_users_scenario(self, client, app, scenario):
        """Cannot export another user's scenario."""
        from app.models import User
        with app.app_context():
            other = User('other', 'other@example.com', 'password')
            db.session.add(other)
            db.session.commit()
        client.post('/auth/login', data={'username': 'other', 'password': 'password'})
        response = client.get(f'/scenarios/{scenario.id}/export')
        assert response.status_code in (302, 404)


class TestImportRoute:

    def _make_upload(self, doc):
        raw = json.dumps(doc).encode()
        return {'file': (io.BytesIO(raw), 'export.json')}

    def _valid_doc(self):
        return {
            'schema_version': SCHEMA_VERSION,
            'exported_at': '2026-05-27T09:00:00+00:00',
            'exported_by': 'alice',
            'scenario': {
                'name': 'Route Import Test',
                'description': None,
                'color': '#3B82F6',
                'is_active': True,
            },
            'agents': [
                {
                    'export_id': 0,
                    'name': 'Feed',
                    'job_type': 'rss_agent',
                    'description': None,
                    'config': {'feed_url': 'https://example.com'},
                    'schedule_cron': None,
                    'schedule_enabled': False,
                    'is_active': True,
                    'priority': 0,
                    'tags': None,
                }
            ],
            'links': [],
        }

    def test_import_get_requires_login(self, client):
        response = client.get('/scenarios/import')
        assert response.status_code == 302
        assert 'login' in response.location.lower()

    def test_import_get_shows_form(self, auth_client):
        response = auth_client.get('/scenarios/import')
        assert response.status_code == 200
        assert b'Import' in response.data

    def test_import_post_requires_login(self, client):
        response = client.post('/scenarios/import', data={})
        assert response.status_code == 302
        assert 'login' in response.location.lower()

    def test_import_success_redirects_to_detail(self, auth_client):
        response = auth_client.post(
            '/scenarios/import',
            data=self._make_upload(self._valid_doc()),
            content_type='multipart/form-data',
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert '/scenarios/' in response.location

    def test_import_success_creates_scenario(self, auth_client, app, test_user):
        auth_client.post(
            '/scenarios/import',
            data=self._make_upload(self._valid_doc()),
            content_type='multipart/form-data',
        )
        with app.app_context():
            s = db.session.query(Scenario).filter_by(
                user_id=test_user.id,
                name='Route Import Test',
            ).first()
        assert s is not None

    def test_import_bad_json_shows_error(self, auth_client):
        bad = {'file': (io.BytesIO(b'{bad json'), 'export.json')}
        response = auth_client.post(
            '/scenarios/import',
            data=bad,
            content_type='multipart/form-data',
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b'Invalid JSON' in response.data or b'error' in response.data.lower()

    def test_import_wrong_schema_version_shows_error(self, auth_client):
        doc = self._valid_doc()
        doc['schema_version'] = 999
        response = auth_client.post(
            '/scenarios/import',
            data=self._make_upload(doc),
            content_type='multipart/form-data',
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b'schema_version' in response.data or b'error' in response.data.lower()

    def test_import_no_file_shows_error(self, auth_client):
        response = auth_client.post(
            '/scenarios/import',
            data={},
            content_type='multipart/form-data',
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b'select' in response.data.lower() or b'error' in response.data.lower()

    def test_import_unknown_agent_type_shows_error(self, auth_client):
        doc = self._valid_doc()
        doc['agents'][0]['job_type'] = 'not_a_real_agent'
        response = auth_client.post(
            '/scenarios/import',
            data=self._make_upload(doc),
            content_type='multipart/form-data',
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b'not_a_real_agent' in response.data or b'Unknown' in response.data

    def test_import_cross_user_via_route(self, auth_client2, app, test_user2, scenario, agents_and_links):
        """User B can import a scenario originally created by User A via the HTTP route.

        The resulting scenario must be owned by User B (the importer).
        Note: we construct the export doc directly to avoid g._login_user leaking
        between two different clients within the same test.
        """
        with app.app_context():
            s = db.session.get(Scenario, scenario.id)
            doc = export_scenario(s)

        response = auth_client2.post(
            '/scenarios/import',
            data=self._make_upload(doc),
            content_type='multipart/form-data',
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert '/scenarios/' in response.location

        with app.app_context():
            imported = db.session.query(Scenario).filter_by(
                user_id=test_user2.id,
                name=scenario.name,
            ).first()
        assert imported is not None
        assert imported.user_id == test_user2.id
