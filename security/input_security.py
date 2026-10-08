"""
security/input_security.py - Input Validation and Sanitization Layer.

Guards against input abuse, oversized payloads, malformed data, null bytes,
and unauthorized script or shell injection patterns.
"""

import re
from typing import Optional, Tuple
from security.config import DEFAULT_SECURITY_CONFIG, SecurityConfig


# Strict pattern for safe datapack naming identifiers
SAFE_IDENTIFIER_REGEX = re.compile(r"^[a-zA-Z0-9_\-]+$")

# Strict pattern for Minecraft version strings
VERSION_REGEX = re.compile(r"^\d+\.\d+(?:\.\d+)?$")

# Disallowed dangerous control characters (excluding standard whitespace \t, \n, \r)
DANGEROUS_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class InputValidationError(ValueError):
    """Raised when an input fails security validation checks."""
    pass


def validate_prompt(
    text: str,
    config: Optional[SecurityConfig] = None
) -> str:
    """
    Validates and normalizes user-provided natural-language request prompt.

    Enforces:
    - Non-empty, non-whitespace content.
    - Minimum and maximum character length.
    - Zero null bytes or malicious binary control characters.
    - Normalized whitespace.
    """
    cfg = config or DEFAULT_SECURITY_CONFIG

    if not isinstance(text, str):
        raise InputValidationError("Prompt must be a text string.")

    cleaned = text.strip()

    if not cleaned:
        raise InputValidationError("Prompt cannot be empty or whitespace only.")

    if len(cleaned) < cfg.min_prompt_length:
        raise InputValidationError(
            f"Prompt is too short ({len(cleaned)} characters). Minimum length is {cfg.min_prompt_length} characters."
        )

    if len(cleaned) > cfg.max_prompt_length:
        raise InputValidationError(
            f"Prompt exceeds maximum permitted length of {cfg.max_prompt_length} characters (received {len(cleaned)})."
        )

    # Check for null bytes and dangerous control characters
    if "\x00" in text:
        raise InputValidationError("Null bytes are strictly prohibited in input.")

    if DANGEROUS_CONTROL_CHARS.search(text):
        raise InputValidationError("Input contains prohibited control characters.")

    # Prevent HTML script tag injection in prompt
    if re.search(r"<\s*script\b", text, re.IGNORECASE):
        raise InputValidationError("Script tags and HTML execution sequences are prohibited in prompts.")

    return cleaned


def validate_version_string(
    version: str,
    supported_versions: Optional[set] = None
) -> str:
    """
    Validates a Minecraft version identifier.

    Enforces:
    - Standard semantic version pattern (e.g. '1.21.11', '1.21.1').
    - Membership in the registered supported versions set if provided.
    """
    if not isinstance(version, str):
        raise InputValidationError("Version must be a string.")

    v_clean = version.strip()
    if not VERSION_REGEX.match(v_clean):
        raise InputValidationError(f"Invalid Minecraft version format: '{v_clean}'.")

    if supported_versions is not None and v_clean not in supported_versions:
        raise InputValidationError(
            f"Unsupported Minecraft version '{v_clean}'. Supported versions: {sorted(list(supported_versions))}"
        )

    return v_clean


def sanitize_datapack_name(
    name: str,
    default: str = "custom_datapack",
    max_len: int = 48
) -> str:
    """
    Sanitizes and bounds an identifier for use in file and datapack naming.

    Transforms illegal characters to underscores, strips leading/trailing
    punctuation, and truncates to max_len.
    """
    if not name or not isinstance(name, str):
        return default

    # Lowercase and replace spaces/unapproved chars with underscore
    clean = re.sub(r"[^a-zA-Z0-9_\-]", "_", name.strip().lower())
    clean = re.sub(r"_+", "_", clean).strip("_")

    if not clean:
        return default

    return clean[:max_len]


def validate_clarification_answer(
    answer: str,
    max_len: int = 500
) -> str:
    """
    Validates user response to a clarification inquiry.
    """
    if not isinstance(answer, str):
        raise InputValidationError("Clarification answer must be a string.")

    cleaned = answer.strip()
    if not cleaned:
        raise InputValidationError("Clarification answer cannot be empty.")

    if len(cleaned) > max_len:
        raise InputValidationError(f"Clarification answer exceeds maximum length of {max_len} characters.")

    if "\x00" in cleaned or DANGEROUS_CONTROL_CHARS.search(cleaned):
        raise InputValidationError("Prohibited control characters in clarification answer.")

    return cleaned
