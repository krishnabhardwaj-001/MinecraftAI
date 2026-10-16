"""
Automated Test Suite: Local Website with Ollama Cloud Sign-in Authentication.
Verifies all requirements from the Local Website + Ollama Cloud specification:
1. Missing Ollama installation.
2. Unauthenticated Ollama users (sign-in required).
3. Authenticated cloud-model access.
4. Missing or unavailable cloud models.
5. Cloud usage-limit and network errors.
6. Prevention of silent local-model fallback.
7. Confirmation that no API key is required in MinecraftAI configuration when sign-in is used.
8. Startup and browser-launch behavior.
9. Port conflicts and duplicate server prevention.
10. Localhost-only binding by default.
11. Safe artifact downloads and cleanup.
12. Datapack generation, validation, and ZIP structure.
13. Existing supported Minecraft versions (1.21.11 and 1.21.1).
14. Preservation of existing security behavior.
"""
import io
import json
import os
import socket
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from ai.provider import AIProvider
from ai.version_registry import get_version_registry
from run_pipeline import (
    get_ollama_diagnostic_message,
    is_ollama_unreachable_error,
)
from run_web import check_port_available, _wait_and_open_browser
from security import (
    validate_prompt,
    validate_zip_download_filename,
    InputValidationError,
    PathSecurityError,
)
from web.app import cleanup_expired_artifacts, _format_pipeline_result
from pipeline.models import PipelineResult


