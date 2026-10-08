"""
Security Tests: Input Validation and Sanitization.
Tests prompt boundary checks, character filtering, version validation,
and safe naming sanitizers.
"""

import pytest
from security.input_security import (
    validate_prompt,
    validate_version_string,
    validate_clarification_answer,
    sanitize_datapack_name,
    InputValidationError,
)
from security.path_security import (
    is_safe_filename,
    validate_zip_download_filename,
    PathSecurityError,
)


class TestInputValidation:
    """Tests for prompt validation and sanitization."""

    def test_valid_prompt_passes(self):
        prompt = "When it rains, give every player one diamond."
        cleaned = validate_prompt(prompt)
        assert cleaned == prompt

    def test_empty_prompt_rejected(self):
        with pytest.raises(InputValidationError, match="cannot be empty"):
            validate_prompt("")

    def test_whitespace_only_prompt_rejected(self):
        with pytest.raises(InputValidationError, match="cannot be empty"):
            validate_prompt("   \n\t   ")

    def test_oversized_prompt_rejected(self):
        oversized = "a" * 2001
        with pytest.raises(InputValidationError, match="exceeds maximum permitted length"):
            validate_prompt(oversized)

    def test_null_byte_prompt_rejected(self):
        with pytest.raises(InputValidationError, match="Null bytes are strictly prohibited"):
            validate_prompt("give diamond \x00 drop")

    def test_excessive_control_chars_rejected(self):
        malicious = "test\x01\x02\x03\x04\x05\x06\x07\x08"
        with pytest.raises(InputValidationError, match="contains prohibited control characters"):
            validate_prompt(malicious)

    def test_script_tag_injection_rejected(self):
        xss_prompt = "give diamond <script>alert('xss')</script>"
        with pytest.raises(InputValidationError, match="Script tags"):
            validate_prompt(xss_prompt)

    def test_valid_clarification_answer(self):
        ans = "5 diamonds"
        cleaned = validate_clarification_answer(ans)
        assert cleaned == "5 diamonds"

    def test_oversized_clarification_rejected(self):
        oversized = "x" * 501
        with pytest.raises(InputValidationError, match="exceeds maximum length"):
            validate_clarification_answer(oversized)

    def test_empty_clarification_rejected(self):
        with pytest.raises(InputValidationError, match="cannot be empty"):
            validate_clarification_answer("   ")


class TestVersionValidation:
    """Tests for Minecraft version validation."""

    def test_supported_versions_pass(self):
        supported = {"1.21.11", "1.21.1"}
        assert validate_version_string("1.21.11", supported) == "1.21.11"
        assert validate_version_string("1.21.1", supported) == "1.21.1"

    def test_unsupported_version_rejected(self):
        supported = {"1.21.11", "1.21.1"}
        with pytest.raises(InputValidationError, match="Unsupported Minecraft version"):
            validate_version_string("1.19.4", supported)

    def test_malformed_version_rejected(self):
        supported = {"1.21.11", "1.21.1"}
        with pytest.raises(InputValidationError, match="Invalid Minecraft version format"):
            validate_version_string("1.21.11; DROP TABLE", supported)

    def test_path_traversal_version_rejected(self):
        supported = {"1.21.11", "1.21.1"}
        with pytest.raises(InputValidationError, match="Invalid Minecraft version format"):
            validate_version_string("../../../etc/passwd", supported)


class TestNamingSanitization:
    """Tests for safe identifier and filename sanitization."""

    def test_sanitize_normal_name(self):
        assert sanitize_datapack_name("diamond_rain") == "diamond_rain"

    def test_sanitize_spaces_and_special_chars(self):
        assert sanitize_datapack_name("Diamond Rain & Gold!") == "diamond_rain_gold"

    def test_sanitize_traversal_name(self):
        cleaned = sanitize_datapack_name("../../secret_pack")
        assert ".." not in cleaned
        assert "/" not in cleaned
        assert cleaned == "secret_pack"

    def test_sanitize_empty_name_defaults(self):
        assert sanitize_datapack_name("!@#$%^") == "custom_datapack"

    def test_valid_safe_filename(self):
        assert is_safe_filename("diamond_rain.zip") is True
        assert validate_zip_download_filename("diamond_rain.zip") == "diamond_rain.zip"

    def test_traversal_filename_rejected(self):
        assert is_safe_filename("../diamond_rain.zip") is False
        with pytest.raises(PathSecurityError):
            validate_zip_download_filename("../diamond_rain.zip")

    def test_windows_separator_filename_rejected(self):
        assert is_safe_filename("..\\diamond_rain.zip") is False
        with pytest.raises(PathSecurityError):
            validate_zip_download_filename("..\\diamond_rain.zip")

    def test_disallowed_extension_rejected(self):
        with pytest.raises(PathSecurityError, match="Invalid archive filename"):
            validate_zip_download_filename("exploit.exe")
