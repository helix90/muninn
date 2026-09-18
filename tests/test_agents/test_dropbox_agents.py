"""Tests for DropboxReadAgent and DropboxWriteAgent."""

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.agents.registry import agent_registry
from app.agents.types.dropbox_read_agent import DropboxReadAgent
from app.agents.types.dropbox_write_agent import DropboxWriteAgent
from app.models import Event


# ── shared fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def test_user(db_session):
    from app.models import User
    user = User(username='dropboxtest', email='dropboxtest@example.com', password='password123')
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def read_job(db_session, test_user):
    from app.models import Job
    job = Job(
        name='Dropbox Read Agent',
        job_type='dropbox_read_agent',
        config={
            'access_token': 'test-token',
            'folder_path': '/reports',
        },
        user_id=test_user.id,
    )
    db_session.add(job)
    db_session.commit()
    return job


@pytest.fixture
def write_job(db_session, test_user):
    from app.models import Job
    job = Job(
        name='Dropbox Write Agent',
        job_type='dropbox_write_agent',
        config={
            'access_token': 'test-token',
            'path_template': '/backup/{{name}}.txt',
            'content_template': '{{content}}',
        },
        user_id=test_user.id,
    )
    db_session.add(job)
    db_session.commit()
    return job


def _make_agent(job, db_session, config=None):
    """Instantiate a DropboxReadAgent with an optional config override."""
    cfg = config if config is not None else job.config
    return DropboxReadAgent(
        agent_id=job.id, config=cfg, user_id=job.user_id, db_session=db_session,
    )


def _make_write_agent(job, db_session, config=None):
    cfg = config if config is not None else job.config
    return DropboxWriteAgent(
        agent_id=job.id, config=cfg, user_id=job.user_id, db_session=db_session,
    )


def _fake_list_response(entries, has_more=False, cursor='cur1'):
    """Build a mock requests.Response for /files/list_folder."""
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {'entries': entries, 'has_more': has_more, 'cursor': cursor}
    return resp


def _fake_upload_response(path='/backup/report.txt'):
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        'path_display': path,
        'size': 12,
        'rev': 'rev1',
    }
    return resp


_SAMPLE_FILE = {
    '.tag': 'file',
    'name': 'report.csv',
    'path_lower': '/reports/report.csv',
    'path_display': '/reports/report.csv',
    'size': 1024,
    'rev': 'abc1',
    'id': 'id:abc1',
    'server_modified': '2026-09-18T09:00:00Z',
    'client_modified': '2026-09-18T08:00:00Z',
}

_SAMPLE_FOLDER = {
    '.tag': 'folder',
    'name': 'archive',
    'path_lower': '/reports/archive',
}


# ══════════════════════════════════════════════════════════════════════════════
# DropboxReadAgent — registration & validation
# ══════════════════════════════════════════════════════════════════════════════

class TestDropboxReadAgentRegistration:
    def test_registered(self):
        assert agent_registry.get_agent_class('dropbox_read_agent') is DropboxReadAgent

    def test_capabilities(self, read_job, db_session):
        agent = _make_agent(read_job, db_session)
        assert agent.can_be_scheduled is True
        assert agent.can_create_events is True
        assert agent.can_receive_events is False


class TestDropboxReadAgentValidation:
    def test_missing_access_token_raises(self, read_job, db_session):
        with pytest.raises(ValueError, match='access_token'):
            _make_agent(read_job, db_session, config={
                'folder_path': '/reports',
            })

    def test_missing_folder_path_raises(self, read_job, db_session):
        with pytest.raises(ValueError, match='folder_path'):
            _make_agent(read_job, db_session, config={
                'access_token': 'tok',
            })

    def test_invalid_read_content_type_raises(self, read_job, db_session):
        with pytest.raises(ValueError, match='read_content'):
            _make_agent(read_job, db_session, config={
                'access_token': 'tok',
                'folder_path': '/reports',
                'read_content': 'yes',
            })

    def test_invalid_max_files_raises(self, read_job, db_session):
        with pytest.raises(ValueError, match='max_files'):
            _make_agent(read_job, db_session, config={
                'access_token': 'tok',
                'folder_path': '/reports',
                'max_files': 0,
            })

    def test_valid_config_succeeds(self, read_job, db_session):
        agent = _make_agent(read_job, db_session)
        assert agent is not None


# ══════════════════════════════════════════════════════════════════════════════
# DropboxReadAgent — fetch behaviour
# ══════════════════════════════════════════════════════════════════════════════