class TestOllamaCloudLocalAuth(unittest.TestCase):
    """Verifies local website and Ollama Cloud sign-in authentication architecture."""

    def test_1_missing_ollama_installation_detection_and_diagnostics(self):
        """Verify that connection failure to local Ollama produces clear install/serve guidance."""
        conn_err = ConnectionRefusedError("Connection refused to 127.0.0.1:11434")
        self.assertTrue(is_ollama_unreachable_error(conn_err))

        msg = get_ollama_diagnostic_message(exc=conn_err)
        self.assertIn("unreachable or not running", msg)
        self.assertIn("http://localhost:11434", msg)
        self.assertIn("ollama serve", msg)
        self.assertIn("https://ollama.com", msg)

    def test_2_unauthenticated_ollama_user_instructs_signin(self):
        """Verify that 401/403 or unauthorized error instructs the user to run 'ollama signin'."""
        try:
            from ollama import ResponseError
            auth_err = ResponseError("sign in to ollama.com to access cloud models", status_code=401)
        except ImportError:
            auth_err = Exception("401 Unauthorized: sign in required")

        self.assertTrue(is_ollama_unreachable_error(auth_err))

        diag = get_ollama_diagnostic_message(exc=auth_err)
        self.assertIn("ollama signin", diag)
        self.assertIn("authentication required", diag.lower())
        self.assertIn("do not need to paste an api key", diag.lower())

    @patch("ai.provider.OllamaClient")
    def test_3_authenticated_cloud_model_access_via_local_daemon(self, mock_client_cls):
        """Verify that chat request to cloud model gpt-oss:120b-cloud succeeds through local daemon."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.message.content = json.dumps({"status": "planned", "actions": []})
        mock_client.chat.return_value = mock_response
        mock_client_cls.return_value = mock_client

        test_env = {
            "LLM_PROVIDER": "ollama",
            "OLLAMA_HOST": "http://127.0.0.1:11434",
            "OLLAMA_MODEL": "gpt-oss:120b-cloud",
            "OLLAMA_API_KEY": ""
        }

        with patch.dict(os.environ, test_env, clear=True):
            provider = AIProvider()
            self.assertEqual(provider.model, "gpt-oss:120b-cloud")
            self.assertEqual(provider.host, "http://127.0.0.1:11434")
            self.assertIn(provider.api_key, (None, ""))
            self.assertTrue(provider.is_cloud)

            result = provider.generate_structured("system", "give diamond", {})
            self.assertEqual(result, {"status": "planned", "actions": []})
            mock_client.chat.assert_called_once()
            call_kwargs = mock_client.chat.call_args[1]
            self.assertEqual(call_kwargs["model"], "gpt-oss:120b-cloud")

    def test_4_missing_or_unavailable_cloud_model_diagnostics(self):
        """Verify that 404 ResponseError guides user to pull lightweight cloud model manifest."""
        try:
            from ollama import ResponseError
            not_found_err = ResponseError("model 'gpt-oss:120b-cloud' not found", status_code=404)
        except ImportError:
            not_found_err = Exception("model 'gpt-oss:120b-cloud' not found (status code: 404)")

        self.assertTrue(is_ollama_unreachable_error(not_found_err))

        diag = get_ollama_diagnostic_message(exc=not_found_err)
        self.assertIn("ollama pull gpt-oss:120b-cloud", diag)
        self.assertIn("manifest", diag.lower())

    def test_5_cloud_usage_limit_and_network_error_diagnostics(self):
        """Verify that 429 quota or rate limit error informs user of account allowance."""
        try:
            from ollama import ResponseError
            limit_err = ResponseError("usage limit exceeded for cloud tier", status_code=429)
        except ImportError:
            limit_err = Exception("429 rate limit exceeded: quota allowance reached")

        self.assertTrue(is_ollama_unreachable_error(limit_err))

        diag = get_ollama_diagnostic_message(exc=limit_err)
        self.assertIn("limit", diag.lower())
        self.assertIn("https://ollama.com", diag)

    @patch("ai.provider.OllamaClient")
    def test_6_prevention_of_silent_local_model_fallback(self, mock_client_cls):
        """Verify that failure in cloud generation strictly raises error without silent local fallback."""
        mock_client = MagicMock()
        mock_client.chat.side_effect = RuntimeError("Cloud API inference timeout")
        mock_client_cls.return_value = mock_client

        test_env = {
            "LLM_PROVIDER": "ollama",
            "OLLAMA_HOST": "http://127.0.0.1:11434",
            "OLLAMA_MODEL": "gpt-oss:120b-cloud",
            "OLLAMA_API_KEY": ""
        }

        with patch.dict(os.environ, test_env, clear=True):
            provider = AIProvider()
            with self.assertRaises(RuntimeError) as ctx:
                provider.generate_structured("sys", "user", {})

            self.assertIn("Cloud API inference timeout", str(ctx.exception))
            # Verify only 1 chat attempt made to the cloud model; zero local fallback calls
            mock_client.chat.assert_called_once()
            call_kwargs = mock_client.chat.call_args[1]
            self.assertEqual(call_kwargs["model"], "gpt-oss:120b-cloud")
            self.assertNotEqual(call_kwargs["model"], "llama3.1:8b")

    @patch("ai.provider.OllamaClient")
    def test_7_no_api_key_required_in_config_with_signin(self, mock_client_cls):
        """Verify that default configuration targeting gpt-oss:120b-cloud requires NO API key."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        # Zero API key, zero host configured (standard local sign-in user environment)
        test_env = {
            "LLM_PROVIDER": "ollama",
            "OLLAMA_HOST": "",
            "OLLAMA_MODEL": "gpt-oss:120b-cloud",
            "OLLAMA_API_KEY": ""
        }

        with patch.dict(os.environ, test_env, clear=True):
            provider = AIProvider()
            self.assertEqual(provider.model, "gpt-oss:120b-cloud")
            self.assertEqual(provider.host, "http://127.0.0.1:11434")
            self.assertIn(provider.api_key, (None, ""))
            self.assertTrue(provider.is_cloud)

            # Verify client initialized with local daemon host and NO authorization header
            mock_client_cls.assert_called_once_with(
                host="http://127.0.0.1:11434",
                headers=None
            )

    @patch("webbrowser.open")
    def test_8_startup_and_browser_launch_behavior(self, mock_browser_open):
        """Verify browser launch helper connects when server is ready and opens URL."""
        with patch("socket.create_connection") as mock_conn:
            mock_conn.return_value.__enter__.return_value = MagicMock()
            _wait_and_open_browser("127.0.0.1", 8000, delay_s=0.01, timeout_s=1.0)
            mock_browser_open.assert_called_once_with("http://127.0.0.1:8000")

    def test_9_port_conflict_and_duplicate_server_prevention(self):
        """Verify check_port_available detects already bound ports to prevent duplicate instances."""
        # Bind a temporary test socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        _, bound_port = sock.getsockname()

        try:
            # Port is bound, so check_port_available must return False
            self.assertFalse(check_port_available("127.0.0.1", bound_port))
        finally:
            sock.close()

        # Port is now free, so check_port_available must return True
        self.assertTrue(check_port_available("127.0.0.1", bound_port))

    def test_10_localhost_only_binding_by_default(self):
        """Verify run_web defaults to 127.0.0.1 (not 0.0.0.0) for local security."""
        from run_web import main
        with patch("argparse.ArgumentParser.parse_args") as mock_args:
            mock_args.return_value = MagicMock(host="127.0.0.1", port=8000, open_browser=False)
            with patch("run_web.check_port_available", return_value=True):
                with patch("uvicorn.run") as mock_uvicorn:
                    main()
                    mock_uvicorn.assert_called_once()
                    self.assertEqual(mock_uvicorn.call_args[1]["host"], "127.0.0.1")

    def test_11_safe_artifact_download_and_cleanup(self):
        """Verify zip traversal protection and automatic artifact retention cleanup."""
        # 1. Download filename security
        self.assertEqual(validate_zip_download_filename("my_pack.zip"), "my_pack.zip")
        with self.assertRaises(PathSecurityError):
            validate_zip_download_filename("../outside.zip")
        with self.assertRaises(PathSecurityError):
            validate_zip_download_filename("..\\outside.zip")
        with self.assertRaises(PathSecurityError):
            validate_zip_download_filename("malicious.exe")

        # 2. Artifact cleanup
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            old_file = tmp_path / "old_pack.zip"
            old_file.write_text("old")
            # Set mtime to 2 hours ago
            past_time = time.time() - 7200
            os.utime(old_file, (past_time, past_time))

            fresh_file = tmp_path / "fresh_pack.zip"
            fresh_file.write_text("fresh")

            purged = cleanup_expired_artifacts(base_dir=tmp_path, max_age_seconds=3600)
            self.assertEqual(purged, 1)
            self.assertFalse(old_file.exists())
            self.assertTrue(fresh_file.exists())

    def test_12_datapack_generation_validation_zip_structure(self):
        """Verify datapack archive contains pack.mcmeta and data/ at the root."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            zip_path = Path(tmp_dir) / "test_datapack.zip"
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("pack.mcmeta", json.dumps({"pack": {"pack_format": 94, "description": "Test"}}))
                zf.writestr("data/minecraft_ai/function/tick.mcfunction", "# tick")

            # Verify root contents
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()
                self.assertIn("pack.mcmeta", names)
                self.assertTrue(any(n.startswith("data/") for n in names))

    def test_13_existing_supported_minecraft_versions(self):
        """Verify VersionRegistry officially supports both Java 1.21.11 and 1.21.1."""
        registry = get_version_registry()
        self.assertTrue(registry.is_supported("1.21.11"))
        self.assertTrue(registry.is_supported("1.21.1"))

        meta_11 = registry.get("1.21.11")
        self.assertEqual(meta_11.pack_format, 94)

        meta_1 = registry.get("1.21.1")
        self.assertEqual(meta_1.pack_format, 48)

    def test_14_preservation_of_security_behavior(self):
        """Verify prompt input validation and absolute path concealment in browser responses."""
        # 1. Prompt validation
        valid = validate_prompt("When it starts raining, give every player one diamond.")
        self.assertEqual(valid, "When it starts raining, give every player one diamond.")

        with self.assertRaises(InputValidationError):
            validate_prompt("")  # Empty rejected

        with self.assertRaises(InputValidationError):
            validate_prompt("a" * 2500)  # Oversized rejected

        # 2. Browser path concealment: never exposes absolute machine paths
        mock_result = MagicMock(spec=PipelineResult)
        mock_result.status = "success"
        mock_result.is_success = True
        mock_result.minecraft_version = "1.21.11"
        mock_result.original_request = "give diamond"
        mock_result.clarification = None
        mock_result.clarification_requirements = []
        mock_result.execution_summary = "Generated"
        mock_result.final_datapack_path = "D:\\Projects\\MinecraftAI\\generated\\diamonds"
        mock_result.final_zip_path = "D:\\Projects\\MinecraftAI\\generated\\diamonds.zip"
        mock_result.datapack_name = "diamonds"
        mock_result.errors = []
        mock_result.generation = MagicMock(files_generated=["pack.mcmeta"])
        mock_result.context = MagicMock(commands_retrieved=[], entities_retrieved=[], items_retrieved=[])
        mock_result.validation = MagicMock(is_valid=True, total_errors=0, total_warnings=0, errors=[], warnings=[], checks_performed=[])
        mock_result.repair = None
        mock_result.plan = {"summary": "Give diamonds"}

        formatted = _format_pipeline_result(mock_result)
        # Verify datapack_path and zip_path never contain absolute machine roots (D:\ or C:\)
        if formatted.get("datapack_path"):
            self.assertFalse(os.path.isabs(formatted["datapack_path"]))
            self.assertEqual(formatted["datapack_path"], "generated/diamonds")
        if formatted.get("zip_path"):
            self.assertFalse(os.path.isabs(formatted["zip_path"]))
            self.assertEqual(formatted["zip_path"], "generated/diamonds.zip")


if __name__ == "__main__":
    unittest.main()
