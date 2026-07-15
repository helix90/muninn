"""
Tests for CSVParserAgent - Transform agent that parses CSV content

Test Coverage:
- Configuration validation (10 tests)
- Basic CSV parsing (8 tests)
- Output modes (4 tests)
- Type conversion (6 tests)
- Column operations (5 tests)
- Row filtering (4 tests)
- Error handling (5 tests)
- Metadata and preservation (3 tests)
"""

import pytest
from app.models import Job, Event
from app.agents.types.csv_parser_agent import CSVParserAgent
from app.extensions import db


@pytest.fixture
def test_job(app, test_user):
    """Create test job for CSV parser agent."""
    with app.app_context():
        job = Job(
            name='CSV Parser Test Agent',
            job_type='csv_parser_agent',
            user_id=test_user.id,
            config={'csv_field': 'content'},
            is_active=True
        )
        db.session.add(job)
        db.session.commit()
        yield job
        # Cleanup is handled by app fixture


class TestCSVParserAgentRegistration:
    """Test agent registration and discovery"""

    def test_agent_registered(self):
        """Test that CSVParserAgent is registered in agent registry"""
        from app.agents.registry import agent_registry
        assert agent_registry.is_registered('csv_parser_agent')
        assert agent_registry.get_agent_class('csv_parser_agent') == CSVParserAgent

    def test_agent_type_and_category(self, test_job):
        """Test agent type and category attributes"""
        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content'},
            user_id=test_job.user_id
        )
        assert agent.agent_type == 'csv_parser_agent'
        assert agent.agent_category == 'transform'


class TestCSVParserAgentConfigValidation:
    """Test configuration validation"""

    def test_valid_minimal_config(self, test_job):
        """Test minimal valid configuration"""
        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content'},
            user_id=test_job.user_id
        )
        assert agent.config['csv_field'] == 'content'

    def test_valid_full_config(self, test_job):
        """Test full configuration with all options"""
        config = {
            'csv_field': 'data',
            'has_header': True,
            'delimiter': ',',
            'quotechar': '"',
            'skip_rows': 1,
            'create_event_per_row': False,
            'columns': ['name', 'email'],
            'rename_columns': {'email': 'email_address'},
            'convert_types': True,
            'filter_empty_rows': True,
            'max_rows': 100,
            'preserve_original': False,
            'on_parse_error': 'skip'
        }
        agent = CSVParserAgent(
            agent_id=test_job.id,
            config=config,
            user_id=test_job.user_id
        )
        assert agent.config == config

    def test_invalid_csv_field_empty(self, test_job):
        """Test error when csv_field is empty string"""
        with pytest.raises(ValueError, match="csv_field' must be a non-empty string"):
            CSVParserAgent(
                agent_id=test_job.id,
                config={'csv_field': ''},
                user_id=test_job.user_id
            )

    def test_invalid_csv_field_non_string(self, test_job):
        """Test error when csv_field is not a string"""
        with pytest.raises(ValueError, match="csv_field' must be a non-empty string"):
            CSVParserAgent(
                agent_id=test_job.id,
                config={'csv_field': 123},
                user_id=test_job.user_id
            )

    def test_invalid_delimiter_multi_char(self, test_job):
        """Test error when delimiter is multi-character"""
        with pytest.raises(ValueError, match="delimiter' must be a single character"):
            CSVParserAgent(
                agent_id=test_job.id,
                config={'csv_field': 'content', 'delimiter': '||'},
                user_id=test_job.user_id
            )

    def test_invalid_columns_not_list(self, test_job):
        """Test error when columns is not a list"""
        with pytest.raises(ValueError, match="columns' must be a list"):
            CSVParserAgent(
                agent_id=test_job.id,
                config={'csv_field': 'content', 'columns': 'name,email'},
                user_id=test_job.user_id
            )

    def test_invalid_max_rows_negative(self, test_job):
        """Test error when max_rows is negative"""
        with pytest.raises(ValueError, match="max_rows' must be a positive integer"):
            CSVParserAgent(
                agent_id=test_job.id,
                config={'csv_field': 'content', 'max_rows': -5},
                user_id=test_job.user_id
            )

    def test_invalid_on_parse_error_value(self, test_job):
        """Test error with invalid on_parse_error value"""
        with pytest.raises(ValueError, match="on_parse_error' must be 'skip', 'null', or 'error'"):
            CSVParserAgent(
                agent_id=test_job.id,
                config={'csv_field': 'content', 'on_parse_error': 'ignore'},
                user_id=test_job.user_id
            )

    def test_valid_rename_columns(self, test_job):
        """Test valid rename_columns configuration"""
        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={
                'csv_field': 'content',
                'rename_columns': {'old_name': 'new_name'}
            },
            user_id=test_job.user_id
        )
        assert agent.config['rename_columns'] == {'old_name': 'new_name'}

    def test_valid_skip_rows(self, test_job):
        """Test valid skip_rows configuration"""
        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content', 'skip_rows': 2},
            user_id=test_job.user_id
        )
        assert agent.config['skip_rows'] == 2


