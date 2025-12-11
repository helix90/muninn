"""
HTML Parser Agent - Extract data from HTML via CSS selectors

Single responsibility: ONLY parses HTML and extracts data.
Does NOT fetch web pages (that's WebFetchAgent's job).
"""

from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from app.agents.base import TransformAgent
from app.agents.registry import register_agent
from app.models import Event


@register_agent
class HTMLParserAgent(TransformAgent):
    """
    Parses HTML content and extracts data via CSS selectors.

    Designed to work with WebFetchAgent output.
    Extracts data from 'content' field in incoming events.

    Configuration:
        selectors (dict): CSS selectors for data extraction
            Format: {'field_name': 'css_selector'}
        extract_mode (str): 'first' or 'all' (default: 'first')
        content_field (str): Field containing HTML content (default: 'content')
        create_event_per_item (bool): Create separate event for each match (default: False)
    """

    agent_type = 'html_parser_agent'

    def validate_config(self) -> None:
        """Validate HTML parser agent configuration."""
        super().validate_config()

        if 'selectors' not in self.config:
            raise ValueError("HTML parser agent requires 'selectors' in config")

        if not isinstance(self.config['selectors'], dict):
            raise ValueError("'selectors' must be a dictionary")

        if len(self.config['selectors']) == 0:
            raise ValueError("'selectors' must contain at least one selector")

        # Validate optional fields
        if 'extract_mode' in self.config:
            if self.config['extract_mode'] not in ['first', 'all']:
                raise ValueError("'extract_mode' must be 'first' or 'all'")

        if 'content_field' in self.config:
            if not isinstance(self.config['content_field'], str):
                raise ValueError("'content_field' must be a string")

        if 'create_event_per_item' in self.config:
            if not isinstance(self.config['create_event_per_item'], bool):
                raise ValueError("'create_event_per_item' must be a boolean")

    def process(self, events: List[Event]) -> List[Event]:
        """
        Parse HTML content and extract data.

        Args:
            events: Events containing HTML content

        Returns:
            List of events with extracted data
        """
        selectors = self.config['selectors']
        extract_mode = self.config.get('extract_mode', 'first')
        content_field = self.config.get('content_field', 'content')
        create_event_per_item = self.config.get('create_event_per_item', False)

        output_events = []

        for event in events:
            # Get HTML content from event
            html_content = event.get_payload_field(content_field)

            if not html_content:
                self.log(f'No HTML content found in field "{content_field}"',
                        level='warning', data={'event_id': event.id})
                continue

            # Parse HTML
            try:
                soup = BeautifulSoup(html_content, 'html.parser')
            except Exception as e:
                self.log(f'Error parsing HTML: {e}', level='error',
                        data={'event_id': event.id})
                continue

            # Extract data
            if extract_mode == 'first':
                extracted_data = self._extract_first(soup, selectors)
                if extracted_data:
                    new_event = self._create_parsed_event(event, extracted_data)
                    output_events.append(new_event)

            else:  # extract_mode == 'all'
                extracted_items = self._extract_all(soup, selectors)

                if create_event_per_item:
                    # Create separate event for each extracted item
                    for item in extracted_items:
                        new_event = self._create_parsed_event(event, item)
                        output_events.append(new_event)
                else:
                    # Create single event with all items
                    if extracted_items:
                        combined_data = {'items': extracted_items, 'count': len(extracted_items)}
                        new_event = self._create_parsed_event(event, combined_data)
                        output_events.append(new_event)

        self.log(f'Parsed {len(events)} HTML events', data={
            'input_count': len(events),
            'output_count': len(output_events),
            'extract_mode': extract_mode,
            'create_event_per_item': create_event_per_item
        })

        return output_events

    def _extract_first(self, soup: BeautifulSoup, selectors: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """
        Extract first match for each selector.

        Args:
            soup: BeautifulSoup object
            selectors: Dictionary of field_name: css_selector

        Returns:
            Dictionary of extracted data or None
        """
        result = {}

        for field_name, css_selector in selectors.items():
            try:
                element = soup.select_one(css_selector)
                if element:
                    # Get text content by default
                    result[field_name] = element.get_text(strip=True)
                else:
                    result[field_name] = None
            except Exception as e:
                self.log(f'Error selecting "{css_selector}": {e}',
                        level='warning', data={'field': field_name})
                result[field_name] = None

        # Only return if we found at least one value
        if any(v is not None for v in result.values()):
            return result
        return None

    def _extract_all(self, soup: BeautifulSoup, selectors: Dict[str, str]) -> List[Dict[str, Any]]:
        """
        Extract all matches for each selector.

        Assumes first selector is the "item" selector, and other selectors
        are applied within each item.

        Args:
            soup: BeautifulSoup object
            selectors: Dictionary of field_name: css_selector

        Returns:
            List of dictionaries with extracted data
        """
        results = []

        # Get first selector as the item selector
        selector_items = list(selectors.items())
        if not selector_items:
            return results

        item_field, item_selector = selector_items[0]
        remaining_selectors = dict(selector_items[1:])

        # Find all items
        try:
            items = soup.select(item_selector)
        except Exception as e:
            self.log(f'Error selecting items with "{item_selector}": {e}', level='error')
            return results

        # Extract data from each item
        for item_element in items:
            item_data = {}

            # Extract from first selector (the item itself)
            item_data[item_field] = item_element.get_text(strip=True)

            # Extract from remaining selectors (within the item)
            for field_name, css_selector in remaining_selectors.items():
                try:
                    element = item_element.select_one(css_selector)
                    if element:
                        item_data[field_name] = element.get_text(strip=True)
                    else:
                        item_data[field_name] = None
                except Exception as e:
                    self.log(f'Error selecting "{css_selector}" within item: {e}',
                            level='warning', data={'field': field_name})
                    item_data[field_name] = None

            results.append(item_data)

        return results

    def _create_parsed_event(self, source_event: Event, extracted_data: Dict[str, Any]) -> Event:
        """
        Create new event with extracted data.

        Args:
            source_event: Original event
            extracted_data: Extracted data dictionary

        Returns:
            New event with parsed data
        """
        # Create payload with extracted data
        payload = extracted_data.copy()

        # Optionally preserve original payload fields
        if self.config.get('preserve_original', False):
            # Merge with original payload (extracted data takes precedence)
            original_payload = source_event.payload.copy()
            original_payload.update(payload)
            payload = original_payload

        # Create metadata
        metadata = {
            'source_event_id': source_event.id,
            'parser': 'html',
            'selectors': list(self.config['selectors'].keys())
        }

        # Preserve source metadata if present
        if source_event.event_metadata:
            metadata['source_metadata'] = source_event.event_metadata

        return self.create_event(payload=payload, metadata=metadata)

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """Get configuration schema for HTML parser agent."""
        schema = super().get_config_schema()
        schema['required_fields'] = ['selectors']
        schema['optional_fields'] = [
            {
                'name': 'extract_mode',
                'type': 'string',
                'default': 'first',
                'options': ['first', 'all'],
                'description': 'Extract first match or all matches for each selector'
            },
            {
                'name': 'content_field',
                'type': 'string',
                'default': 'content',
                'description': 'Field in incoming events containing HTML content'
            },
            {
                'name': 'create_event_per_item',
                'type': 'boolean',
                'default': False,
                'description': 'In "all" mode, create separate event for each extracted item'
            },
            {
                'name': 'preserve_original',
                'type': 'boolean',
                'default': False,
                'description': 'Preserve fields from original event payload'
            }
        ]
        return schema
