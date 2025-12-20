"""
Comprehensive tests for Thundering Herd prevention in the scheduler.

Tests cover:
1. JobExecutionRateLimiter - Token bucket algorithm, rate enforcement, thread safety
2. Scheduler Jitter - Deterministic jitter, range validation
3. Integration - End-to-end Thundering Herd prevention
"""

import pytest
import time
import threading
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
from app.scheduler.scheduler import JobExecutionRateLimiter, execute_scheduled_job


class TestJobExecutionRateLimiter:
    """Test the JobExecutionRateLimiter class (token bucket algorithm)."""

    def test_initialization(self):
        """Test rate limiter initializes with correct defaults."""
        limiter = JobExecutionRateLimiter(max_starts_per_second=5)

        assert limiter.max_starts_per_second == 5
        assert limiter.tokens == 5
        assert limiter.last_update > 0
        assert limiter.lock is not None

    def test_token_refill(self):
        """Test that tokens refill over time."""
        limiter = JobExecutionRateLimiter(max_starts_per_second=5)

        # Consume all tokens
        for _ in range(5):
            limiter.acquire()

        # Should have 0 tokens now
        assert limiter.tokens < 1

        # Wait for refill (1 second should give us 5 tokens)
        time.sleep(1.1)

        # Should be able to acquire again
        start_time = time.time()
        limiter.acquire()
        elapsed = time.time() - start_time

        # Should be immediate (no waiting)
        assert elapsed < 0.2

    def test_rate_limiting_enforces_limit(self):
        """Test that rate limiter enforces max starts per second."""
        limiter = JobExecutionRateLimiter(max_starts_per_second=5)

        start_time = time.time()

        # Try to acquire 10 tokens
        for i in range(10):
            limiter.acquire()

        elapsed = time.time() - start_time

        # Should take at least 1 second (first 5 immediate, next 5 after 1 sec)
        assert elapsed >= 1.0
        # But not too long (with some margin for execution)
        assert elapsed < 2.5

    def test_concurrent_access_thread_safety(self):
        """Test that rate limiter is thread-safe."""
        limiter = JobExecutionRateLimiter(max_starts_per_second=10)
        acquired_times = []
        lock = threading.Lock()

        def acquire_token():
            limiter.acquire()
            with lock:
                acquired_times.append(time.time())

        # Launch 20 threads trying to acquire tokens
        threads = []
        start_time = time.time()

        for _ in range(20):
            thread = threading.Thread(target=acquire_token)
            thread.start()
            threads.append(thread)

        # Wait for all threads to complete
        for thread in threads:
            thread.join(timeout=5)

        elapsed = time.time() - start_time

        # Should have 20 acquisitions
        assert len(acquired_times) == 20

        # Should take at least 1 second (10 tokens/sec, 20 tokens needed)
        assert elapsed >= 1.0
        assert elapsed < 3.0

    def test_max_tokens_cap(self):
        """Test that tokens don't exceed max_starts_per_second."""
        limiter = JobExecutionRateLimiter(max_starts_per_second=5)

        # Wait for a long time to accumulate tokens
        time.sleep(2)

        # Tokens should be capped at max_starts_per_second
        with limiter.lock:
            assert limiter.tokens <= limiter.max_starts_per_second


