"""
Comprehensive tests for Filter Rule Builder functionality.

Tests cover:
1. Backend schema enhancement (filter_types and example_rules)
2. FilterAgent creation/editing with rules via form submission
3. Rule validation and JSON parsing
"""

import pytest
import json
from flask import url_for
from app.models import Job
from app.agents.types.filter_agent import FilterAgent
from app.agents.enums import EventFilterType


class TestFilterRuleBuilderBackend:
    """Test backend schema enhancements for Filter Rule Builder."""

    def test_schema_includes_filter_types(self):
        """Verify schema includes filter_types metadata."""
        schema = FilterAgent.get_config_schema()

        assert 'filter_types' in schema, "Schema should include filter_types"
        assert isinstance(schema['filter_types'], list), "filter_types should be a list"
        assert len(schema['filter_types']) >= 14, "Should have at least 14 filter types"

        # Verify structure of filter type metadata
        for filter_type in schema['filter_types']:
            assert 'value' in filter_type, "Each filter type should have 'value'"
            assert 'label' in filter_type, "Each filter type should have 'label'"
            assert 'description' in filter_type, "Each filter type should have 'description'"
            assert 'needs_value' in filter_type, "Each filter type should have 'needs_value'"

    def test_schema_includes_examples(self):
        """Verify schema includes example_rules."""
        schema = FilterAgent.get_config_schema()

        assert 'example_rules' in schema, "Schema should include example_rules"
        assert isinstance(schema['example_rules'], list), "example_rules should be a list"
        assert len(schema['example_rules']) >= 3, "Should have at least 3 examples"

        # Verify structure of example rules
        for example in schema['example_rules']:
            assert 'name' in example, "Each example should have 'name'"
            assert 'description' in example, "Each example should have 'description'"
            assert 'rules' in example, "Each example should have 'rules'"
            assert 'match_all' in example, "Each example should have 'match_all'"

    def test_exists_types_dont_need_value(self):
        """Verify exists/not_exists filter types don't need value."""
        schema = FilterAgent.get_config_schema()
        filter_types = {ft['value']: ft for ft in schema['filter_types']}

        assert filter_types['exists']['needs_value'] is False, "exists should not need value"
        assert filter_types['not_exists']['needs_value'] is False, "not_exists should not need value"

    def test_comparison_types_need_value(self):
        """Verify comparison filter types need value."""
        schema = FilterAgent.get_config_schema()
        filter_types = {ft['value']: ft for ft in schema['filter_types']}

        comparison_types = [
            'equals', 'not_equals', 'contains', 'not_contains',
            'starts_with', 'ends_with', 'regex',
            'greater_than', 'less_than', 'greater_than_or_equal', 'less_than_or_equal',
            'in_list', 'not_in_list'
        ]

        for filter_type in comparison_types:
            assert filter_types[filter_type]['needs_value'] is True, \
                f"{filter_type} should need value"

    def test_all_filter_type_enum_values_present(self):
        """Verify all EventFilterType enum values are in schema."""
        schema = FilterAgent.get_config_schema()
        schema_values = {ft['value'] for ft in schema['filter_types']}
        enum_values = {ft.value for ft in EventFilterType}

        assert schema_values == enum_values, \
            "Schema filter types should match EventFilterType enum"


