"""
test_audit_b3_config.py - Tests for B3: Unify .env Security Settings and Configuration Loading.

Verifies:
1. Environment variables (MC_* and legacy MINECRAFTAI_* aliases) correctly configure SecurityConfig.
2. Invalid environment values fall back safely to default values.
3. InMemoryRateLimiter respects max_concurrent_generations from the loaded configuration.
4. Default limits match across documented values (50 MB zip size, 500 entries, etc.).
"""

import os
import pytest
from security.config import SecurityConfig, load_security_config
from security.rate_limit import InMemoryRateLimiter


def test_default_security_config_matches_documentation():
    """Default SecurityConfig values must match documented limits."""
    cfg = SecurityConfig()
    assert cfg.max_prompt_length == 2000
    assert cfg.rate_limit_requests_per_minute == 30
    assert cfg.rate_limit_burst == 10
    assert cfg.rate_limit_enabled is True
    assert cfg.max_concurrent_generations == 4
    assert cfg.max_zip_file_count == 500
    assert cfg.max_zip_total_uncompressed_bytes == 50 * 1024 * 1024
    assert cfg.generation_timeout_seconds == 60.0
    assert cfg.artifact_retention_seconds == 3600
    assert cfg.mask_sensitive_logs is True
    assert cfg.mask_prompts_in_logs is False
    assert cfg.log_prompts is True


def test_mc_env_vars_override_security_config(monkeypatch):
    """Setting MC_* environment variables overrides defaults properly."""
    monkeypatch.setenv("MC_MAX_PROMPT_LENGTH", "1500")
    monkeypatch.setenv("MC_RATE_LIMIT_PER_MINUTE", "45")
    monkeypatch.setenv("MC_BURST_ALLOWANCE", "15")
    monkeypatch.setenv("MC_RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("MC_MAX_CONCURRENT_GENERATIONS", "8")
    monkeypatch.setenv("MC_GENERATION_TIMEOUT_SECONDS", "120.5")
    monkeypatch.setenv("MC_MAX_ZIP_SIZE_MB", "75")
    monkeypatch.setenv("MC_MAX_ZIP_ENTRIES", "600")
    monkeypatch.setenv("MC_ARTIFACT_RETENTION_SECONDS", "7200")
    monkeypatch.setenv("MC_ALLOWED_CORS_ORIGINS", "https://example.com,https://api.example.com")
    monkeypatch.setenv("MC_ANONYMIZE_LOGS", "false")
    monkeypatch.setenv("MC_MASK_PROMPTS_IN_LOGS", "true")
    monkeypatch.setenv("ENVIRONMENT", "production")

    cfg = load_security_config()

    assert cfg.max_prompt_length == 1500
    assert cfg.rate_limit_requests_per_minute == 45
    assert cfg.rate_limit_burst == 15
    assert cfg.rate_limit_enabled is False
    assert cfg.max_concurrent_generations == 8
    assert cfg.generation_timeout_seconds == 120.5
    assert cfg.max_zip_total_uncompressed_bytes == 75 * 1024 * 1024
    assert cfg.max_zip_file_count == 600
    assert cfg.artifact_retention_seconds == 7200
    assert cfg.allowed_cors_origins == ["https://example.com", "https://api.example.com"]
    assert cfg.mask_sensitive_logs is False
    assert cfg.mask_prompts_in_logs is True
    assert cfg.log_prompts is False
    assert cfg.is_development_mode is False


def test_legacy_aliases_override_security_config(monkeypatch):
    """Legacy MINECRAFTAI_* and unprefixed env vars work as backwards-compatible fallbacks."""
    monkeypatch.delenv("MC_MAX_PROMPT_LENGTH", raising=False)
    monkeypatch.delenv("MC_RATE_LIMIT_PER_MINUTE", raising=False)
    monkeypatch.delenv("MC_MAX_CONCURRENT_GENERATIONS", raising=False)
    monkeypatch.delenv("MC_MAX_ZIP_SIZE_MB", raising=False)
    monkeypatch.delenv("MC_MAX_ZIP_ENTRIES", raising=False)

    monkeypatch.setenv("MINECRAFTAI_MAX_PROMPT_LENGTH", "1200")
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "25")
    monkeypatch.setenv("MAX_CONCURRENT_GENERATIONS", "6")
    monkeypatch.setenv("MINECRAFTAI_MAX_ZIP_SIZE_MB", "30")
    monkeypatch.setenv("MINECRAFTAI_MAX_ZIP_ENTRIES", "350")
    monkeypatch.setenv("MINECRAFTAI_ENV", "dev")

    cfg = load_security_config()

    assert cfg.max_prompt_length == 1200
    assert cfg.rate_limit_requests_per_minute == 25
    assert cfg.max_concurrent_generations == 6
    assert cfg.max_zip_total_uncompressed_bytes == 30 * 1024 * 1024
    assert cfg.max_zip_file_count == 350
    assert cfg.is_development_mode is True


def test_invalid_env_vars_fallback_safely(monkeypatch):
    """Malformed or invalid environment variables fall back safely to defaults without crashing."""
    monkeypatch.setenv("MC_MAX_PROMPT_LENGTH", "not-a-number")
    monkeypatch.setenv("MC_RATE_LIMIT_PER_MINUTE", "-5")
    monkeypatch.setenv("MC_BURST_ALLOWANCE", "invalid")
    monkeypatch.setenv("MC_MAX_CONCURRENT_GENERATIONS", "zero")
    monkeypatch.setenv("MC_GENERATION_TIMEOUT_SECONDS", "invalid_seconds")
    monkeypatch.setenv("MC_MAX_ZIP_SIZE_MB", "huge")
    monkeypatch.setenv("MC_MAX_ZIP_ENTRIES", "many")
    monkeypatch.setenv("MC_ARTIFACT_RETENTION_SECONDS", "-100")

    cfg = load_security_config()

    # Must retain safe default values
    assert cfg.max_prompt_length == 2000
    assert cfg.rate_limit_requests_per_minute == 30
    assert cfg.rate_limit_burst == 10
    assert cfg.max_concurrent_generations == 4
    assert cfg.generation_timeout_seconds == 60.0
    assert cfg.max_zip_total_uncompressed_bytes == 50 * 1024 * 1024
    assert cfg.max_zip_file_count == 500
    assert cfg.artifact_retention_seconds == 3600


def test_in_memory_rate_limiter_uses_configured_concurrency(monkeypatch):
    """InMemoryRateLimiter initializes semaphore with loaded max_concurrent_generations."""
    monkeypatch.setenv("MC_MAX_CONCURRENT_GENERATIONS", "7")
    cfg = load_security_config()
    limiter = InMemoryRateLimiter(config=cfg)

    assert limiter.max_concurrent_generations == 7
    # Should be able to acquire exactly 7 slots without blocking
    acquired = []
    for _ in range(7):
        acquired.append(limiter.acquire_generation_slot(timeout_s=0.05))
    assert all(acquired)

    # The 8th slot should fail
    assert limiter.acquire_generation_slot(timeout_s=0.05) is False

    # Release slots
    for _ in range(7):
        limiter.release_generation_slot()