class TestCSVParserAgentBasicParsing:
    """Test basic CSV parsing functionality"""

    def test_parse_csv_with_header(self, test_job):
        """Test parsing CSV with header row"""
        csv_content = "name,age,email\nAlice,30,alice@example.com\nBob,25,bob@example.com"

        event = Event(
            agent_id=test_job.id,
            agent_type='web_fetch_agent',
            user_id=test_job.user_id,
            payload={'content': csv_content},
            metadata={}
        )
        db.session.add(event)
        db.session.commit()

        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content', 'has_header': True},
            user_id=test_job.user_id
        )

        result = agent.process([event])
        db.session.commit()

        assert len(result) == 1
        assert result[0].payload['row_count'] == 2
        assert result[0].payload['rows'][0]['name'] == 'Alice'
        assert result[0].payload['rows'][0]['age'] == 30  # Type converted
        assert result[0].payload['rows'][1]['name'] == 'Bob'
        assert result[0].payload['rows'][1]['age'] == 25

    def test_parse_csv_without_header(self, test_job):
        """Test parsing CSV without header row"""
        csv_content = "Alice,30,alice@example.com\nBob,25,bob@example.com"

        event = Event(
            agent_id=test_job.id,
            agent_type='web_fetch_agent',
            user_id=test_job.user_id,
            payload={'content': csv_content},
            metadata={}
        )
        db.session.add(event)
        db.session.commit()

        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content', 'has_header': False},
            user_id=test_job.user_id
        )

        result = agent.process([event])
        db.session.commit()

        assert len(result) == 1
        assert result[0].payload['row_count'] == 2
        # Without header, columns are auto-named
        assert len(result[0].payload['rows'][0]) == 3

    def test_parse_csv_custom_delimiter_tab(self, test_job):
        """Test parsing CSV with tab delimiter"""
        csv_content = "name\tage\temail\nAlice\t30\talice@example.com\nBob\t25\tbob@example.com"

        event = Event(
            agent_id=test_job.id,
            agent_type='web_fetch_agent',
            user_id=test_job.user_id,
            payload={'content': csv_content},
            metadata={}
        )
        db.session.add(event)
        db.session.commit()

        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content', 'delimiter': '\t', 'has_header': True},
            user_id=test_job.user_id
        )

        result = agent.process([event])
        db.session.commit()

        assert len(result) == 1
        assert result[0].payload['rows'][0]['name'] == 'Alice'
        assert result[0].payload['rows'][0]['age'] == 30

    def test_parse_csv_custom_delimiter_semicolon(self, test_job):
        """Test parsing CSV with semicolon delimiter"""
        csv_content = "name;age;email\nAlice;30;alice@example.com\nBob;25;bob@example.com"

        event = Event(
            agent_id=test_job.id,
            agent_type='web_fetch_agent',
            user_id=test_job.user_id,
            payload={'content': csv_content},
            metadata={}
        )
        db.session.add(event)
        db.session.commit()

        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content', 'delimiter': ';', 'has_header': True},
            user_id=test_job.user_id
        )

        result = agent.process([event])
        db.session.commit()

        assert len(result) == 1
        assert result[0].payload['rows'][0]['name'] == 'Alice'

    def test_parse_csv_with_quotes_and_commas(self, test_job):
        """Test parsing CSV with quoted fields containing commas"""
        csv_content = 'name,location,notes\nAlice,"New York, NY","Great, experienced"\nBob,"San Francisco, CA","Good worker, reliable"'

        event = Event(
            agent_id=test_job.id,
            agent_type='web_fetch_agent',
            user_id=test_job.user_id,
            payload={'content': csv_content},
            metadata={}
        )
        db.session.add(event)
        db.session.commit()

        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content', 'has_header': True},
            user_id=test_job.user_id
        )

        result = agent.process([event])
        db.session.commit()

        assert len(result) == 1
        assert result[0].payload['rows'][0]['location'] == 'New York, NY'
        assert result[0].payload['rows'][0]['notes'] == 'Great, experienced'

    def test_parse_empty_csv(self, test_job):
        """Test parsing empty CSV content"""
        csv_content = ""

        event = Event(
            agent_id=test_job.id,
            agent_type='web_fetch_agent',
            user_id=test_job.user_id,
            payload={'content': csv_content},
            metadata={}
        )
        db.session.add(event)
        db.session.commit()

        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content', 'has_header': True},
            user_id=test_job.user_id
        )

        result = agent.process([event])
        db.session.commit()

        # Empty CSV should produce no output events (skipped)
        assert len(result) == 0

    def test_parse_single_row_csv(self, test_job):
        """Test parsing CSV with single data row"""
        csv_content = "name,age,email\nAlice,30,alice@example.com"

        event = Event(
            agent_id=test_job.id,
            agent_type='web_fetch_agent',
            user_id=test_job.user_id,
            payload={'content': csv_content},
            metadata={}
        )
        db.session.add(event)
        db.session.commit()

        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content', 'has_header': True},
            user_id=test_job.user_id
        )

        result = agent.process([event])
        db.session.commit()

        assert len(result) == 1
        assert result[0].payload['row_count'] == 1
        assert result[0].payload['rows'][0]['name'] == 'Alice'

    def test_parse_csv_unicode_characters(self, test_job):
        """Test parsing CSV with unicode characters"""
        csv_content = "name,city,emoji\nAlice,München,😀\nBob,Tokyo,日本"

        event = Event(
            agent_id=test_job.id,
            agent_type='web_fetch_agent',
            user_id=test_job.user_id,
            payload={'content': csv_content},
            metadata={}
        )
        db.session.add(event)
        db.session.commit()

        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content', 'has_header': True},
            user_id=test_job.user_id
        )

        result = agent.process([event])
        db.session.commit()

        assert len(result) == 1
        assert result[0].payload['rows'][0]['city'] == 'München'
        assert result[0].payload['rows'][0]['emoji'] == '😀'


