"""
Template Agent - Transform data via Jinja2 templates

Single responsibility: ONLY transforms event data using Jinja2 templates.
Does NOT fetch or filter data.
"""

from typing import List, Dict, Any
from jinja2 import Template, TemplateSyntaxError, UndefinedError
from app.agents.base import TransformAgent
from app.agents.registry import register_agent
from app.models import Event


@register_agent
class TemplateAgent(TransformAgent):
    """
    Transforms event data using Jinja2 templates.

    Useful for:
    - Formatting data for emails or messages
    - Extracting/combining fields
    - Generating dynamic content

    Configuration:
        template (str): Single Jinja2 template for all events (alternative to templates dict)
        templates (dict): Multiple Jinja2 templates
            Format: {'field_name': 'template_string'}
        output_field (str): Field to store template output (default: 'formatted')
        preserve_original (bool): Keep original payload fields (default: True)
    """

    agent_type = 'template_agent'

    def validate_config(self) -> None:
        """Validate template agent configuration."""
        super().validate_config()

        # Must have either 'template' or 'templates'
        has_template = 'template' in self.config
        has_templates = 'templates' in self.config

        if not has_template and not has_templates:
            raise ValueError("Template agent requires 'template' or 'templates' in config")

        if has_template and has_templates:
            raise ValueError("Template agent cannot have both 'template' and 'templates'")

        # Validate template string
        if has_template:
            if not isinstance(self.config['template'], str):
                raise ValueError("'template' must be a string")

            # Test template syntax
            try:
                Template(self.config['template'])
            except TemplateSyntaxError as e:
                raise ValueError(f"Invalid Jinja2 template syntax: {e}")

        # Validate templates dict
        if has_templates:
            if not isinstance(self.config['templates'], dict):
                raise ValueError("'templates' must be a dictionary")

            if len(self.config['templates']) == 0:
                raise ValueError("'templates' must contain at least one template")

            # Test each template syntax
            for field_name, template_str in self.config['templates'].items():
                if not isinstance(template_str, str):
                    raise ValueError(f"Template for '{field_name}' must be a string")

                try:
                    Template(template_str)
                except TemplateSyntaxError as e:
                    raise ValueError(f"Invalid Jinja2 syntax in template '{field_name}': {e}")

        # Validate optional fields
        if 'output_field' in self.config:
            if not isinstance(self.config['output_field'], str):
                raise ValueError("'output_field' must be a string")

        if 'preserve_original' in self.config:
            if not isinstance(self.config['preserve_original'], bool):
                raise ValueError("'preserve_original' must be a boolean")

    def process(self, events: List[Event]) -> List[Event]:
        """
        Transform events using templates.

        Args:
            events: Events to transform

        Returns:
            List of transformed events
        """
        preserve_original = self.config.get('preserve_original', True)
        has_single_template = 'template' in self.config

        output_events = []

        for event in events:
            try:
                if has_single_template:
                    # Single template mode
                    output_field = self.config.get('output_field', 'formatted')
                    transformed_data = self._apply_template(
                        self.config['template'],
                        event.payload
                    )

                    # Create new payload
                    if preserve_original:
                        payload = event.payload.copy()
                        payload[output_field] = transformed_data
                    else:
                        payload = {output_field: transformed_data}

                else:
                    # Multiple templates mode
                    templates = self.config['templates']
                    transformed_data = {}

                    for field_name, template_str in templates.items():
                        transformed_data[field_name] = self._apply_template(
                            template_str,
                            event.payload
                        )

                    # Create new payload
                    if preserve_original:
                        payload = event.payload.copy()
                        payload.update(transformed_data)
                    else:
                        payload = transformed_data

                # Create new event with transformed data
                metadata = {
                    'source_event_id': event.id,
                    'transformer': 'template'
                }

                if event.event_metadata:
                    metadata['source_metadata'] = event.event_metadata

                new_event = self.create_event(payload=payload, metadata=metadata)
                output_events.append(new_event)

            except Exception as e:
                self.log(f'Error transforming event: {e}', level='error',
                        data={'event_id': event.id, 'error': str(e)})
                # Skip this event on error
                continue

        self.log(f'Transformed {len(output_events)} events', data={
            'input_count': len(events),
            'output_count': len(output_events),
            'preserve_original': preserve_original
        })

        return output_events

    def _apply_template(self, template_str: str, data: Dict[str, Any]) -> str:
        """
        Apply Jinja2 template to data.

        Args:
            template_str: Jinja2 template string
            data: Data dictionary for template context

        Returns:
            Rendered template string
        """
        try:
            template = Template(template_str)
            return template.render(**data)
        except UndefinedError as e:
            # Handle undefined variables gracefully
            self.log(f'Undefined variable in template: {e}', level='warning')
            return f'[Template Error: {e}]'
        except Exception as e:
            self.log(f'Template rendering error: {e}', level='error')
            return f'[Render Error: {e}]'

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """Get configuration schema for template agent."""
        schema = super().get_config_schema()
        schema['required_fields'] = []  # Either template or templates required (validated above)
        schema['optional_fields'] = [
            {
                'name': 'template',
                'type': 'string',
                'description': 'Single Jinja2 template string (alternative to templates dict)'
            },
            {
                'name': 'templates',
                'type': 'object',
                'description': 'Dictionary of field_name: template_string for multiple templates'
            },
            {
                'name': 'output_field',
                'type': 'string',
                'default': 'formatted',
                'description': 'Field name for template output (only used with single template)'
            },
            {
                'name': 'preserve_original',
                'type': 'boolean',
                'default': True,
                'description': 'Keep original payload fields in output'
            }
        ]
        schema['jinja2_features'] = {
            'variables': 'Access event payload fields: {{ title }}, {{ user.name }}',
            'filters': 'Built-in filters: {{ text|upper }}, {{ date|default("N/A") }}',
            'control': 'Control structures: {% if %}, {% for %}, etc.'
        }
        return schema
