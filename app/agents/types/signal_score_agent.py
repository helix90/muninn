"""
Signal Score Agent - decides which topics are "quiet signal" worth surfacing.

Consumes two distinct kinds of upstream events:
  1. Hype snapshots (event_metadata['event_kind'] == 'hype_snapshot') from
     HypeTermAgent - merged into this agent's own memory, not re-emitted.
  2. Candidate topic events (from FrequencyTrackerAgent) carrying
     payload['topic_stats'] - scored against the cached hype terms and
     persistence thresholds, and emitted if they pass.

Muninn's event propagation calls process() once per upstream source per run
(events are grouped by originating agent before an agent is invoked), so a
single call only ever contains one kind of batch. This agent branches on
event_metadata['event_kind'] to tell them apart, rather than requiring both
inputs to arrive together.

Hype snapshots are MERGED, not replaced: each term remembers when it was last
seen and expires on its own after hype_terms_max_age_hours. With several
noise-baseline feeds (each feeding its own HypeTermAgent, or one agent fed by
several feeds - which runs once per feed), replacing would mean only the last
feed's snapshot ever counted.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from app.agents.base import TransformAgent
from app.agents.registry import register_agent
from app.models import Event


@register_agent
class SignalScoreAgent(TransformAgent):
    """
    Configuration:
        max_distinct_sources_48h (int): drop topics already covered by more
            than this many distinct sources in the last 48h (default: 4)
        min_recurrences (int): minimum mentions within the tracking window
            to count as persistent rather than a one-off (default: 2)
        min_span_days (int): mentions must be spread across at least this
            many days (default: 10)
        hype_terms_max_age_hours (int): forget a hype term this long after
            the last snapshot that contained it. If every cached term has
            expired, hype filtering is skipped rather than blocking
            everything (default: 6)
        max_hype_overlap (float): drop a topic when its topic_key matches the
            hype terms, or when at least this fraction of its topic_terms do
            (default: 0.5). A multi-word term also matches when every one of
            its words is itself a hype term.
        max_hype_language_hits (int): drop items whose text used more than
            this many promotional/clickbait words (payload['hype_language']
            from TopicExtractAgent) (default: 1)
        resurface_cooldown_days (int): once a topic cluster has been
            surfaced, suppress further items from the same cluster for this
            many days, so one persistent story doesn't fill the digest.
            0 disables (default: 0)
    """

    agent_type = 'signal_score_agent'
    agent_category = 'transform'

    def validate_config(self) -> None:
        super().validate_config()

        for field in ('max_distinct_sources_48h', 'min_recurrences',
                      'min_span_days', 'hype_terms_max_age_hours',
                      'max_hype_language_hits', 'resurface_cooldown_days'):
            if field in self.config:
                value = self.config[field]
                if not isinstance(value, (int, float)) or value < 0:
                    raise ValueError(f"'{field}' must be a non-negative number")

        if 'max_hype_overlap' in self.config:
            value = self.config['max_hype_overlap']
            if not isinstance(value, (int, float)) or not 0 < value <= 1:
                raise ValueError("'max_hype_overlap' must be a number in (0, 1]")

    def process(self, events: List[Event]) -> List[Event]:
        if not events:
            return []

        if events[0].event_metadata.get('event_kind') == 'hype_snapshot':
            for event in events:
                self._absorb_hype_snapshot(event)
            return []

        return self._score_candidates(events)

    def _absorb_hype_snapshot(self, event: Event) -> None:
        hype_terms = event.get_payload_field('hype_terms') or []
        max_age_hours = self.config.get('hype_terms_max_age_hours', 6)
        now = datetime.now(timezone.utc)

        term_seen = self._active_term_seen(max_age_hours, now)
        for term in hype_terms:
            # Re-insert so the dict order reflects recency.
            term_seen.pop(term, None)
            term_seen[term] = now.isoformat()

        self.memory.set('hype_terms_state', {
            'terms': list(term_seen),
            'term_seen': term_seen,
            'updated_at': now.isoformat(),
        })
        self.log(f'Merged {len(hype_terms)} hype terms ({len(term_seen)} active)', level='debug')

    def _score_candidates(self, events: List[Event]) -> List[Event]:
        max_sources = self.config.get('max_distinct_sources_48h', 4)
        min_recurrences = self.config.get('min_recurrences', 2)
        min_span_days = self.config.get('min_span_days', 10)
        max_age_hours = self.config.get('hype_terms_max_age_hours', 6)
        max_overlap = self.config.get('max_hype_overlap', 0.5)
        max_language_hits = self.config.get('max_hype_language_hits', 1)
        cooldown_days = self.config.get('resurface_cooldown_days', 0)

        hype_terms = set(self._current_hype_terms(max_age_hours))
        hype_words = {t for t in hype_terms if ' ' not in t}

        output_events = []
        rejected = {'hype_terms': 0, 'hype_language': 0, 'not_persistent': 0,
                    'too_widely_covered': 0, 'cooldown': 0}

        for event in events:
            topic_key = event.get_payload_field('topic_key')
            topic_terms = event.get_payload_field('topic_terms') or []
            stats = event.get_payload_field('topic_stats') or {}

            if not topic_key or not stats:
                self.log('Missing topic_key/topic_stats, skipping', level='warning',
                         data={'event_id': event.id})
                continue

            def is_hype_term(term):
                return term in hype_terms or (
                    ' ' in term and all(w in hype_words for w in term.split())
                )

            terms = topic_terms or [topic_key]
            hype_matches = [t for t in terms if is_hype_term(t)]
            is_hype = is_hype_term(topic_key) or len(hype_matches) / len(terms) >= max_overlap

            hype_language = event.get_payload_field('hype_language') or []
            is_oversold = len(hype_language) > max_language_hits

            is_persistent = (
                stats.get('recurrence_count', 0) >= min_recurrences
                and stats.get('span_days', 0) >= min_span_days
            )
            is_quiet = stats.get('distinct_sources_48h', 0) <= max_sources

            if is_hype:
                rejected['hype_terms'] += 1
                continue
            if is_oversold:
                rejected['hype_language'] += 1
                continue
            if not is_persistent:
                rejected['not_persistent'] += 1
                continue
            if not is_quiet:
                rejected['too_widely_covered'] += 1
                continue

            cluster_keys = self._cluster_keys(event, topic_key)
            if cooldown_days and any(self.memory.exists(f'surfaced:{k}') for k in cluster_keys):
                rejected['cooldown'] += 1
                continue

            payload = event.payload.copy()
            payload['signal_reason'] = (
                f"{stats.get('recurrence_count')} mentions over "
                f"{stats.get('span_days')} days; "
                f"{stats.get('distinct_sources_48h')} source(s) in the last 48h; "
                f"{len(hype_matches)}/{len(terms)} topic terms overlap current hype"
            )

            metadata = {'source_event_id': event.id, 'transformer': 'signal_score'}
            if event.event_metadata:
                metadata['source_metadata'] = event.event_metadata

            output_events.append(self.create_event(payload=payload, metadata=metadata))

            if cooldown_days:
                ttl = int(timedelta(days=cooldown_days).total_seconds())
                for key in cluster_keys:
                    self.memory.set(f'surfaced:{key}', True, ttl=ttl)

        self.log(f'{len(output_events)}/{len(events)} candidates scored as quiet signal',
                 data={'rejected': rejected, 'active_hype_terms': len(hype_terms)})
        return output_events

    @staticmethod
    def _cluster_keys(event: Event, topic_key: str) -> List[str]:
        """Phrase-level keys identifying the story cluster. Single anchor
        words from FrequencyTrackerAgent are left out - they are too broad
        and would put unrelated stories on cooldown."""
        terms = event.get_payload_field('topic_cluster_terms') or event.get_payload_field('topic_terms') or []
        keys = [t for t in terms if ' ' in t]
        if topic_key not in keys:
            keys.append(topic_key)
        return keys

    def _active_term_seen(self, max_age_hours: float, now: datetime) -> Dict[str, str]:
        """Cached hype terms that haven't expired, as {term: last_seen_iso}."""
        state = self.memory.get('hype_terms_state')
        if not state:
            return {}

        term_seen = state.get('term_seen')
        if term_seen is None:
            # Pre-merge format: one timestamp for the whole snapshot.
            term_seen = {t: state.get('updated_at') for t in state.get('terms', [])}

        cutoff = now - timedelta(hours=max_age_hours)
        active = {}
        for term, seen_at in term_seen.items():
            seen_dt = self._parse_time(seen_at)
            if seen_dt is not None and seen_dt >= cutoff:
                active[term] = seen_at
        return active

    def _current_hype_terms(self, max_age_hours: float) -> List[str]:
        if not self.memory.get('hype_terms_state'):
            self.log('No hype-term snapshot cached yet - skipping hype filtering this run',
                     level='warning')
            return []

        active = self._active_term_seen(max_age_hours, datetime.now(timezone.utc))
        if not active:
            self.log('Cached hype terms are stale - skipping hype filtering this run',
                     level='warning')
        return list(active)

    @staticmethod
    def _parse_time(value) -> Optional[datetime]:
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    @classmethod
    def get_config_schema(cls):
        schema = super().get_config_schema()
        schema['required_fields'] = []
        schema['optional_fields'] = [
            {
                'name': 'max_distinct_sources_48h',
                'type': 'number',
                'default': 4,
                'description': 'Drop topics covered by more than this many distinct sources in the last 48h (higher = less strict hype filter).',
            },
            {
                'name': 'min_recurrences',
                'type': 'number',
                'default': 2,
                'description': 'Minimum number of mentions within the tracking window to be considered persistent.',
            },
            {
                'name': 'min_span_days',
                'type': 'number',
                'default': 10,
                'description': 'Mentions must span at least this many days. Lower to 2–3 on a new installation with limited history.',
            },
            {
                'name': 'hype_terms_max_age_hours',
                'type': 'number',
                'default': 6,
                'description': 'Forget a hype term this many hours after the last snapshot that contained it.',
            },
            {
                'name': 'max_hype_overlap',
                'type': 'number',
                'default': 0.5,
                'description': 'Drop a topic when its key, or at least this fraction (0–1) of its topic terms, matches current hype terms. Lower = stricter.',
            },
            {
                'name': 'max_hype_language_hits',
                'type': 'number',
                'default': 1,
                'description': 'Drop items using more than this many promotional/clickbait words ("revolutionary", "game-changing", "here\'s why"). 0 = strictest.',
            },
            {
                'name': 'resurface_cooldown_days',
                'type': 'number',
                'default': 0,
                'description': 'After surfacing a topic, suppress more items from the same story cluster for this many days (0 = off). Set to 7 for a weekly digest.',
            },
        ] + schema['optional_fields']
        return schema