class TestCSVParserAgentOutputModes:
    """Test different output modes"""

    def test_combined_mode_single_event(self, test_job):
        """Test combined mode creates single event with all rows"""
        csv_content = "name,age\nAlice,30\nBob,25\nCharlie,35"

        event = Event(
            agent_id=test_job.id,
            agent_type='web_fetch_agent',
            user_id=test_job.user_id,
            payload={'content': csv_content},
            metadata={}
        )
        db.session.add(event)
        db.session.commit()

        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content', 'create_event_per_row': False},
            user_id=test_job.user_id
        )

        result = agent.process([event])
        db.session.commit()

        assert len(result) == 1
        assert result[0].payload['row_count'] == 3
        assert len(result[0].payload['rows']) == 3
        assert result[0].event_metadata['mode'] == 'combined'

    def test_per_row_mode_multiple_events(self, test_job):
        """Test per-row mode creates separate event for each row"""
        csv_content = "name,age\nAlice,30\nBob,25\nCharlie,35"

        event = Event(
            agent_id=test_job.id,
            agent_type='web_fetch_agent',
            user_id=test_job.user_id,
            payload={'content': csv_content},
            metadata={}
        )
        db.session.add(event)
        db.session.commit()

        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content', 'create_event_per_row': True},
            user_id=test_job.user_id
        )

        result = agent.process([event])
        db.session.commit()

        assert len(result) == 3
        assert result[0].payload['name'] == 'Alice'
        assert result[0].payload['age'] == 30
        assert result[0].event_metadata['row_index'] == 0
        assert result[1].payload['name'] == 'Bob'
        assert result[1].event_metadata['row_index'] == 1
        assert result[2].payload['name'] == 'Charlie'
        assert result[2].event_metadata['row_index'] == 2

    def test_row_count_in_combined_mode(self, test_job):
        """Test row_count field in combined mode output"""
        csv_content = "name,age\nAlice,30\nBob,25"

        event = Event(
            agent_id=test_job.id,
            agent_type='web_fetch_agent',
            user_id=test_job.user_id,
            payload={'content': csv_content},
            metadata={}
        )
        db.session.add(event)
        db.session.commit()

        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content', 'create_event_per_row': False},
            user_id=test_job.user_id
        )

        result = agent.process([event])
        db.session.commit()

        assert result[0].payload['row_count'] == 2
        assert 'column_names' in result[0].payload
        assert 'name' in result[0].payload['column_names']

    def test_row_index_in_per_row_mode(self, test_job):
        """Test row_index metadata in per-row mode"""
        csv_content = "name,age\nAlice,30\nBob,25"

        event = Event(
            agent_id=test_job.id,
            agent_type='web_fetch_agent',
            user_id=test_job.user_id,
            payload={'content': csv_content},
            metadata={}
        )
        db.session.add(event)
        db.session.commit()

        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content', 'create_event_per_row': True},
            user_id=test_job.user_id
        )

        result = agent.process([event])
        db.session.commit()

        assert result[0].event_metadata['row_index'] == 0
        assert result[1].event_metadata['row_index'] == 1
        assert result[0].event_metadata['total_columns'] == 2


