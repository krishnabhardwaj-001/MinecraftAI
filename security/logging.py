"""
security/logging.py - Safe Structured Logging with Secret Masking.

Ensures server logs do not expose sensitive environment variables, credentials,
bearer tokens, passwords, raw absolute filesystem paths, or unbounded user prompts.
"""

import logging
import re
from typing import Any, Dict, Optional
from security.config import DEFAULT_SECURITY_CONFIG, SecurityConfig


# Patterns matching sensitive information in log strings
SENSITIVE_PATTERNS = [
    (re.compile(r"(api[_-]?key\s*[:=]\s*)['\"]?([a-zA-Z0-9_\-]{8,})['\"]?", re.IGNORECASE), r"\1[MASKED_KEY]"),
    (re.compile(r"(token\s*[:=]\s*)['\"]?([a-zA-Z0-9_\-\.]{8,})['\"]?", re.IGNORECASE), r"\1[MASKED_TOKEN]"),
    (re.compile(r"(password\s*[:=]\s*)['\"]?([^\s'\"]+)['\"]?", re.IGNORECASE), r"\1[MASKED_PASSWORD]"),
    (re.compile(r"(Bearer\s+)[a-zA-Z0-9_\-\.]{10,}", re.IGNORECASE), r"\1[MASKED_BEARER]"),
    (re.compile(r"([a-zA-Z]:\\[^\s'\"]+)", re.IGNORECASE), r"[REDACTED_PATH]"),
]


def mask_sensitive_text(text: str) -> str:
    """
    Scans a string and masks known sensitive patterns (keys, tokens, paths).
    """
    if not isinstance(text, str):
        return str(text)

    masked = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        masked = pattern.sub(replacement, masked)

    return masked


def sanitize_prompt_for_logging(
    prompt: str,
    config: Optional[SecurityConfig] = None
) -> str:
    """
    Truncates and cleans a user prompt for safe logging.
    """
    cfg = config or DEFAULT_SECURITY_CONFIG
    if not cfg.log_prompts or not prompt:
        return "[PROMPT_LOGGING_DISABLED]"

    cleaned = " ".join(prompt.strip().split())
    if len(cleaned) > cfg.max_logged_prompt_chars:
        cleaned = cleaned[:cfg.max_logged_prompt_chars] + "...[TRUNCATED]"

    return mask_sensitive_text(cleaned)


def mask_ip_address(ip: str) -> str:
    """
    Anonymizes an IPv4 or IPv6 address for privacy preservation in logs.
    """
    if not ip or not isinstance(ip, str):
        return "unknown"

    # Localhost
    if ip in ("127.0.0.1", "localhost", "::1"):
        return "127.0.0.1"

    # IPv4: mask last two octets
    if "." in ip:
        parts = ip.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.*.*"

    # IPv6: mask host segment
    if ":" in ip:
        parts = ip.split(":")
        if len(parts) >= 2:
            return f"{parts[0]}:{parts[1]}:*:*:*"

    return "[MASKED_IP]"


class SafeLoggerAdapter(logging.LoggerAdapter):
    """
    Logger adapter that automatically scrubs sensitive information from log messages.
    """

    def process(self, msg: Any, kwargs: Dict[str, Any]) -> tuple:
        return mask_sensitive_text(str(msg)), kwargs


def get_safe_logger(name: str = "minecraft_ai.security") -> logging.LoggerAdapter:
    """
    Returns a configured SafeLoggerAdapter for security-compliant logging.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    return SafeLoggerAdapter(logger, {})