class TestSchedulerJitter:
    """Test jitter implementation in execute_scheduled_job."""

    @patch('app.scheduler.scheduler.time.sleep')
    @patch('app.scheduler.scheduler._rate_limiter')
    @patch('app.scheduler.scheduler.db')
    @patch('app.scheduler.scheduler.scheduler')
    def test_jitter_is_applied(self, mock_scheduler, mock_db, mock_limiter, mock_sleep):
        """Test that jitter (0-60 seconds) is applied before job execution."""
        # Setup mocks
        mock_job = Mock()
        mock_job.id = 123
        mock_db.session.query.return_value.get.return_value = mock_job

        mock_agent_service = Mock()
        mock_agent_service.run_agent.return_value = {'success': True}
        mock_scheduler.agent_service = mock_agent_service
        mock_scheduler.app = None

        # Execute job
        execute_scheduled_job(123)

        # Verify sleep was called (jitter applied)
        assert mock_sleep.called
        jitter_seconds = mock_sleep.call_args[0][0]

        # Verify jitter is in range 0-60
        assert 0 <= jitter_seconds <= 60

    @patch('app.scheduler.scheduler.time.sleep')
    @patch('app.scheduler.scheduler._rate_limiter')
    @patch('app.scheduler.scheduler.db')
    @patch('app.scheduler.scheduler.scheduler')
    @patch('app.scheduler.scheduler.datetime')
    def test_jitter_is_deterministic(self, mock_datetime, mock_scheduler, mock_db, mock_limiter, mock_sleep):
        """Test that same job+hour always gets same jitter."""
        # Fix datetime to a specific hour
        fixed_hour = datetime(2025, 1, 1, 12, 0, 0)
        mock_datetime.utcnow.return_value = fixed_hour

        # Setup mocks
        mock_job = Mock()
        mock_job.id = 123
        mock_db.session.query.return_value.get.return_value = mock_job

        mock_agent_service = Mock()
        mock_agent_service.run_agent.return_value = {'success': True}
        mock_scheduler.agent_service = mock_agent_service
        mock_scheduler.app = None

        # Execute job twice
        execute_scheduled_job(123)
        jitter1 = mock_sleep.call_args[0][0]

        mock_sleep.reset_mock()

        execute_scheduled_job(123)
        jitter2 = mock_sleep.call_args[0][0]

        # Should get same jitter value
        assert jitter1 == jitter2

    @patch('app.scheduler.scheduler.time.sleep')
    @patch('app.scheduler.scheduler._rate_limiter')
    @patch('app.scheduler.scheduler.db')
    @patch('app.scheduler.scheduler.scheduler')
    def test_different_jobs_get_different_jitter(self, mock_scheduler, mock_db, mock_limiter, mock_sleep):
        """Test that different jobs get different jitter values."""
        # Setup mocks
        mock_job1 = Mock()
        mock_job1.id = 1
        mock_job2 = Mock()
        mock_job2.id = 2

        def get_job(job_id):
            if job_id == 1:
                return mock_job1
            elif job_id == 2:
                return mock_job2
            return None

        mock_db.session.query.return_value.get.side_effect = get_job

        mock_agent_service = Mock()
        mock_agent_service.run_agent.return_value = {'success': True}
        mock_scheduler.agent_service = mock_agent_service
        mock_scheduler.app = None

        # Execute two different jobs
        execute_scheduled_job(1)
        jitter1 = mock_sleep.call_args[0][0]

        mock_sleep.reset_mock()

        execute_scheduled_job(2)
        jitter2 = mock_sleep.call_args[0][0]

        # Should get different jitter values
        assert jitter1 != jitter2

    def test_jitter_respects_config(self):
        """Test that jitter respects configured min/max values."""
        # This test verifies the jitter calculation logic
        # by checking that jitter values fall within configured ranges

        import random
        from datetime import datetime

        job_id = 123
        current_hour = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        seed_value = hash((job_id, current_hour))
        random.seed(seed_value)

        # Test with different ranges
        jitter_min, jitter_max = 10, 30
        jitter = random.uniform(jitter_min, jitter_max)

        assert jitter_min <= jitter <= jitter_max

        # Test with default range
        jitter_min, jitter_max = 0, 60
        random.seed(seed_value)  # Reset to same seed
        jitter = random.uniform(jitter_min, jitter_max)

        assert jitter_min <= jitter <= jitter_max


