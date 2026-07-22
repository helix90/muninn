"""Tests for DataStoreWriteAgent and DataStoreReadAgent."""

import pytest
from unittest.mock import patch

from app.agents.types.datastore_write_agent import DataStoreWriteAgent
from app.agents.types.datastore_read_agent import DataStoreReadAgent
from app.agents.registry import agent_registry
from app.models import Event, DataStore
from app.extensions import db


@pytest.fixture
def test_user(db_session):
    from app.models import User
    user = User(username='dstest', email='dstest@example.com', password='password123')
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def test_job(db_session, test_user):
    from app.models import Job
    job = Job(
        name='DataStore Test Agent',
        job_type='rss_agent',
        config={'feed_url': 'https://example.com/feed'},
        user_id=test_user.id,
    )
    db_session.add(job)
    db_session.commit()
    return job


def _event(test_job, payload):
    return Event(
        agent_id=test_job.id,
        agent_type='rss_agent',
        user_id=test_job.user_id,
        payload=payload,
        metadata={},
    )


# ──────────────────────────────────────────────────────────────────────────────
# DataStoreWriteAgent
# ──────────────────────────────────────────────────────────────────────────────

class TestDataStoreWriteRegistration:
    def test_registered(self):
        assert agent_registry.get_agent_class('datastore_write_agent') is DataStoreWriteAgent

    def test_capabilities(self, test_job, db_session):
        agent = DataStoreWriteAgent(
            agent_id=test_job.id,
            config={'namespace': 'ns', 'key_template': 'k', 'value_template': 'v'},
            user_id=test_job.user_id,
            db_session=db_session,
        )
        assert agent.can_receive_events is True
        assert agent.can_create_events is False


class TestDataStoreWriteValidation:
    def test_namespace_required(self, test_job, db_session):
        with pytest.raises(ValueError, match='namespace is required'):
            DataStoreWriteAgent(
                agent_id=test_job.id,
                config={'key_template': 'k', 'value_template': 'v'},
                user_id=test_job.user_id,
                db_session=db_session,
            )

    def test_key_template_required(self, test_job, db_session):
        with pytest.raises(ValueError, match='key_template is required'):
            DataStoreWriteAgent(
                agent_id=test_job.id,
                config={'namespace': 'ns', 'value_template': 'v'},
                user_id=test_job.user_id,
                db_session=db_session,
            )

    def test_value_template_required(self, test_job, db_session):
        with pytest.raises(ValueError, match='value_template is required'):
            DataStoreWriteAgent(
                agent_id=test_job.id,
                config={'namespace': 'ns', 'key_template': 'k'},
                user_id=test_job.user_id,
                db_session=db_session,
            )

    def test_invalid_key_template_syntax(self, test_job, db_session):
        with pytest.raises(ValueError, match='Invalid key_template syntax'):
            DataStoreWriteAgent(
                agent_id=test_job.id,
                config={'namespace': 'ns', 'key_template': '{{ bad', 'value_template': 'v'},
                user_id=test_job.user_id,
                db_session=db_session,
            )


class TestDataStoreWriteAct:
    def test_writes_key_value(self, test_job, db_session, test_user):
        agent = DataStoreWriteAgent(
            agent_id=test_job.id,
            config={
                'namespace': 'prices',
                'key_template': '{{ ticker }}',
                'value_template': '{{ price }}',
            },
            user_id=test_user.id,
            db_session=db_session,
        )
        event = _event(test_job, {'ticker': 'AAPL', 'price': '185.50'})
        result = agent.check([event])
        assert result == []

        entry = db_session.query(DataStore).filter_by(
            user_id=test_user.id, namespace='prices', key='AAPL'
        ).first()
        assert entry is not None
        assert entry.value == '185.50'

    def test_overwrites_existing_key(self, test_job, db_session, test_user):
        config = {
            'namespace': 'scores',
            'key_template': 'player_{{ id }}',
            'value_template': '{{ score }}',
        }
        agent = DataStoreWriteAgent(
            agent_id=test_job.id, config=config,
            user_id=test_user.id, db_session=db_session,
        )
        agent.check([_event(test_job, {'id': '1', 'score': '100'})])
        agent.check([_event(test_job, {'id': '1', 'score': '200'})])

        entries = db_session.query(DataStore).filter_by(
            user_id=test_user.id, namespace='scores', key='player_1'
        ).all()
        assert len(entries) == 1
        assert entries[0].value == '200'

    def test_skips_empty_key(self, test_job, db_session, test_user):
        agent = DataStoreWriteAgent(
            agent_id=test_job.id,
            config={'namespace': 'ns', 'key_template': '   ', 'value_template': 'v'},
            user_id=test_user.id,
            db_session=db_session,
        )
        agent.check([_event(test_job, {})])
        count = db_session.query(DataStore).filter_by(user_id=test_user.id).count()
        assert count == 0


