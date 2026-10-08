"""
security/config.py - Centralized Security Configuration for MinecraftAI.

Defines security boundaries, thresholds, limits, and environment overrides.
"""

import os
from pathlib import Path
from typing import List, Set
from pydantic import BaseModel, Field


class SecurityConfig(BaseModel):
    """
    Configuration parameters governing application security boundaries.
    """
    # Input Constraints
    max_prompt_length: int = Field(
        default=2000,
        description="Maximum allowed character length for natural-language prompts"
    )
    min_prompt_length: int = Field(
        default=3,
        description="Minimum non-whitespace character length for prompts"
    )
    max_payload_bytes: int = Field(
        default=64 * 1024,  # 64 KB
        description="Maximum request payload body size in bytes"
    )

    # Rate Limiting
    rate_limit_requests_per_minute: int = Field(
        default=30,
        description="Maximum requests allowed per client IP per minute"
    )
    rate_limit_burst: int = Field(
        default=10,
        description="Maximum burst requests allowed within a 5-second window"
    )
    rate_limit_enabled: bool = Field(
        default=True,
        description="Enable/disable rate limiting"
    )

    # Concurrency and Generation Timeout
    max_concurrent_generations: int = Field(
        default=4,
        description="Maximum simultaneous datapack generation pipelines running"
    )
    generation_timeout_seconds: int = Field(
        default=180,
        description="Hard timeout for pipeline execution in seconds"
    )

    # Filesystem & Path Constraints
    base_dir: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parent.parent,
        description="Root directory of the application repository"
    )
    allowed_output_dirs: List[Path] = Field(
        default_factory=lambda: [
            Path(__file__).resolve().parent.parent / "generated",
            Path(__file__).resolve().parent.parent / "scratch",
        ],
        description="Approved directories within which generated files may be written"
    )

    # Archive / ZIP Security
    max_zip_file_count: int = Field(
        default=250,
        description="Maximum number of files allowed within a generated or served ZIP archive"
    )
    max_zip_total_uncompressed_bytes: int = Field(
        default=25 * 1024 * 1024,  # 25 MB
        description="Maximum total uncompressed size of archive contents"
    )
    max_zip_single_file_bytes: int = Field(
        default=5 * 1024 * 1024,  # 5 MB
        description="Maximum size of an individual file inside a ZIP archive"
    )
    max_compression_ratio: float = Field(
        default=100.0,
        description="Maximum allowed ratio between uncompressed and compressed size (zip bomb protection)"
    )
    allowed_archive_extensions: Set[str] = Field(
        default_factory=lambda: {".json", ".mcfunction", ".mcmeta", ".png", ".txt"},
        description="Whitelisted file extensions permitted inside a datapack ZIP"
    )

    # Web & CORS Security
    allowed_cors_origins: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        description="Permitted CORS origins. Wildcard '*' with credentials is strictly disallowed."
    )
    is_development_mode: bool = Field(
        default_factory=lambda: os.getenv("MINECRAFTAI_ENV", "development").lower() == "development",
        description="Flag indicating development environment"
    )

    # Observability & Logging
    mask_sensitive_logs: bool = Field(
        default=True,
        description="Sanitize IP addresses, tokens, and internal paths in log output"
    )
    log_prompts: bool = Field(
        default=True,
        description="Log request prompt text (truncated) for observability"
    )
    max_logged_prompt_chars: int = Field(
        default=120,
        description="Maximum characters of prompt text recorded in server logs"
    )


def load_security_config() -> SecurityConfig:
    """
    Constructs SecurityConfig with environment variable overrides where configured.
    """
    config = SecurityConfig()

    # Environment variable overrides
    if env_prompt_len := os.getenv("MINECRAFTAI_MAX_PROMPT_LENGTH"):
        try:
            config.max_prompt_length = int(env_prompt_len)
        except ValueError:
            pass

    if env_rate_limit := os.getenv("MINECRAFTAI_RATE_LIMIT_PER_MINUTE"):
        try:
            config.rate_limit_requests_per_minute = int(env_rate_limit)
        except ValueError:
            pass

    if env_cors := os.getenv("MINECRAFTAI_CORS_ORIGINS"):
        origins = [o.strip() for o in env_cors.split(",") if o.strip()]
        if origins:
            config.allowed_cors_origins = origins

    if env_rate_enabled := os.getenv("MINECRAFTAI_RATE_LIMIT_ENABLED"):
        config.rate_limit_enabled = env_rate_enabled.lower() in ("true", "1", "yes")

    return config


# Global singleton instance
DEFAULT_SECURITY_CONFIG = load_security_config()