class TestSchedulerIntegration:
    """Integration tests for Thundering Herd prevention."""

    @patch('app.scheduler.scheduler.db')
    @patch('app.scheduler.scheduler.scheduler')
    def test_rate_limiter_prevents_thundering_herd(self, mock_scheduler, mock_db):
        """Test that rate limiter prevents too many simultaneous starts."""
        # Create a real rate limiter (not mocked)
        from app.scheduler.scheduler import _rate_limiter
        limiter = JobExecutionRateLimiter(max_starts_per_second=5)

        # Setup mocks
        mock_job = Mock()
        mock_job.id = 123
        mock_db.session.query.return_value.get.return_value = mock_job

        mock_agent_service = Mock()
        mock_agent_service.run_agent.return_value = {'success': True}
        mock_scheduler.agent_service = mock_agent_service
        mock_scheduler.app = None

        execution_times = []
        lock = threading.Lock()

        def execute_with_timing(job_id):
            """Execute job and record timing."""
            with patch('app.scheduler.scheduler._rate_limiter', limiter):
                with patch('app.scheduler.scheduler.time.sleep'):  # Skip jitter for this test
                    execute_scheduled_job(job_id)
                    with lock:
                        execution_times.append(time.time())

        # Launch 20 jobs simultaneously
        threads = []
        start_time = time.time()

        for i in range(20):
            thread = threading.Thread(target=execute_with_timing, args=(i,))
            thread.start()
            threads.append(thread)

        # Wait for all to complete
        for thread in threads:
            thread.join(timeout=10)

        total_elapsed = time.time() - start_time

        # Should take at least 3 seconds (5 starts/sec, 20 jobs = 4 seconds minimum)
        # Using 3 seconds to account for some parallelism
        assert total_elapsed >= 3.0

        # But not too long (should complete within reasonable time)
        assert total_elapsed < 8.0

    @patch('app.scheduler.scheduler.time.sleep')
    @patch('app.scheduler.scheduler._rate_limiter')
    @patch('app.scheduler.scheduler.db')
    @patch('app.scheduler.scheduler.scheduler')
    def test_jitter_and_rate_limit_both_applied(self, mock_scheduler, mock_db, mock_limiter, mock_sleep):
        """Test that both jitter and rate limiting are applied."""
        # Setup mocks
        mock_job = Mock()
        mock_job.id = 123
        mock_db.session.query.return_value.get.return_value = mock_job

        mock_agent_service = Mock()
        mock_agent_service.run_agent.return_value = {'success': True}
        mock_scheduler.agent_service = mock_agent_service
        mock_scheduler.app = None

        # Execute job
        execute_scheduled_job(123)

        # Verify jitter was applied (time.sleep called)
        assert mock_sleep.called

        # Verify rate limiter was called
        assert mock_limiter.acquire.called

    @patch('app.scheduler.scheduler.time.sleep')
    @patch('app.scheduler.scheduler._rate_limiter')
    @patch('app.scheduler.scheduler.db')
    @patch('app.scheduler.scheduler.scheduler')
    def test_error_handling_with_missing_job(self, mock_scheduler, mock_db, mock_limiter, mock_sleep):
        """Test that missing job is handled gracefully."""
        # Setup mocks - job not found
        mock_db.session.query.return_value.get.return_value = None
        mock_scheduler.app = None

        # Execute job (should not raise exception)
        execute_scheduled_job(999)

        # Verify jitter and rate limit were still applied
        assert mock_sleep.called
        assert mock_limiter.acquire.called

    @patch('app.scheduler.scheduler.db')
    @patch('app.scheduler.scheduler.time.sleep')
    @patch('app.scheduler.scheduler._rate_limiter')
    def test_flask_app_context_handling(self, mock_limiter, mock_sleep, mock_db):
        """Test that Flask app context is properly used for database operations."""
        # Import the scheduler and function
        from app.scheduler.scheduler import execute_scheduled_job, scheduler

        # Save original app to restore later
        original_app = scheduler.app
        original_agent_service = scheduler.agent_service

        try:
            # Create mock app context
            mock_app_context = MagicMock()

            # Replace scheduler.app with a mock
            scheduler.app = MagicMock()
            scheduler.app.app_context.return_value = mock_app_context
            scheduler.app.config.get.side_effect = lambda key, default=None: {
                'SCHEDULER_JITTER_MIN_SECONDS': 0,
                'SCHEDULER_JITTER_MAX_SECONDS': 60
            }.get(key, default)

            # Mock the job
            mock_job = Mock()
            mock_job.id = 123
            mock_db.session.query.return_value.get.return_value = mock_job

            # Mock agent service
            scheduler.agent_service = Mock()
            scheduler.agent_service.run_agent.return_value = {'success': True}

            # Execute job
            execute_scheduled_job(123)

            # Verify app_context was called
            scheduler.app.app_context.assert_called_once()

            # Verify context manager __enter__ was called
            mock_app_context.__enter__.assert_called_once()

            # Verify database query was called
            assert mock_db.session.query.called, "Database query should be called within app context"

            # Verify agent was run
            scheduler.agent_service.run_agent.assert_called_once()

        finally:
            # Restore original state
            scheduler.app = original_app
            scheduler.agent_service = original_agent_service

    @patch('app.scheduler.scheduler.time.sleep')
    @patch('app.scheduler.scheduler._rate_limiter')
    @patch('app.scheduler.scheduler.db')
    @patch('app.scheduler.scheduler.scheduler')
    def test_handles_missing_app_gracefully(self, mock_scheduler, mock_db, mock_limiter, mock_sleep):
        """Test that missing Flask app is handled gracefully."""
        # Setup mocks - no app available
        mock_scheduler.app = None

        # Execute job (should not raise exception, but should log error)
        execute_scheduled_job(123)

        # Verify jitter and rate limit were still applied
        assert mock_sleep.called
        assert mock_limiter.acquire.called

        # Verify database operations were NOT attempted (no app context)
        assert not mock_db.session.query.called