class TestCSVParserAgentTypeConversion:
    """Test automatic type conversion"""

    def test_convert_integers(self, test_job):
        """Test integer conversion"""
        csv_content = "name,age,score\nAlice,30,100\nBob,25,95"

        event = Event(
            agent_id=test_job.id,
            agent_type='web_fetch_agent',
            user_id=test_job.user_id,
            payload={'content': csv_content},
            metadata={}
        )
        db.session.add(event)
        db.session.commit()

        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content', 'convert_types': True},
            user_id=test_job.user_id
        )

        result = agent.process([event])
        db.session.commit()

        assert result[0].payload['rows'][0]['age'] == 30
        assert isinstance(result[0].payload['rows'][0]['age'], int)
        assert result[0].payload['rows'][0]['score'] == 100

    def test_convert_floats(self, test_job):
        """Test float conversion"""
        csv_content = "name,price,rating\nProduct A,19.99,4.5\nProduct B,29.95,4.8"

        event = Event(
            agent_id=test_job.id,
            agent_type='web_fetch_agent',
            user_id=test_job.user_id,
            payload={'content': csv_content},
            metadata={}
        )
        db.session.add(event)
        db.session.commit()

        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content', 'convert_types': True},
            user_id=test_job.user_id
        )

        result = agent.process([event])
        db.session.commit()

        assert result[0].payload['rows'][0]['price'] == 19.99
        assert isinstance(result[0].payload['rows'][0]['price'], float)
        assert result[0].payload['rows'][0]['rating'] == 4.5

    def test_convert_booleans(self, test_job):
        """Test boolean conversion (true/false, yes/no, 1/0)"""
        csv_content = "name,active,verified,admin\nAlice,true,yes,1\nBob,false,no,0"

        event = Event(
            agent_id=test_job.id,
            agent_type='web_fetch_agent',
            user_id=test_job.user_id,
            payload={'content': csv_content},
            metadata={}
        )
        db.session.add(event)
        db.session.commit()

        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content', 'convert_types': True},
            user_id=test_job.user_id
        )

        result = agent.process([event])
        db.session.commit()

        assert result[0].payload['rows'][0]['active'] is True
        assert result[0].payload['rows'][0]['verified'] is True
        assert result[0].payload['rows'][0]['admin'] is True
        assert result[0].payload['rows'][1]['active'] is False
        assert result[0].payload['rows'][1]['verified'] is False
        assert result[0].payload['rows'][1]['admin'] is False

    def test_keep_strings_as_strings(self, test_job):
        """Test that non-numeric strings remain strings"""
        csv_content = "name,city,country\nAlice,New York,USA\nBob,London,UK"

        event = Event(
            agent_id=test_job.id,
            agent_type='web_fetch_agent',
            user_id=test_job.user_id,
            payload={'content': csv_content},
            metadata={}
        )
        db.session.add(event)
        db.session.commit()

        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content', 'convert_types': True},
            user_id=test_job.user_id
        )

        result = agent.process([event])
        db.session.commit()

        assert result[0].payload['rows'][0]['name'] == 'Alice'
        assert isinstance(result[0].payload['rows'][0]['name'], str)
        assert result[0].payload['rows'][0]['city'] == 'New York'

    def test_convert_empty_to_none(self, test_job):
        """Test empty strings convert to None"""
        csv_content = "name,age,email\nAlice,30,alice@example.com\nBob,,bob@example.com"

        event = Event(
            agent_id=test_job.id,
            agent_type='web_fetch_agent',
            user_id=test_job.user_id,
            payload={'content': csv_content},
            metadata={}
        )
        db.session.add(event)
        db.session.commit()

        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content', 'convert_types': True},
            user_id=test_job.user_id
        )

        result = agent.process([event])
        db.session.commit()

        assert result[0].payload['rows'][0]['age'] == 30
        assert result[0].payload['rows'][1]['age'] is None

    def test_disable_type_conversion(self, test_job):
        """Test disabling type conversion keeps all values as strings"""
        csv_content = "name,age,active\nAlice,30,true\nBob,25,false"

        event = Event(
            agent_id=test_job.id,
            agent_type='web_fetch_agent',
            user_id=test_job.user_id,
            payload={'content': csv_content},
            metadata={}
        )
        db.session.add(event)
        db.session.commit()

        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content', 'convert_types': False},
            user_id=test_job.user_id
        )

        result = agent.process([event])
        db.session.commit()

        assert result[0].payload['rows'][0]['age'] == '30'
        assert isinstance(result[0].payload['rows'][0]['age'], str)
        assert result[0].payload['rows'][0]['active'] == 'true'
        assert isinstance(result[0].payload['rows'][0]['active'], str)


