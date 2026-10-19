"""
security/config.py - Centralized Security Configuration for MinecraftAI.

Defines security boundaries, thresholds, limits, and environment overrides.
"""

import os
from pathlib import Path
from typing import List, Optional, Set
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load environment variables early before defaults are read
load_dotenv()


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
    generation_timeout_seconds: float = Field(
        default=60.0,
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
        default=500,
        description="Maximum number of files allowed within a generated or served ZIP archive"
    )
    max_zip_total_uncompressed_bytes: int = Field(
        default=50 * 1024 * 1024,  # 50 MB
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
        default=True,
        description="Flag indicating development environment"
    )

    # Artifact Retention / Storage
    artifact_retention_seconds: int = Field(
        default=3600,  # 1 hour
        description="Duration in seconds before temporary generated datapack archives and folders are eligible for cleanup"
    )

    # Observability & Logging
    mask_sensitive_logs: bool = Field(
        default=True,
        description="Sanitize IP addresses, tokens, and internal paths in log output"
    )
    mask_prompts_in_logs: bool = Field(
        default=False,
        description="Mask or disable full prompt logging in server logs"
    )
    log_prompts: bool = Field(
        default=True,
        description="Log request prompt text (truncated) for observability"
    )
    max_logged_prompt_chars: int = Field(
        default=120,
        description="Maximum characters of prompt text recorded in server logs"
    )

    @property
    def is_production_mode(self) -> bool:
        return not self.is_development_mode


def load_security_config() -> SecurityConfig:
    """
    Constructs SecurityConfig with environment variable overrides where configured.
    Primary naming scheme: MC_* prefix (as documented in .env.example).
    Backward-compatible aliases: MINECRAFTAI_* prefix and unprefixed legacy names.
    """
    config = SecurityConfig()

    def _get_env(*keys: str) -> Optional[str]:
        for k in keys:
            val = os.getenv(k)
            if val is not None and val.strip() != "":
                return val.strip()
        return None

    # Max Prompt Length
    if val := _get_env("MC_MAX_PROMPT_LENGTH", "MINECRAFTAI_MAX_PROMPT_LENGTH"):
        try:
            parsed = int(val)
            if parsed > 0:
                config.max_prompt_length = parsed
        except ValueError:
            pass

    # Rate Limiting
    if val := _get_env("MC_RATE_LIMIT_PER_MINUTE", "MINECRAFTAI_RATE_LIMIT_PER_MINUTE", "RATE_LIMIT_PER_MINUTE"):
        try:
            parsed = int(val)
            if parsed > 0:
                config.rate_limit_requests_per_minute = parsed
        except ValueError:
            pass

    if val := _get_env("MC_BURST_ALLOWANCE", "MINECRAFTAI_BURST_ALLOWANCE"):
        try:
            parsed = int(val)
            if parsed > 0:
                config.rate_limit_burst = parsed
        except ValueError:
            pass

    if val := _get_env("MC_RATE_LIMIT_ENABLED", "MINECRAFTAI_RATE_LIMIT_ENABLED", "RATE_LIMIT_ENABLED"):
        config.rate_limit_enabled = val.lower() in ("true", "1", "yes")

    # Concurrency and Generation Timeout
    if val := _get_env("MC_MAX_CONCURRENT_GENERATIONS", "MINECRAFTAI_MAX_CONCURRENT_GENERATIONS", "MAX_CONCURRENT_GENERATIONS"):
        try:
            parsed = int(val)
            if parsed > 0:
                config.max_concurrent_generations = parsed
        except ValueError:
            pass

    if val := _get_env("MC_GENERATION_TIMEOUT_SECONDS", "MINECRAFTAI_GENERATION_TIMEOUT_SECONDS"):
        try:
            parsed = float(val)
            if parsed > 0:
                config.generation_timeout_seconds = parsed
        except ValueError:
            pass

    # Archive / ZIP Security
    if val := _get_env("MC_MAX_ZIP_SIZE_MB", "MINECRAFTAI_MAX_ZIP_SIZE_MB"):
        try:
            parsed_mb = float(val)
            if parsed_mb > 0:
                config.max_zip_total_uncompressed_bytes = int(parsed_mb * 1024 * 1024)
        except ValueError:
            pass

    if val := _get_env("MC_MAX_ZIP_ENTRIES", "MINECRAFTAI_MAX_ZIP_ENTRIES", "MINECRAFTAI_MAX_ZIP_FILE_COUNT"):
        try:
            parsed = int(val)
            if parsed > 0:
                config.max_zip_file_count = parsed
        except ValueError:
            pass

    if val := _get_env("MC_ARTIFACT_RETENTION_SECONDS", "MINECRAFTAI_ARTIFACT_RETENTION_SECONDS"):
        try:
            parsed = int(val)
            if parsed >= 0:
                config.artifact_retention_seconds = parsed
        except ValueError:
            pass

    # CORS configuration
    if val := _get_env("MC_ALLOWED_CORS_ORIGINS", "PUBLIC_ORIGIN", "MINECRAFTAI_CORS_ORIGINS"):
        origins = [o.strip() for o in val.split(",") if o.strip()]
        if origins:
            config.allowed_cors_origins = origins

    # Logging and Observability
    if val := _get_env("MC_ANONYMIZE_LOGS", "MINECRAFTAI_ANONYMIZE_LOGS", "MINECRAFTAI_MASK_SENSITIVE_LOGS"):
        config.mask_sensitive_logs = val.lower() in ("true", "1", "yes")

    if val := _get_env("MC_MASK_PROMPTS_IN_LOGS", "MINECRAFTAI_MASK_PROMPTS_IN_LOGS"):
        masked = val.lower() in ("true", "1", "yes")
        config.mask_prompts_in_logs = masked
        config.log_prompts = not masked

    # Environment
    if val := _get_env("ENVIRONMENT", "MINECRAFTAI_ENV", "ENV"):
        config.is_development_mode = val.lower() in ("development", "dev")

    return config


# Global singleton instance
DEFAULT_SECURITY_CONFIG = load_security_config()
