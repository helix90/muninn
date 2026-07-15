"""
Tests for JSONPath Agent - Extract fields using JSONPath expressions
"""

import pytest
from app.agents.types.jsonpath_agent import JSONPathAgent
from app.models import Event
from app.extensions import db


class TestJSONPathAgentRegistration:
    """Test JSONPathAgent registration"""

    def test_jsonpath_agent_registered(self, test_job):
        """Test that JSONPathAgent is properly registered"""
        from app.agents.registry import agent_registry

        assert agent_registry.is_registered('jsonpath_agent')
        assert 'jsonpath_agent' in agent_registry.get_transform_agents()

    def test_jsonpath_agent_capabilities(self, test_job):
        """Test agent capabilities and category"""
        agent = JSONPathAgent(
            agent_id=test_job.id,
            config={'path': '$.field'},
            user_id=test_job.user_id
        )

        assert agent.agent_type == 'jsonpath_agent'
        assert agent.agent_category == 'transform'
        assert not agent.can_be_scheduled
        assert agent.can_receive_events
        assert agent.can_create_events
        assert agent.requires_input


class TestJSONPathAgentConfig:
    """Test JSONPathAgent configuration validation"""

    def test_valid_simple_mode_config(self, test_job):
        """Test valid simple mode configuration"""
        agent = JSONPathAgent(
            agent_id=test_job.id,
            config={
                'path': '$.user.email',
                'output_field': 'email',
                'on_missing': 'skip'
            },
            user_id=test_job.user_id
        )

        assert agent.config['path'] == '$.user.email'
        assert agent.config['output_field'] == 'email'
        assert agent.on_missing == 'skip'

    def test_valid_multi_field_mode_config(self, test_job):
        """Test valid multi-field mode configuration"""
        agent = JSONPathAgent(
            agent_id=test_job.id,
            config={
                'extractions': [
                    {'path': '$.user.email', 'output_field': 'email'},
                    {'path': '$.user.name', 'output_field': 'name'}
                ],
                'on_missing': 'null'
            },
            user_id=test_job.user_id
        )

        assert len(agent.config['extractions']) == 2
        assert agent.on_missing == 'null'

    def test_missing_path_and_extractions(self, test_job):
        """Test error when neither path nor extractions provided"""
        with pytest.raises(ValueError, match="Must specify either 'path'.*or 'extractions'"):
            JSONPathAgent(
                agent_id=test_job.id,
                config={},
                user_id=test_job.user_id
            )

    def test_both_path_and_extractions_error(self, test_job):
        """Test error when both path and extractions provided"""
        with pytest.raises(ValueError, match="Cannot specify both 'path' and 'extractions'"):
            JSONPathAgent(
                agent_id=test_job.id,
                config={
                    'path': '$.field',
                    'extractions': [{'path': '$.other', 'output_field': 'out'}]
                },
                user_id=test_job.user_id
            )

    def test_invalid_jsonpath_expression(self, test_job):
        """Test error with invalid JSONPath expression"""
        with pytest.raises(ValueError, match="Invalid JSONPath expression"):
            JSONPathAgent(
                agent_id=test_job.id,
                config={'path': '$[invalid'},  # Invalid JSONPath syntax
                user_id=test_job.user_id
            )

    def test_extractions_must_be_list(self, test_job):
        """Test error when extractions is not a list"""
        with pytest.raises(ValueError, match="'extractions' must be a list"):
            JSONPathAgent(
                agent_id=test_job.id,
                config={'extractions': 'not a list'},
                user_id=test_job.user_id
            )

    def test_empty_extractions_list(self, test_job):
        """Test error with empty extractions list"""
        with pytest.raises(ValueError, match="must contain at least one extraction rule"):
            JSONPathAgent(
                agent_id=test_job.id,
                config={'extractions': []},
                user_id=test_job.user_id
            )

    def test_extraction_missing_path(self, test_job):
        """Test error when extraction missing path field"""
        with pytest.raises(ValueError, match="Extraction 0 missing 'path' field"):
            JSONPathAgent(
                agent_id=test_job.id,
                config={
                    'extractions': [
                        {'output_field': 'out'}  # Missing 'path'
                    ]
                },
                user_id=test_job.user_id
            )

    def test_extraction_missing_output_field(self, test_job):
        """Test error when extraction missing output_field"""
        with pytest.raises(ValueError, match="Extraction 0 missing 'output_field' field"):
            JSONPathAgent(
                agent_id=test_job.id,
                config={
                    'extractions': [
                        {'path': '$.field'}  # Missing 'output_field'
                    ]
                },
                user_id=test_job.user_id
            )

    def test_invalid_on_missing_value(self, test_job):
        """Test error with invalid on_missing value"""
        with pytest.raises(ValueError, match="'on_missing' must be 'skip', 'null', or 'error'"):
            JSONPathAgent(
                agent_id=test_job.id,
                config={
                    'path': '$.field',
                    'on_missing': 'invalid'
                },
                user_id=test_job.user_id
            )


