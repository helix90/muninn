"""
Ephemeral agent test runner.

Executes an agent with a user-supplied payload without persisting any output
to the database. Uses a dedicated SQLAlchemy session that is always rolled
back after the test completes.

Side-effect note: agents that call session.commit() internally during their
process() method (e.g. deduplication_agent updating AgentMemory,
datastore_write_agent writing a value) will commit those changes to the DB.
The most common transform agents (filter, template, router) have no such
side effects. The suppression of _cleanup_old_events() prevents accidental
deletion of existing events during a test run.
"""

import time
from typing import Any, Dict

from app.agents.registry import agent_registry
from app.models import Event
from app.services.credential_service import CredentialService


def run_agent_test(agent_model, payload_dict: Dict[str, Any], db_session) -> Dict[str, Any]:
    """
    Run *agent_model* with *payload_dict* as the test event payload.

    Returns a result dict:
      {
        'status':         'ok' | 'error',
        'agent_category': 'source' | 'transform' | 'action',
        'output_events':  [{'payload': {...}, 'event_metadata': {...}}, ...],
        'output_count':   int,
        'filtered':       bool,   # True when transform produced 0 events from 1 input
        'duration_ms':    int,
        'error':          str,    # only on status='error'
      }
    """
    from app.agents.base import ActionAgent, SourceAgent
    from app.extensions import db
    from sqlalchemy.orm import Session

    # Determine agent category from class hierarchy
    try:
        agent_class = agent_registry.get_agent_class(agent_model.job_type)
    except ValueError as exc:
        return {'status': 'error', 'error': str(exc), 'agent_category': 'unknown'}

    if issubclass(agent_class, SourceAgent):
        agent_category = 'source'
    elif issubclass(agent_class, ActionAgent):
        agent_category = 'action'
    else:
        agent_category = 'transform'

    # Resolve credentials using the caller's session (read-only)
    credential_service = CredentialService(db_session)
    try:
        resolved_config = credential_service.resolve_credentials_in_config(
            agent_model.config,
            agent_model.user_id,
        )
    except ValueError as exc:
        return {
            'status': 'error',
            'error': f'Credential resolution failed: {exc}',
            'agent_category': agent_category,
        }

    # Isolated session — always rolled back at the end.
    # We replace commit() with flush() so that agents that call session.commit()
    # internally (e.g. MemoryManager, DataStoreWriteAgent) still work correctly
    # (FK checks, ID assignment) but the underlying transaction stays open.
    # The final rollback() undoes everything, so no rows persist.
    test_session = Session(db.engine)
    test_session.commit = test_session.flush  # type: ignore[method-assign]
    try:
        agent = agent_registry.create_agent(
            agent_type=agent_model.job_type,
            agent_id=agent_model.id,
            config=resolved_config,
            user_id=agent_model.user_id,
            db_session=test_session,
        )

        # Suppress event cleanup so no existing events are deleted during the test
        agent._cleanup_old_events = lambda: 0

        # Build input events
        if agent_category == 'source':
            input_events = []
        else:
            # Transient Event — not added to any session
            test_event = Event(
                agent_id=agent_model.id,
                agent_type='test',
                user_id=agent_model.user_id,
                payload=payload_dict,
            )
            input_events = [test_event]

        t0 = time.time()
        output_events = agent.check(input_events)
        duration_ms = round((time.time() - t0) * 1000)

        # Serialize BEFORE rolling back (some agents flush new events to the session)
        output_dicts = []
        for e in (output_events or []):
            try:
                payload = dict(e.payload) if e.payload else {}
                meta = dict(e.event_metadata) if e.event_metadata else {}
            except Exception:
                payload = {}
                meta = {}
            output_dicts.append({'payload': payload, 'event_metadata': meta})

        filtered = (
            agent_category == 'transform'
            and len(output_dicts) == 0
            and len(input_events) > 0
        )

        return {
            'status': 'ok',
            'agent_category': agent_category,
            'output_events': output_dicts,
            'output_count': len(output_dicts),
            'filtered': filtered,
            'duration_ms': duration_ms,
        }

    except Exception as exc:
        return {
            'status': 'error',
            'error': str(exc),
            'agent_category': agent_category,
        }

    finally:
        test_session.rollback()
        test_session.close()
