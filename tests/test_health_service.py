"""Tests for the agent health service."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from app.models import Job, AgentRun
from app.services.health_service import (
    compute_health, get_fleet_summary, sweep_all_agents,
    HEALTH_HEALTHY, HEALTH_WARNING, HEALTH_CRITICAL, HEALTH_UNKNOWN,
)


class TestComputeHealth:
    """Tests for compute_health()."""

    def test_unknown_when_never_run(self, db_session, test_user, test_job):
        """Agent that has never run gets UNKNOWN status."""
        job = test_job
        # No agent runs exist
        status = compute_health(job, db_session)
        assert status == HEALTH_UNKNOWN
        assert job.health_status == HEALTH_UNKNOWN
        assert job.health_checked_at is not None

    def test_healthy_after_successful_run(self, db_session, test_user, test_job):
        """Agent with a completed run and no failures gets HEALTHY."""
        run = AgentRun(agent_id=test_job.id, status='completed')
        db_session.add(run)
        db_session.flush()

        status = compute_health(test_job, db_session)
        assert status == HEALTH_HEALTHY

    def test_warning_on_one_failure(self, db_session, test_user, test_job):
        """One consecutive failure → WARNING."""
        test_job.consecutive_failures = 1
        status = compute_health(test_job, db_session)
        assert status == HEALTH_WARNING

    def test_critical_on_three_failures(self, db_session, test_user, test_job):
        """Three consecutive failures → CRITICAL."""
        test_job.consecutive_failures = 3
        status = compute_health(test_job, db_session)
        assert status == HEALTH_CRITICAL

    def test_critical_supersedes_warning_threshold(self, db_session, test_user, test_job):
        """Five failures is still CRITICAL, not WARNING."""
        test_job.consecutive_failures = 5
        status = compute_health(test_job, db_session)
        assert status == HEALTH_CRITICAL

    def test_staleness_warning_when_no_recent_run(self, db_session, test_user, test_job):
        """Agent with expected_receive_period set but no recent success → WARNING."""
        test_job.expected_receive_period_in_days = 1
        test_job.consecutive_failures = 0
        # Add a run that is older than the window
        old_run = AgentRun(agent_id=test_job.id, status='completed')
        old_run.started_at = datetime.utcnow() - timedelta(days=3)
        db_session.add(old_run)
        db_session.flush()

        status = compute_health(test_job, db_session)
        assert status == HEALTH_WARNING

    def test_healthy_when_recent_success_within_window(self, db_session, test_user, test_job):
        """Agent with recent successful run within expected window → HEALTHY."""
        test_job.expected_receive_period_in_days = 7
        test_job.consecutive_failures = 0
        recent_run = AgentRun(agent_id=test_job.id, status='completed')
        db_session.add(recent_run)
        db_session.flush()

        status = compute_health(test_job, db_session)
        assert status == HEALTH_HEALTHY

    def test_failure_takes_precedence_over_staleness_check(self, db_session, test_user, test_job):
        """Consecutive failures → CRITICAL even if expected_receive_period is also exceeded."""
        test_job.expected_receive_period_in_days = 1
        test_job.consecutive_failures = 3
        status = compute_health(test_job, db_session)
        assert status == HEALTH_CRITICAL


class TestGetFleetSummary:
    """Tests for get_fleet_summary()."""

    def test_empty_fleet(self, db_session, test_user):
        """User with no agents gets all-zero summary."""
        # Deactivate or delete all agents first
        db_session.query(Job).filter_by(user_id=test_user.id).update({'is_active': False})
        db_session.flush()
        summary = get_fleet_summary(test_user.id, db_session)
        assert summary['total'] == 0
        assert summary['has_critical'] is False

    def test_fleet_counts_reflect_health_status(self, db_session, test_user, test_job):
        """Summary counts correct statuses."""
        test_job.health_status = HEALTH_CRITICAL
        db_session.flush()
        summary = get_fleet_summary(test_user.id, db_session)
        assert summary['critical'] == 1
        assert summary['has_critical'] is True
        assert summary['healthy'] == 0

    def test_fleet_ignores_inactive_agents(self, db_session, test_user, test_job):
        """Inactive agents are excluded from the summary."""
        test_job.is_active = False
        test_job.health_status = HEALTH_CRITICAL
        db_session.flush()
        summary = get_fleet_summary(test_user.id, db_session)
        assert summary['total'] == 0
        assert summary['has_critical'] is False


class TestSweepAllAgents:
    """Tests for sweep_all_agents()."""

    def test_sweep_updates_health_for_all_active_agents(self, db_session, test_user, test_job):
        """Sweep evaluates and persists health for active agents."""
        test_job.health_status = HEALTH_UNKNOWN
        db_session.commit()

        count = sweep_all_agents(user_id=test_user.id, db_session=db_session)
        assert count >= 1

        db_session.refresh(test_job)
        # No runs exist → should be UNKNOWN (still evaluated)
        assert test_job.health_checked_at is not None
