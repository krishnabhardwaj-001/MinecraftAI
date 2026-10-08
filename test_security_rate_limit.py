"""
Security Tests: Rate Limiting and Concurrency Control.
Tests sliding window rate limiter, burst handling, IP tracking,
concurrency semaphore management, and retry-after calculation.
"""

import time
import pytest
from security.rate_limit import InMemoryRateLimiter
from security.config import SecurityConfig


class TestRateLimiter:
    """Tests for in-memory rate limiting and concurrency management."""

    def test_requests_within_limit_allowed(self):
        cfg = SecurityConfig(rate_limit_requests_per_minute=5, rate_limit_burst=5)
        limiter = InMemoryRateLimiter(config=cfg)
        client_ip = "192.168.1.100"

        # 5 requests should pass
        for _ in range(5):
            allowed, retry_after = limiter.check_rate_limit(client_ip)
            assert allowed is True
            assert retry_after is None

    def test_requests_exceeding_limit_blocked(self):
        cfg = SecurityConfig(rate_limit_requests_per_minute=3, rate_limit_burst=3)
        limiter = InMemoryRateLimiter(config=cfg)
        client_ip = "192.168.1.101"

        # 3 requests allowed
        for _ in range(3):
            allowed, _ = limiter.check_rate_limit(client_ip)
            assert allowed is True

        # 4th request must be blocked
        allowed, retry_after = limiter.check_rate_limit(client_ip)
        assert allowed is False
        assert retry_after is not None
        assert retry_after > 0

    def test_client_isolation(self):
        cfg = SecurityConfig(rate_limit_requests_per_minute=2, rate_limit_burst=2)
        limiter = InMemoryRateLimiter(config=cfg)
        client_a = "10.0.0.1"
        client_b = "10.0.0.2"

        # Block client A
        limiter.check_rate_limit(client_a)
        limiter.check_rate_limit(client_a)
        allowed_a, _ = limiter.check_rate_limit(client_a)
        assert allowed_a is False

        # Client B must remain unaffected
        allowed_b, _ = limiter.check_rate_limit(client_b)
        assert allowed_b is True

    def test_reset(self):
        cfg = SecurityConfig(rate_limit_requests_per_minute=1, rate_limit_burst=1)
        limiter = InMemoryRateLimiter(config=cfg)
        client_ip = "10.0.0.3"

        limiter.check_rate_limit(client_ip)
        allowed, _ = limiter.check_rate_limit(client_ip)
        assert allowed is False

        limiter.reset()
        allowed_after_reset, _ = limiter.check_rate_limit(client_ip)
        assert allowed_after_reset is True

    def test_concurrency_slots(self):
        cfg = SecurityConfig(max_concurrent_generations=2)
        limiter = InMemoryRateLimiter(config=cfg)

        # Slot 1
        assert limiter.acquire_generation_slot(timeout_s=0.1) is True
        # Slot 2
        assert limiter.acquire_generation_slot(timeout_s=0.1) is True

        # Slot 3 must fail due to limit of 2
        assert limiter.acquire_generation_slot(timeout_s=0.05) is False

        # Release slot 1
        limiter.release_generation_slot()

        # Slot 3 can now be acquired
        assert limiter.acquire_generation_slot(timeout_s=0.1) is True

        # Cleanup
        limiter.release_generation_slot()
        limiter.release_generation_slot()