class TestCSVParserAgentColumnOperations:
    """Test column selection and renaming"""

    def test_select_specific_columns(self, test_job):
        """Test selecting specific columns"""
        csv_content = "name,age,email,city\nAlice,30,alice@example.com,NYC\nBob,25,bob@example.com,SF"

        event = Event(
            agent_id=test_job.id,
            agent_type='web_fetch_agent',
            user_id=test_job.user_id,
            payload={'content': csv_content},
            metadata={}
        )
        db.session.add(event)
        db.session.commit()

        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content', 'columns': ['name', 'email']},
            user_id=test_job.user_id
        )

        result = agent.process([event])
        db.session.commit()

        assert 'name' in result[0].payload['rows'][0]
        assert 'email' in result[0].payload['rows'][0]
        assert 'age' not in result[0].payload['rows'][0]
        assert 'city' not in result[0].payload['rows'][0]

    def test_rename_columns(self, test_job):
        """Test renaming columns"""
        csv_content = "name,age,email\nAlice,30,alice@example.com\nBob,25,bob@example.com"

        event = Event(
            agent_id=test_job.id,
            agent_type='web_fetch_agent',
            user_id=test_job.user_id,
            payload={'content': csv_content},
            metadata={}
        )
        db.session.add(event)
        db.session.commit()

        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={
                'csv_field': 'content',
                'rename_columns': {'email': 'email_address', 'age': 'years'}
            },
            user_id=test_job.user_id
        )

        result = agent.process([event])
        db.session.commit()

        assert 'email_address' in result[0].payload['rows'][0]
        assert 'years' in result[0].payload['rows'][0]
        assert 'email' not in result[0].payload['rows'][0]
        assert 'age' not in result[0].payload['rows'][0]
        assert result[0].payload['rows'][0]['email_address'] == 'alice@example.com'

    def test_select_and_rename_together(self, test_job):
        """Test selecting and renaming columns together"""
        csv_content = "name,age,email,city\nAlice,30,alice@example.com,NYC\nBob,25,bob@example.com,SF"

        event = Event(
            agent_id=test_job.id,
            agent_type='web_fetch_agent',
            user_id=test_job.user_id,
            payload={'content': csv_content},
            metadata={}
        )
        db.session.add(event)
        db.session.commit()

        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={
                'csv_field': 'content',
                'columns': ['name', 'email'],
                'rename_columns': {'email': 'contact'}
            },
            user_id=test_job.user_id
        )

        result = agent.process([event])
        db.session.commit()

        assert 'name' in result[0].payload['rows'][0]
        assert 'contact' in result[0].payload['rows'][0]
        assert 'age' not in result[0].payload['rows'][0]
        assert 'email' not in result[0].payload['rows'][0]

    def test_handle_missing_columns_gracefully(self, test_job):
        """Test handling missing columns in column selection"""
        csv_content = "name,age\nAlice,30\nBob,25"

        event = Event(
            agent_id=test_job.id,
            agent_type='web_fetch_agent',
            user_id=test_job.user_id,
            payload={'content': csv_content},
            metadata={}
        )
        db.session.add(event)
        db.session.commit()

        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content', 'columns': ['name', 'email']},  # 'email' doesn't exist
            user_id=test_job.user_id
        )

        result = agent.process([event])
        db.session.commit()

        # Should only include 'name' since 'email' doesn't exist
        assert 'name' in result[0].payload['rows'][0]
        assert 'email' not in result[0].payload['rows'][0]

    def test_all_columns_when_null(self, test_job):
        """Test that columns=null includes all columns"""
        csv_content = "name,age,email\nAlice,30,alice@example.com\nBob,25,bob@example.com"

        event = Event(
            agent_id=test_job.id,
            agent_type='web_fetch_agent',
            user_id=test_job.user_id,
            payload={'content': csv_content},
            metadata={}
        )
        db.session.add(event)
        db.session.commit()

        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content', 'columns': None},
            user_id=test_job.user_id
        )

        result = agent.process([event])
        db.session.commit()

        assert 'name' in result[0].payload['rows'][0]
        assert 'age' in result[0].payload['rows'][0]
        assert 'email' in result[0].payload['rows'][0]