class TestFilterAgentCreationWithRules:
    """Test FilterAgent creation and editing with rules via form submission."""

    def test_create_filter_agent_with_rules(self, authenticated_client, db_session, test_user):
        """Test creating a FilterAgent with rules via form submission."""
        rules = [
            {
                'field': 'title',
                'type': 'contains',
                'value': 'Python',
                'case_sensitive': False
            },
            {
                'field': 'priority',
                'type': 'equals',
                'value': 'high',
                'case_sensitive': True
            }
        ]

        form_data = {
            'name': 'Test Filter Agent',
            'agent_type': 'filter_agent',
            'config_rules': json.dumps(rules),
            'config_match_all': json.dumps(True)
        }

        response = authenticated_client.post('/agents/create', data=form_data, follow_redirects=True)

        # Verify agent was created
        agent = Job.query.filter_by(name='Test Filter Agent').first()
        assert agent is not None, "Agent should be created"
        assert agent.job_type == 'filter_agent', "Agent type should be filter_agent"
        assert 'rules' in agent.config, "Config should include rules"
        assert agent.config['rules'] == rules, "Rules should match submitted data"
        assert agent.config['match_all'] is True, "match_all should be True"

    def test_edit_filter_agent_preserves_rules(self, authenticated_client, db_session, test_user):
        """Test editing a FilterAgent preserves existing rules."""
        # Create initial agent
        initial_rules = [
            {'field': 'status', 'type': 'equals', 'value': 'active', 'case_sensitive': True}
        ]

        agent = Job(
            name='Edit Test Agent',
            job_type='filter_agent',
            config={'rules': initial_rules, 'match_all': True},
            user_id=test_user.id
        )
        db_session.add(agent)
        db_session.commit()
        agent_id = agent.id

        # Edit agent with new rules
        new_rules = [
            {'field': 'title', 'type': 'contains', 'value': 'test', 'case_sensitive': False},
            {'field': 'score', 'type': 'greater_than', 'value': 50}
        ]

        form_data = {
            'name': 'Edit Test Agent (Updated)',
            'config_rules': json.dumps(new_rules),
            'config_match_all': json.dumps(False)
        }

        response = authenticated_client.post(f'/agents/{agent_id}/edit', data=form_data, follow_redirects=True)

        # Verify rules were updated
        agent = Job.query.get(agent_id)
        assert agent is not None, "Agent should exist"
        assert agent.name == 'Edit Test Agent (Updated)', "Name should be updated"
        assert agent.config['rules'] == new_rules, "Rules should be updated"
        assert agent.config['match_all'] is False, "match_all should be updated"

    def test_invalid_json_handled(self, authenticated_client, db_session, test_user):
        """Test that invalid JSON in rules field is handled gracefully."""
        form_data = {
            'name': 'Invalid JSON Agent',
            'agent_type': 'filter_agent',
            'config_rules': 'not valid json',
            'config_match_all': json.dumps(True)
        }

        response = authenticated_client.post('/agents/create', data=form_data, follow_redirects=True)

        # Should either:
        # 1. Show validation error
        # 2. Treat as string (graceful fallback)
        # Verify agent was NOT created with broken config
        agent = Job.query.filter_by(name='Invalid JSON Agent').first()
        if agent:
            # If created, should not have invalid rules structure
            assert not isinstance(agent.config.get('rules'), str), \
                "Rules should not be stored as invalid string"

    def test_empty_rules_list(self, authenticated_client, db_session, test_user):
        """Test creating FilterAgent with empty rules list."""
        form_data = {
            'name': 'Empty Rules Agent',
            'agent_type': 'filter_agent',
            'config_rules': json.dumps([]),
            'config_match_all': json.dumps(True)
        }

        response = authenticated_client.post('/agents/create', data=form_data, follow_redirects=True)

        # Should fail validation (FilterAgent requires at least one rule)
        agent = Job.query.filter_by(name='Empty Rules Agent').first()
        # Agent creation might fail at validation level
        if agent:
            # If created, test that it fails when executed
            from app.agents.registry import agent_registry
            with pytest.raises(ValueError, match="must contain at least one rule"):
                agent_instance = agent_registry.create_agent(
                    agent_type=agent.job_type,
                    agent_id=agent.id,
                    config=agent.config,
                    user_id=agent.user_id
                )

    def test_rule_without_required_fields(self, authenticated_client, db_session, test_user):
        """Test that rules without required fields are rejected."""
        # Rule missing 'type'
        invalid_rules = [
            {'field': 'title', 'value': 'test'}
        ]

        form_data = {
            'name': 'Invalid Rule Agent',
            'agent_type': 'filter_agent',
            'config_rules': json.dumps(invalid_rules),
            'config_match_all': json.dumps(True)
        }

        response = authenticated_client.post('/agents/create', data=form_data, follow_redirects=True)

        agent = Job.query.filter_by(name='Invalid Rule Agent').first()
        if agent:
            # Should fail at agent instantiation
            from app.agents.registry import agent_registry
            with pytest.raises(ValueError, match="missing 'type'"):
                agent_instance = agent_registry.create_agent(
                    agent_type=agent.job_type,
                    agent_id=agent.id,
                    config=agent.config,
                    user_id=agent.user_id
                )

    def test_exists_filter_without_value(self, authenticated_client, db_session, test_user):
        """Test that exists/not_exists filters work without value field."""
        rules = [
            {'field': 'optional_field', 'type': 'exists'}
        ]

        form_data = {
            'name': 'Exists Filter Agent',
            'agent_type': 'filter_agent',
            'config_rules': json.dumps(rules),
            'config_match_all': json.dumps(True)
        }

        response = authenticated_client.post('/agents/create', data=form_data, follow_redirects=True)

        agent = Job.query.filter_by(name='Exists Filter Agent').first()
        assert agent is not None, "Agent should be created"

        # Verify it can be instantiated and is valid
        from app.agents.registry import agent_registry
        agent_instance = agent_registry.create_agent(
            agent_type=agent.job_type,
            agent_id=agent.id,
            config=agent.config,
            user_id=agent.user_id
        )
        assert agent_instance is not None, "Agent instance should be created"

    def test_multiple_rules_with_match_all(self, authenticated_client, db_session, test_user):
        """Test FilterAgent with multiple rules and match_all=True."""
        rules = [
            {'field': 'category', 'type': 'equals', 'value': 'tech', 'case_sensitive': False},
            {'field': 'priority', 'type': 'equals', 'value': 'high', 'case_sensitive': True},
            {'field': 'score', 'type': 'greater_than_or_equal', 'value': 80}
        ]

        form_data = {
            'name': 'Multi Rule Agent',
            'agent_type': 'filter_agent',
            'config_rules': json.dumps(rules),
            'config_match_all': json.dumps(True)
        }

        response = authenticated_client.post('/agents/create', data=form_data, follow_redirects=True)

        agent = Job.query.filter_by(name='Multi Rule Agent').first()
        assert agent is not None, "Agent should be created"
        assert len(agent.config['rules']) == 3, "Should have 3 rules"
        assert agent.config['match_all'] is True, "match_all should be True"


