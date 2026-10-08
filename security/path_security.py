"""
security/path_security.py - Path Traversal Prevention and Filesystem Sandbox Guard.

Guards against directory traversal (../, ..\\), Windows drive escapes (C:, D:),
UNC shares (\\\\host\\share), symlink attacks, and arbitrary filesystem access.
"""

import os
import re
from pathlib import Path
from typing import Optional, Union
from security.config import DEFAULT_SECURITY_CONFIG, SecurityConfig


# Strict pattern for downloadable ZIP filenames
SAFE_ZIP_FILENAME_REGEX = re.compile(r"^[a-zA-Z0-9_\-]+\.zip$")


class PathSecurityError(PermissionError):
    """Raised when an unapproved filesystem access or path traversal attempt is detected."""
    pass


def is_safe_filename(filename: str) -> bool:
    """
    Checks if a filename consists solely of safe characters without path separators.
    """
    if not filename or not isinstance(filename, str):
        return False

    # Disallow null bytes, slashes, backslashes, colons
    if any(c in filename for c in ("\x00", "/", "\\", ":", "\n", "\r")):
        return False

    # Disallow current and parent directory markers
    if filename in (".", ".."):
        return False

    return True


def validate_zip_download_filename(filename: str) -> str:
    """
    Validates that a filename requested for download is strictly a safe .zip artifact name.
    Rejects path components, double extensions, non-alphanumeric characters, and path traversal.
    """
    if not isinstance(filename, str) or not filename.strip():
        raise PathSecurityError("Filename cannot be empty.")

    cleaned = filename.strip()

    if not SAFE_ZIP_FILENAME_REGEX.match(cleaned):
        raise PathSecurityError(
            f"Invalid archive filename '{cleaned}'. Filenames must be alphanumeric with a single .zip extension."
        )

    # Secondary check: ensure no directory traversal tokens
    if ".." in cleaned or "/" in cleaned or "\\" in cleaned:
        raise PathSecurityError("Path traversal tokens detected in filename.")

    return cleaned


def resolve_safe_path(
    untrusted_target: Union[str, Path],
    base_directory: Union[str, Path],
    allow_creation: bool = False
) -> Path:
    """
    Resolves an untrusted target path within a designated base directory sandbox.

    Guarantees:
    - The target path resolves strictly inside base_directory.
    - Path traversal sequences (../, ..\\) cannot escape the sandbox.
    - Windows drive prefixes, UNC shares, and absolute roots are rejected.

    Raises:
    - PathSecurityError if the resolved path falls outside base_directory.
    """
    base_path = Path(base_directory).resolve()

    target_str = str(untrusted_target).strip()
    if not target_str:
        raise PathSecurityError("Target path cannot be empty.")

    # Guard against null bytes
    if "\x00" in target_str:
        raise PathSecurityError("Null bytes are prohibited in file paths.")

    # Explicitly reject UNC shares, drive letters, and root/absolute paths
    if target_str.startswith("\\\\") or target_str.startswith("//"):
        raise PathSecurityError(f"UNC share specification '{target_str}' is prohibited.")

    if re.match(r"^[a-zA-Z]:", target_str):
        raise PathSecurityError(f"Drive letter specification '{target_str}' is prohibited.")

    if os.path.isabs(target_str) or target_str.startswith("/") or target_str.startswith("\\"):
        raise PathSecurityError(f"Absolute or root path '{target_str}' is prohibited in untrusted path specification.")

    # Resolve combined path
    resolved_target = (base_path / target_str).resolve()

    # Verify containment within sandbox
    try:
        resolved_target.relative_to(base_path)
    except ValueError:
        raise PathSecurityError(
            f"Path traversal detected: '{target_str}' attempts to resolve outside sandbox '{base_path}'."
        )

    return resolved_target


def ensure_safe_output_directory(
    output_dir: Union[str, Path],
    config: Optional[SecurityConfig] = None
) -> Path:
    """
    Ensures that a specified output directory resides within the configured
    allowed output directories for datapack generation.
    """
    cfg = config or DEFAULT_SECURITY_CONFIG
    resolved_out = Path(output_dir).resolve()

    # Verify against approved output directories
    is_allowed = False
    for approved in cfg.allowed_output_dirs:
        approved_resolved = approved.resolve()
        try:
            resolved_out.relative_to(approved_resolved)
            is_allowed = True
            break
        except ValueError:
            continue

    if not is_allowed:
        raise PathSecurityError(
            f"Output directory '{resolved_out}' is outside approved generation directories: "
            f"{[str(p) for p in cfg.allowed_output_dirs]}"
        )

    return resolved_out
