"""
security/error_sanitizer.py - User-Facing Error Message Sanitization.

Ensures that API responses never leak internal Python stack traces, filesystem
paths, raw exception representations, environment variables, or server internals.
"""

import re
from typing import Optional, Union
from security.logging import get_safe_logger

logger = get_safe_logger("minecraft_ai.error_sanitizer")

# Patterns matching internal file paths or stack trace markers
STACK_TRACE_PATTERNS = [
    re.compile(r'File\s+"[^"]+",\s+line\s+\d+', re.IGNORECASE),
    re.compile(r"Traceback\s+\(most\s+recent\s+call\s+last\):", re.IGNORECASE),
    re.compile(r"[a-zA-Z]:\\[a-zA-Z0-9_\-\\]+"),
    re.compile(r"/(?:home|usr|var|tmp|etc|app|mnt|root|opt|srv)/[a-zA-Z0-9_\-/]+"),
]


def sanitize_user_error_message(
    error: Union[Exception, str],
    default_message: str = "An unexpected error occurred during datapack processing."
) -> str:
    """
    Converts an internal Python exception into a clean, safe, user-facing error message.

    Logs the original internal error safely for diagnostics while stripping
    all internal system paths and stack traces from the user-facing text.
    """
    raw_text = str(error).strip()

    # Log original error safely
    logger.error("Internal exception caught: %s (%s)", type(error).__name__, raw_text)

    if not raw_text:
        return default_message

    # Check if the text contains a stack trace or raw file path
    for pat in STACK_TRACE_PATTERNS:
        if pat.search(raw_text):
            return default_message

    # If the error is an expected user-facing error, strip system paths, IPs, and URLs
    clean_message = re.sub(r"[a-zA-Z]:\\[^\s'\"]+", "[file]", raw_text)
    clean_message = re.sub(r"/(?:home|usr|var|tmp|etc|app|mnt|root|opt|srv)/[^\s'\"]+", "[file]", clean_message)
    clean_message = re.sub(r"https?://[^\s'\"\)]+", "[endpoint]", clean_message)
    clean_message = re.sub(r"\b(?:localhost|127\.0\.0\.1)(?::\d+)?\b", "[host]", clean_message, flags=re.IGNORECASE)
    clean_message = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b", "[host]", clean_message)

    return clean_message