class TestDropboxReadAgentFetch:
    def test_new_file_emits_event(self, read_job, db_session):
        agent = _make_agent(read_job, db_session)
        with patch('requests.post', return_value=_fake_list_response([_SAMPLE_FILE])):
            events = agent.fetch()
        assert len(events) == 1
        assert events[0].payload['name'] == 'report.csv'
        assert events[0].payload['size'] == 1024
        assert events[0].payload['rev'] == 'abc1'

    def test_subfolder_entries_are_skipped(self, read_job, db_session):
        agent = _make_agent(read_job, db_session)
        with patch('requests.post', return_value=_fake_list_response([_SAMPLE_FOLDER, _SAMPLE_FILE])):
            events = agent.fetch()
        assert len(events) == 1
        assert events[0].payload['name'] == 'report.csv'

    def test_seen_revision_not_re_emitted(self, read_job, db_session):
        agent = _make_agent(read_job, db_session)
        # Pre-seed memory with the revision already seen
        agent.memory.set('rev:/reports/report.csv', 'abc1')
        with patch('requests.post', return_value=_fake_list_response([_SAMPLE_FILE])):
            events = agent.fetch()
        assert events == []

    def test_updated_revision_is_emitted(self, read_job, db_session):
        agent = _make_agent(read_job, db_session)
        # Seen an older revision
        agent.memory.set('rev:/reports/report.csv', 'old_rev')
        updated = {**_SAMPLE_FILE, 'rev': 'abc2'}
        with patch('requests.post', return_value=_fake_list_response([updated])):
            events = agent.fetch()
        assert len(events) == 1
        assert events[0].payload['rev'] == 'abc2'

    def test_memory_is_updated_after_emit(self, read_job, db_session):
        agent = _make_agent(read_job, db_session)
        with patch('requests.post', return_value=_fake_list_response([_SAMPLE_FILE])):
            agent.fetch()
        assert agent.memory.get('rev:/reports/report.csv') == 'abc1'

    def test_file_filter_excludes_non_matching(self, read_job, db_session):
        agent = _make_agent(read_job, db_session, config={
            'access_token': 'tok',
            'folder_path': '/reports',
            'file_filter': '.json',
        })
        with patch('requests.post', return_value=_fake_list_response([_SAMPLE_FILE])):
            events = agent.fetch()
        assert events == []  # report.csv does not match .json

    def test_file_filter_case_insensitive(self, read_job, db_session):
        agent = _make_agent(read_job, db_session, config={
            'access_token': 'tok',
            'folder_path': '/reports',
            'file_filter': 'REPORT',
        })
        with patch('requests.post', return_value=_fake_list_response([_SAMPLE_FILE])):
            events = agent.fetch()
        assert len(events) == 1

    def test_max_files_limits_output(self, read_job, db_session):
        agent = _make_agent(read_job, db_session, config={
            'access_token': 'tok',
            'folder_path': '/reports',
            'max_files': 2,
        })
        entries = [
            {**_SAMPLE_FILE, 'name': f'f{i}.csv', 'path_lower': f'/reports/f{i}.csv', 'rev': f'rev{i}'}
            for i in range(5)
        ]
        with patch('requests.post', return_value=_fake_list_response(entries)):
            events = agent.fetch()
        assert len(events) == 2

    def test_empty_folder_emits_no_events(self, read_job, db_session):
        agent = _make_agent(read_job, db_session)
        with patch('requests.post', return_value=_fake_list_response([])):
            events = agent.fetch()
        assert events == []

    def test_api_error_propagates(self, read_job, db_session):
        agent = _make_agent(read_job, db_session)
        bad_resp = MagicMock()
        bad_resp.raise_for_status.side_effect = requests.HTTPError('409 Conflict')
        with patch('requests.post', return_value=bad_resp):
            with pytest.raises(requests.HTTPError):
                agent.fetch()

    def test_pagination_followed(self, read_job, db_session):
        """has_more=True triggers a second call to list_folder/continue."""
        file_a = {**_SAMPLE_FILE, 'name': 'a.csv', 'path_lower': '/reports/a.csv', 'rev': 'r1'}
        file_b = {**_SAMPLE_FILE, 'name': 'b.csv', 'path_lower': '/reports/b.csv', 'rev': 'r2'}

        page1 = MagicMock()
        page1.raise_for_status = MagicMock()
        page1.json.return_value = {'entries': [file_a], 'has_more': True, 'cursor': 'cur1'}

        page2 = MagicMock()
        page2.raise_for_status = MagicMock()
        page2.json.return_value = {'entries': [file_b], 'has_more': False, 'cursor': 'cur2'}

        agent = _make_agent(read_job, db_session)
        with patch('requests.post', side_effect=[page1, page2]):
            events = agent.fetch()
        assert len(events) == 2
        names = {e.payload['name'] for e in events}
        assert names == {'a.csv', 'b.csv'}

    def test_read_content_downloads_file(self, read_job, db_session):
        agent = _make_agent(read_job, db_session, config={
            'access_token': 'tok',
            'folder_path': '/reports',
            'read_content': True,
        })

        list_resp = _fake_list_response([_SAMPLE_FILE])
        content_resp = MagicMock()
        content_resp.status_code = 200
        content_resp.text = 'col1,col2\nval1,val2\n'

        with patch('requests.post', side_effect=[list_resp, content_resp]):
            events = agent.fetch()

        assert len(events) == 1
        assert events[0].payload['content'] == 'col1,col2\nval1,val2\n'

    def test_read_content_download_failure_omits_content_field(self, read_job, db_session):
        agent = _make_agent(read_job, db_session, config={
            'access_token': 'tok',
            'folder_path': '/reports',
            'read_content': True,
        })

        list_resp = _fake_list_response([_SAMPLE_FILE])
        fail_resp = MagicMock()
        fail_resp.status_code = 409
        fail_resp.text = ''

        with patch('requests.post', side_effect=[list_resp, fail_resp]):
            events = agent.fetch()

        assert len(events) == 1
        assert 'content' not in events[0].payload

    def test_bearer_token_sent_in_authorization_header(self, read_job, db_session):
        agent = _make_agent(read_job, db_session)
        with patch('requests.post', return_value=_fake_list_response([])) as mock_post:
            agent.fetch()
        call_headers = mock_post.call_args.kwargs.get('headers') or mock_post.call_args[1].get('headers', {})
        assert call_headers.get('Authorization') == 'Bearer test-token'


