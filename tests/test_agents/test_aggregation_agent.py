"""
Test suite for AggregationAgent

Covers configuration validation, window closure logic, all aggregation modes,
state persistence, memory safety, and edge cases.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from app.agents.types.aggregation_agent import AggregationAgent
from app.models import Event


@pytest.fixture
def test_user(db_session):
    """Create a test user."""
    from app.models import User
    user = User(username='testuser', email='test@example.com', password='password123')
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def test_job(db_session, test_user):
    """Create a test job for event creation."""
    from app.models import Job
    job = Job(
        name='Test Agent',
        job_type='aggregation_agent',
        config={
            'window_size': 10,
            'window_duration_seconds': 300,
            'aggregation_mode': 'simple'
        },
        user_id=test_user.id,
        is_active=True
    )
    db_session.add(job)
    db_session.commit()
    return job


@pytest.fixture
def sample_events(test_job, db_session):
    """Create sample events for testing."""
    events = []
    for i in range(5):
        event = Event(
            agent_id=test_job.id,
            agent_type='test_agent',
            user_id=test_job.user_id,
            payload={
                'title': f'Event {i + 1}',
                'price': 10.0 + i,
                'quantity': i + 1,
                'category': 'electronics' if i < 3 else 'books'
            },
            metadata={'source': 'test'}
        )
        db_session.add(event)
        events.append(event)
    db_session.commit()
    return events


# ============================================================================
# Configuration Validation Tests
# ============================================================================

def test_config_missing_window_size(db_session):
    """Test validation fails when window_size is missing."""
    config = {
        'window_duration_seconds': 300,
        'aggregation_mode': 'simple'
    }

    with pytest.raises(ValueError, match="'window_size' is required"):
        AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)


def test_config_invalid_window_size_type(db_session):
    """Test validation fails when window_size is not an integer."""
    config = {
        'window_size': '10',
        'window_duration_seconds': 300,
        'aggregation_mode': 'simple'
    }

    with pytest.raises(ValueError, match="'window_size' must be an integer"):
        AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)


def test_config_invalid_window_size_value(db_session):
    """Test validation fails when window_size is <= 0."""
    config = {
        'window_size': 0,
        'window_duration_seconds': 300,
        'aggregation_mode': 'simple'
    }

    with pytest.raises(ValueError, match="'window_size' must be greater than 0"):
        AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)


def test_config_missing_window_duration(db_session):
    """Test validation fails when window_duration_seconds is missing."""
    config = {
        'window_size': 10,
        'aggregation_mode': 'simple'
    }

    with pytest.raises(ValueError, match="'window_duration_seconds' is required"):
        AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)


def test_config_invalid_window_duration_type(db_session):
    """Test validation fails when window_duration_seconds is not numeric."""
    config = {
        'window_size': 10,
        'window_duration_seconds': '300',
        'aggregation_mode': 'simple'
    }

    with pytest.raises(ValueError, match="'window_duration_seconds' must be a number"):
        AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)


def test_config_invalid_window_duration_value(db_session):
    """Test validation fails when window_duration_seconds is <= 0."""
    config = {
        'window_size': 10,
        'window_duration_seconds': -1,
        'aggregation_mode': 'simple'
    }

    with pytest.raises(ValueError, match="'window_duration_seconds' must be greater than 0"):
        AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)


def test_config_missing_aggregation_mode(db_session):
    """Test validation fails when aggregation_mode is missing."""
    config = {
        'window_size': 10,
        'window_duration_seconds': 300
    }

    with pytest.raises(ValueError, match="'aggregation_mode' is required"):
        AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)


def test_config_invalid_aggregation_mode(db_session):
    """Test validation fails when aggregation_mode is invalid."""
    config = {
        'window_size': 10,
        'window_duration_seconds': 300,
        'aggregation_mode': 'invalid_mode'
    }

    with pytest.raises(ValueError, match="'aggregation_mode' must be one of"):
        AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)


def test_config_statistics_mode_missing_config(db_session):
    """Test validation fails when statistics mode lacks statistics_config."""
    config = {
        'window_size': 10,
        'window_duration_seconds': 300,
        'aggregation_mode': 'statistics'
    }

    with pytest.raises(ValueError, match="'statistics_config' is required"):
        AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)


def test_config_statistics_invalid_fields_type(db_session):
    """Test validation fails when statistics fields is not a list."""
    config = {
        'window_size': 10,
        'window_duration_seconds': 300,
        'aggregation_mode': 'statistics',
        'statistics_config': {
            'fields': 'price',
            'operations': ['sum']
        }
    }

    with pytest.raises(ValueError, match="'statistics_config.fields' must be a list"):
        AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)


def test_config_statistics_empty_fields(db_session):
    """Test validation fails when statistics fields is empty."""
    config = {
        'window_size': 10,
        'window_duration_seconds': 300,
        'aggregation_mode': 'statistics',
        'statistics_config': {
            'fields': [],
            'operations': ['sum']
        }
    }

    with pytest.raises(ValueError, match="'statistics_config.fields' must contain at least one field"):
        AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)


def test_config_statistics_invalid_operations_type(db_session):
    """Test validation fails when operations is not a list."""
    config = {
        'window_size': 10,
        'window_duration_seconds': 300,
        'aggregation_mode': 'statistics',
        'statistics_config': {
            'fields': ['price'],
            'operations': 'sum'
        }
    }

    with pytest.raises(ValueError, match="'statistics_config.operations' must be a list"):
        AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)


def test_config_statistics_invalid_operation(db_session):
    """Test validation fails when operation is invalid."""
    config = {
        'window_size': 10,
        'window_duration_seconds': 300,
        'aggregation_mode': 'statistics',
        'statistics_config': {
            'fields': ['price'],
            'operations': ['sum', 'invalid_op']
        }
    }

    with pytest.raises(ValueError, match="Invalid operation 'invalid_op'"):
        AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)


def test_config_group_by_missing_field(db_session):
    """Test validation fails when group_by mode lacks group_by_field."""
    config = {
        'window_size': 10,
        'window_duration_seconds': 300,
        'aggregation_mode': 'group_by'
    }

    with pytest.raises(ValueError, match="'group_by_field' is required"):
        AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)


def test_config_valid_simple_mode(db_session):
    """Test validation passes for valid simple mode config."""
    config = {
        'window_size': 10,
        'window_duration_seconds': 300,
        'aggregation_mode': 'simple'
    }

    agent = AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)
    assert agent.agent_type == 'aggregation_agent'
    assert agent.aggregation_mode == 'simple'


def test_config_valid_statistics_mode(db_session):
    """Test validation passes for valid statistics mode config."""
    config = {
        'window_size': 10,
        'window_duration_seconds': 300,
        'aggregation_mode': 'statistics',
        'statistics_config': {
            'fields': ['price', 'quantity'],
            'operations': ['sum', 'avg', 'min', 'max', 'count']
        }
    }

    agent = AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)
    assert agent.aggregation_mode == 'statistics'


# ============================================================================
# Window Closure Tests - Count Threshold
# ============================================================================

def test_window_closes_on_count_threshold(db_session, sample_events):
    """Test window closes when exactly window_size events are added."""
    config = {
        'window_size': 5,
        'window_duration_seconds': 3600,  # 1 hour (won't trigger)
        'aggregation_mode': 'simple'
    }

    agent = AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)

    # Process 5 events (exactly window_size)
    result = agent.process(sample_events)

    # Should emit aggregated event
    assert len(result) == 1
    assert result[0].payload['event_count'] == 5
    assert 'count_threshold_5' in result[0].payload['_aggregation']['close_reason']


def test_window_does_not_close_below_count_threshold(db_session, sample_events):
    """Test window does not close when events < window_size."""
    config = {
        'window_size': 10,  # More than sample events
        'window_duration_seconds': 3600,
        'aggregation_mode': 'simple'
    }

    agent = AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)

    # Process 5 events (less than window_size)
    result = agent.process(sample_events)

    # Should not emit (window still open)
    assert len(result) == 0


def test_window_accumulates_across_multiple_calls(db_session, sample_events):
    """Test window accumulates events across multiple process() calls."""
    config = {
        'window_size': 10,
        'window_duration_seconds': 3600,
        'aggregation_mode': 'simple'
    }

    agent = AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)

    # Process 3 events
    result1 = agent.process(sample_events[:3])
    assert len(result1) == 0  # Window still open

    # Process 2 more events (total 5)
    result2 = agent.process(sample_events[3:5])
    assert len(result2) == 0  # Still below threshold

    # Process 5 more events (total 10, reaches threshold)
    result3 = agent.process(sample_events)
    assert len(result3) == 1
    assert result3[0].payload['event_count'] == 10


# ============================================================================
# Window Closure Tests - Time Threshold
# ============================================================================

def test_window_closes_on_time_threshold(db_session, sample_events):
    """Test window closes when time threshold is reached."""
    config = {
        'window_size': 100,  # Won't trigger
        'window_duration_seconds': 1,  # 1 second
        'aggregation_mode': 'simple'
    }

    agent = AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)

    # Process some events
    result1 = agent.process(sample_events[:2])
    assert len(result1) == 0  # Window still open

    # Wait for time threshold
    import time
    time.sleep(1.1)

    # Process more events (should trigger time-based closure)
    result2 = agent.process(sample_events[2:3])

    # Should emit aggregated event for first 2 events
    assert len(result2) == 1
    assert result2[0].payload['event_count'] == 2
    assert 'time_threshold_1s' in result2[0].payload['_aggregation']['close_reason']


def test_window_closes_on_time_before_count(db_session, sample_events):
    """Test window closes on time threshold before reaching count threshold."""
    config = {
        'window_size': 100,  # High count
        'window_duration_seconds': 1,  # Short time
        'aggregation_mode': 'collect_all'
    }

    agent = AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)

    # Process 3 events
    agent.process(sample_events[:3])

    # Wait for time threshold
    import time
    time.sleep(1.1)

    # Process 1 more event (triggers time-based closure)
    result = agent.process(sample_events[3:4])

    # Should emit with only first 3 events (time closed before count)
    assert len(result) == 1
    assert result[0].payload['event_count'] == 3
    assert len(result[0].payload['events']) == 3


# ============================================================================
# Window Closure Tests - Combined Thresholds
# ============================================================================

def test_window_closes_on_count_before_time(db_session, sample_events):
    """Test window closes on count threshold before time threshold."""
    config = {
        'window_size': 3,  # Low count
        'window_duration_seconds': 3600,  # High time
        'aggregation_mode': 'simple'
    }

    agent = AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)

    # Process 3 events (reaches count threshold)
    result = agent.process(sample_events[:3])

    # Should emit immediately (count threshold reached)
    assert len(result) == 1
    assert 'count_threshold_3' in result[0].payload['_aggregation']['close_reason']


# ============================================================================
# Empty Window Tests
# ============================================================================

def test_empty_window_not_emitted(db_session):
    """Test empty window is not emitted when time threshold reached."""
    config = {
        'window_size': 10,
        'window_duration_seconds': 1,
        'aggregation_mode': 'simple'
    }

    agent = AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)

    # Initialize window but don't add events
    agent.process([])

    # Wait for time threshold
    import time
    time.sleep(1.1)

    # Try to close window
    result = agent.process([])

    # Should not emit (empty window)
    assert len(result) == 0


# ============================================================================
# Aggregation Mode Tests - Simple
# ============================================================================

def test_simple_mode_output(db_session, sample_events):
    """Test simple mode produces correct minimal output."""
    config = {
        'window_size': 5,
        'window_duration_seconds': 3600,
        'aggregation_mode': 'simple'
    }

    agent = AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)
    result = agent.process(sample_events)

    assert len(result) == 1
    payload = result[0].payload

    # Check required fields
    assert payload['event_count'] == 5
    assert 'window_start' in payload
    assert '_aggregation' in payload
    assert payload['_aggregation']['mode'] == 'simple'
    assert payload['_aggregation']['event_count'] == 5


# ============================================================================
# Aggregation Mode Tests - Collect All
# ============================================================================

def test_collect_all_mode_output(db_session, sample_events):
    """Test collect_all mode bundles all event payloads."""
    config = {
        'window_size': 5,
        'window_duration_seconds': 3600,
        'aggregation_mode': 'collect_all'
    }

    agent = AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)
    result = agent.process(sample_events)

    assert len(result) == 1
    payload = result[0].payload

    # Check events array
    assert 'events' in payload
    assert len(payload['events']) == 5
    assert payload['event_count'] == 5

    # Verify event contents
    assert payload['events'][0]['title'] == 'Event 1'
    assert payload['events'][1]['price'] == 11.0


def test_collect_all_with_metadata(db_session, sample_events):
    """Test collect_all mode includes metadata when configured."""
    config = {
        'window_size': 5,
        'window_duration_seconds': 3600,
        'aggregation_mode': 'collect_all',
        'include_metadata': True
    }

    agent = AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)
    result = agent.process(sample_events)

    assert len(result) == 1
    payload = result[0].payload

    # Check metadata included
    assert 'metadata_list' in payload
    assert len(payload['metadata_list']) == 5


# ============================================================================
# Aggregation Mode Tests - Statistics
# ============================================================================

def test_statistics_mode_sum(db_session, sample_events):
    """Test statistics mode calculates sum correctly."""
    config = {
        'window_size': 5,
        'window_duration_seconds': 3600,
        'aggregation_mode': 'statistics',
        'statistics_config': {
            'fields': ['price'],
            'operations': ['sum']
        }
    }

    agent = AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)
    result = agent.process(sample_events)

    assert len(result) == 1
    stats = result[0].payload['statistics']

    # prices: 10, 11, 12, 13, 14 -> sum = 60
    assert stats['price']['sum'] == 60.0


def test_statistics_mode_avg(db_session, sample_events):
    """Test statistics mode calculates average correctly."""
    config = {
        'window_size': 5,
        'window_duration_seconds': 3600,
        'aggregation_mode': 'statistics',
        'statistics_config': {
            'fields': ['price'],
            'operations': ['avg']
        }
    }

    agent = AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)
    result = agent.process(sample_events)

    stats = result[0].payload['statistics']

    # prices: 10, 11, 12, 13, 14 -> avg = 12.0
    assert stats['price']['avg'] == 12.0


def test_statistics_mode_min_max(db_session, sample_events):
    """Test statistics mode calculates min and max correctly."""
    config = {
        'window_size': 5,
        'window_duration_seconds': 3600,
        'aggregation_mode': 'statistics',
        'statistics_config': {
            'fields': ['quantity'],
            'operations': ['min', 'max']
        }
    }

    agent = AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)
    result = agent.process(sample_events)

    stats = result[0].payload['statistics']

    # quantities: 1, 2, 3, 4, 5
    assert stats['quantity']['min'] == 1.0
    assert stats['quantity']['max'] == 5.0


def test_statistics_mode_count(db_session, sample_events):
    """Test statistics mode calculates count correctly."""
    config = {
        'window_size': 5,
        'window_duration_seconds': 3600,
        'aggregation_mode': 'statistics',
        'statistics_config': {
            'fields': ['price'],
            'operations': ['count']
        }
    }

    agent = AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)
    result = agent.process(sample_events)

    stats = result[0].payload['statistics']
    assert stats['price']['count'] == 5


def test_statistics_mode_multiple_fields(db_session, sample_events):
    """Test statistics mode handles multiple fields."""
    config = {
        'window_size': 5,
        'window_duration_seconds': 3600,
        'aggregation_mode': 'statistics',
        'statistics_config': {
            'fields': ['price', 'quantity'],
            'operations': ['sum', 'avg']
        }
    }

    agent = AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)
    result = agent.process(sample_events)

    stats = result[0].payload['statistics']

    # Check both fields present
    assert 'price' in stats
    assert 'quantity' in stats

    # Check price stats
    assert stats['price']['sum'] == 60.0
    assert stats['price']['avg'] == 12.0

    # Check quantity stats (1+2+3+4+5 = 15, avg = 3.0)
    assert stats['quantity']['sum'] == 15.0
    assert stats['quantity']['avg'] == 3.0


def test_statistics_mode_all_operations(db_session, sample_events):
    """Test statistics mode with all operations."""
    config = {
        'window_size': 5,
        'window_duration_seconds': 3600,
        'aggregation_mode': 'statistics',
        'statistics_config': {
            'fields': ['price'],
            'operations': ['sum', 'avg', 'min', 'max', 'count']
        }
    }

    agent = AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)
    result = agent.process(sample_events)

    stats = result[0].payload['statistics']['price']

    assert stats['sum'] == 60.0
    assert stats['avg'] == 12.0
    assert stats['min'] == 10.0
    assert stats['max'] == 14.0
    assert stats['count'] == 5


# ============================================================================
# Aggregation Mode Tests - Group By
# ============================================================================

def test_group_by_mode_basic(db_session, sample_events):
    """Test group_by mode groups events correctly."""
    config = {
        'window_size': 5,
        'window_duration_seconds': 3600,
        'aggregation_mode': 'group_by',
        'group_by_field': 'category'
    }

    agent = AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)
    result = agent.process(sample_events)

    assert len(result) == 1
    payload = result[0].payload

    # Check groups
    assert 'groups' in payload
    assert 'electronics' in payload['groups']
    assert 'books' in payload['groups']

    # Check group counts (first 3 are electronics, last 2 are books)
    assert payload['groups']['electronics']['event_count'] == 3
    assert payload['groups']['books']['event_count'] == 2

    # Check totals
    assert payload['total_event_count'] == 5
    assert payload['group_count'] == 2
    assert payload['group_by_field'] == 'category'


def test_group_by_mode_with_statistics(db_session, sample_events):
    """Test group_by mode with per-group statistics."""
    config = {
        'window_size': 5,
        'window_duration_seconds': 3600,
        'aggregation_mode': 'group_by',
        'group_by_field': 'category',
        'statistics_config': {
            'fields': ['price'],
            'operations': ['sum', 'avg']
        }
    }

    agent = AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)
    result = agent.process(sample_events)

    payload = result[0].payload

    # Check electronics group statistics (prices: 10, 11, 12)
    electronics_stats = payload['groups']['electronics']['statistics']['price']
    assert electronics_stats['sum'] == 33.0  # 10 + 11 + 12
    assert electronics_stats['avg'] == 11.0  # 33 / 3

    # Check books group statistics (prices: 13, 14)
    books_stats = payload['groups']['books']['statistics']['price']
    assert books_stats['sum'] == 27.0  # 13 + 14
    assert books_stats['avg'] == 13.5  # 27 / 2


def test_group_by_mode_events_included(db_session, sample_events):
    """Test group_by mode includes events in each group."""
    config = {
        'window_size': 5,
        'window_duration_seconds': 3600,
        'aggregation_mode': 'group_by',
        'group_by_field': 'category'
    }

    agent = AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)
    result = agent.process(sample_events)

    payload = result[0].payload

    # Check electronics group events
    electronics_events = payload['groups']['electronics']['events']
    assert len(electronics_events) == 3
    assert electronics_events[0]['title'] == 'Event 1'

    # Check books group events
    books_events = payload['groups']['books']['events']
    assert len(books_events) == 2
    assert books_events[0]['title'] == 'Event 4'


def test_group_by_missing_field(db_session, test_job):
    """Test group_by handles events missing the group field."""
    config = {
        'window_size': 3,
        'window_duration_seconds': 3600,
        'aggregation_mode': 'group_by',
        'group_by_field': 'category'
    }

    # Create events with missing category field
    events = [
        Event(agent_id=test_job.id, agent_type='test', user_id=test_job.user_id,
              payload={'title': 'Event 1', 'category': 'electronics'},
              metadata={}),
        Event(agent_id=test_job.id, agent_type='test', user_id=test_job.user_id,
              payload={'title': 'Event 2'},  # Missing category
              metadata={}),
        Event(agent_id=test_job.id, agent_type='test', user_id=test_job.user_id,
              payload={'title': 'Event 3', 'category': 'books'},
              metadata={})
    ]

    agent = AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)
    result = agent.process(events)

    payload = result[0].payload

    # Check that __null__ group exists for missing field
    assert '__null__' in payload['groups']
    assert payload['groups']['__null__']['event_count'] == 1
    assert payload['group_count'] == 3  # electronics, books, __null__


def test_group_by_nested_field(db_session, test_job):
    """Test group_by with nested field path (dot notation)."""
    config = {
        'window_size': 3,
        'window_duration_seconds': 3600,
        'aggregation_mode': 'group_by',
        'group_by_field': 'user.role'
    }

    # Create events with nested structure
    events = [
        Event(agent_id=test_job.id, agent_type='test', user_id=test_job.user_id,
              payload={'title': 'Event 1', 'user': {'role': 'admin'}},
              metadata={}),
        Event(agent_id=test_job.id, agent_type='test', user_id=test_job.user_id,
              payload={'title': 'Event 2', 'user': {'role': 'user'}},
              metadata={}),
        Event(agent_id=test_job.id, agent_type='test', user_id=test_job.user_id,
              payload={'title': 'Event 3', 'user': {'role': 'admin'}},
              metadata={})
    ]

    agent = AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)
    result = agent.process(events)

    payload = result[0].payload

    # Check groups by nested field
    assert 'admin' in payload['groups']
    assert 'user' in payload['groups']
    assert payload['groups']['admin']['event_count'] == 2
    assert payload['groups']['user']['event_count'] == 1


# ============================================================================
# State Persistence Tests
# ============================================================================

def test_state_persists_across_calls(db_session, sample_events):
    """Test window state persists across multiple process() calls."""
    config = {
        'window_size': 10,
        'window_duration_seconds': 3600,
        'aggregation_mode': 'simple'
    }

    agent = AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)

    # Add 3 events
    result1 = agent.process(sample_events[:3])
    assert len(result1) == 0

    # Verify state persisted
    state = agent._get_window_state()
    assert state['event_count'] == 3
    assert len(state['events']) == 3

    # Add 2 more events
    result2 = agent.process(sample_events[3:5])
    assert len(result2) == 0

    # Verify state updated
    state = agent._get_window_state()
    assert state['event_count'] == 5
    assert len(state['events']) == 5


def test_window_resets_after_emission(db_session, sample_events):
    """Test window state is reset after emission."""
    config = {
        'window_size': 3,
        'window_duration_seconds': 3600,
        'aggregation_mode': 'simple'
    }

    agent = AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)

    # Trigger emission with 3 events
    result1 = agent.process(sample_events[:3])
    assert len(result1) == 1

    # Check state is reset
    state = agent._get_window_state()
    assert state['event_count'] == 0
    assert len(state['events']) == 0

    # New window should start fresh
    result2 = agent.process(sample_events[3:5])
    assert len(result2) == 0

    state = agent._get_window_state()
    assert state['event_count'] == 2


# ============================================================================
# Memory Safety Tests
# ============================================================================

def test_max_window_size_enforcement(db_session, test_job):
    """Test FIFO eviction when max_window_size is exceeded."""
    config = {
        'window_size': 100,  # High threshold (won't trigger with 10 events)
        'window_duration_seconds': 3600,
        'aggregation_mode': 'collect_all',
        'max_window_size': 5  # Low limit (will trigger FIFO eviction before window closes)
    }

    # Create 10 events
    events = []
    for i in range(10):
        event = Event(
            agent_id=test_job.id,
            agent_type='test',
            user_id=test_job.user_id,
            payload={'index': i},
            metadata={}
        )
        events.append(event)

    agent = AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)

    # Add 10 events (should be limited to 5)
    agent.process(events)

    # Check state
    state = agent._get_window_state()
    assert state['event_count'] == 10  # Count is accurate
    assert len(state['events']) == 5  # Events limited to max_window_size

    # Check FIFO: oldest events evicted, keeping last 5
    assert state['events'][0]['index'] == 5
    assert state['events'][4]['index'] == 9


# ============================================================================
# Edge Case Tests
# ============================================================================

def test_non_numeric_statistics(db_session, test_job):
    """Test statistics gracefully handles non-numeric values."""
    config = {
        'window_size': 3,
        'window_duration_seconds': 3600,
        'aggregation_mode': 'statistics',
        'statistics_config': {
            'fields': ['value'],
            'operations': ['sum', 'avg']
        }
    }

    # Create events with non-numeric values
    events = [
        Event(agent_id=test_job.id, agent_type='test', user_id=test_job.user_id,
              payload={'value': 10},
              metadata={}),
        Event(agent_id=test_job.id, agent_type='test', user_id=test_job.user_id,
              payload={'value': 'not a number'},
              metadata={}),
        Event(agent_id=test_job.id, agent_type='test', user_id=test_job.user_id,
              payload={'value': 20},
              metadata={})
    ]

    agent = AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)
    result = agent.process(events)

    stats = result[0].payload['statistics']['value']

    # Should only use numeric values (10, 20)
    assert stats['sum'] == 30.0
    assert stats['avg'] == 15.0


def test_statistics_all_non_numeric(db_session, test_job):
    """Test statistics when all values are non-numeric."""
    config = {
        'window_size': 2,
        'window_duration_seconds': 3600,
        'aggregation_mode': 'statistics',
        'statistics_config': {
            'fields': ['value'],
            'operations': ['sum', 'avg']
        }
    }

    # Create events with all non-numeric values
    events = [
        Event(agent_id=test_job.id, agent_type='test', user_id=test_job.user_id,
              payload={'value': 'text'},
              metadata={}),
        Event(agent_id=test_job.id, agent_type='test', user_id=test_job.user_id,
              payload={'value': 'more text'},
              metadata={})
    ]

    agent = AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)
    result = agent.process(events)

    stats = result[0].payload['statistics']['value']

    # Should be None when no numeric values
    assert stats['sum'] is None
    assert stats['avg'] is None


def test_missing_statistics_field(db_session, test_job):
    """Test statistics when configured field is missing from events."""
    config = {
        'window_size': 2,
        'window_duration_seconds': 3600,
        'aggregation_mode': 'statistics',
        'statistics_config': {
            'fields': ['nonexistent_field'],
            'operations': ['sum', 'count']
        }
    }

    events = [
        Event(agent_id=test_job.id, agent_type='test', user_id=test_job.user_id,
              payload={'other_field': 10},
              metadata={}),
        Event(agent_id=test_job.id, agent_type='test', user_id=test_job.user_id,
              payload={'other_field': 20},
              metadata={})
    ]

    agent = AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)
    result = agent.process(events)

    stats = result[0].payload['statistics']['nonexistent_field']

    # Should be None/0 when field doesn't exist
    assert stats['sum'] is None
    assert stats['count'] == 0


def test_empty_events_list(db_session):
    """Test processing empty events list."""
    config = {
        'window_size': 10,
        'window_duration_seconds': 3600,
        'aggregation_mode': 'simple'
    }

    agent = AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)

    # Process empty list
    result = agent.process([])

    # Should return empty (no events added)
    assert len(result) == 0


def test_metadata_aggregation_output(db_session, sample_events):
    """Test _aggregation metadata is correctly added to output."""
    config = {
        'window_size': 5,
        'window_duration_seconds': 3600,
        'aggregation_mode': 'simple'
    }

    agent = AggregationAgent(agent_id=1, config=config, user_id=1, db_session=db_session)
    result = agent.process(sample_events)

    aggregation_meta = result[0].payload['_aggregation']

    # Check required metadata fields
    assert aggregation_meta['mode'] == 'simple'
    assert aggregation_meta['event_count'] == 5
    assert 'window_start' in aggregation_meta
    assert 'window_end' in aggregation_meta
    assert 'close_reason' in aggregation_meta
    assert 'count_threshold_5' in aggregation_meta['close_reason']


# ============================================================================
# Config Schema Tests
# ============================================================================

def test_get_config_schema():
    """Test get_config_schema returns valid schema."""
    schema = AggregationAgent.get_config_schema()

    # Check schema structure
    assert 'required_fields' in schema
    assert 'optional_fields' in schema

    # Check that required_fields is a list
    assert isinstance(schema['required_fields'], list)

    # Check required field names
    if schema['required_fields']:
        required_names = [f['name'] if isinstance(f, dict) else f for f in schema['required_fields']]
        assert 'window_size' in required_names
        assert 'window_duration_seconds' in required_names
        assert 'aggregation_mode' in required_names

    # Check optional fields
    optional_names = [f['name'] for f in schema['optional_fields']]
    assert 'max_window_size' in optional_names
    assert 'include_metadata' in optional_names