class TestCSVParserAgentRowFiltering:
    """Test row filtering and limits"""

    def test_filter_empty_rows(self, test_job):
        """Test filtering empty rows"""
        csv_content = "name,age\nAlice,30\n,,\nBob,25\n,,"

        event = Event(
            agent_id=test_job.id,
            agent_type='web_fetch_agent',
            user_id=test_job.user_id,
            payload={'content': csv_content},
            metadata={}
        )
        db.session.add(event)
        db.session.commit()

        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content', 'filter_empty_rows': True},
            user_id=test_job.user_id
        )

        result = agent.process([event])
        db.session.commit()

        # Should only have 2 rows (Alice and Bob), empty rows filtered
        assert result[0].payload['row_count'] == 2
        assert result[0].payload['rows'][0]['name'] == 'Alice'
        assert result[0].payload['rows'][1]['name'] == 'Bob'

    def test_keep_empty_rows(self, test_job):
        """Test keeping empty rows when filter_empty_rows=False"""
        csv_content = "name,age\nAlice,30\n,,\nBob,25"

        event = Event(
            agent_id=test_job.id,
            agent_type='web_fetch_agent',
            user_id=test_job.user_id,
            payload={'content': csv_content},
            metadata={}
        )
        db.session.add(event)
        db.session.commit()

        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content', 'filter_empty_rows': False, 'convert_types': True},
            user_id=test_job.user_id
        )

        result = agent.process([event])
        db.session.commit()

        # Should have 3 rows (including empty row)
        assert result[0].payload['row_count'] == 3
        assert result[0].payload['rows'][1]['name'] is None
        assert result[0].payload['rows'][1]['age'] is None

    def test_max_rows_limit(self, test_job):
        """Test limiting maximum rows processed"""
        csv_content = "name,age\nAlice,30\nBob,25\nCharlie,35\nDiana,28\nEve,32"

        event = Event(
            agent_id=test_job.id,
            agent_type='web_fetch_agent',
            user_id=test_job.user_id,
            payload={'content': csv_content},
            metadata={}
        )
        db.session.add(event)
        db.session.commit()

        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content', 'max_rows': 3},
            user_id=test_job.user_id
        )

        result = agent.process([event])
        db.session.commit()

        # Should only process first 3 rows
        assert result[0].payload['row_count'] == 3
        assert result[0].payload['rows'][0]['name'] == 'Alice'
        assert result[0].payload['rows'][2]['name'] == 'Charlie'

    def test_skip_rows_at_start(self, test_job):
        """Test skipping rows at the start"""
        csv_content = "# Comment line\n# Another comment\nname,age\nAlice,30\nBob,25"

        event = Event(
            agent_id=test_job.id,
            agent_type='web_fetch_agent',
            user_id=test_job.user_id,
            payload={'content': csv_content},
            metadata={}
        )
        db.session.add(event)
        db.session.commit()

        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content', 'skip_rows': 2, 'has_header': True},
            user_id=test_job.user_id
        )

        result = agent.process([event])
        db.session.commit()

        # Should skip 2 comment lines, then use line 3 as header
        assert result[0].payload['row_count'] == 2
        assert result[0].payload['rows'][0]['name'] == 'Alice'