# ══════════════════════════════════════════════════════════════════════════════
# DropboxWriteAgent — registration & validation
# ══════════════════════════════════════════════════════════════════════════════

class TestDropboxWriteAgentRegistration:
    def test_registered(self):
        assert agent_registry.get_agent_class('dropbox_write_agent') is DropboxWriteAgent

    def test_capabilities(self, write_job, db_session):
        agent = _make_write_agent(write_job, db_session)
        assert agent.can_receive_events is True
        assert agent.can_create_events is False
        assert agent.can_be_scheduled is False


class TestDropboxWriteAgentValidation:
    def test_missing_access_token_raises(self, write_job, db_session):
        with pytest.raises(ValueError, match='access_token'):
            _make_write_agent(write_job, db_session, config={
                'path_template': '/backup/{{name}}.txt',
                'content_template': '{{content}}',
            })

    def test_missing_path_template_raises(self, write_job, db_session):
        with pytest.raises(ValueError, match='path_template'):
            _make_write_agent(write_job, db_session, config={
                'access_token': 'tok',
                'content_template': '{{content}}',
            })

    def test_missing_content_template_raises(self, write_job, db_session):
        with pytest.raises(ValueError, match='content_template'):
            _make_write_agent(write_job, db_session, config={
                'access_token': 'tok',
                'path_template': '/backup/{{name}}.txt',
            })

    def test_invalid_mode_raises(self, write_job, db_session):
        with pytest.raises(ValueError, match='mode'):
            _make_write_agent(write_job, db_session, config={
                'access_token': 'tok',
                'path_template': '/backup/{{name}}.txt',
                'content_template': '{{content}}',
                'mode': 'append',
            })

    def test_invalid_path_template_syntax_raises(self, write_job, db_session):
        with pytest.raises(ValueError, match='path_template'):
            _make_write_agent(write_job, db_session, config={
                'access_token': 'tok',
                'path_template': '/backup/{% bad syntax %}.txt',
                'content_template': '{{content}}',
            })

    def test_valid_config_with_add_mode(self, write_job, db_session):
        agent = _make_write_agent(write_job, db_session, config={
            'access_token': 'tok',
            'path_template': '/backup/{{name}}.txt',
            'content_template': '{{content}}',
            'mode': 'add',
        })
        assert agent is not None


# ══════════════════════════════════════════════════════════════════════════════
# DropboxWriteAgent — act behaviour
# ══════════════════════════════════════════════════════════════════════════════

