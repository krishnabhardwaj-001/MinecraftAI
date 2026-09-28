import io
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from run_pipeline import (
    get_ollama_diagnostic_message,
    is_ollama_unreachable_error,
    run_cli,
)
from web.app import app


class TestStep21Diagnostics(unittest.TestCase):
    """
    Step 21 Automated Test Suite: Offline Ollama Diagnostic Hardening.
    Verifies user-friendly error diagnostics in CLI and Web interfaces
    when the local Ollama service is unreachable or offline.
    """

    def test_1_is_ollama_unreachable_error_detection(self):
        """
        Verify that various connection error classes and message signatures
        are correctly identified as Ollama unreachable errors.
        """
        # Built-in socket / connection exceptions
        self.assertTrue(is_ollama_unreachable_error(ConnectionRefusedError("Connection refused")))
        self.assertTrue(is_ollama_unreachable_error(ConnectionError("Connection failed")))

        # Text-based indicators
        self.assertTrue(is_ollama_unreachable_error(Exception("Connection refused to 127.0.0.1:11434")))
        self.assertTrue(is_ollama_unreachable_error(Exception("WinError 10061: No connection could be made")))
        self.assertTrue(is_ollama_unreachable_error(Exception("All connection attempts failed")))
        self.assertTrue(is_ollama_unreachable_error(Exception("Is Ollama running?")))
        self.assertTrue(is_ollama_unreachable_error(Exception("dial tcp: lookup localhost: no such host")))

        # Chained exceptions
        try:
            try:
                raise ConnectionRefusedError("Offline")
            except ConnectionRefusedError as inner:
                raise RuntimeError("AI generation failed") from inner
        except RuntimeError as chained:
            self.assertTrue(is_ollama_unreachable_error(chained))

        # httpx if present
        try:
            import httpx
            self.assertTrue(is_ollama_unreachable_error(httpx.ConnectError("Failed to connect")))
            self.assertTrue(is_ollama_unreachable_error(httpx.ConnectTimeout("Connect timeout")))
        except ImportError:
            pass

    def test_2_is_ollama_unreachable_error_false_positives(self):
        """
        Verify that unrelated semantic, validation, or code errors
        are not misclassified as Ollama unreachable errors.
        """
        self.assertFalse(is_ollama_unreachable_error(None))
        self.assertFalse(is_ollama_unreachable_error(ValueError("Invalid item id minecraft:unknown")))
        self.assertFalse(is_ollama_unreachable_error(KeyError("missing_key")))
        self.assertFalse(is_ollama_unreachable_error(TypeError("unsupported operand")))
        self.assertFalse(is_ollama_unreachable_error(RuntimeError("Pack generation failed due to invalid schema")))

    def test_3_get_ollama_diagnostic_message_contents(self):
        """
        Verify that the diagnostic message contains all required actionable explanations:
        unreachable explanation, local endpoint, how to start, and external provider option.
        """
        msg = get_ollama_diagnostic_message()
        self.assertIn("unreachable or not running", msg)
        self.assertIn("http://localhost:11434", msg)
        self.assertIn("ollama serve", msg)
        self.assertIn("OPENAI_API_KEY", msg)

        # Custom endpoint support
        custom_msg = get_ollama_diagnostic_message(endpoint="http://192.168.1.50:11434")
        self.assertIn("http://192.168.1.50:11434", custom_msg)

    def test_4_cli_offline_ollama_diagnostic_display(self):
        """
        Verify that run_cli intercepts unreachable Ollama connection errors,
        prints actionable diagnostics, and exits cleanly with code 1 without a traceback.
        """
        def offline_pipeline(*args, **kwargs):
            raise ConnectionRefusedError("Connection refused to 127.0.0.1:11434")

        captured_stdout = io.StringIO()
        with patch("sys.stdout", captured_stdout):
            exit_code = run_cli(
                args=["give", "me", "diamonds"],
                pipeline_fn=offline_pipeline
            )

        output = captured_stdout.getvalue()
        self.assertEqual(exit_code, 1)
        self.assertIn("[!] OLLAMA SERVICE UNREACHABLE", output)
        self.assertIn("ollama serve", output)
        self.assertIn("http://localhost:11434", output)
        self.assertIn("OPENAI_API_KEY", output)

    def test_5_cli_unexpected_error_handling(self):
        """
        Verify that run_cli handles non-Ollama unexpected errors cleanly.
        """
        def failing_pipeline(*args, **kwargs):
            raise RuntimeError("Disk quota exceeded")

        captured_stdout = io.StringIO()
        with patch("sys.stdout", captured_stdout):
            exit_code = run_cli(
                args=["give", "me", "diamonds"],
                pipeline_fn=failing_pipeline
            )

        output = captured_stdout.getvalue()
        self.assertEqual(exit_code, 1)
        self.assertIn("[-] Unexpected pipeline execution error: Disk quota exceeded", output)
        self.assertNotIn("[!] OLLAMA SERVICE UNREACHABLE", output)

    def test_6_cli_success_behavior_preserved(self):
        """
        Verify that run_cli behaves normally when the pipeline succeeds.
        """
        mock_result = MagicMock()
        mock_result.status = "success"
        mock_result.is_success = True
        mock_result.final_datapack_path = "generated/diamonds_pack"
        mock_result.final_zip_path = "generated/diamonds_pack.zip"
        mock_result.summary.return_value = "Plan completed successfully."

        captured_stdout = io.StringIO()
        with patch("sys.stdout", captured_stdout):
            exit_code = run_cli(
                args=["give", "me", "diamonds"],
                pipeline_fn=lambda *args, **kwargs: mock_result
            )

        output = captured_stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("[+] SUCCESS: Validated Datapack Ready for Minecraft 1.21.11!", output)
        self.assertIn("diamonds_pack.zip", output)

    def test_7_web_api_offline_ollama_returns_503(self):
        """
        Verify that POST /api/generate returns HTTP 503 with actionable diagnostics
        when the Ollama service is unreachable.
        """
        client = TestClient(app)

        with patch("web.app.run_minecraft_pipeline", side_effect=ConnectionRefusedError("Connection refused")):
            response = client.post("/api/generate", json={"request": "make me 10 times faster"})

        self.assertEqual(response.status_code, 503)
        data = response.json()
        detail = data.get("detail", "")
        self.assertIn("unreachable or not running", detail)
        self.assertIn("ollama serve", detail)
        self.assertIn("http://localhost:11434", detail)
        self.assertIn("OPENAI_API_KEY", detail)

    def test_8_web_api_unexpected_error_returns_500(self):
        """
        Verify that POST /api/generate returns standard HTTP 500 on unexpected non-Ollama errors.
        """
        client = TestClient(app)

        with patch("web.app.run_minecraft_pipeline", side_effect=RuntimeError("Internal computation error")):
            response = client.post("/api/generate", json={"request": "make me 10 times faster"})

        self.assertEqual(response.status_code, 500)
        detail = response.json().get("detail", "")
        self.assertIn("Pipeline execution encountered an unexpected error", detail)


if __name__ == "__main__":
    unittest.main()