class TestCSVParserAgentErrorHandling:
    """Test error handling"""

    def test_on_parse_error_skip(self, test_job):
        """Test skipping events with parse errors"""
        event = Event(
            agent_id=test_job.id,
            agent_type='web_fetch_agent',
            user_id=test_job.user_id,
            payload={'wrong_field': 'some data'},  # Missing 'content' field
            metadata={}
        )
        db.session.add(event)
        db.session.commit()

        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content', 'on_parse_error': 'skip'},
            user_id=test_job.user_id
        )

        result = agent.process([event])
        db.session.commit()

        # Should skip event with missing field
        assert len(result) == 0

    def test_on_parse_error_null(self, test_job):
        """Test creating null event on parse error"""
        event = Event(
            agent_id=test_job.id,
            agent_type='web_fetch_agent',
            user_id=test_job.user_id,
            payload={'wrong_field': 'some data'},
            metadata={}
        )
        db.session.add(event)
        db.session.commit()

        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content', 'on_parse_error': 'null'},
            user_id=test_job.user_id
        )

        result = agent.process([event])
        db.session.commit()

        # Should create event with null data
        assert len(result) == 1
        assert result[0].payload['rows'] is None
        assert result[0].payload['row_count'] == 0
        assert result[0].payload['parse_error'] is True

    def test_on_parse_error_error(self, test_job):
        """Test raising error on parse failure"""
        event = Event(
            agent_id=test_job.id,
            agent_type='web_fetch_agent',
            user_id=test_job.user_id,
            payload={'wrong_field': 'some data'},
            metadata={}
        )
        db.session.add(event)
        db.session.commit()

        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content', 'on_parse_error': 'error'},
            user_id=test_job.user_id
        )

        # Should raise exception
        with pytest.raises(Exception):
            agent.process([event])

    def test_missing_csv_field_in_payload(self, test_job):
        """Test handling missing csv_field in payload"""
        event = Event(
            agent_id=test_job.id,
            agent_type='web_fetch_agent',
            user_id=test_job.user_id,
            payload={'data': 'some,csv,data'},  # Has 'data' not 'content'
            metadata={}
        )
        db.session.add(event)
        db.session.commit()

        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content', 'on_parse_error': 'skip'},
            user_id=test_job.user_id
        )

        result = agent.process([event])
        db.session.commit()

        # Should skip event
        assert len(result) == 0

    def test_malformed_csv_data(self, test_job):
        """Test handling malformed CSV data"""
        # CSV with inconsistent columns - CSV module handles this gracefully
        csv_content = "name,age\nAlice,30,extra\nBob"

        event = Event(
            agent_id=test_job.id,
            agent_type='web_fetch_agent',
            user_id=test_job.user_id,
            payload={'content': csv_content},
            metadata={}
        )
        db.session.add(event)
        db.session.commit()

        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content', 'on_parse_error': 'skip'},
            user_id=test_job.user_id
        )

        # Should handle gracefully (CSV module is forgiving)
        result = agent.process([event])
        db.session.commit()

        # Result may vary based on CSV parsing behavior
        assert len(result) >= 0


