"""
Audit B21 Regression Tests: POSIX path log masking, rate limiter idle key eviction,
trusted reverse proxy X-Forwarded-For resolution, and dual-version app metadata.
"""

import time
from unittest.mock import MagicMock
from fastapi import Request
from security.config import SecurityConfig
from security.logging import mask_sensitive_text
from security.rate_limit import InMemoryRateLimiter
from web.app import app, get_client_ip


def test_logging_masks_posix_paths():
    """Verify mask_sensitive_text scrubs /mnt, /root, /opt, /srv and other server paths."""
    samples = [
        "Error reading /root/secret/key.txt",
        "Failed accessing /mnt/data/server.properties",
        "Config file at /opt/minecraft/config.json",
        "Backup stored in /srv/backups/world.zip",
        "Windows path C:\\Users\\Admin\\AppData\\Local\\secret",
    ]
    for s in samples:
        masked = mask_sensitive_text(s)
        assert "[REDACTED_PATH]" in masked
        assert "/root/" not in masked
        assert "/mnt/" not in masked
        assert "/opt/" not in masked
        assert "/srv/" not in masked
        assert "C:\\Users" not in masked


def test_rate_limiter_evicts_idle_keys():
    """Verify InMemoryRateLimiter evicts idle IP records preventing unbounded memory growth."""
    cfg = SecurityConfig(rate_limit_enabled=True, rate_limit_requests_per_minute=30)
    limiter = InMemoryRateLimiter(config=cfg)

    # Simulate 3 clients sending requests
    now = time.time()
    limiter._requests["10.0.0.1"] = [now - 500]  # Old idle client
    limiter._requests["10.0.0.2"] = [now - 400]  # Old idle client
    limiter._requests["10.0.0.3"] = [now - 5]    # Active client

    assert len(limiter._requests) == 3
    evicted = limiter.evict_idle_keys(max_idle_seconds=300)
    assert evicted == 2
    assert "10.0.0.1" not in limiter._requests
    assert "10.0.0.2" not in limiter._requests
    assert "10.0.0.3" in limiter._requests


def test_client_ip_trusted_proxy_forwarded_for():
    """Verify get_client_ip only honors X-Forwarded-For when trust_forwarded_for is enabled."""
    req = MagicMock(spec=Request)
    req.client = MagicMock()
    req.client.host = "192.168.1.100"  # Proxy IP
    req.headers = {"x-forwarded-for": "203.0.113.195, 192.168.1.100"}

    # Default: trust_forwarded_for is False -> uses socket host
    ip_default = get_client_ip(req)
    assert ip_default == "192.168.1.100"

    # With trust_forwarded_for enabled via config
    trusted_cfg = SecurityConfig(trust_forwarded_for=True)
    ip_trusted = get_client_ip(req, config=trusted_cfg)
    assert ip_trusted == "203.0.113.195"


def test_fastapi_app_metadata_dual_version():
    """Verify FastAPI app is not hardcoded to version 1.21.11 only."""
    assert app.version != "1.21.11"
    assert app.version == "1.0.0"
    assert "1.21.11 / 1.21.1" in app.description
