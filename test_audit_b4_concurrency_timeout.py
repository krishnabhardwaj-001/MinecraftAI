"""
test_audit_b4_concurrency_timeout.py - Tests for B4: Generation Concurrency, Timeout, and Non-Blocking Web Server.

Verifies:
1. Long-running synchronous pipeline runs in a worker thread and does NOT block the FastAPI event loop (/api/health responds concurrently).
2. Generation timeout is enforced (returns HTTP 504 Gateway Timeout).
3. Concurrency slot in DEFAULT_RATE_LIMITER is released on timeout or completion.
4. Request payload size limit (max_payload_bytes) is enforced (returns HTTP 413).
"""

import asyncio
import time
from unittest.mock import patch
import httpx
import pytest
from fastapi.testclient import TestClient

from web.app import app
from security.config import DEFAULT_SECURITY_CONFIG, load_security_config
from security.rate_limit import DEFAULT_RATE_LIMITER


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Ensure limiter has full capacity before each test."""
    DEFAULT_RATE_LIMITER.reset()
    yield
    DEFAULT_RATE_LIMITER.reset()


def test_generation_does_not_block_health_check():
    """
    While a slow generation is executing, the event loop must remain free
    so concurrent requests to /api/health succeed immediately.
    """
    def slow_pipeline(*args, **kwargs):
        time.sleep(0.6)
        from pipeline.models import PipelineResult
        return PipelineResult(
            status="success",
            is_success=True,
            original_request="slow request",
            minecraft_version="1.21.11"
        )

    with patch("web.app.run_minecraft_pipeline", side_effect=slow_pipeline):
        async def run_concurrent():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                gen_task = asyncio.create_task(
                    client.post("/api/generate", json={"request": "Make skeletons drop iron."})
                )
                # Wait briefly so generation starts and enters worker thread
                await asyncio.sleep(0.1)

                # Health check should return immediately while generation is still running
                health_start = time.time()
                health_resp = await client.get("/api/health")
                health_duration = time.time() - health_start

                assert health_resp.status_code == 200
                assert health_resp.json()["status"] == "ok"
                # Health check should not have waited for the 0.6s pipeline
                assert health_duration < 0.4

                gen_resp = await gen_task
                assert gen_resp.status_code == 200

        asyncio.run(run_concurrent())


def test_generation_timeout_enforced_and_slot_released(monkeypatch):
    """
    When generation exceeds configured generation_timeout_seconds,
    HTTP 504 is returned and the concurrency slot is released.
    """
    monkeypatch.setenv("MC_GENERATION_TIMEOUT_SECONDS", "0.2")

    def blocking_pipeline(*args, **kwargs):
        time.sleep(0.8)
        from pipeline.models import PipelineResult
        return PipelineResult(status="success", is_success=True, original_request="timeout test")

    with patch("web.app.run_minecraft_pipeline", side_effect=blocking_pipeline):
        async def run_timeout():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                start = time.time()
                resp = await client.post("/api/generate", json={"request": "Make creepers drop glowstone."})
                elapsed = time.time() - start

                # Must return 504 Gateway Timeout in around ~0.2s, not 0.8s
                assert resp.status_code == 504
                assert "timed out" in resp.json()["detail"].lower()
                assert elapsed < 0.6

        asyncio.run(run_timeout())

        # Crucial check: the concurrency slot must have been released!
        # Acquiring all slots from limiter must succeed without blocking
        max_slots = DEFAULT_RATE_LIMITER.max_concurrent_generations
        acquired = [DEFAULT_RATE_LIMITER.acquire_generation_slot(timeout_s=0.05) for _ in range(max_slots)]
        assert all(acquired)
        for _ in range(max_slots):
            DEFAULT_RATE_LIMITER.release_generation_slot()


def test_request_payload_size_limit_enforced():
    """Requests exceeding max_payload_bytes return HTTP 413."""
    client = TestClient(app)
    max_bytes = DEFAULT_SECURITY_CONFIG.max_payload_bytes
    oversized_headers = {"content-length": str(max_bytes + 500)}

    resp = client.post(
        "/api/generate",
        json={"request": "Make zombies fast."},
        headers=oversized_headers
    )
    assert resp.status_code == 413
    assert "exceeds maximum allowed size" in resp.json()["detail"].lower()
