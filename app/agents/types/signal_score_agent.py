"""
Signal Score Agent - decides which topics are "quiet signal" worth surfacing.

Consumes two distinct kinds of upstream events:
  1. Hype snapshots (event_metadata['event_kind'] == 'hype_snapshot') from
     HypeTermAgent - cached into this agent's own memory, not re-emitted.
  2. Candidate topic events (from FrequencyTrackerAgent) carrying
     payload['topic_stats'] - scored against the cached hype terms and
     persistence thresholds, and emitted if they pass.

Muninn's event propagation calls process() once per upstream source per run
(events are grouped by originating agent before an agent is invoked), so a
single call only ever contains one kind of batch. This agent branches on
event_metadata['event_kind'] to tell them apart, rather than requiring both
inputs to arrive together.
"""

from datetime import datetime, timedelta, timezone
from typing import List

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
        hype_terms_max_age_hours (int): treat a cached hype snapshot as
            stale after this long, and stop applying hype filtering until a
            fresh snapshot arrives rather than blocking everything
            (default: 6)
    """

    agent_type = 'signal_score_agent'
    agent_category = 'transform'

    def validate_config(self) -> None:
        super().validate_config()

        for field in ('max_distinct_sources_48h', 'min_recurrences',
                      'min_span_days', 'hype_terms_max_age_hours'):
            if field in self.config:
                value = self.config[field]
                if not isinstance(value, (int, float)) or value < 0:
                    raise ValueError(f"'{field}' must be a non-negative number")

    def process(self, events: List[Event]) -> List[Event]:
        if not events:
            return []

        if events[0].event_metadata.get('event_kind') == 'hype_snapshot':
            return self._absorb_hype_snapshot(events[0])

        return self._score_candidates(events)

    def _absorb_hype_snapshot(self, event: Event) -> List[Event]:
        hype_terms = event.get_payload_field('hype_terms') or []
        self.memory.set('hype_terms_state', {
            'terms': hype_terms,
            'updated_at': datetime.now(timezone.utc).isoformat(),
        })
        self.log(f'Cached {len(hype_terms)} hype terms', level='debug')
        return []

    def _score_candidates(self, events: List[Event]) -> List[Event]:
        max_sources = self.config.get('max_distinct_sources_48h', 4)
        min_recurrences = self.config.get('min_recurrences', 2)
        min_span_days = self.config.get('min_span_days', 10)
        max_age_hours = self.config.get('hype_terms_max_age_hours', 6)

        hype_terms = set(self._current_hype_terms(max_age_hours))

        output_events = []

        for event in events:
            topic_key = event.get_payload_field('topic_key')
            topic_terms = event.get_payload_field('topic_terms') or []
            stats = event.get_payload_field('topic_stats') or {}

            if not topic_key or not stats:
                self.log('Missing topic_key/topic_stats, skipping', level='warning',
                         data={'event_id': event.id})
                continue

            is_hype = topic_key in hype_terms or any(t in hype_terms for t in topic_terms)
            is_persistent = (
                stats.get('recurrence_count', 0) >= min_recurrences
                and stats.get('span_days', 0) >= min_span_days
            )
            is_quiet = stats.get('distinct_sources_48h', 0) <= max_sources

            if is_hype or not is_persistent or not is_quiet:
                continue

            payload = event.payload.copy()
            payload['signal_reason'] = (
                f"{stats.get('recurrence_count')} mentions over "
                f"{stats.get('span_days')} days across "
                f"<= {stats.get('distinct_sources_48h')} sources in 48h; "
                f"not in this run's hype terms"
            )

            metadata = {'source_event_id': event.id, 'transformer': 'signal_score'}
            if event.event_metadata:
                metadata['source_metadata'] = event.event_metadata

            output_events.append(self.create_event(payload=payload, metadata=metadata))

        self.log(f'{len(output_events)}/{len(events)} candidates scored as quiet signal')
        return output_events

    def _current_hype_terms(self, max_age_hours: float) -> List[str]:
        state = self.memory.get('hype_terms_state')
        if not state:
            self.log('No hype-term snapshot cached yet - skipping hype filtering this run',
                     level='warning')
            return []

        updated_at = state.get('updated_at')
        try:
            updated_dt = datetime.fromisoformat(updated_at) if updated_at else None
        except (ValueError, TypeError):
            updated_dt = None

        if updated_dt is None:
            return []

        if updated_dt.tzinfo is None:
            updated_dt = updated_dt.replace(tzinfo=timezone.utc)

        age = datetime.now(timezone.utc) - updated_dt
        if age > timedelta(hours=max_age_hours):
            self.log('Cached hype terms are stale - skipping hype filtering this run',
                     level='warning', data={'age_hours': age.total_seconds() / 3600})
            return []

        return state.get('terms', [])
