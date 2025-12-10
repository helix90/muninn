"""
Filter job for content filtering and transformation
"""

import re
from typing import Dict, Any, Optional, List, Union
from ..base import BaseJob


class FilterJob(BaseJob):
    """Job for filtering and transforming content."""
    
    job_type = 'filter'
    required_config_fields = ['input_data', 'filters']
    optional_config_fields = ['output_format', 'case_sensitive', 'regex_enabled']
    
    def _validate_config_values(self):
        """Validate configuration field values."""
        # Validate input_data
        input_data = self.config.get('input_data')
        if not isinstance(input_data, (dict, list, str)):
            raise ValueError("input_data must be a dictionary, list, or string")
        
        # Validate filters
        filters = self.config.get('filters')
        if not isinstance(filters, list) or not filters:
            raise ValueError("filters must be a non-empty list")
        
        for filter_config in filters:
            if not isinstance(filter_config, dict):
                raise ValueError("Each filter must be a dictionary")
            
            required_filter_fields = ['type', 'field', 'value']
            for field in required_filter_fields:
                if field not in filter_config:
                    raise ValueError(f"Filter missing required field: {field}")
            
            # Validate filter type
            filter_type = filter_config['type']
            valid_types = ['equals', 'contains', 'regex', 'greater_than', 'less_than', 'in_list', 'not_in_list']
            if filter_type not in valid_types:
                raise ValueError(f"Invalid filter type: {filter_type}. Must be one of: {valid_types}")
        
        # Validate case_sensitive
        case_sensitive = self.config.get('case_sensitive', True)
        if not isinstance(case_sensitive, bool):
            raise ValueError("case_sensitive must be a boolean")
        
        # Validate regex_enabled
        regex_enabled = self.config.get('regex_enabled', False)
        if not isinstance(regex_enabled, bool):
            raise ValueError("regex_enabled must be a boolean")
    
    def _apply_filter(self, data: Any, filter_config: Dict[str, Any]) -> bool:
        """Apply a single filter to data."""
        filter_type = filter_config['type']
        field = filter_config['field']
        value = filter_config['value']
        case_sensitive = self.config.get('case_sensitive', True)
        
        # Extract field value from data
        if isinstance(data, dict):
            field_value = data.get(field)
        elif isinstance(data, (list, tuple)) and isinstance(field, int):
            try:
                field_value = data[field]
            except IndexError:
                return False
        else:
            field_value = data
        
        # Apply filter based on type
        if filter_type == 'equals':
            if not case_sensitive and isinstance(field_value, str) and isinstance(value, str):
                return field_value.lower() == value.lower()
            return field_value == value
        
        elif filter_type == 'contains':
            if isinstance(field_value, str) and isinstance(value, str):
                if not case_sensitive:
                    return value.lower() in field_value.lower()
                return value in field_value
            return False
        
        elif filter_type == 'regex':
            if not self.config.get('regex_enabled', False):
                raise ValueError("Regex filtering is not enabled")
            if isinstance(field_value, str):
                try:
                    pattern = re.compile(value, flags=0 if case_sensitive else re.IGNORECASE)
                    return bool(pattern.search(field_value))
                except re.error:
                    raise ValueError(f"Invalid regex pattern: {value}")
            return False
        
        elif filter_type == 'greater_than':
            try:
                return field_value > value
            except (TypeError, ValueError):
                return False
        
        elif filter_type == 'less_than':
            try:
                return field_value < value
            except (TypeError, ValueError):
                return False
        
        elif filter_type == 'in_list':
            if isinstance(value, list):
                return field_value in value
            return False
        
        elif filter_type == 'not_in_list':
            if isinstance(value, list):
                return field_value not in value
            return False
        
        return False
    
    def _filter_data(self, data: Any) -> Any:
        """Apply all filters to the data."""
        if isinstance(data, list):
            # Filter list items
            filtered_items = []
            for item in data:
                if self._passes_all_filters(item):
                    filtered_items.append(item)
            return filtered_items
        elif isinstance(data, dict):
            # Filter dictionary
            if self._passes_all_filters(data):
                return data
            return None
        else:
            # Filter single value
            if self._passes_all_filters(data):
                return data
            return None
    
    def _passes_all_filters(self, data: Any) -> bool:
        """Check if data passes all filters."""
        for filter_config in self.config['filters']:
            if not self._apply_filter(data, filter_config):
                return False
        return True
    
    def _transform_output(self, data: Any) -> Any:
        """Transform output based on output_format configuration."""
        output_format = self.config.get('output_format', 'original')
        
        if output_format == 'original':
            return data
        
        elif output_format == 'count':
            if isinstance(data, list):
                return len(data)
            elif isinstance(data, dict):
                return len(data.keys())
            else:
                return 1 if data is not None else 0
        
        elif output_format == 'summary':
            if isinstance(data, list):
                return {
                    'count': len(data),
                    'items': data[:10] if len(data) > 10 else data,
                    'truncated': len(data) > 10
                }
            elif isinstance(data, dict):
                return {
                    'count': len(data.keys()),
                    'keys': list(data.keys()),
                    'values': list(data.values())
                }
            else:
                return {'value': data, 'type': type(data).__name__}
        
        return data
    
    def execute(self, input_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute the filter job.
        
        Args:
            input_data: Optional input data (overrides config input_data if provided)
            
        Returns:
            Dictionary containing filtered and transformed data
        """
        try:
            self.pre_execute(input_data)
            
            # Use input_data parameter if provided, otherwise use config
            data_to_filter = input_data if input_data is not None else self.config['input_data']
            
            # Apply filters
            filtered_data = self._filter_data(data_to_filter)
            
            # Transform output
            transformed_output = self._transform_output(filtered_data)
            
            # Prepare result
            result = {
                'original_data': data_to_filter,
                'filtered_data': filtered_data,
                'transformed_output': transformed_output,
                'filters_applied': self.config['filters'],
                'input_count': self._get_data_count(data_to_filter),
                'output_count': self._get_data_count(filtered_data),
                'filtering_success': True
            }
            
            self.post_execute(result, success=True)
            return result
            
        except Exception as e:
            error_result = self.handle_error(e)
            self.post_execute(error_result, success=False)
            return error_result
    
    def _get_data_count(self, data: Any) -> int:
        """Get the count of data items."""
        if isinstance(data, list):
            return len(data)
        elif isinstance(data, dict):
            return len(data.keys())
        else:
            return 1 if data is not None else 0
    
    def get_config_schema(self) -> Dict[str, Any]:
        """Get the configuration schema for filter jobs."""
        schema = super().get_config_schema()
        schema.update({
            'description': 'Filters and transforms content based on configurable rules',
            'example_config': {
                'input_data': {'name': 'John', 'age': 30, 'city': 'New York'},
                'filters': [
                    {'type': 'greater_than', 'field': 'age', 'value': 25},
                    {'type': 'contains', 'field': 'city', 'value': 'New'}
                ],
                'output_format': 'summary',
                'case_sensitive': False
            }
        })
        return schema
