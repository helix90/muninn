"""
Frequency Tracker Agent - tracks how many distinct sources mention each
topic over a rolling window, using persistent agent memory.

Single responsibility: ONLY maintains per-topic mention history and attaches
the resulting stats to each event. Does not decide what counts as "hype" or
"signal" - that's SignalScoreAgent's job.

Matching strategy: two articles about "the same" quiet story almost never
share one exact canonical label - one says "supply chain resilience",
another says "supply chain risk". Requiring an exact topic_key match would
miss that. Instead, this agent treats each event's topic_terms as a small
set of candidate labels and clusters via ANY shared multi-word phrase: it
looks up history under every one of the event's phrase-terms, unions
whatever it finds, appends this event, and writes the merged history back
under every one of those terms. That lets a chain of partially-overlapping
articles link up transitively (A shares a phrase with B, B shares a
different phrase with C) without ever needing one all-three-share term.

Only MULTI-WORD terms (phrases with a space) are used for clustering -
single words are far more likely to coincidentally recur across unrelated
stories ("manufacturing", "market"), which would over-merge distinct topics
into one. Single-word terms are still passed through in the payload for
display/hype-matching, just not used to link history together.
"""

from datetime import datetime, timedelta, timezone
from typing import List

from app.agents.base import TransformAgent
from app.agents.registry import register_agent
from app.agents.text_utils import domain_from_url
from app.models import Event


@register_agent
class FrequencyTrackerAgent(TransformAgent):
    """
    Maintains a rolling history of topic mentions (in this agent's own
    memory, keyed by topic) and computes, per incoming event:
        - distinct_sources_48h: distinct sources mentioning the topic in the last 48h
        - recurrence_count: total mentions retained in the window
        - span_days: days between the earliest and latest mention in the window

    Configuration:
        window_days (int): rolling window size in days (default: 14)
        max_records_per_topic (int): cap on stored history per topic (default: 200)
    """

    agent_type = 'frequency_tracker_agent'
    agent_category = 'transform'

    def validate_config(self) -> None:
        super().validate_config()

        if 'window_days' in self.config:
            if not isinstance(self.config['window_days'], (int, float)) or self.config['window_days'] <= 0:
                raise ValueError("'window_days' must be a positive number")

        if 'max_records_per_topic' in self.config:
            if not isinstance(self.config['max_records_per_topic'], int) or self.config['max_records_per_topic'] < 1:
                raise ValueError("'max_records_per_topic' must be a positive integer")

    def process(self, events: List[Event]) -> List[Event]:
        window_days = self.config.get('window_days', 14)
        max_records = self.config.get('max_records_per_topic', 200)
        ttl = int(timedelta(days=window_days).total_seconds())

        output_events = []
        now = datetime.now(timezone.utc)
        window_cutoff = now - timedelta(days=window_days)
        cutoff_48h = now - timedelta(hours=48)

        for event in events:
            terms = [t for t in (event.get_payload_field('topic_terms') or []) if t]
            if not terms:
                self.log('Event missing topic_terms, skipping', level='warning',
                         data={'event_id': event.id})
                continue

            # Only multi-word phrases are used to LINK history across articles;
            # lone words are too likely to coincidentally recur. Fall back to
            # all terms only if the article produced no phrases at all.
            cluster_terms = [t for t in terms if ' ' in t] or terms

            source = (
                event.get_payload_field('source_domain')
                or domain_from_url(event.get_payload_field('link'))
                or 'unknown'
            )

            # Union whatever history already exists under any of this event's
            # cluster terms (transitively links partially-overlapping stories).
            merged = []
            seen_pairs = set()
            for term in cluster_terms:
                for record in self.memory.get(f'topic_hist:{term}', []) or []:
                    if not self._within(record, window_cutoff):
                        continue
                    pair = (record.get('source'), record.get('seen_at'))
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    merged.append(record)

            merged.append({'source': source, 'seen_at': now.isoformat()})
            merged.sort(key=lambda r: r.get('seen_at') or '')
            if len(merged) > max_records:
                merged = merged[-max_records:]

            # Write the merged history back under EVERY cluster term this
            # event has, so a future article sharing any one of them inherits
            # the full combined history.
            for term in cluster_terms:
                self.memory.set(f'topic_hist:{term}', merged, ttl=ttl)

            distinct_sources_48h = len({
                r['source'] for r in merged if self._within(r, cutoff_48h)
            })
            seen_times = [t for t in (self._parse_time(r.get('seen_at')) for r in merged) if t]
            span_days = (max(seen_times) - min(seen_times)).total_seconds() / 86400 if seen_times else 0.0

            payload = event.payload.copy()
            payload['topic_stats'] = {
                'distinct_sources_48h': distinct_sources_48h,
                'recurrence_count': len(merged),
                'span_days': round(span_days, 2),
            }
            payload['topic_cluster_terms'] = cluster_terms

            metadata = {'source_event_id': event.id, 'transformer': 'frequency_tracker'}
            if event.event_metadata:
                metadata['source_metadata'] = event.event_metadata

            output_events.append(self.create_event(payload=payload, metadata=metadata))

        return output_events

    def _within(self, record, cutoff) -> bool:
        seen_at = self._parse_time(record.get('seen_at'))
        return seen_at is not None and seen_at >= cutoff

    @staticmethod
    def _parse_time(value):
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
