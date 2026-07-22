"""Tests for the Template Library (Feature 10)."""

import pytest
from app.template_library import catalog


class TestCatalog:
    def test_returns_list(self):
        templates = catalog.get_all()
        assert isinstance(templates, list)

    def test_all_templates_loaded(self):
        templates = catalog.get_all()
        assert len(templates) >= 8

    def test_template_has_required_keys(self):
        for tmpl in catalog.get_all():
            assert 'slug' in tmpl
            assert 'display_name' in tmpl
            assert 'description' in tmpl
            assert 'tags' in tmpl
            assert 'difficulty' in tmpl
            assert 'agent_count' in tmpl
            assert 'doc' in tmpl

    def test_difficulty_values_valid(self):
        valid = {'beginner', 'intermediate', 'advanced'}
        for tmpl in catalog.get_all():
            assert tmpl['difficulty'] in valid, f"{tmpl['slug']} has invalid difficulty"

    def test_sorted_by_difficulty_then_name(self):
        order = {'beginner': 0, 'intermediate': 1, 'advanced': 2}
        templates = catalog.get_all()
        for i in range(len(templates) - 1):
            a, b = templates[i], templates[i + 1]
            rank_a = order.get(a['difficulty'], 99)
            rank_b = order.get(b['difficulty'], 99)
            assert (rank_a, a['display_name']) <= (rank_b, b['display_name'])

    def test_get_by_slug_found(self):
        slug = catalog.get_all()[0]['slug']
        tmpl = catalog.get_by_slug(slug)
        assert tmpl is not None
        assert tmpl['slug'] == slug

    def test_get_by_slug_missing(self):
        assert catalog.get_by_slug('nonexistent-slug-xyz') is None

    def test_each_doc_has_schema_version(self):
        for tmpl in catalog.get_all():
            assert tmpl['doc'].get('schema_version') == 1, f"{tmpl['slug']} missing schema_version"

    def test_each_doc_has_agents_list(self):
        for tmpl in catalog.get_all():
            assert isinstance(tmpl['doc'].get('agents'), list)
            assert len(tmpl['doc']['agents']) > 0

    def test_each_doc_has_links_list(self):
        for tmpl in catalog.get_all():
            assert isinstance(tmpl['doc'].get('links'), list)

    def test_agent_count_matches_doc(self):
        for tmpl in catalog.get_all():
            assert tmpl['agent_count'] == len(tmpl['doc']['agents'])


class TestGalleryRoute:
    def test_gallery_redirects_unauthenticated(self, client):
        resp = client.get('/template-library/')
        assert resp.status_code in (302, 401)

    def test_gallery_accessible_when_logged_in(self, auth_client):
        resp = auth_client.get('/template-library/')
        assert resp.status_code == 200
        assert b'Template Library' in resp.data

    def test_gallery_shows_all_templates(self, auth_client):
        resp = auth_client.get('/template-library/')
        assert resp.status_code == 200
        templates = catalog.get_all()
        for tmpl in templates:
            assert tmpl['display_name'].encode() in resp.data

    def test_gallery_shows_difficulty_badges(self, auth_client):
        resp = auth_client.get('/template-library/')
        assert b'beginner' in resp.data or b'intermediate' in resp.data or b'advanced' in resp.data

    def test_gallery_shows_import_buttons(self, auth_client):
        resp = auth_client.get('/template-library/')
        assert b'Import Template' in resp.data


class TestImportRoute:
    def test_import_redirects_unauthenticated(self, client):
        resp = client.post('/template-library/01_rss_to_email/import')
        assert resp.status_code in (302, 401)

    def test_import_creates_scenario(self, auth_client, db_session):
        from app.models import Scenario
        resp = auth_client.post(
            '/template-library/01_rss_to_email/import',
            follow_redirects=True,
        )
        assert resp.status_code == 200
        scenarios = db_session.query(Scenario).all()
        assert len(scenarios) == 1
        assert 'RSS to Email Digest' in scenarios[0].name

    def test_import_creates_correct_agent_count(self, auth_client, db_session):
        from app.models import Job
        auth_client.post(
            '/template-library/01_rss_to_email/import',
            follow_redirects=True,
        )
        jobs = db_session.query(Job).all()
        assert len(jobs) == 3

    def test_import_creates_links(self, auth_client, db_session):
        from app.models import AgentLink
        auth_client.post(
            '/template-library/01_rss_to_email/import',
            follow_redirects=True,
        )
        links = db_session.query(AgentLink).all()
        assert len(links) == 2

    def test_import_shows_success_flash(self, auth_client):
        resp = auth_client.post(
            '/template-library/01_rss_to_email/import',
            follow_redirects=True,
        )
        assert b'imported as' in resp.data or b'RSS to Email Digest' in resp.data

    def test_import_nonexistent_slug_redirects(self, auth_client):
        resp = auth_client.post(
            '/template-library/nonexistent-slug-xyz/import',
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b'not found' in resp.data.lower() or b'Template Library' in resp.data

    def test_import_all_templates_succeed(self, auth_client, db_session):
        from app.models import Scenario
        templates = catalog.get_all()
        for tmpl in templates:
            resp = auth_client.post(
                f'/template-library/{tmpl["slug"]}/import',
                follow_redirects=True,
            )
            assert resp.status_code == 200, f"Import failed for {tmpl['slug']}"

        count = db_session.query(Scenario).count()
        assert count == len(templates)

    def test_import_same_template_twice_gets_unique_name(self, auth_client, db_session):
        from app.models import Scenario
        auth_client.post('/template-library/01_rss_to_email/import', follow_redirects=True)
        auth_client.post('/template-library/01_rss_to_email/import', follow_redirects=True)
        scenarios = db_session.query(Scenario).all()
        assert len(scenarios) == 2
        names = {s.name for s in scenarios}
        assert len(names) == 2
