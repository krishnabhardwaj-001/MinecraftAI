"""
security - Centralized Security Layer for MinecraftAI.

Provides:
- Security configuration (SecurityConfig, load_security_config)
- Input validation (validate_prompt, validate_version_string, sanitize_datapack_name, validate_clarification_answer)
- Path security (resolve_safe_path, validate_zip_download_filename, is_safe_filename, ensure_safe_output_directory)
- Archive security (validate_zip_archive, validate_archive_entry_name, safe_extract_zip)
- Command security (validate_minecraft_command, validate_mcfunction_content)
- Rate limiting (InMemoryRateLimiter, DEFAULT_RATE_LIMITER)
- Web security headers (SecurityHeadersMiddleware)
- Safe logging (mask_sensitive_text, sanitize_prompt_for_logging, get_safe_logger)
- Error sanitization (sanitize_user_error_message)
"""

from security.config import DEFAULT_SECURITY_CONFIG, SecurityConfig, load_security_config
from security.input_security import (
    InputValidationError,
    sanitize_datapack_name,
    validate_clarification_answer,
    validate_prompt,
    validate_version_string,
)
from security.path_security import (
    PathSecurityError,
    ensure_safe_output_directory,
    is_safe_filename,
    resolve_safe_path,
    validate_zip_download_filename,
)
from security.archive_security import (
    ArchiveSecurityError,
    safe_extract_zip,
    validate_archive_entry_name,
    validate_zip_archive,
)
from security.command_security import (
    ALLOWED_COMMAND_VERBS,
    CommandSecurityError,
    validate_mcfunction_content,
    validate_minecraft_command,
)
from security.rate_limit import (
    DEFAULT_RATE_LIMITER,
    InMemoryRateLimiter,
    RateLimitExceededError,
)
from security.headers import SecurityHeadersMiddleware
from security.logging import (
    get_safe_logger,
    mask_ip_address,
    mask_sensitive_text,
    sanitize_prompt_for_logging,
)
from security.error_sanitizer import sanitize_user_error_message

__all__ = [
    "SecurityConfig",
    "DEFAULT_SECURITY_CONFIG",
    "load_security_config",
    "InputValidationError",
    "validate_prompt",
    "validate_version_string",
    "sanitize_datapack_name",
    "validate_clarification_answer",
    "PathSecurityError",
    "resolve_safe_path",
    "validate_zip_download_filename",
    "is_safe_filename",
    "ensure_safe_output_directory",
    "ArchiveSecurityError",
    "validate_zip_archive",
    "validate_archive_entry_name",
    "safe_extract_zip",
    "CommandSecurityError",
    "validate_minecraft_command",
    "validate_mcfunction_content",
    "ALLOWED_COMMAND_VERBS",
    "InMemoryRateLimiter",
    "DEFAULT_RATE_LIMITER",
    "RateLimitExceededError",
    "SecurityHeadersMiddleware",
    "get_safe_logger",
    "mask_sensitive_text",
    "sanitize_prompt_for_logging",
    "mask_ip_address",
    "sanitize_user_error_message",
]
