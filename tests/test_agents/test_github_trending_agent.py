"""Tests for GitHubTrendingAgent."""

from unittest.mock import MagicMock, patch

import pytest
import requests as req_lib

from app.agents.registry import agent_registry
from app.agents.types.github_trending_agent import GitHubTrendingAgent


# ── minimal GitHub Trending HTML fixture ──────────────────────────────────────

def _make_article(
    href='/owner/repo-one',
    description='A cool project',
    language='Python',
    stars_text='123 stars today',
):
    lang_span = (
        f'<span itemprop="programmingLanguage">{language}</span>'
        if language else ''
    )
    stars_span = (
        f'<span class="d-inline-block float-sm-right">{stars_text}</span>'
        if stars_text else ''
    )
    return f"""
    <article class="Box-row">
      <h2 class="h3"><a href="{href}">  owner / repo-one  </a></h2>
      <p>{description}</p>
      {lang_span}
      {stars_span}
    </article>
    """


def _make_page(*articles):
    return '<html><body>' + '\n'.join(articles) + '</body></html>'


_ONE_REPO_HTML = _make_page(_make_article())
_THREE_REPOS_HTML = _make_page(
    _make_article('/alice/project-alpha', 'Alpha', 'Rust', '500 stars today'),
    _make_article('/bob/project-beta',   'Beta',  'Go',   '300 stars today'),
    _make_article('/carol/project-gamma', 'Gamma', 'TypeScript', '1,200 stars today'),
)
_NO_ARTICLES_HTML = '<html><body><p>Nothing here</p></body></html>'
_NO_LANG_HTML     = _make_page(_make_article(language='',    stars_text='50 stars today'))
_NO_STARS_HTML    = _make_page(_make_article(stars_text=''))


# ── fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def test_user(db_session):
    from app.models import User
    user = User(
        username='ghtrend_test',
        email='ghtrend@example.com',
        password='password123',
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def trending_job(db_session, test_user):
    from app.models import Job
    job = Job(
        name='GitHub Trending',
        job_type='github_trending_agent',
        config={'since': 'daily'},
        user_id=test_user.id,
    )
    db_session.add(job)
    db_session.commit()
    return job


def _make_agent(job, db_session, config=None):
    cfg = config if config is not None else job.config
    return GitHubTrendingAgent(
        agent_id=job.id,
        config=cfg,
        user_id=job.user_id,
        db_session=db_session,
    )


# ── mock HTTP helper ───────────────────────────────────────────────────────────

def _mock_resp(html: str, status: int = 200):
    resp = MagicMock()
    resp.status_code = status
    resp.text = html
    resp.raise_for_status = MagicMock()
    return resp


# ── registration ───────────────────────────────────────────────────────────────

class TestRegistration:
    def test_registered(self):
        assert agent_registry.get_agent_class('github_trending_agent') is GitHubTrendingAgent

    def test_category(self):
        assert GitHubTrendingAgent.agent_category == 'source'

    def test_capabilities(self, trending_job, db_session):
        agent = _make_agent(trending_job, db_session)
        assert agent.can_be_scheduled is True
        assert agent.can_create_events is True
        assert agent.can_receive_events is False


# ── validate_config ────────────────────────────────────────────────────────────

class TestValidateConfig:
    def test_defaults_valid(self, trending_job, db_session):
        _make_agent(trending_job, db_session)  # should not raise

    def test_all_since_values_valid(self, trending_job, db_session):
        for since in ('daily', 'weekly', 'monthly'):
            _make_agent(trending_job, db_session, config={'since': since})

    def test_invalid_since_raises(self, trending_job, db_session):
        with pytest.raises(ValueError, match='daily.*weekly.*monthly'):
            _make_agent(trending_job, db_session, config={'since': 'hourly'})

    def test_invalid_max_repos_raises(self, trending_job, db_session):
        with pytest.raises(ValueError, match='max_repos'):
            _make_agent(trending_job, db_session, config={'max_repos': -5})

    def test_zero_max_repos_raises(self, trending_job, db_session):
        with pytest.raises(ValueError, match='max_repos'):
            _make_agent(trending_job, db_session, config={'max_repos': 0})


# ── fetch — happy path ─────────────────────────────────────────────────────────

class TestFetch:
    def test_emits_one_event(self, trending_job, db_session):
        agent = _make_agent(trending_job, db_session)
        with patch('requests.get', return_value=_mock_resp(_ONE_REPO_HTML)):
            events = agent.fetch()
        assert len(events) == 1

    def test_event_payload_fields(self, trending_job, db_session):
        agent = _make_agent(trending_job, db_session)
        with patch('requests.get', return_value=_mock_resp(_ONE_REPO_HTML)):
            events = agent.fetch()
        p = events[0].payload
        assert p['repo'] == 'owner/repo-one'
        assert p['owner'] == 'owner'
        assert p['name'] == 'repo-one'
        assert p['title'] == 'owner/repo-one'   # for TopicExtractAgent
        assert p['url'] == 'https://github.com/owner/repo-one'
        assert p['description'] == 'A cool project'
        assert p['language'] == 'Python'
        assert p['stars_today'] == 123
        assert p['since'] == 'daily'

    def test_emits_multiple_repos(self, trending_job, db_session):
        agent = _make_agent(trending_job, db_session)
        with patch('requests.get', return_value=_mock_resp(_THREE_REPOS_HTML)):
            events = agent.fetch()
        assert len(events) == 3

    def test_stars_with_comma_parses_correctly(self, trending_job, db_session):
        """'1,200 stars today' should parse to 1200."""
        agent = _make_agent(trending_job, db_session)
        with patch('requests.get', return_value=_mock_resp(_THREE_REPOS_HTML)):
            events = agent.fetch()
        carol = next(e for e in events if 'gamma' in e.payload['repo'])
        assert carol.payload['stars_today'] == 1200

    def test_missing_language_is_empty_string(self, trending_job, db_session):
        agent = _make_agent(trending_job, db_session)
        with patch('requests.get', return_value=_mock_resp(_NO_LANG_HTML)):
            events = agent.fetch()
        assert events[0].payload['language'] == ''

    def test_missing_stars_is_zero(self, trending_job, db_session):
        agent = _make_agent(trending_job, db_session)
        with patch('requests.get', return_value=_mock_resp(_NO_STARS_HTML)):
            events = agent.fetch()
        assert events[0].payload['stars_today'] == 0

    def test_no_articles_returns_empty_list(self, trending_job, db_session):
        agent = _make_agent(trending_job, db_session)
        with patch('requests.get', return_value=_mock_resp(_NO_ARTICLES_HTML)):
            events = agent.fetch()
        assert events == []

    def test_returns_event_objects(self, trending_job, db_session):
        from app.models import Event
        agent = _make_agent(trending_job, db_session)
        with patch('requests.get', return_value=_mock_resp(_ONE_REPO_HTML)):
            events = agent.fetch()
        assert all(isinstance(e, Event) for e in events)


# ── deduplication via memory ───────────────────────────────────────────────────

class TestDeduplication:
    def test_second_run_skips_seen_repos(self, trending_job, db_session):
        agent = _make_agent(trending_job, db_session)
        with patch('requests.get', return_value=_mock_resp(_ONE_REPO_HTML)):
            first = agent.fetch()
        assert len(first) == 1
        with patch('requests.get', return_value=_mock_resp(_ONE_REPO_HTML)):
            second = agent.fetch()
        assert second == []

    def test_new_repo_emitted_on_later_run(self, trending_job, db_session):
        two_html = _make_page(
            _make_article('/alice/alpha', stars_text='100 stars today'),
            _make_article('/bob/beta',   stars_text='50 stars today'),
        )
        three_html = _make_page(
            _make_article('/alice/alpha', stars_text='100 stars today'),
            _make_article('/bob/beta',   stars_text='50 stars today'),
            _make_article('/carol/new',  stars_text='200 stars today'),
        )
        agent = _make_agent(trending_job, db_session)
        with patch('requests.get', return_value=_mock_resp(two_html)):
            first = agent.fetch()
        assert len(first) == 2

        with patch('requests.get', return_value=_mock_resp(two_html)):
            second = agent.fetch()
        assert second == []

        with patch('requests.get', return_value=_mock_resp(three_html)):
            third = agent.fetch()
        assert len(third) == 1
        assert third[0].payload['repo'] == 'carol/new'

    def test_daily_and_weekly_memory_keys_independent(
        self, db_session, test_user
    ):
        """A repo seen under 'daily' should NOT be suppressed under 'weekly'."""
        from app.models import Job

        daily_job = Job(
            name='GH Daily',
            job_type='github_trending_agent',
            config={'since': 'daily'},
            user_id=test_user.id,
        )
        weekly_job = Job(
            name='GH Weekly',
            job_type='github_trending_agent',
            config={'since': 'weekly'},
            user_id=test_user.id,
        )
        db_session.add(daily_job)
        db_session.add(weekly_job)
        db_session.commit()

        daily_agent  = _make_agent(daily_job,  db_session)
        weekly_agent = _make_agent(weekly_job, db_session)

        with patch('requests.get', return_value=_mock_resp(_ONE_REPO_HTML)):
            d_events = daily_agent.fetch()
        assert len(d_events) == 1

        with patch('requests.get', return_value=_mock_resp(_ONE_REPO_HTML)):
            w_events = weekly_agent.fetch()
        assert len(w_events) == 1


# ── max_repos limit ────────────────────────────────────────────────────────────

class TestMaxRepos:
    def test_max_repos_caps_output(self, trending_job, db_session):
        agent = _make_agent(trending_job, db_session, config={'since': 'daily', 'max_repos': 2})
        with patch('requests.get', return_value=_mock_resp(_THREE_REPOS_HTML)):
            events = agent.fetch()
        assert len(events) == 2


# ── URL construction ───────────────────────────────────────────────────────────

class TestURLConstruction:
    def _capture(self, agent, html):
        calls = []
        def fake_get(url, **kw):
            calls.append((url, kw))
            return _mock_resp(html)
        with patch('requests.get', side_effect=fake_get):
            agent.fetch()
        return calls[0] if calls else (None, {})

    def test_base_url_no_language(self, trending_job, db_session):
        agent = _make_agent(trending_job, db_session)
        url, _ = self._capture(agent, _ONE_REPO_HTML)
        assert url == 'https://github.com/trending'

    def test_language_appended_to_path(self, trending_job, db_session):
        agent = _make_agent(trending_job, db_session, config={'language': 'python'})
        url, _ = self._capture(agent, _ONE_REPO_HTML)
        assert url == 'https://github.com/trending/python'

    def test_language_lowercased(self, trending_job, db_session):
        agent = _make_agent(trending_job, db_session, config={'language': 'TypeScript'})
        url, _ = self._capture(agent, _ONE_REPO_HTML)
        assert url == 'https://github.com/trending/typescript'

    def test_since_weekly_adds_query_param(self, trending_job, db_session):
        agent = _make_agent(trending_job, db_session, config={'since': 'weekly'})
        _, kwargs = self._capture(agent, _ONE_REPO_HTML)
        assert kwargs['params']['since'] == 'weekly'

    def test_since_daily_omits_query_param(self, trending_job, db_session):
        agent = _make_agent(trending_job, db_session)
        _, kwargs = self._capture(agent, _ONE_REPO_HTML)
        assert 'since' not in kwargs.get('params', {})

    def test_spoken_language_adds_param(self, trending_job, db_session):
        agent = _make_agent(trending_job, db_session, config={'spoken_language_code': 'en'})
        _, kwargs = self._capture(agent, _ONE_REPO_HTML)
        assert kwargs['params']['spoken_language_code'] == 'en'

    def test_user_agent_header_set(self, trending_job, db_session):
        agent = _make_agent(trending_job, db_session)
        _, kwargs = self._capture(agent, _ONE_REPO_HTML)
        assert 'Mozilla' in kwargs['headers']['User-Agent']


# ── HTTP errors ────────────────────────────────────────────────────────────────

class TestHTTPErrors:
    def test_http_error_propagates(self, trending_job, db_session):
        agent = _make_agent(trending_job, db_session)
        err_resp = MagicMock()
        err_resp.raise_for_status.side_effect = req_lib.HTTPError('403 Forbidden')
        with patch('requests.get', return_value=err_resp):
            with pytest.raises(req_lib.HTTPError):
                agent.fetch()


# ── config schema ──────────────────────────────────────────────────────────────

class TestConfigSchema:
    def test_schema_has_expected_optional_fields(self):
        schema = GitHubTrendingAgent.get_config_schema()
        names = {f['name'] for f in schema['optional_fields']}
        assert {'language', 'since', 'max_repos', 'spoken_language_code'}.issubset(names)

    def test_schema_has_no_required_fields(self):
        schema = GitHubTrendingAgent.get_config_schema()
        assert schema['required_fields'] == []

    def test_since_is_select_with_three_options(self):
        schema = GitHubTrendingAgent.get_config_schema()
        since = next(f for f in schema['optional_fields'] if f['name'] == 'since')
        assert since['type'] == 'select'
        values = {o['value'] for o in since['options']}
        assert values == {'daily', 'weekly', 'monthly'}

    def test_max_repos_is_number_with_default_25(self):
        schema = GitHubTrendingAgent.get_config_schema()
        max_repos = next(f for f in schema['optional_fields'] if f['name'] == 'max_repos')
        assert max_repos['type'] == 'number'
        assert max_repos['default'] == 25