def _make_event(job, payload):
    return Event(
        agent_id=job.id,
        agent_type='dropbox_write_agent',
        user_id=job.user_id,
        payload=payload,
        metadata={},
    )


class TestDropboxWriteAgentAct:
    def test_uploads_rendered_content(self, write_job, db_session):
        agent = _make_write_agent(write_job, db_session)
        event = _make_event(write_job, {'name': 'report', 'content': 'hello world'})

        with patch('requests.post', return_value=_fake_upload_response('/backup/report.txt')) as mock_post:
            agent.act([event])

        assert mock_post.called
        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs['data'] == b'hello world'

    def test_path_template_is_rendered(self, write_job, db_session):
        agent = _make_write_agent(write_job, db_session)
        event = _make_event(write_job, {'name': 'daily', 'content': 'x'})

        with patch('requests.post', return_value=_fake_upload_response('/backup/daily.txt')) as mock_post:
            agent.act([event])

        api_arg = json.loads(mock_post.call_args.kwargs['headers']['Dropbox-API-Arg'])
        assert api_arg['path'] == '/backup/daily.txt'

    def test_default_mode_is_overwrite(self, write_job, db_session):
        agent = _make_write_agent(write_job, db_session)
        event = _make_event(write_job, {'name': 'r', 'content': 'x'})

        with patch('requests.post', return_value=_fake_upload_response()) as mock_post:
            agent.act([event])

        api_arg = json.loads(mock_post.call_args.kwargs['headers']['Dropbox-API-Arg'])
        assert api_arg['mode'] == 'overwrite'

    def test_add_mode_passed_to_api(self, write_job, db_session):
        agent = _make_write_agent(write_job, db_session, config={
            'access_token': 'tok',
            'path_template': '/backup/{{name}}.txt',
            'content_template': '{{content}}',
            'mode': 'add',
        })
        event = _make_event(write_job, {'name': 'r', 'content': 'x'})

        with patch('requests.post', return_value=_fake_upload_response()) as mock_post:
            agent.act([event])

        api_arg = json.loads(mock_post.call_args.kwargs['headers']['Dropbox-API-Arg'])
        assert api_arg['mode'] == 'add'

    def test_bearer_token_sent_in_authorization_header(self, write_job, db_session):
        agent = _make_write_agent(write_job, db_session)
        event = _make_event(write_job, {'name': 'r', 'content': 'x'})

        with patch('requests.post', return_value=_fake_upload_response()) as mock_post:
            agent.act([event])

        auth = mock_post.call_args.kwargs['headers']['Authorization']
        assert auth == 'Bearer test-token'

    def test_multiple_events_produce_multiple_uploads(self, write_job, db_session):
        agent = _make_write_agent(write_job, db_session)
        events = [
            _make_event(write_job, {'name': f'file{i}', 'content': f'body{i}'})
            for i in range(3)
        ]

        with patch('requests.post', return_value=_fake_upload_response()) as mock_post:
            agent.act(events)

        assert mock_post.call_count == 3

    def test_http_error_collected_in_test_mode(self, write_job, db_session):
        agent = _make_write_agent(write_job, db_session)
        agent._test_mode_errors = []
        event = _make_event(write_job, {'name': 'r', 'content': 'x'})

        bad_resp = MagicMock()
        bad_resp.raise_for_status.side_effect = requests.HTTPError('401 Unauthorized')

        with patch('requests.post', return_value=bad_resp):
            agent.act([event])

        assert len(agent._test_mode_errors) == 1
        assert '401' in agent._test_mode_errors[0]

    def test_http_error_not_raised_in_production_mode(self, write_job, db_session):
        """act() swallows errors in normal mode so one bad event doesn't halt the rest."""
        agent = _make_write_agent(write_job, db_session)
        event = _make_event(write_job, {'name': 'r', 'content': 'x'})

        bad_resp = MagicMock()
        bad_resp.raise_for_status.side_effect = requests.HTTPError('500 Server Error')

        with patch('requests.post', return_value=bad_resp):
            agent.act([event])  # must not raise

    def test_content_template_rendered_with_payload(self, write_job, db_session):
        agent = _make_write_agent(write_job, db_session, config={
            'access_token': 'tok',
            'path_template': '/out/data.txt',
            'content_template': 'Name: {{name}}\nSize: {{size}}',
        })
        event = _make_event(write_job, {'name': 'Alice', 'size': 42})

        with patch('requests.post', return_value=_fake_upload_response()) as mock_post:
            agent.act([event])

        assert mock_post.call_args.kwargs['data'] == b'Name: Alice\nSize: 42'
