"""
Hype Term Agent - build a "what's trending right now" term snapshot from a
noise-reference feed (e.g. a mainstream front page), so downstream agents
can suppress topics that overlap with it.

Single responsibility: ONLY computes a hype-term snapshot per run. Does not
filter or score anything itself - that's SignalScoreAgent's job.
"""

from datetime import datetime, timezone
from typing import List
from collections import Counter

from app.agents.base import TransformAgent
from app.agents.registry import register_agent
from app.agents.text_utils import document_term_set
from app.models import Event


@register_agent
class HypeTermAgent(TransformAgent):
    """
    Computes document-frequency term counts across a batch of noise-reference
    events and emits a single snapshot event tagged
    event_metadata['event_kind'] = 'hype_snapshot'.

    Configuration:
        source_fields (list): payload fields to read text from (default: ['title'])
        top_n_terms (int): number of terms to keep in the snapshot (default: 25)
        min_term_length (int): minimum word length to consider (default: 4)
        blocklist (list): additional terms to always exclude from the snapshot,
            e.g. ["energy", "windows"] for domain-specific noise you want
            suppressed regardless of their frequency. Case-insensitive.
    """

    agent_type = 'hype_term_agent'
    agent_category = 'transform'

    def validate_config(self) -> None:
        super().validate_config()

        if 'top_n_terms' in self.config:
            if not isinstance(self.config['top_n_terms'], int) or self.config['top_n_terms'] < 1:
                raise ValueError("'top_n_terms' must be a positive integer")

        if 'min_term_length' in self.config:
            if not isinstance(self.config['min_term_length'], int) or self.config['min_term_length'] < 1:
                raise ValueError("'min_term_length' must be a positive integer")

        if 'source_fields' in self.config:
            if not isinstance(self.config['source_fields'], list) or not self.config['source_fields']:
                raise ValueError("'source_fields' must be a non-empty list")

        if 'blocklist' in self.config:
            if not isinstance(self.config['blocklist'], list):
                raise ValueError("'blocklist' must be a list of strings")
            if not all(isinstance(t, str) for t in self.config['blocklist']):
                raise ValueError("all 'blocklist' entries must be strings")

    def process(self, events: List[Event]) -> List[Event]:
        if not events:
            return []

        source_fields = self.config.get('source_fields', ['title'])
        top_n = self.config.get('top_n_terms', 25)
        min_length = self.config.get('min_term_length', 4)
        blocklist = {t.lower() for t in self.config.get('blocklist', [])}

        # Document frequency: how many DISTINCT items mention each term this
        # run, not raw word count - one wordy article shouldn't dominate.
        doc_frequency = Counter()

        for event in events:
            text = ' '.join(
                str(event.get_payload_field(field, '') or '')
                for field in source_fields
            )
            terms = document_term_set(text, min_length=min_length)
            doc_frequency.update(terms)

        top_terms = [
            term for term, _ in doc_frequency.most_common(top_n + len(blocklist))
            if term not in blocklist
        ][:top_n]

        payload = {
            'hype_terms': top_terms,
            'item_count': len(events),
            'generated_at': datetime.now(timezone.utc).isoformat(),
        }
        metadata = {'event_kind': 'hype_snapshot'}

        self.log(f'Built hype-term snapshot from {len(events)} items', data={
            'top_terms': top_terms[:10],
        })

        return [self.create_event(payload=payload, metadata=metadata)]

    @classmethod
    def get_config_schema(cls):
        schema = super().get_config_schema()
        schema['required_fields'] = []
        schema['optional_fields'] = [
            {
                'name': 'top_n_terms',
                'type': 'number',
                'default': 25,
                'description': 'Number of hype terms to keep in the snapshot. Raise to 40-50 now that bigrams are included.',
            },
            {
                'name': 'min_term_length',
                'type': 'number',
                'default': 4,
                'description': 'Minimum character length for a word to be considered.',
            },
            {
                'name': 'source_fields',
                'type': 'text',
                'default': 'title',
                'description': 'Comma-separated payload fields to read text from (e.g. "title" or "title,summary").',
            },
            {
                'name': 'blocklist',
                'type': 'textarea',
                'description': 'JSON array of terms to always exclude from the snapshot regardless of frequency, e.g. ["windows", "energy"].',
                'placeholder': '["windows", "energy"]',
            },
        ] + schema['optional_fields']
        return schema
