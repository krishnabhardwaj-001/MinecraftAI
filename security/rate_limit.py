"""
security/rate_limit.py - In-Memory Thread-Safe Rate Limiter & Concurrency Limiter.

Protects the API against denial-of-service, rapid automated flooding,
and resource exhaustion from concurrent expensive generation requests.
"""

import threading
import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple
from security.config import DEFAULT_SECURITY_CONFIG, SecurityConfig


class RateLimitExceededError(Exception):
    """Raised when a client exceeds allowed request frequencies."""
    def __init__(self, message: str, retry_after: int = 60):
        super().__init__(message)
        self.retry_after = retry_after


class InMemoryRateLimiter:
    """
    Sliding-window in-memory rate limiter.
    Thread-safe and requires no external database or redis dependency.
    """

    def __init__(self, config: Optional[SecurityConfig] = None):
        self.config = config or DEFAULT_SECURITY_CONFIG
        self._lock = threading.Lock()
        # client_ip -> list of epoch timestamps
        self._requests: Dict[str, List[float]] = defaultdict(list)
        # Concurrency semaphore
        self._concurrency_sem = threading.Semaphore(self.config.max_concurrent_generations)
        self._active_generations = 0

    def check_rate_limit(self, client_ip: str) -> Tuple[bool, Optional[int]]:
        """
        Checks whether client_ip is permitted to perform a request under rate limits.

        Returns:
            (allowed: bool, retry_after_seconds: Optional[int])
        """
        if not self.config.rate_limit_enabled:
            return True, None

        now = time.time()
        window_seconds = 60.0
        burst_window_seconds = 5.0

        with self._lock:
            self._call_count = getattr(self, "_call_count", 0) + 1
            if self._call_count % 100 == 0:
                self._evict_idle_keys_locked(now, max_idle_seconds=window_seconds * 5)

            history = self._requests[client_ip]

            # Prune timestamps older than 60 seconds
            history = [t for t in history if now - t < window_seconds]
            if not history:
                self._requests.pop(client_ip, None)
            else:
                self._requests[client_ip] = history

            # Check minute limit
            if len(history) >= self.config.rate_limit_requests_per_minute:
                oldest_in_window = history[0]
                retry_after = max(1, int(window_seconds - (now - oldest_in_window)))
                return False, retry_after

            # Check burst limit
            recent_burst = [t for t in history if now - t < burst_window_seconds]
            if len(recent_burst) >= self.config.rate_limit_burst:
                oldest_burst = recent_burst[0]
                retry_after = max(1, int(burst_window_seconds - (now - oldest_burst)))
                return False, retry_after

            # Record this request
            history.append(now)
            self._requests[client_ip] = history
            return True, None

    def _evict_idle_keys_locked(self, now: float, max_idle_seconds: float = 300.0) -> int:
        """Internal helper to evict keys whose requests are completely outside retention window."""
        evicted = 0
        for ip in list(self._requests.keys()):
            history = self._requests[ip]
            if not history or (now - history[-1] >= max_idle_seconds):
                del self._requests[ip]
                evicted += 1
        return evicted

    def evict_idle_keys(self, max_idle_seconds: float = 300.0) -> int:
        """
        Public method to prune idle IP addresses from memory.
        Returns the number of keys evicted.
        """
        now = time.time()
        with self._lock:
            return self._evict_idle_keys_locked(now, max_idle_seconds)

    def acquire_generation_slot(self, timeout_s: float = 2.0) -> bool:
        """
        Acquires a concurrency slot for a heavy generation pipeline execution.
        """
        acquired = self._concurrency_sem.acquire(timeout=timeout_s)
        if acquired:
            with self._lock:
                self._active_generations += 1
        return acquired

    def release_generation_slot(self) -> None:
        """
        Releases an acquired concurrency slot.
        """
        with self._lock:
            if self._active_generations > 0:
                self._active_generations -= 1
        self._concurrency_sem.release()

    @property
    def max_concurrent_generations(self) -> int:
        return self.config.max_concurrent_generations

    def reset(self) -> None:
        """
        Clears all recorded rate limit history and reinitializes concurrency semaphore.
        """
        with self._lock:
            self._requests.clear()
            self._active_generations = 0
            self._concurrency_sem = threading.Semaphore(self.config.max_concurrent_generations)


# Global singleton instance
DEFAULT_RATE_LIMITER = InMemoryRateLimiter()