class TestJSONPathAgentSimpleMode:
    """Test JSONPathAgent simple mode extraction"""

    def test_extract_simple_field(self, test_job):
        """Test extracting a simple root-level field"""
        # Create input event
        event = Event(
            agent_id=test_job.id,
            agent_type='test_agent',
            user_id=test_job.user_id,
            payload={'name': 'Alice', 'age': 30},
            metadata={'source': 'test'}
        )
        db.session.add(event)
        db.session.commit()

        # Create agent
        agent = JSONPathAgent(
            agent_id=test_job.id,
            config={'path': '$.name'},
            user_id=test_job.user_id
        )

        # Process
        output_events = agent.process([event])
        db.session.commit()

        assert len(output_events) == 1
        assert output_events[0].payload == {'extracted': 'Alice'}
        assert output_events[0].event_metadata['source_event_id'] == event.id

    def test_extract_nested_field(self, test_job):
        """Test extracting a nested field"""
        event = Event(
            agent_id=test_job.id,
            agent_type='test_agent',
            user_id=test_job.user_id,
            payload={
                'user': {
                    'name': 'Bob',
                    'email': 'bob@example.com'
                },
                'order_id': 123
            },
            metadata={'source': 'test'}
        )
        db.session.add(event)
        db.session.commit()

        agent = JSONPathAgent(
            agent_id=test_job.id,
            config={
                'path': '$.user.email',
                'output_field': 'email'
            },
            user_id=test_job.user_id
        )

        output_events = agent.process([event])
        db.session.commit()

        assert len(output_events) == 1
        assert output_events[0].payload == {'email': 'bob@example.com'}

    def test_extract_array_element(self, test_job):
        """Test extracting specific array element"""
        event = Event(
            agent_id=test_job.id,
            agent_type='test_agent',
            user_id=test_job.user_id,
            payload={
                'items': [
                    {'name': 'Item 1', 'price': 10},
                    {'name': 'Item 2', 'price': 20}
                ]
            },
            metadata={'source': 'test'}
        )
        db.session.add(event)
        db.session.commit()

        agent = JSONPathAgent(
            agent_id=test_job.id,
            config={
                'path': '$.items[0].name',
                'output_field': 'first_item'
            },
            user_id=test_job.user_id
        )

        output_events = agent.process([event])
        db.session.commit()

        assert len(output_events) == 1
        assert output_events[0].payload == {'first_item': 'Item 1'}

    def test_custom_output_field_name(self, test_job):
        """Test using custom output field name"""
        event = Event(
            agent_id=test_job.id,
            agent_type='test_agent',
            user_id=test_job.user_id,
            payload={'value': 42},
            metadata={'source': 'test'}
        )
        db.session.add(event)
        db.session.commit()

        agent = JSONPathAgent(
            agent_id=test_job.id,
            config={
                'path': '$.value',
                'output_field': 'my_value'
            },
            user_id=test_job.user_id
        )

        output_events = agent.process([event])
        db.session.commit()

        assert output_events[0].payload == {'my_value': 42}

    def test_path_not_found_skip(self, test_job):
        """Test skipping event when path not found (default behavior)"""
        event = Event(
            agent_id=test_job.id,
            agent_type='test_agent',
            user_id=test_job.user_id,
            payload={'name': 'Alice'},
            metadata={'source': 'test'}
        )
        db.session.add(event)
        db.session.commit()

        agent = JSONPathAgent(
            agent_id=test_job.id,
            config={
                'path': '$.nonexistent',
                'on_missing': 'skip'
            },
            user_id=test_job.user_id
        )

        output_events = agent.process([event])
        db.session.commit()

        assert len(output_events) == 0  # Event skipped

    def test_path_not_found_null(self, test_job):
        """Test using null value when path not found"""
        event = Event(
            agent_id=test_job.id,
            agent_type='test_agent',
            user_id=test_job.user_id,
            payload={'name': 'Alice'},
            metadata={'source': 'test'}
        )
        db.session.add(event)
        db.session.commit()

        agent = JSONPathAgent(
            agent_id=test_job.id,
            config={
                'path': '$.nonexistent',
                'on_missing': 'null'
            },
            user_id=test_job.user_id
        )

        output_events = agent.process([event])
        db.session.commit()

        assert len(output_events) == 1
        assert output_events[0].payload == {'extracted': None}

    def test_path_not_found_error(self, test_job):
        """Test raising error when path not found"""
        event = Event(
            agent_id=test_job.id,
            agent_type='test_agent',
            user_id=test_job.user_id,
            payload={'name': 'Alice'},
            metadata={'source': 'test'}
        )
        db.session.add(event)
        db.session.commit()

        agent = JSONPathAgent(
            agent_id=test_job.id,
            config={
                'path': '$.nonexistent',
                'on_missing': 'error'
            },
            user_id=test_job.user_id
        )

        with pytest.raises(ValueError, match="No data extracted"):
            agent.process([event])

    def test_preserve_original_payload(self, test_job):
        """Test preserving original payload in output"""
        event = Event(
            agent_id=test_job.id,
            agent_type='test_agent',
            user_id=test_job.user_id,
            payload={'name': 'Alice', 'age': 30, 'email': 'alice@example.com'},
            metadata={'source': 'test'}
        )
        db.session.add(event)
        db.session.commit()

        agent = JSONPathAgent(
            agent_id=test_job.id,
            config={
                'path': '$.email',
                'output_field': 'extracted_email',
                'preserve_original': True
            },
            user_id=test_job.user_id
        )

        output_events = agent.process([event])
        db.session.commit()

        assert len(output_events) == 1
        assert output_events[0].payload['name'] == 'Alice'
        assert output_events[0].payload['age'] == 30
        assert output_events[0].payload['email'] == 'alice@example.com'
        assert output_events[0].payload['extracted_email'] == 'alice@example.com'


