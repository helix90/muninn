"""
Health Service - Agent health computation and fleet summary
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List
import logging
from app.extensions import db
from app.models import Job, AgentRun
from app.constants import (
    ALERT_CONSECUTIVE_FAILURES_CRITICAL,
    ALERT_CONSECUTIVE_FAILURES_WARNING,
    AGENT_FAILURE_WINDOW_DAYS,
)

logger = logging.getLogger(__name__)

# Health status constants
HEALTH_HEALTHY = 'healthy'
HEALTH_WARNING = 'warning'
HEALTH_CRITICAL = 'critical'
HEALTH_UNKNOWN = 'unknown'


def compute_health(agent: Job, db_session=None) -> str:
    """
    Compute and persist health status for a single agent.

    Rules (in precedence order):
    1. CRITICAL — consecutive_failures >= ALERT_CONSECUTIVE_FAILURES_CRITICAL
    2. WARNING  — consecutive_failures >= ALERT_CONSECUTIVE_FAILURES_WARNING
    3. WARNING  — expected_receive_period_in_days is set and no event received
                  within that window (checked via last completed agent run)
    4. HEALTHY  — at least one completed run exists and no failures
    5. UNKNOWN  — never run

    Returns the new status string.
    """
    session = db_session or db.session

    failures = agent.consecutive_failures or 0

    if failures >= ALERT_CONSECUTIVE_FAILURES_CRITICAL:
        status = HEALTH_CRITICAL
    elif failures >= ALERT_CONSECUTIVE_FAILURES_WARNING:
        status = HEALTH_WARNING
    elif agent.expected_receive_period_in_days:
        # Check if a successful run occurred within the expected window
        cutoff = datetime.utcnow() - timedelta(days=agent.expected_receive_period_in_days)
        recent_success = (
            session.query(AgentRun)
            .filter(
                AgentRun.agent_id == agent.id,
                AgentRun.status == 'completed',
                AgentRun.started_at >= cutoff,
            )
            .first()
        )
        if recent_success is None:
            status = HEALTH_WARNING
        else:
            status = HEALTH_HEALTHY
    else:
        # No staleness check — look for any completed run
        any_run = (
            session.query(AgentRun)
            .filter(AgentRun.agent_id == agent.id)
            .first()
        )
        status = HEALTH_HEALTHY if any_run else HEALTH_UNKNOWN

    agent.health_status = status
    agent.health_checked_at = datetime.utcnow()
    return status


def get_fleet_summary(user_id: int, db_session=None) -> Dict[str, Any]:
    """
    Return health summary counts for all active agents owned by user_id.

    Returns:
        {
            'total': int,
            'healthy': int,
            'warning': int,
            'critical': int,
            'unknown': int,
            'has_critical': bool,
        }
    """
    session = db_session or db.session

    agents = (
        session.query(Job)
        .filter(Job.user_id == user_id, Job.is_active == True)
        .all()
    )

    counts = {HEALTH_HEALTHY: 0, HEALTH_WARNING: 0, HEALTH_CRITICAL: 0, HEALTH_UNKNOWN: 0}
    for agent in agents:
        status = agent.health_status or HEALTH_UNKNOWN
        counts[status] = counts.get(status, 0) + 1

    return {
        'total': len(agents),
        'healthy': counts[HEALTH_HEALTHY],
        'warning': counts[HEALTH_WARNING],
        'critical': counts[HEALTH_CRITICAL],
        'unknown': counts[HEALTH_UNKNOWN],
        'has_critical': counts[HEALTH_CRITICAL] > 0,
    }


def sweep_all_agents(user_id: int = None, db_session=None) -> int:
    """
    Recompute health for all active agents (optionally filtered by user).

    Returns the number of agents evaluated.
    """
    session = db_session or db.session

    query = session.query(Job).filter(Job.is_active == True)
    if user_id is not None:
        query = query.filter(Job.user_id == user_id)

    agents = query.all()
    for agent in agents:
        try:
            compute_health(agent, session)
        except Exception as e:
            logger.error(f"Health check failed for agent {agent.id}: {e}")

    try:
        session.commit()
    except Exception as e:
        logger.error(f"Failed to commit health sweep results: {e}")
        session.rollback()

    return len(agents)
