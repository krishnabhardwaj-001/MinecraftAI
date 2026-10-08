"""
security/archive_security.py - Datapack Archive & ZIP Security Validation.

Prevents Zip Slip attacks, zip bombs, extraction escapes, and ensures that
all served and processed archives conform to valid Minecraft datapack structure.
"""

import io
import os
import zipfile
from pathlib import Path
from typing import List, Optional, Set, Union
from security.config import DEFAULT_SECURITY_CONFIG, SecurityConfig


class ArchiveSecurityError(ValueError):
    """Raised when an archive fails security validation or structural checks."""
    pass


def validate_archive_entry_name(entry_name: str) -> None:
    """
    Validates a single entry path within an archive for traversal or illegal characters.
    """
    if not entry_name or not isinstance(entry_name, str):
        raise ArchiveSecurityError("Archive entry name cannot be empty.")

    normalized = entry_name.replace("\\", "/")

    # Reject null bytes
    if "\x00" in normalized:
        raise ArchiveSecurityError(f"Null byte detected in archive entry '{entry_name}'.")

    # Reject absolute paths and drive letters
    if normalized.startswith("/") or normalized.startswith("\\"):
        raise ArchiveSecurityError(f"Absolute archive entry '{entry_name}' is prohibited.")

    if len(normalized) > 1 and normalized[1] == ":":
        raise ArchiveSecurityError(f"Drive letter specification in archive entry '{entry_name}' is prohibited.")

    # Reject directory traversal components
    parts = normalized.split("/")
    for part in parts:
        if part == "..":
            raise ArchiveSecurityError(f"Path traversal sequence '..' detected in archive entry '{entry_name}'.")


def validate_zip_archive(
    archive_source: Union[str, Path, bytes, io.BytesIO],
    config: Optional[SecurityConfig] = None
) -> List[str]:
    """
    Performs comprehensive security and structural validation on a datapack ZIP archive.

    Checks:
    1. Integrity: archive is a valid, readable ZIP format.
    2. Zip Slip: no entry contains traversal sequences or escapes root.
    3. Zip Bomb: bounds on file count, single-file size, total size, and compression ratio.
    4. Whitelisted extensions: only permitted datapack resource types.
    5. Datapack structure: requires 'pack.mcmeta' at archive root and 'data/' directory.

    Returns:
        List of verified file entry names.

    Raises:
        ArchiveSecurityError if validation fails.
    """
    cfg = config or DEFAULT_SECURITY_CONFIG

    try:
        if isinstance(archive_source, (str, Path)):
            p = Path(archive_source)
            if not p.exists() or not p.is_file():
                raise ArchiveSecurityError(f"Archive file '{p}' does not exist.")
            zip_context = zipfile.ZipFile(p, "r")
        elif isinstance(archive_source, bytes):
            zip_context = zipfile.ZipFile(io.BytesIO(archive_source), "r")
        elif isinstance(archive_source, io.BytesIO):
            zip_context = zipfile.ZipFile(archive_source, "r")
        else:
            raise ArchiveSecurityError(f"Unsupported archive source type: {type(archive_source)}")
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError) as e:
        raise ArchiveSecurityError(f"Invalid or corrupt ZIP archive: {e}")

    with zip_context as zf:
        infolist = zf.infolist()

        # 1. File count check
        if len(infolist) == 0:
            raise ArchiveSecurityError("Archive is empty.")

        if len(infolist) > cfg.max_zip_file_count:
            raise ArchiveSecurityError(
                f"Archive contains {len(infolist)} entries, exceeding maximum permitted of {cfg.max_zip_file_count}."
            )

        total_uncompressed_bytes = 0
        total_compressed_bytes = 0
        has_pack_mcmeta = False
        has_data_dir = False
        valid_entries: List[str] = []

        for info in infolist:
            name = info.filename
            validate_archive_entry_name(name)

            norm_name = name.replace("\\", "/").rstrip("/")

            # Check for required datapack root resources
            if norm_name == "pack.mcmeta":
                has_pack_mcmeta = True
            if norm_name == "data" or norm_name.startswith("data/"):
                has_data_dir = True

            # If it's a directory entry, proceed
            if info.is_dir() or name.endswith("/"):
                continue

            # 2. Single file size check
            if info.file_size > cfg.max_zip_single_file_bytes:
                raise ArchiveSecurityError(
                    f"Entry '{name}' size ({info.file_size} bytes) exceeds maximum single-file limit of "
                    f"{cfg.max_zip_single_file_bytes} bytes."
                )

            total_uncompressed_bytes += info.file_size
            total_compressed_bytes += info.compress_size

            # 3. Whitelisted extensions check
            ext = Path(name).suffix.lower()
            if ext and ext not in cfg.allowed_archive_extensions:
                raise ArchiveSecurityError(
                    f"Prohibited file type '{ext}' in archive entry '{name}'. "
                    f"Permitted types: {sorted(list(cfg.allowed_archive_extensions))}"
                )

            valid_entries.append(name)

        # 4. Total uncompressed size limit
        if total_uncompressed_bytes > cfg.max_zip_total_uncompressed_bytes:
            raise ArchiveSecurityError(
                f"Total uncompressed archive size ({total_uncompressed_bytes} bytes) exceeds limit of "
                f"{cfg.max_zip_total_uncompressed_bytes} bytes."
            )

        # 5. Zip bomb compression ratio check
        if total_compressed_bytes > 0:
            ratio = total_uncompressed_bytes / total_compressed_bytes
            if ratio > cfg.max_compression_ratio:
                raise ArchiveSecurityError(
                    f"Suspicious compression ratio ({ratio:.1f}:1) exceeds safety threshold of "
                    f"{cfg.max_compression_ratio}:1 (potential zip bomb)."
                )

        # 6. Datapack structure enforcement
        if not has_pack_mcmeta:
            raise ArchiveSecurityError("Archive is missing required 'pack.mcmeta' at root.")

        if not has_data_dir:
            raise ArchiveSecurityError("Archive is missing required 'data/' directory.")

    return valid_entries


def safe_extract_zip(
    archive_path: Union[str, Path],
    destination_dir: Union[str, Path],
    config: Optional[SecurityConfig] = None
) -> Path:
    """
    Safely extracts a verified ZIP archive into destination_dir, ensuring
    every extracted file lands strictly within the destination sandbox.
    """
    dest = Path(destination_dir).resolve()
    dest.mkdir(parents=True, exist_ok=True)

    # First perform complete security validation
    validate_zip_archive(archive_path, config=config)

    with zipfile.ZipFile(archive_path, "r") as zf:
        for member in zf.infolist():
            validate_archive_entry_name(member.filename)
            target_path = (dest / member.filename).resolve()

            # Containment check
            try:
                target_path.relative_to(dest)
            except ValueError:
                raise ArchiveSecurityError(
                    f"Extract path escape detected for '{member.filename}' -> '{target_path}'"
                )

            if member.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
            else:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as source, open(target_path, "wb") as target:
                    target.write(source.read())

    return dest