class TestJSONPathAgentMultiFieldMode:
    """Test JSONPathAgent multi-field extraction mode"""

    def test_extract_multiple_fields(self, test_job):
        """Test extracting multiple fields"""
        event = Event(
            agent_id=test_job.id,
            agent_type='test_agent',
            user_id=test_job.user_id,
            payload={
                'user': {
                    'name': 'Charlie',
                    'email': 'charlie@example.com',
                    'age': 25
                },
                'order': {
                    'id': 456,
                    'total': 99.99
                }
            },
            metadata={'source': 'test'}
        )
        db.session.add(event)
        db.session.commit()

        agent = JSONPathAgent(
            agent_id=test_job.id,
            config={
                'extractions': [
                    {'path': '$.user.email', 'output_field': 'email'},
                    {'path': '$.user.name', 'output_field': 'name'},
                    {'path': '$.order.total', 'output_field': 'amount'}
                ]
            },
            user_id=test_job.user_id
        )

        output_events = agent.process([event])
        db.session.commit()

        assert len(output_events) == 1
        assert output_events[0].payload == {
            'email': 'charlie@example.com',
            'name': 'Charlie',
            'amount': 99.99
        }

    def test_mixed_existing_and_missing_fields(self, test_job):
        """Test extraction with mix of existing and missing fields"""
        event = Event(
            agent_id=test_job.id,
            agent_type='test_agent',
            user_id=test_job.user_id,
            payload={
                'user': {'name': 'Dave'},
                'order': {'id': 789}
            },
            metadata={'source': 'test'}
        )
        db.session.add(event)
        db.session.commit()

        agent = JSONPathAgent(
            agent_id=test_job.id,
            config={
                'extractions': [
                    {'path': '$.user.name', 'output_field': 'name'},
                    {'path': '$.user.email', 'output_field': 'email'},  # Missing
                    {'path': '$.order.id', 'output_field': 'order_id'}
                ],
                'on_missing': 'null'
            },
            user_id=test_job.user_id
        )

        output_events = agent.process([event])
        db.session.commit()

        assert len(output_events) == 1
        assert output_events[0].payload == {
            'name': 'Dave',
            'email': None,  # Missing field becomes null
            'order_id': 789
        }

    def test_preserve_original_with_extractions(self, test_job):
        """Test preserve_original with multi-field extraction"""
        event = Event(
            agent_id=test_job.id,
            agent_type='test_agent',
            user_id=test_job.user_id,
            payload={
                'id': 1,
                'user': {'name': 'Eve', 'email': 'eve@example.com'}
            },
            metadata={'source': 'test'}
        )
        db.session.add(event)
        db.session.commit()

        agent = JSONPathAgent(
            agent_id=test_job.id,
            config={
                'extractions': [
                    {'path': '$.user.name', 'output_field': 'name'}
                ],
                'preserve_original': True
            },
            user_id=test_job.user_id
        )

        output_events = agent.process([event])
        db.session.commit()

        assert output_events[0].payload['id'] == 1
        assert output_events[0].payload['user'] == {'name': 'Eve', 'email': 'eve@example.com'}
        assert output_events[0].payload['name'] == 'Eve'