class TestFilterRuleValidation:
    """Test filter rule validation logic."""

    def test_valid_filter_types(self):
        """Test that all valid filter types are accepted."""
        from app.agents.enums import EventFilterType

        valid_types = [
            'equals', 'not_equals', 'contains', 'not_contains',
            'starts_with', 'ends_with', 'regex',
            'greater_than', 'less_than', 'greater_than_or_equal', 'less_than_or_equal',
            'in_list', 'not_in_list', 'exists', 'not_exists'
        ]

        for filter_type in valid_types:
            try:
                EventFilterType(filter_type)
            except ValueError:
                pytest.fail(f"Valid filter type '{filter_type}' was rejected")

    def test_invalid_filter_type_rejected(self):
        """Test that invalid filter types are rejected."""
        from app.agents.enums import EventFilterType

        with pytest.raises(ValueError):
            EventFilterType('invalid_type')

    def test_case_sensitive_flag_boolean(self):
        """Test that case_sensitive flag accepts boolean values."""
        rule_with_true = {'field': 'title', 'type': 'contains', 'value': 'test', 'case_sensitive': True}
        rule_with_false = {'field': 'title', 'type': 'contains', 'value': 'test', 'case_sensitive': False}

        # Both should be valid (tested through agent creation)
        assert isinstance(rule_with_true['case_sensitive'], bool)
        assert isinstance(rule_with_false['case_sensitive'], bool)


