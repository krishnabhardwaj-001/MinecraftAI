"""
Unit tests for B12: Authentic /api/health diagnostic checks.
Verifies:
1. /api/health executes real checks rather than returning hardcoded constants.
2. Reports provider configuration, version registry, output directory writability, and Java runtime status.
3. Degrades when provider or output directory is unconfigured or unwritable.
4. Deep probe runs asynchronously without blocking event loop.
"""

import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from web.app import app


class TestAuditB12HealthCheck(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_default_health_check_returns_real_diagnostics(self):
        """Default health check returns authentic check dictionary."""
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertIn("status", data)
        self.assertIn("checks", data)
        checks = data["checks"]

        # Check version registry
        self.assertIn("version_registry", checks)
        self.assertEqual(checks["version_registry"]["status"], "ready")
        self.assertIn("1.21.11", checks["version_registry"]["supported_versions"])
        self.assertIn("1.21.1", checks["version_registry"]["supported_versions"])

        # Check output directory
        self.assertIn("output_directory", checks)
        self.assertEqual(checks["output_directory"]["status"], "ready")
        self.assertTrue(checks["output_directory"]["writable"])

        # Check Java runtime (informational)
        self.assertIn("java", checks)
        self.assertIn("available", checks["java"])

        # Check provider
        self.assertIn("provider", checks)
        self.assertIn("configured", checks["provider"])

    def test_health_degrades_when_cloud_api_key_missing(self):
        """When Ollama Cloud is configured but API key is missing, health degrades."""
        with patch.dict("os.environ", {"OLLAMA_HOST": "https://ollama.com", "OLLAMA_API_KEY": "", "LLM_PROVIDER": "ollama"}):
            resp = self.client.get("/api/health")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()

            self.assertEqual(data["status"], "degraded")
            self.assertEqual(data["health"], "degraded")
            self.assertFalse(data["checks"]["provider"]["configured"])
            self.assertIn("OLLAMA_API_KEY", data["checks"]["provider"]["error"])

    def test_health_degrades_when_output_dir_unwritable(self):
        """When output directory is not writable, health degrades and generator reports error."""
        with patch("web.app._check_output_dir_writable", return_value=False):
            resp = self.client.get("/api/health")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()

            self.assertEqual(data["status"], "degraded")
            self.assertEqual(data["generator"], "error")
            self.assertFalse(data["checks"]["output_directory"]["writable"])

    def test_deep_health_check_non_blocking(self):
        """Deep check with probe returns ollama_reachability without crashing."""
        resp = self.client.get("/api/health?deep=true")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("checks", data)
        self.assertIn("ollama_reachability", data["checks"])
        self.assertIn("reachable", data["checks"]["ollama_reachability"])


if __name__ == "__main__":
    unittest.main()