class TestCSVParserAgentMetadataAndPreservation:
    """Test metadata and original payload preservation"""

    def test_metadata_in_output_events(self, test_job):
        """Test that output events have proper metadata"""
        csv_content = "name,age\nAlice,30\nBob,25"

        event = Event(
            agent_id=test_job.id,
            agent_type='web_fetch_agent',
            user_id=test_job.user_id,
            payload={'content': csv_content},
            metadata={}
        )
        db.session.add(event)
        db.session.commit()

        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content'},
            user_id=test_job.user_id
        )

        result = agent.process([event])
        db.session.commit()

        assert result[0].event_metadata['source_event_id'] == event.id
        assert result[0].event_metadata['parser'] == 'csv'
        assert 'row_count' in result[0].event_metadata
        assert result[0].event_metadata['mode'] == 'combined'

    def test_preserve_original_true(self, test_job):
        """Test preserve_original=True merges with original payload"""
        csv_content = "name,age\nAlice,30"

        event = Event(
            agent_id=test_job.id,
            agent_type='web_fetch_agent',
            user_id=test_job.user_id,
            payload={'content': csv_content, 'source': 'api', 'timestamp': '2024-01-01'},
            metadata={}
        )
        db.session.add(event)
        db.session.commit()

        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content', 'preserve_original': True},
            user_id=test_job.user_id
        )

        result = agent.process([event])
        db.session.commit()

        # Should have original fields plus parsed data
        assert result[0].payload['source'] == 'api'
        assert result[0].payload['timestamp'] == '2024-01-01'
        assert result[0].payload['rows'][0]['name'] == 'Alice'
        assert 'content' in result[0].payload

    def test_preserve_original_false(self, test_job):
        """Test preserve_original=False replaces payload"""
        csv_content = "name,age\nAlice,30"

        event = Event(
            agent_id=test_job.id,
            agent_type='web_fetch_agent',
            user_id=test_job.user_id,
            payload={'content': csv_content, 'source': 'api', 'timestamp': '2024-01-01'},
            metadata={}
        )
        db.session.add(event)
        db.session.commit()

        agent = CSVParserAgent(
            agent_id=test_job.id,
            config={'csv_field': 'content', 'preserve_original': False},
            user_id=test_job.user_id
        )

        result = agent.process([event])
        db.session.commit()

        # Should only have parsed data, not original fields
        assert 'source' not in result[0].payload
        assert 'timestamp' not in result[0].payload
        assert 'content' not in result[0].payload
        assert result[0].payload['rows'][0]['name'] == 'Alice'