class TestJSONPathAgentArrayHandling:
    """Test JSONPathAgent array handling"""

    def test_extract_all_array_items(self, test_job):
        """Test extracting all items from an array"""
        event = Event(
            agent_id=test_job.id,
            agent_type='test_agent',
            user_id=test_job.user_id,
            payload={
                'products': [
                    {'name': 'Widget', 'price': 10},
                    {'name': 'Gadget', 'price': 20},
                    {'name': 'Doohickey', 'price': 30}
                ]
            },
            metadata={'source': 'test'}
        )
        db.session.add(event)
        db.session.commit()

        agent = JSONPathAgent(
            agent_id=test_job.id,
            config={
                'path': '$.products[*].name',
                'output_field': 'product_names'
            },
            user_id=test_job.user_id
        )

        output_events = agent.process([event])
        db.session.commit()

        assert len(output_events) == 1
        assert output_events[0].payload == {
            'product_names': ['Widget', 'Gadget', 'Doohickey']
        }

    def test_flatten_list_to_single_value(self, test_job):
        """Test flatten_lists option"""
        event = Event(
            agent_id=test_job.id,
            agent_type='test_agent',
            user_id=test_job.user_id,
            payload={
                'items': [{'value': 42}]
            },
            metadata={'source': 'test'}
        )
        db.session.add(event)
        db.session.commit()

        agent = JSONPathAgent(
            agent_id=test_job.id,
            config={
                'path': '$.items[0].value',
                'output_field': 'single_value',
                'flatten_lists': True
            },
            user_id=test_job.user_id
        )

        output_events = agent.process([event])
        db.session.commit()

        assert output_events[0].payload == {'single_value': 42}

    def test_nested_array_extraction(self, test_job):
        """Test extracting from nested arrays"""
        event = Event(
            agent_id=test_job.id,
            agent_type='test_agent',
            user_id=test_job.user_id,
            payload={
                'data': {
                    'items': [
                        {'id': 1, 'tags': ['a', 'b']},
                        {'id': 2, 'tags': ['c', 'd']}
                    ]
                }
            },
            metadata={'source': 'test'}
        )
        db.session.add(event)
        db.session.commit()

        agent = JSONPathAgent(
            agent_id=test_job.id,
            config={
                'path': '$.data.items[*].id',
                'output_field': 'ids'
            },
            user_id=test_job.user_id
        )

        output_events = agent.process([event])
        db.session.commit()

        assert output_events[0].payload == {'ids': [1, 2]}


