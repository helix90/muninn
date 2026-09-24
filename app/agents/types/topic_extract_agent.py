"""
Topic Extract Agent - naive keyword/phrase extraction from event text

Single responsibility: ONLY extracts candidate topic terms from an event's
title/summary text. Does no scoring, filtering, or cross-event comparison -
that's FrequencyTrackerAgent and SignalScoreAgent's job.

No ML/embeddings - just tokenization, stopword removal, and simple term-
frequency + adjacent-bigram heuristics (see app/agents/text_utils.py).
"""

from typing import List
from app.agents.base import TransformAgent
from app.agents.registry import register_agent
from app.agents.text_utils import top_terms_for_document, domain_from_url
from app.models import Event


@register_agent
class TopicExtractAgent(TransformAgent):
    """
    Extracts naive topic terms from each event's text fields.

    Configuration:
        source_fields (list): payload fields to read text from (default: ['title', 'summary'])
        max_topics_per_item (int): max terms to keep per item (default: 3)
        min_term_length (int): minimum word length to consider (default: 4)
    """

    agent_type = 'topic_extract_agent'
    agent_category = 'transform'

    def validate_config(self) -> None:
        super().validate_config()

        if 'source_fields' in self.config:
            if not isinstance(self.config['source_fields'], list) or not self.config['source_fields']:
                raise ValueError("'source_fields' must be a non-empty list")

        if 'max_topics_per_item' in self.config:
            if not isinstance(self.config['max_topics_per_item'], int) or self.config['max_topics_per_item'] < 1:
                raise ValueError("'max_topics_per_item' must be a positive integer")

        if 'min_term_length' in self.config:
            if not isinstance(self.config['min_term_length'], int) or self.config['min_term_length'] < 1:
                raise ValueError("'min_term_length' must be a positive integer")

    def process(self, events: List[Event]) -> List[Event]:
        source_fields = self.config.get('source_fields', ['title', 'summary'])
        max_topics = self.config.get('max_topics_per_item', 3)
        min_length = self.config.get('min_term_length', 4)

        output_events = []

        for event in events:
            try:
                text = ' '.join(
                    str(event.get_payload_field(field, '') or '')
                    for field in source_fields
                )

                topic_terms = top_terms_for_document(text, max_terms=max_topics, min_length=min_length)

                if not topic_terms:
                    self.log('No topic terms extracted, skipping event', level='debug',
                             data={'event_id': event.id})
                    continue

                payload = event.payload.copy()
                payload['topic_terms'] = topic_terms
                payload['topic_key'] = topic_terms[0]
                payload['source_domain'] = domain_from_url(event.get_payload_field('link'))

                metadata = {'source_event_id': event.id, 'transformer': 'topic_extract'}
                if event.event_metadata:
                    metadata['source_metadata'] = event.event_metadata

                output_events.append(self.create_event(payload=payload, metadata=metadata))

            except Exception as e:
                self.log(f'Error extracting topics: {e}', level='error',
                         data={'event_id': event.id, 'error': str(e)})
                continue

        self.log(f'Extracted topics for {len(output_events)}/{len(events)} events')
        return output_events

    @classmethod
    def get_config_schema(cls):
        schema = super().get_config_schema()
        schema['required_fields'] = []
        schema['optional_fields'] = [
            {
                'name': 'max_topics_per_item',
                'type': 'number',
                'default': 3,
                'description': 'Maximum topic terms to extract per article.',
            },
            {
                'name': 'min_term_length',
                'type': 'number',
                'default': 4,
                'description': 'Minimum character length for a word to be considered as a topic term.',
            },
            {
                'name': 'source_fields',
                'type': 'text',
                'default': 'title, summary',
                'description': 'Comma-separated payload fields to extract topics from.',
            },
        ] + schema['optional_fields']
        return schema
