"""
test_audit_b2_diagnostics.py - Regression test for B2: Provider unreachable/auth diagnostics in pipeline, CLI, and Web.
"""
import io
import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from pipeline.minecraft_pipeline import run_minecraft_pipeline, MinecraftPipeline
from run_pipeline import run_cli
from web.app import app


class TestAuditB2Diagnostics(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_pipeline_classifies_provider_connection_error(self):
        """Pipeline must classify ConnectionError as provider_unreachable and populate diagnostic."""
        mock_understanding = MagicMock()
        mock_understanding.understand.side_effect = ConnectionError("Connection refused to 127.0.0.1:11434")

        with patch("pipeline.minecraft_pipeline.MinecraftUnderstanding", return_value=mock_understanding):
            pipeline = MinecraftPipeline(provider="ollama")
            result = pipeline.run("Make creepers drop diamonds.")

            self.assertEqual(result.status, "error")
            self.assertEqual(result.error_code, "provider_unreachable")
            self.assertEqual(result.failed_stage, "understanding")
            self.assertIsNotNone(result.diagnostic)
            self.assertIn("ollama serve", result.diagnostic.lower())
            # Ensure errors are sanitized
            for err in result.errors:
                self.assertNotIn("11434", err)

    def test_pipeline_classifies_provider_auth_error(self):
        """Pipeline must classify missing API key as provider_auth."""
        mock_understanding = MagicMock()
        mock_understanding.understand.side_effect = RuntimeError("OLLAMA_API_KEY is required for Ollama Cloud (endpoint: https://ollama.com)")

        with patch("pipeline.minecraft_pipeline.MinecraftUnderstanding", return_value=mock_understanding):
            pipeline = MinecraftPipeline(provider="ollama")
            result = pipeline.run("Make creepers drop diamonds.")

            self.assertEqual(result.status, "error")
            self.assertEqual(result.error_code, "provider_auth")
            self.assertIsNotNone(result.diagnostic)
            self.assertTrue("authentication" in result.diagnostic.lower() or "sign in" in result.diagnostic.lower())

    def test_cli_prints_diagnostic_on_provider_error(self):
        """CLI must print the diagnostic message when pipeline returns a provider error."""
        mock_understanding = MagicMock()
        mock_understanding.understand.side_effect = ConnectionError("Failed to connect to 127.0.0.1:11434")

        with patch("pipeline.minecraft_pipeline.MinecraftUnderstanding", return_value=mock_understanding):
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                exit_code = run_cli(args=["--request", "Make creepers drop diamonds."])
                output = mock_stdout.getvalue()

                self.assertEqual(exit_code, 1)
                self.assertIn("PROVIDER_UNREACHABLE", output)
                self.assertIn("ollama serve", output.lower())

    def test_web_returns_503_with_diagnostic_on_provider_error(self):
        """Web POST /api/generate must return HTTP 503 with the diagnostic message on provider error."""
        mock_understanding = MagicMock()
        mock_understanding.understand.side_effect = ConnectionError("Connection refused to 127.0.0.1:11434")

        with patch("pipeline.minecraft_pipeline.MinecraftUnderstanding", return_value=mock_understanding):
            resp = self.client.post("/api/generate", json={"request": "Make creepers drop diamonds."})

            self.assertEqual(resp.status_code, 503)
            body = resp.json()
            detail = body.get("detail", "")
            self.assertIn("ollama serve", detail.lower())
            # Ensure internal paths are not leaked
            self.assertNotIn("127.0.0.1:11434", detail)


if __name__ == "__main__":
    unittest.main()
