"""
GitHub Trending Agent — emit one event per newly-trending repository.

GitHub has no official RSS feed or API for trending repositories. This agent
fetches the trending page directly and parses the HTML. Uses agent memory to
track which repos have already been emitted so each run only surfaces new
entries.

Single responsibility: ONLY fetches trending repos and emits events.
"""

import re
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from app.agents.base import SourceAgent
from app.agents.registry import register_agent
from app.models import Event

_USER_AGENT = (
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
)
_SINCE_VALUES = ('daily', 'weekly', 'monthly')


@register_agent
class GitHubTrendingAgent(SourceAgent):
    """
    Fetches GitHub's trending repository list and emits one event per newly-
    seen repository. Memory is keyed per (repo, since) pair so switching
    between daily/weekly/monthly windows doesn't suppress results.

    Each event payload contains:
        repo          — "owner/name" path
        owner         — repository owner
        name          — repository name
        title         — same as repo (for downstream agents expecting title)
        url           — full https://github.com/owner/name URL
        description   — repository description (empty string if none)
        language      — primary programming language (empty string if unset)
        stars_today   — stars gained in the trending period (int)
        since         — "daily", "weekly", or "monthly"

    Configuration:
        language (str, optional): Filter by programming language slug as it
            appears in GitHub URLs, e.g. "python", "javascript", "typescript".
            Leave blank for all languages.
        since (str): Trending period — "daily" (default), "weekly", "monthly".
        max_repos (int): Maximum repos to emit per run (default: 25).
        spoken_language_code (str, optional): ISO 639-1 code to filter by
            human language of the repo content, e.g. "en".
    """

    agent_type = 'github_trending_agent'
    agent_category = 'source'

    def validate_config(self) -> None:
        super().validate_config()
        since = self.config.get('since', 'daily')
        if since not in _SINCE_VALUES:
            raise ValueError(
                f"'since' must be one of: {', '.join(_SINCE_VALUES)}"
            )
        if 'max_repos' in self.config:
            v = self.config['max_repos']
            if not isinstance(v, int) or v < 1:
                raise ValueError("'max_repos' must be a positive integer")

    def fetch(self) -> List[Event]:
        language = self.config.get('language', '').strip().lower()
        since = self.config.get('since', 'daily')
        max_repos = self.config.get('max_repos', 25)
        spoken = self.config.get('spoken_language_code', '').strip()

        url = 'https://github.com/trending'
        if language:
            url += f'/{language}'

        params = {}
        if since != 'daily':
            params['since'] = since
        if spoken:
            params['spoken_language_code'] = spoken

        resp = requests.get(
            url,
            params=params,
            headers={'User-Agent': _USER_AGENT},
            timeout=20,
        )
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, 'html.parser')
        articles = soup.select('article.Box-row')

        if not articles:
            self.log(
                'No trending repositories found — GitHub may have changed '
                'their page structure',
                level='warning',
            )
            return []

        events = []
        for article in articles:
            repo_path = self._parse_repo_path(article)
            if not repo_path:
                continue

            mem_key = f'seen:{since}:{repo_path}'
            if self.memory.get(mem_key):
                continue

            payload = self._build_payload(article, repo_path, since)
            ttl_days = {'daily': 2, 'weekly': 8, 'monthly': 32}[since]
            self.memory.set(mem_key, True, ttl=ttl_days * 86400)
            events.append(self.create_event(payload=payload))

            if len(events) >= max_repos:
                break

        period_label = f'{since} trending'
        self.log(
            f'Emitting {len(events)} new repo(s) from {period_label}',
            data={'language': language or 'all', 'since': since},
        )
        return events

    # ── helpers ───────────────────────────────────────────────────────────────

    def _parse_repo_path(self, article) -> Optional[str]:
        link = article.select_one('h2 a')
        if not link:
            return None
        return link.get('href', '').lstrip('/')

    def _build_payload(self, article, repo_path: str, since: str) -> dict:
        parts = repo_path.split('/', 1)
        owner = parts[0] if parts else ''
        name = parts[1] if len(parts) > 1 else repo_path

        desc_el = article.select_one('p')
        description = desc_el.get_text(strip=True) if desc_el else ''

        lang_el = article.select_one("span[itemprop='programmingLanguage']")
        language = lang_el.get_text(strip=True) if lang_el else ''

        stars_today = self._parse_stars_today(article, since)

        return {
            'repo': repo_path,
            'owner': owner,
            'name': name,
            'title': repo_path,           # for TopicExtractAgent compatibility
            'url': f'https://github.com/{repo_path}',
            'description': description,
            'language': language,
            'stars_today': stars_today,
            'since': since,
        }

    def _parse_stars_today(self, article, since: str) -> int:
        """Extract the 'N stars today/this week/this month' count."""
        el = article.select_one('span.d-inline-block.float-sm-right')
        if not el:
            return 0
        text = el.get_text(strip=True).replace(',', '')
        match = re.search(r'(\d+)', text)
        return int(match.group(1)) if match else 0

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        schema = super().get_config_schema()
        schema['required_fields'] = []
        schema['optional_fields'] = [
            {
                'name': 'language',
                'type': 'text',
                'description': (
                    'Filter by programming language slug as used in GitHub URLs '
                    '(e.g. "python", "javascript", "typescript"). '
                    'Leave blank for all languages.'
                ),
                'placeholder': 'e.g. python',
            },
            {
                'name': 'since',
                'type': 'select',
                'default': 'daily',
                'description': 'Trending period.',
                'options': [
                    {'value': 'daily',   'label': 'Daily'},
                    {'value': 'weekly',  'label': 'Weekly'},
                    {'value': 'monthly', 'label': 'Monthly'},
                ],
            },
            {
                'name': 'max_repos',
                'type': 'number',
                'default': 25,
                'description': 'Maximum repositories to emit per run.',
            },
            {
                'name': 'spoken_language_code',
                'type': 'text',
                'description': (
                    'ISO 639-1 code to filter repos by human language '
                    '(e.g. "en"). Leave blank for all.'
                ),
                'placeholder': 'e.g. en',
            },
        ] + schema['optional_fields']
        return schema