class TestJSONPathAgentEventMetadata:
    """Test JSONPathAgent event metadata"""

    def test_output_event_has_source_event_id(self, test_job):
        """Test output event includes source event ID"""
        event = Event(
            agent_id=test_job.id,
            agent_type='test_agent',
            user_id=test_job.user_id,
            payload={'value': 123},
            metadata={'source': 'test'}
        )
        db.session.add(event)
        db.session.commit()

        agent = JSONPathAgent(
            agent_id=test_job.id,
            config={'path': '$.value'},
            user_id=test_job.user_id
        )

        output_events = agent.process([event])
        db.session.commit()

        assert output_events[0].event_metadata['source_event_id'] == event.id
        assert output_events[0].event_metadata['transformer'] == 'jsonpath'

    def test_output_event_has_transformer_metadata(self, test_job):
        """Test output event has transformer metadata"""
        event = Event(
            agent_id=test_job.id,
            agent_type='test_agent',
            user_id=test_job.user_id,
            payload={'data': 'test'},
            metadata={'source': 'test'}
        )
        db.session.add(event)
        db.session.commit()

        agent = JSONPathAgent(
            agent_id=test_job.id,
            config={'path': '$.data'},
            user_id=test_job.user_id
        )

        output_events = agent.process([event])
        db.session.commit()

        metadata = output_events[0].event_metadata
        assert metadata['transformer'] == 'jsonpath'
        assert metadata['extraction_mode'] == 'simple'
        assert 'extracted_at' in metadata

    def test_multiple_events_processed(self, test_job):
        """Test processing multiple events"""
        events = [
            Event(
                agent_id=test_job.id,
                agent_type='test_agent',
                user_id=test_job.user_id,
                payload={'name': f'User{i}', 'email': f'user{i}@example.com'},
                metadata={'source': 'test'}
            )
            for i in range(3)
        ]
        for event in events:
            db.session.add(event)
        db.session.commit()

        agent = JSONPathAgent(
            agent_id=test_job.id,
            config={
                'path': '$.email',
                'output_field': 'email'
            },
            user_id=test_job.user_id
        )

        output_events = agent.process(events)
        db.session.commit()

        assert len(output_events) == 3
        assert output_events[0].payload == {'email': 'user0@example.com'}
        assert output_events[1].payload == {'email': 'user1@example.com'}
        assert output_events[2].payload == {'email': 'user2@example.com'}


class TestJSONPathAgentConfigSchema:
    """Test JSONPathAgent configuration schema"""

    def test_get_config_schema(self, test_job):
        """Test get_config_schema returns valid schema"""
        schema = JSONPathAgent.get_config_schema()

        assert schema['agent_type'] == 'jsonpath_agent'
        assert isinstance(schema['optional_fields'], list)

        # Check that key fields are in schema
        field_names = [f['name'] for f in schema['optional_fields']]
        assert 'path' in field_names
        assert 'output_field' in field_names
        assert 'extractions' in field_names
        assert 'preserve_original' in field_names
        assert 'on_missing' in field_names
        assert 'flatten_lists' in field_names