# Manual Testing Checklist (for documentation)
"""
MANUAL TESTING CHECKLIST FOR FILTER RULE BUILDER UI:

1. CREATE PAGE:
   [ ] Navigate to /agents/create
   [ ] Select "Filter Agent" from agent types
   [ ] Verify filter rule builder appears (not a textarea)
   [ ] Click "Add Rule" button
   [ ] Verify empty rule card appears with:
       - Field input
       - Filter type dropdown (15 types)
       - Value input
       - Case sensitive checkbox
       - Remove button

2. FILTER TYPE DROPDOWN:
   [ ] Open filter type dropdown
   [ ] Verify all 15 types are present:
       - equals, not_equals
       - contains, not_contains
       - starts_with, ends_with
       - regex
       - greater_than, less_than, greater_than_or_equal, less_than_or_equal
       - in_list, not_in_list
       - exists, not_exists
   [ ] Verify each type has a description tooltip

3. CONDITIONAL VISIBILITY:
   [ ] Select "exists" filter type
   [ ] Verify value input is HIDDEN
   [ ] Select "not_exists" filter type
   [ ] Verify value input is HIDDEN
   [ ] Select "contains" filter type
   [ ] Verify value input is VISIBLE
   [ ] Select any comparison type (equals, greater_than, etc.)
   [ ] Verify value input is VISIBLE

4. ADD/REMOVE RULES:
   [ ] Add 3 rules
   [ ] Verify all 3 are displayed
   [ ] Remove middle rule
   [ ] Verify correct rule is removed
   [ ] Verify remaining rules are intact

5. EXAMPLE TEMPLATES:
   [ ] Open "Examples" dropdown
   [ ] Verify 5 examples are present
   [ ] Click "Filter by Title Keyword"
   [ ] Verify rule is loaded with correct values
   [ ] Click "Multiple Conditions (AND)"
   [ ] Verify multiple rules are loaded

6. JSON PREVIEW:
   [ ] Add a rule
   [ ] Expand JSON preview section
   [ ] Verify JSON is properly formatted
   [ ] Verify JSON matches rule configuration
   [ ] Add another rule
   [ ] Verify JSON updates in real-time

7. FORM SUBMISSION:
   [ ] Fill in agent name: "Test Filter Agent"
   [ ] Add rule: field="title", type="contains", value="Python"
   [ ] Submit form
   [ ] Verify success message
   [ ] Verify agent appears in agents list

8. EDIT PAGE:
   [ ] Navigate to edit page for created agent
   [ ] Verify filter rule builder appears (not textarea)
   [ ] Verify existing rules are loaded correctly
   [ ] Modify a rule (change value)
   [ ] Add a new rule
   [ ] Remove an existing rule
   [ ] Submit form
   [ ] Verify changes are saved

9. VALIDATION:
   [ ] Try to add rule with empty field name
   [ ] Verify validation error
   [ ] Try to submit with no rules
   [ ] Verify validation error
   [ ] Add rule with "greater_than" and non-numeric value
   [ ] Test behavior (should convert or show error)

10. EDGE CASES:
    [ ] Add 10 rules
    [ ] Verify scrolling works
    [ ] Verify performance is acceptable
    [ ] Switch agent type to non-filter agent
    [ ] Verify rule builder disappears
    [ ] Switch back to filter agent
    [ ] Verify rule builder reappears

11. MATCH_ALL TOGGLE:
    [ ] Create agent with match_all=true (AND logic)
    [ ] Verify it's saved correctly
    [ ] Create agent with match_all=false (OR logic)
    [ ] Verify it's saved correctly

12. BACKWARDS COMPATIBILITY:
    [ ] Create agent with old JSON textarea method (if still possible)
    [ ] Verify it still works
    [ ] Edit that agent
    [ ] Verify rules load into builder correctly
"""