# ──────────────────────────────────────────────────────────────────────────────
# DataStoreReadAgent
# ──────────────────────────────────────────────────────────────────────────────

class TestDataStoreReadRegistration:
    def test_registered(self):
        assert agent_registry.get_agent_class('datastore_read_agent') is DataStoreReadAgent

    def test_capabilities(self, test_job, db_session):
        agent = DataStoreReadAgent(
            agent_id=test_job.id,
            config={'namespace': 'ns'},
            user_id=test_job.user_id,
            db_session=db_session,
        )
        assert agent.can_be_scheduled is True
        assert agent.can_create_events is True
        assert agent.can_receive_events is False


class TestDataStoreReadValidation:
    def test_namespace_required(self, test_job, db_session):
        with pytest.raises(ValueError, match='namespace is required'):
            DataStoreReadAgent(
                agent_id=test_job.id, config={},
                user_id=test_job.user_id, db_session=db_session,
            )


class TestDataStoreReadFetch:
    def _seed(self, db_session, user_id, namespace, entries):
        from datetime import datetime
        for key, value in entries.items():
            row = DataStore(
                user_id=user_id, namespace=namespace, key=key, value=value,
            )
            row.created_at = datetime.utcnow()
            row.updated_at = datetime.utcnow()
            db_session.add(row)
        db_session.commit()

    def test_emits_one_event_per_entry(self, test_job, db_session, test_user):
        self._seed(db_session, test_user.id, 'prices', {'AAPL': 185, 'GOOG': 140})
        agent = DataStoreReadAgent(
            agent_id=test_job.id,
            config={'namespace': 'prices'},
            user_id=test_user.id,
            db_session=db_session,
        )
        events = agent.check([])
        assert len(events) == 2
        keys = {e.payload['key'] for e in events}
        assert keys == {'AAPL', 'GOOG'}

    def test_filters_by_key(self, test_job, db_session, test_user):
        self._seed(db_session, test_user.id, 'prices', {'AAPL': 185, 'GOOG': 140})
        agent = DataStoreReadAgent(
            agent_id=test_job.id,
            config={'namespace': 'prices', 'key': 'AAPL'},
            user_id=test_user.id,
            db_session=db_session,
        )
        events = agent.check([])
        assert len(events) == 1
        assert events[0].payload['key'] == 'AAPL'
        assert events[0].payload['value'] == 185

    def test_custom_emit_field(self, test_job, db_session, test_user):
        self._seed(db_session, test_user.id, 'cfg', {'threshold': 42})
        agent = DataStoreReadAgent(
            agent_id=test_job.id,
            config={'namespace': 'cfg', 'emit_field': 'data'},
            user_id=test_user.id,
            db_session=db_session,
        )
        events = agent.check([])
        assert 'data' in events[0].payload
        assert events[0].payload['data'] == 42

    def test_empty_namespace_returns_no_events(self, test_job, db_session, test_user):
        agent = DataStoreReadAgent(
            agent_id=test_job.id,
            config={'namespace': 'empty_ns'},
            user_id=test_user.id,
            db_session=db_session,
        )
        events = agent.check([])
        assert events == []

    def test_user_isolation(self, test_job, db_session, test_user):
        """A user cannot read another user's DataStore entries."""
        from app.models import User
        other = User(username='other_ds', email='other_ds@example.com', password='password123')
        db_session.add(other)
        db_session.flush()
        self._seed(db_session, other.id, 'secrets', {'key1': 'value1'})

        agent = DataStoreReadAgent(
            agent_id=test_job.id,
            config={'namespace': 'secrets'},
            user_id=test_user.id,
            db_session=db_session,
        )
        events = agent.check([])
        assert events == []
