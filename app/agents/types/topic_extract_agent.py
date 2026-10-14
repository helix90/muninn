"""
Topic Extract Agent - naive keyword/phrase extraction from event text

Single responsibility: ONLY extracts candidate topic terms from an event's
title/summary text. Does no scoring, filtering, or cross-event comparison -
that's FrequencyTrackerAgent and SignalScoreAgent's job.

No ML/embeddings - just tokenization, stopword removal, and simple term-
frequency + adjacent-bigram heuristics (see app/agents/text_utils.py).

Before extraction the text is cleaned of HTML and feed boilerplate (hnrss,
arXiv, WordPress, reddit), and promotional vocabulary ("revolutionary",
"game-changing", "here's why") is kept out of topic terms. The promotional
words found are reported in payload['hype_language'] so SignalScoreAgent
can decide whether the item is being oversold.
"""

from typing import List
from app.agents.base import TransformAgent
from app.agents.registry import register_agent
from app.agents.text_utils import (
    STOPWORDS, HYPE_LANGUAGE_WORDS, clean_text, domain_from_url,
    hype_language_hits, strip_hype_phrases, top_terms_for_document,
)
from app.models import Event


@register_agent
class TopicExtractAgent(TransformAgent):
    """
    Extracts naive topic terms from each event's text fields.

    Configuration:
        source_fields (list): payload fields to read text from (default: ['title', 'summary'])
        max_topics_per_item (int): max terms to keep per item (default: 3)
        min_term_length (int): minimum word length to consider (default: 4)
        exclude_terms (list): extra words never to use as topic terms, e.g.
            recurring feed names or house jargon. Case-insensitive.
        extra_hype_terms (list): words/phrases added to the built-in
            promotional lexicon (reported in hype_language and excluded from
            topic terms). Case-insensitive.
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

        for field in ('exclude_terms', 'extra_hype_terms'):
            if field in self.config:
                value = self.config[field]
                if not isinstance(value, list) or not all(isinstance(t, str) for t in value):
                    raise ValueError(f"'{field}' must be a list of strings")

    def process(self, events: List[Event]) -> List[Event]:
        source_fields = self.config.get('source_fields', ['title', 'summary'])
        max_topics = self.config.get('max_topics_per_item', 3)
        min_length = self.config.get('min_term_length', 4)
        extra_hype = [t.lower().strip() for t in self.config.get('extra_hype_terms', []) if t.strip()]
        exclude = {t.lower().strip() for t in self.config.get('exclude_terms', [])}
        stopwords = STOPWORDS | HYPE_LANGUAGE_WORDS | exclude | {t for t in extra_hype if ' ' not in t}

        output_events = []

        for event in events:
            try:
                # Newline between fields so the last title word and first
                # summary word never form a bigram.
                text = '\n'.join(
                    clean_text(event.get_payload_field(field, '') or '')
                    for field in source_fields
                )

                hype_hits = hype_language_hits(text, extra_terms=extra_hype)
                topic_terms = top_terms_for_document(
                    strip_hype_phrases(text, extra_hype),
                    max_terms=max_topics, min_length=min_length, stopwords=stopwords,
                )

                if not topic_terms:
                    self.log('No topic terms extracted, skipping event', level='debug',
                             data={'event_id': event.id})
                    continue

                payload = event.payload.copy()
                payload['topic_terms'] = topic_terms
                payload['topic_key'] = topic_terms[0]
                payload['source_domain'] = domain_from_url(event.get_payload_field('link'))
                payload['hype_language'] = hype_hits

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
            {
                'name': 'exclude_terms',
                'type': 'textarea',
                'description': 'JSON array of words never to use as topic terms (e.g. recurring feed names).',
                'placeholder': '["podcast", "newsletter"]',
            },
            {
                'name': 'extra_hype_terms',
                'type': 'textarea',
                'description': 'JSON array of extra promotional words/phrases to flag in hype_language and exclude from topics.',
                'placeholder': '["paradigm shift", "agentic"]',
            },
        ] + schema['optional_fields']
        return schema
