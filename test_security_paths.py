"""
Security Tests: Path Traversal and Filesystem Sandboxing.
Tests protection against directory traversal, absolute paths, UNC paths,
drive letters, and sandbox escapes.
"""

from pathlib import Path
import pytest
from security.path_security import (
    resolve_safe_path,
    ensure_safe_output_directory,
    validate_zip_download_filename,
    is_safe_filename,
    PathSecurityError,
)
from security.config import SecurityConfig


class TestPathSecurity:
    """Tests for filesystem sandbox boundaries."""

    @pytest.fixture
    def sandbox_dir(self, tmp_path):
        sb = tmp_path / "sandbox"
        sb.mkdir()
        return sb

    def test_safe_child_path_resolves(self, sandbox_dir):
        resolved = resolve_safe_path("my_pack", sandbox_dir)
        assert resolved.parent.resolve() == sandbox_dir.resolve()
        assert resolved.name == "my_pack"

    def test_relative_subfolder_resolves_inside(self, sandbox_dir):
        resolved = resolve_safe_path("sub/folder/pack", sandbox_dir)
        assert str(resolved.resolve()).startswith(str(sandbox_dir.resolve()))

    def test_parent_traversal_rejected(self, sandbox_dir):
        with pytest.raises(PathSecurityError, match="Path traversal detected"):
            resolve_safe_path("../secret.txt", sandbox_dir)

    def test_nested_parent_traversal_rejected(self, sandbox_dir):
        with pytest.raises(PathSecurityError, match="Path traversal detected"):
            resolve_safe_path("foo/../../secret.txt", sandbox_dir)

    def test_windows_backslashes_traversal_rejected(self, sandbox_dir):
        with pytest.raises(PathSecurityError, match="Path traversal detected"):
            resolve_safe_path("..\\secret.txt", sandbox_dir)

    def test_multi_dot_traversal_rejected(self, sandbox_dir):
        with pytest.raises(PathSecurityError, match="Path traversal detected"):
            resolve_safe_path("..../secret.txt", sandbox_dir)

    def test_absolute_linux_path_rejected(self, sandbox_dir):
        with pytest.raises(PathSecurityError, match="(Absolute or root path|Absolute path)"):
            resolve_safe_path("/etc/passwd", sandbox_dir)

    def test_absolute_windows_path_rejected(self, sandbox_dir):
        with pytest.raises(PathSecurityError, match="(Absolute path|Drive letter)"):
            resolve_safe_path("C:\\Windows\\System32\\cmd.exe", sandbox_dir)

    def test_unc_path_rejected(self, sandbox_dir):
        with pytest.raises(PathSecurityError, match="UNC share"):
            resolve_safe_path("\\\\evilserver\\share\\data", sandbox_dir)

    def test_null_byte_path_rejected(self, sandbox_dir):
        with pytest.raises(PathSecurityError, match="Null bytes"):
            resolve_safe_path("valid\x00/../../secret", sandbox_dir)

    def test_ensure_safe_output_directory_approved(self, tmp_path):
        out = tmp_path / "custom_out"
        out.mkdir()
        cfg = SecurityConfig(allowed_output_dirs=[tmp_path])
        checked = ensure_safe_output_directory(out, cfg)
        assert checked.resolve() == out.resolve()

    def test_ensure_safe_output_directory_unapproved_fails(self, tmp_path):
        outside = tmp_path / "outside"
        outside.mkdir()
        approved = tmp_path / "inside"
        approved.mkdir()
        cfg = SecurityConfig(allowed_output_dirs=[approved])
        with pytest.raises(PathSecurityError, match="outside approved generation directories"):
            ensure_safe_output_directory(outside, cfg)

    def test_validate_zip_download_filename_valid(self):
        assert validate_zip_download_filename("my_pack.zip") == "my_pack.zip"

    def test_validate_zip_download_filename_traversal_fails(self):
        with pytest.raises(PathSecurityError):
            validate_zip_download_filename("../other.zip")

    def test_validate_zip_download_filename_wrong_extension_fails(self):
        with pytest.raises(PathSecurityError, match="Invalid archive filename"):
            validate_zip_download_filename("secret.txt")
