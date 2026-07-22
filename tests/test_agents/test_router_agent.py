"""Tests for RouterAgent."""

import pytest
from app.agents.types.router_agent import RouterAgent
from app.agents.registry import agent_registry
from app.models import Event
from app.extensions import db


@pytest.fixture
def test_user(db_session):
    from app.models import User
    user = User(username='routertest', email='routertest@example.com', password='password123')
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def test_job(db_session, test_user):
    from app.models import Job
    job = Job(
        name='Router Test Agent',
        job_type='router_agent',
        config={
            'routes': [
                {'route': 'high', 'rules': [{'field': 'priority', 'type': 'equals', 'value': 'high'}]},
                {'route': 'low', 'rules': [{'field': 'priority', 'type': 'exists'}]},
            ]
        },
        user_id=test_user.id,
    )
    db_session.add(job)
    db_session.commit()
    return job


def _make_event(test_job, payload):
    return Event(
        agent_id=test_job.id,
        agent_type='router_agent',
        user_id=test_job.user_id,
        payload=payload,
        metadata={},
    )


class TestRouterAgentRegistration:
    def test_registered(self):
        assert agent_registry.get_agent_class('router_agent') is RouterAgent

    def test_capabilities(self, test_job, db_session):
        agent = RouterAgent(
            agent_id=test_job.id,
            config=test_job.config,
            user_id=test_job.user_id,
            db_session=db_session,
        )
        assert agent.can_receive_events is True
        assert agent.can_create_events is True
        assert agent.can_be_scheduled is False


class TestRouterAgentValidation:
    def test_routes_required(self, test_job, db_session):
        with pytest.raises(ValueError, match='routes is required'):
            RouterAgent(
                agent_id=test_job.id, config={},
                user_id=test_job.user_id, db_session=db_session,
            )

    def test_routes_must_be_nonempty(self, test_job, db_session):
        with pytest.raises(ValueError, match='non-empty list'):
            RouterAgent(
                agent_id=test_job.id, config={'routes': []},
                user_id=test_job.user_id, db_session=db_session,
            )

    def test_route_name_required(self, test_job, db_session):
        with pytest.raises(ValueError, match="missing 'route' name"):
            RouterAgent(
                agent_id=test_job.id,
                config={'routes': [{'rules': [{'field': 'x', 'type': 'exists'}]}]},
                user_id=test_job.user_id, db_session=db_session,
            )

    def test_rules_required(self, test_job, db_session):
        with pytest.raises(ValueError, match='must have at least one rule'):
            RouterAgent(
                agent_id=test_job.id,
                config={'routes': [{'route': 'a', 'rules': []}]},
                user_id=test_job.user_id, db_session=db_session,
            )

    def test_invalid_rule_type(self, test_job, db_session):
        with pytest.raises(ValueError, match='invalid type'):
            RouterAgent(
                agent_id=test_job.id,
                config={'routes': [{'route': 'a', 'rules': [
                    {'field': 'x', 'type': 'nonsense', 'value': 'y'}
                ]}]},
                user_id=test_job.user_id, db_session=db_session,
            )


class TestRouterAgentRouting:
    def _make_agent(self, test_job, db_session, routes, default_route='default'):
        return RouterAgent(
            agent_id=test_job.id,
            config={'routes': routes, 'default_route': default_route},
            user_id=test_job.user_id,
            db_session=db_session,
        )

    def test_first_matching_route_wins(self, test_job, db_session):
        agent = self._make_agent(test_job, db_session, [
            {'route': 'urgent', 'rules': [{'field': 'priority', 'type': 'equals', 'value': 'high'}]},
            {'route': 'normal', 'rules': [{'field': 'priority', 'type': 'exists'}]},
        ])
        event = _make_event(test_job, {'priority': 'high'})
        result = agent.check([event])
        assert result[0].event_metadata['_route'] == 'urgent'

    def test_second_route_when_first_no_match(self, test_job, db_session):
        agent = self._make_agent(test_job, db_session, [
            {'route': 'urgent', 'rules': [{'field': 'priority', 'type': 'equals', 'value': 'high'}]},
            {'route': 'normal', 'rules': [{'field': 'priority', 'type': 'exists'}]},
        ])
        event = _make_event(test_job, {'priority': 'low'})
        result = agent.check([event])
        assert result[0].event_metadata['_route'] == 'normal'

    def test_default_route_when_no_match(self, test_job, db_session):
        agent = self._make_agent(test_job, db_session, [
            {'route': 'urgent', 'rules': [{'field': 'priority', 'type': 'equals', 'value': 'critical'}]},
        ], default_route='catch_all')
        event = _make_event(test_job, {'priority': 'low'})
        result = agent.check([event])
        assert result[0].event_metadata['_route'] == 'catch_all'

    def test_numeric_greater_than(self, test_job, db_session):
        agent = self._make_agent(test_job, db_session, [
            {'route': 'big', 'rules': [{'field': 'amount', 'type': 'greater_than', 'value': 100}]},
        ])
        big = _make_event(test_job, {'amount': 150})
        small = _make_event(test_job, {'amount': 50})
        results = agent.check([big, small])
        assert results[0].event_metadata['_route'] == 'big'
        assert results[1].event_metadata['_route'] == 'default'

    def test_regex_route(self, test_job, db_session):
        agent = self._make_agent(test_job, db_session, [
            {'route': 'error', 'rules': [{'field': 'message', 'type': 'regex', 'value': r'error|fail'}]},
        ])
        event = _make_event(test_job, {'message': 'Connection failed'})
        result = agent.check([event])
        assert result[0].event_metadata['_route'] == 'error'

    def test_or_logic_within_route(self, test_job, db_session):
        agent = self._make_agent(test_job, db_session, [
            {
                'route': 'alert',
                'match_all': False,
                'rules': [
                    {'field': 'level', 'type': 'equals', 'value': 'error'},
                    {'field': 'level', 'type': 'equals', 'value': 'critical'},
                ],
            },
        ])
        event = _make_event(test_job, {'level': 'critical'})
        result = agent.check([event])
        assert result[0].event_metadata['_route'] == 'alert'

    def test_all_events_returned(self, test_job, db_session):
        agent = self._make_agent(test_job, db_session, [
            {'route': 'tagged', 'rules': [{'field': 'x', 'type': 'exists'}]},
        ])
        events = [_make_event(test_job, {'x': i}) for i in range(5)]
        result = agent.check(events)
        assert len(result) == 5
        assert all(e.event_metadata['_route'] == 'tagged' for e in result)

    def test_missing_field_routes_to_default(self, test_job, db_session):
        agent = self._make_agent(test_job, db_session, [
            {'route': 'has_title', 'rules': [{'field': 'title', 'type': 'exists'}]},
        ], default_route='no_title')
        event = _make_event(test_job, {'other': 'value'})
        result = agent.check([event])
        assert result[0].event_metadata['_route'] == 'no_title'
