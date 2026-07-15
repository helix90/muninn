"""
CSV Parser Agent - Parse CSV content from event payloads

This transform agent parses CSV data from event payloads and extracts structured
data into rows. Supports both bulk processing (single event with all rows) and
per-row processing (one event per row) modes. Includes automatic type conversion,
column selection, row filtering, and flexible CSV parsing options.
"""

import csv
import logging
from io import StringIO
from typing import Any, Dict, List, Optional
from datetime import datetime

from app.agents.base import TransformAgent
from app.agents.registry import register_agent
from app.models import Event

logger = logging.getLogger(__name__)


@register_agent
class CSVParserAgent(TransformAgent):
    """
    Transform agent that parses CSV content from event payloads.

    Supports two output modes:
    1. Combined mode: Create single event with all rows (default)
    2. Per-row mode: Create separate event for each row

    Configuration:
        csv_field (str): Field containing CSV data (default: "content")
        has_header (bool): CSV has header row (default: True)
        delimiter (str): Delimiter character (default: ",")
        quotechar (str): Quote character (default: '"')
        skip_rows (int): Number of rows to skip at start (default: 0)
        create_event_per_row (bool): Output mode (default: False)
        preserve_original (bool): Keep original payload fields (default: False)
        columns (list): Column names to extract (default: None, extract all)
        rename_columns (dict): Rename columns {"old": "new"} (default: {})
        convert_types (bool): Auto-convert numbers/booleans (default: True)
        filter_empty_rows (bool): Skip empty rows (default: True)
        max_rows (int): Limit rows processed (default: None, unlimited)
        on_parse_error (str): Error handling: 'skip', 'null', 'error' (default: 'skip')

    Example workflows:
        WebFetchAgent → CSVParserAgent → FilterAgent → EmailAgent
        IMAPAgent → CSVParserAgent → AggregationAgent → HTTPPostAgent
        S3BucketMonitorAgent → WebFetchAgent → CSVParserAgent → DiscordWebhookAgent
    """

    agent_type = 'csv_parser_agent'
    agent_category = 'transform'

    def __init__(self, agent_id: int, config: Dict[str, Any], user_id: int, db_session=None):
        """Initialize the CSV Parser agent."""
        # Call parent __init__ which will call validate_config()
        super().__init__(agent_id, config, user_id, db_session)

    def validate_config(self) -> None:
        """
        Validate agent configuration.

        Raises:
            ValueError: If configuration is invalid
        """
        # Call parent validation
        super().validate_config()

        # Validate csv_field
        csv_field = self.config.get('csv_field', 'content')
        if not isinstance(csv_field, str) or not csv_field:
            raise ValueError("'csv_field' must be a non-empty string")

        # Validate has_header
        has_header = self.config.get('has_header', True)
        if not isinstance(has_header, bool):
            raise ValueError("'has_header' must be a boolean")

        # Validate delimiter
        delimiter = self.config.get('delimiter', ',')
        if not isinstance(delimiter, str) or len(delimiter) != 1:
            raise ValueError("'delimiter' must be a single character")

        # Validate quotechar
        quotechar = self.config.get('quotechar', '"')
        if not isinstance(quotechar, str) or len(quotechar) != 1:
            raise ValueError("'quotechar' must be a single character")

        # Validate create_event_per_row
        per_row = self.config.get('create_event_per_row', False)
        if not isinstance(per_row, bool):
            raise ValueError("'create_event_per_row' must be a boolean")

        # Validate columns
        columns = self.config.get('columns')
        if columns is not None:
            if not isinstance(columns, list):
                raise ValueError("'columns' must be a list of column names")
            if not all(isinstance(c, str) for c in columns):
                raise ValueError("'columns' must contain only strings")

        # Validate rename_columns
        rename = self.config.get('rename_columns', {})
        if not isinstance(rename, dict):
            raise ValueError("'rename_columns' must be a dictionary")
        # Validate all keys and values are strings
        if not all(isinstance(k, str) and isinstance(v, str) for k, v in rename.items()):
            raise ValueError("'rename_columns' keys and values must be strings")

        # Validate max_rows
        max_rows = self.config.get('max_rows')
        if max_rows is not None:
            if not isinstance(max_rows, int) or max_rows <= 0:
                raise ValueError("'max_rows' must be a positive integer")

        # Validate skip_rows
        skip_rows = self.config.get('skip_rows', 0)
        if not isinstance(skip_rows, int) or skip_rows < 0:
            raise ValueError("'skip_rows' must be a non-negative integer")

        # Validate on_parse_error
        on_error = self.config.get('on_parse_error', 'skip')
        if on_error not in ['skip', 'null', 'error']:
            raise ValueError("'on_parse_error' must be 'skip', 'null', or 'error'")

        # Validate booleans
        for field in ['convert_types', 'filter_empty_rows', 'preserve_original']:
            value = self.config.get(field, True)
            if not isinstance(value, bool):
                raise ValueError(f"'{field}' must be a boolean")

    def process(self, events: List[Event]) -> List[Event]:
        """
        Parse CSV content from events and create structured output.

        Args:
            events: List of events to process

        Returns:
            List of new events with parsed CSV data
        """
        csv_field = self.config.get('csv_field', 'content')
        create_event_per_row = self.config.get('create_event_per_row', False)

        output_events = []

        for event in events:
            try:
                # Extract CSV content from payload
                csv_content = self._get_csv_content(event, csv_field)

                if not csv_content:
                    # Handle missing/empty CSV content based on on_parse_error setting
                    on_error = self.config.get('on_parse_error', 'skip')
                    self.log(f'No CSV content in field "{csv_field}"',
                            level='warning', data={'event_id': event.id})

                    if on_error == 'skip':
                        continue
                    elif on_error == 'null':
                        # Create event with null data
                        null_event = self._create_null_event(event)
                        output_events.append(null_event)
                        continue
                    else:  # 'error' - already raised in _get_csv_content
                        continue

                # Parse CSV content
                rows = self._parse_csv(csv_content)

                # Create output events based on mode
                if create_event_per_row:
                    # Create separate event for each row
                    for row_index, row in enumerate(rows):
                        new_event = self._create_row_event(event, row, row_index)
                        output_events.append(new_event)
                else:
                    # Create single event with all rows
                    combined_event = self._create_combined_event(event, rows)
                    output_events.append(combined_event)

            except Exception as e:
                self.log(f'Error parsing CSV: {e}', level='error',
                        data={'event_id': event.id})

                on_error = self.config.get('on_parse_error', 'skip')
                if on_error == 'error':
                    raise
                elif on_error == 'null':
                    # Create event with null/empty data
                    null_event = self._create_null_event(event)
                    output_events.append(null_event)
                # else: skip (do nothing)
                continue

        if output_events:
            self.log(f'Parsed {len(events)} CSV events → {len(output_events)} output events',
                    data={'input_count': len(events), 'output_count': len(output_events)})

        return output_events

    def _get_csv_content(self, event: Event, csv_field: str) -> Optional[str]:
        """
        Extract CSV content from event payload.

        Args:
            event: Event to extract from
            csv_field: Field name containing CSV data

        Returns:
            CSV content as string, or None if not found

        Raises:
            ValueError: If csv_field not found and required
        """
        # Try to get field from payload
        if csv_field in event.payload:
            content = event.payload[csv_field]
            # Ensure it's a string
            if isinstance(content, str):
                return content if content.strip() else None
            # Convert to string if it's bytes
            elif isinstance(content, bytes):
                return content.decode('utf-8')

        # Field not found - raise error if on_parse_error='error'
        on_error = self.config.get('on_parse_error', 'skip')
        if on_error == 'error':
            raise ValueError(f'CSV field "{csv_field}" not found in event payload')

        return None

    def _parse_csv(self, csv_content: str) -> List[Dict[str, Any]]:
        """
        Parse CSV string into list of row dictionaries.

        Args:
            csv_content: CSV data as string

        Returns:
            List of row dictionaries
        """
        # Get configuration
        has_header = self.config.get('has_header', True)
        delimiter = self.config.get('delimiter', ',')
        quotechar = self.config.get('quotechar', '"')
        skip_rows = self.config.get('skip_rows', 0)
        max_rows = self.config.get('max_rows')
        filter_empty = self.config.get('filter_empty_rows', True)
        columns = self.config.get('columns')
        rename = self.config.get('rename_columns', {})
        convert_types = self.config.get('convert_types', True)

        # Split into lines
        lines = csv_content.splitlines()

        # Skip initial rows if configured
        if skip_rows > 0:
            lines = lines[skip_rows:]

        if not lines:
            return []

        # Create CSV reader
        if has_header:
            reader = csv.DictReader(
                lines,
                delimiter=delimiter,
                quotechar=quotechar
            )
        else:
            # No header - generate field names (field0, field1, etc.)
            # First, we need to count columns from first row
            first_line_reader = csv.reader([lines[0]], delimiter=delimiter, quotechar=quotechar)
            first_row = next(first_line_reader)
            num_columns = len(first_row)
            fieldnames = [f'field{i}' for i in range(num_columns)]

            reader = csv.DictReader(
                lines,
                fieldnames=fieldnames,
                delimiter=delimiter,
                quotechar=quotechar
            )

        # Parse rows
        rows = []
        for row_num, row in enumerate(reader):
            # Apply max_rows limit
            if max_rows and row_num >= max_rows:
                break

            # Filter empty rows
            if filter_empty and self._is_empty_row(row):
                continue

            # Process row (column selection, renaming, type conversion)
            processed_row = self._process_row(row, columns, rename, convert_types)
            rows.append(processed_row)

        return rows

    def _process_row(self, row: Dict[str, str],
                     columns: Optional[List[str]],
                     rename: Dict[str, str],
                     convert_types: bool) -> Dict[str, Any]:
        """
        Process a single CSV row: select columns, rename, convert types.

        Args:
            row: Raw row dictionary from CSV reader
            columns: List of columns to extract (None = all)
            rename: Column rename mapping
            convert_types: Whether to auto-convert types

        Returns:
            Processed row dictionary
        """
        processed = {}

        for key, value in row.items():
            # Skip None keys (can happen with malformed CSV)
            if key is None:
                continue

            # Column selection
            if columns and key not in columns:
                continue

            # Column renaming
            output_key = rename.get(key, key)

            # Type conversion
            if convert_types:
                value = self._convert_value(value)

            processed[output_key] = value

        return processed

    def _convert_value(self, value: str) -> Any:
        """
        Auto-convert string values to appropriate types.

        Args:
            value: String value to convert

        Returns:
            Converted value (int, float, bool, None, or str)
        """
        if not isinstance(value, str):
            return value

        # Strip whitespace
        value = value.strip()

        # Empty string → None
        if value == '':
            return None

        # Boolean values
        if value.lower() in ('true', 'yes', '1'):
            return True
        if value.lower() in ('false', 'no', '0'):
            return False

        # Try integer conversion
        try:
            # Only convert to int if no decimal point or scientific notation
            if '.' not in value and 'e' not in value.lower():
                return int(value)
        except ValueError:
            pass

        # Try float conversion
        try:
            return float(value)
        except ValueError:
            pass

        # Keep as string
        return value

    def _is_empty_row(self, row: Dict[str, str]) -> bool:
        """
        Check if row is empty (all values are empty/whitespace).

        Args:
            row: Row dictionary to check

        Returns:
            True if row is empty, False otherwise
        """
        # Check all values including extra fields (None key from csv.DictReader)
        for key, value in row.items():
            # Handle extra fields stored under None key (restkey)
            if key is None:
                # If there are extra fields, check if all are empty
                if isinstance(value, list):
                    if not all(not str(v).strip() for v in value):
                        return False
                elif value and str(value).strip():
                    return False
            else:
                # Regular field - check if not empty
                if value and str(value).strip():
                    return False
        return True

    def _create_row_event(self, source_event: Event,
                          row: Dict[str, Any], row_index: int) -> Event:
        """
        Create event for a single CSV row (per-row mode).

        Args:
            source_event: Original event
            row: Parsed row data
            row_index: Index of this row

        Returns:
            New event for this row
        """
        payload = row.copy()

        if self.config.get('preserve_original', False):
            # Merge with original payload
            original = source_event.payload.copy()
            original.update(payload)
            payload = original

        metadata = {
            'source_event_id': source_event.id,
            'parser': 'csv',
            'row_index': row_index,
            'total_columns': len(row)
        }

        return self.create_event(payload=payload, metadata=metadata)

    def _create_combined_event(self, source_event: Event,
                               rows: List[Dict[str, Any]]) -> Event:
        """
        Create single event containing all CSV rows (combined mode).

        Args:
            source_event: Original event
            rows: List of parsed rows

        Returns:
            New event with all rows
        """
        payload = {
            'rows': rows,
            'row_count': len(rows),
            'column_names': list(rows[0].keys()) if rows else []
        }

        if self.config.get('preserve_original', False):
            original = source_event.payload.copy()
            original.update(payload)
            payload = original

        metadata = {
            'source_event_id': source_event.id,
            'parser': 'csv',
            'row_count': len(rows),
            'mode': 'combined'
        }

        return self.create_event(payload=payload, metadata=metadata)

    def _create_null_event(self, source_event: Event) -> Event:
        """
        Create event with null data (parse error with on_parse_error='null').

        Args:
            source_event: Original event

        Returns:
            New event with null/empty data
        """
        payload = {
            'rows': None,
            'row_count': 0,
            'parse_error': True
        }

        metadata = {
            'source_event_id': source_event.id,
            'parser': 'csv',
            'error': True
        }

        return self.create_event(payload=payload, metadata=metadata)

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """
        Get the configuration schema for this agent.

        Returns:
            Configuration schema dictionary
        """
        schema = super().get_config_schema()
        schema['required_fields'] = []  # All fields are optional with defaults
        schema['optional_fields'].extend([
            {
                'name': 'csv_field',
                'type': 'text',
                'default': 'content',
                'description': 'Field name containing CSV data in event payload. Default: "content". Common values: "content", "body", "csv_data".'
            },
            {
                'name': 'has_header',
                'type': 'boolean',
                'default': True,
                'description': 'CSV has header row with column names. If False, auto-generated field names (field0, field1, etc.) will be used.'
            },
            {
                'name': 'delimiter',
                'type': 'text',
                'default': ',',
                'description': 'Delimiter character separating fields. Default: "," (comma). Common: "\\t" (tab), ";" (semicolon), "|" (pipe).'
            },
            {
                'name': 'quotechar',
                'type': 'text',
                'default': '"',
                'description': 'Quote character for escaping delimiters in values. Default: \'"\' (double quote).'
            },
            {
                'name': 'skip_rows',
                'type': 'number',
                'default': 0,
                'description': 'Number of rows to skip at the start of the CSV (before header). Useful for files with metadata rows. Default: 0.'
            },
            {
                'name': 'create_event_per_row',
                'type': 'boolean',
                'default': False,
                'description': 'Output mode: False = single event with all rows (efficient for bulk), True = separate event per row (parallel processing).'
            },
            {
                'name': 'preserve_original',
                'type': 'boolean',
                'default': False,
                'description': 'Include original payload fields in output events. If True, parsed data is merged with original payload.'
            },
            {
                'name': 'columns',
                'type': 'array',
                'default': None,
                'description': 'List of column names to extract (others are ignored). Null/empty = extract all columns. Example: ["name", "email", "age"]. Requires has_header=True.'
            },
            {
                'name': 'rename_columns',
                'type': 'object',
                'default': {},
                'description': 'Rename columns in output. Format: {"old_name": "new_name"}. Example: {"email": "email_address", "qty": "quantity"}.'
            },
            {
                'name': 'convert_types',
                'type': 'boolean',
                'default': True,
                'description': 'Auto-convert string values to int, float, bool, or None. If False, all values remain strings. True recommended for data processing.'
            },
            {
                'name': 'filter_empty_rows',
                'type': 'boolean',
                'default': True,
                'description': 'Skip rows where all fields are empty/whitespace. Helps clean up CSV files with trailing empty rows.'
            },
            {
                'name': 'max_rows',
                'type': 'number',
                'default': None,
                'description': 'Maximum number of rows to process (null = unlimited). Useful for testing or limiting large CSV files.'
            },
            {
                'name': 'on_parse_error',
                'type': 'select',
                'options': ['skip', 'null', 'error'],
                'default': 'skip',
                'description': 'Error handling: "skip" = skip failed event, "null" = create event with null data, "error" = raise exception and stop.'
            }
        ])
        return schema

    def __repr__(self):
        """String representation of the agent."""
        mode = 'per-row' if self.config.get('create_event_per_row', False) else 'combined'
        csv_field = self.config.get('csv_field', 'content')
        return f'<CSVParserAgent {self.agent_id}: mode={mode}, field={csv_field}>'
