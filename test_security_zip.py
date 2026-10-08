"""
Security Tests: Archive and ZIP Security.
Tests Zip Slip prevention, archive entry sanitization, zip bomb limits,
required datapack structure verification, and safe extraction.
"""

import io
import json
import zipfile
from pathlib import Path
import pytest

from security.archive_security import (
    validate_zip_archive,
    safe_extract_zip,
    ArchiveSecurityError,
)
from security.config import SecurityConfig


def create_test_datapack_zip(dest_path: Path, entries: dict[str, str | bytes] | None = None):
    """Helper to create a well-formed datapack ZIP."""
    if entries is None:
        mcmeta = json.dumps({
            "pack": {
                "pack_format": 48,
                "description": "Test Datapack"
            }
        })
        entries = {
            "pack.mcmeta": mcmeta,
            "data/minecraft/tags/function/load.json": '{"values":["test:load"]}',
            "data/test/function/load.mcfunction": "say Hello",
        }

    with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in entries.items():
            if isinstance(content, str):
                zf.writestr(name, content)
            else:
                zf.writestr(name, content)


class TestArchiveSecurity:
    """Tests for ZIP archive security checks and extraction."""

    def test_valid_datapack_zip_passes_validation(self, tmp_path):
        zip_path = tmp_path / "valid.zip"
        create_test_datapack_zip(zip_path)
        # Should not raise
        validate_zip_archive(zip_path)

    def test_missing_pack_mcmeta_rejected(self, tmp_path):
        zip_path = tmp_path / "no_mcmeta.zip"
        entries = {
            "data/test/function/load.mcfunction": "say hi"
        }
        create_test_datapack_zip(zip_path, entries)
        with pytest.raises(ArchiveSecurityError, match="missing required 'pack.mcmeta'"):
            validate_zip_archive(zip_path)

    def test_missing_data_directory_rejected(self, tmp_path):
        zip_path = tmp_path / "no_data.zip"
        entries = {
            "pack.mcmeta": '{"pack":{"pack_format":48,"description":"test"}}',
            "other.txt": "just some text"
        }
        create_test_datapack_zip(zip_path, entries)
        with pytest.raises(ArchiveSecurityError, match="missing required 'data/' directory"):
            validate_zip_archive(zip_path)

    def test_zip_slip_relative_traversal_entry_rejected(self, tmp_path):
        zip_path = tmp_path / "zip_slip.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("pack.mcmeta", '{"pack":{"pack_format":48,"description":"test"}}')
            zf.writestr("data/test.json", "{}")
            zf.writestr("../../outside.txt", "escaped content")

        with pytest.raises(ArchiveSecurityError, match="(Path traversal sequence|Path traversal in archive entry)"):
            validate_zip_archive(zip_path)

    def test_absolute_entry_rejected(self, tmp_path):
        zip_path = tmp_path / "abs_entry.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("pack.mcmeta", '{"pack":{"pack_format":48,"description":"test"}}')
            zf.writestr("data/test.json", "{}")
            zf.writestr("/etc/passwd", "root:x:0:0")

        with pytest.raises(ArchiveSecurityError, match="(Absolute archive entry|Absolute path)"):
            validate_zip_archive(zip_path)

    def test_windows_absolute_entry_rejected(self, tmp_path):
        zip_path = tmp_path / "win_abs.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("pack.mcmeta", '{"pack":{"pack_format":48,"description":"test"}}')
            zf.writestr("data/test.json", "{}")
            zf.writestr("C:\\Windows\\System32\\cmd.exe", "fake")

        with pytest.raises(ArchiveSecurityError, match="(Absolute path|Drive letter|Prohibited file type)"):
            validate_zip_archive(zip_path)

    def test_disallowed_extension_in_zip_rejected(self, tmp_path):
        zip_path = tmp_path / "bad_ext.zip"
        entries = {
            "pack.mcmeta": '{"pack":{"pack_format":48,"description":"test"}}',
            "data/malicious.py": "import os; os.system('echo bad')",
        }
        create_test_datapack_zip(zip_path, entries)
        with pytest.raises(ArchiveSecurityError, match="Prohibited file type"):
            validate_zip_archive(zip_path)

    def test_corrupt_zip_file_rejected(self, tmp_path):
        corrupt = tmp_path / "corrupt.zip"
        corrupt.write_bytes(b"NOT A REAL ZIP ARCHIVE DATA")
        with pytest.raises(ArchiveSecurityError, match="Invalid or corrupt"):
            validate_zip_archive(corrupt)

    def test_zip_bomb_uncompressed_size_limit(self, tmp_path):
        zip_path = tmp_path / "bomb.zip"
        custom_cfg = SecurityConfig(max_zip_total_uncompressed_bytes=1000)
        entries = {
            "pack.mcmeta": '{"pack":{"pack_format":48,"description":"test"}}',
            "data/large.json": "A" * 5000,
        }
        create_test_datapack_zip(zip_path, entries)
        with pytest.raises(ArchiveSecurityError, match="Total uncompressed archive size"):
            validate_zip_archive(zip_path, config=custom_cfg)

    def test_safe_extract_zip_extracts_cleanly(self, tmp_path):
        zip_path = tmp_path / "good.zip"
        create_test_datapack_zip(zip_path)

        extract_dest = tmp_path / "extracted"
        safe_extract_zip(zip_path, extract_dest)

        assert (extract_dest / "pack.mcmeta").exists()
        assert (extract_dest / "data" / "test" / "function" / "load.mcfunction").exists()
        assert (extract_dest / "data" / "test" / "function" / "load.mcfunction").read_text() == "say Hello"

    def test_safe_extract_zip_prevents_escape(self, tmp_path):
        zip_path = tmp_path / "malicious.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("../../outside.txt", "payload")

        extract_dest = tmp_path / "extracted_bad"
        with pytest.raises(ArchiveSecurityError):
            safe_extract_zip(zip_path, extract_dest)
        assert not (tmp_path / "outside.txt").exists()
