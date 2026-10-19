"""
test_audit_b1_run_web.py - Regression test for B1: run_web.py HOST/PORT environment variable and argument resolution.
"""
import io
import unittest
from unittest.mock import patch
from run_web import resolve_server_config, main


class TestAuditB1RunWeb(unittest.TestCase):
    def test_default_fallback_to_127_0_0_1_and_8000(self):
        """When neither env nor CLI flags are provided, defaults must be 127.0.0.1 and 8000."""
        config = resolve_server_config(args=[], env={})
        self.assertEqual(config.host, "127.0.0.1")
        self.assertEqual(config.port, 8000)
        self.assertFalse(config.open_browser)

    def test_env_host_and_port_applied(self):
        """When HOST and PORT are defined in env, they must be used as defaults."""
        config = resolve_server_config(args=[], env={"HOST": "0.0.0.0", "PORT": "9000"})
        self.assertEqual(config.host, "0.0.0.0")
        self.assertEqual(config.port, 9000)

    def test_cli_flags_override_env(self):
        """CLI flags must have higher precedence than environment variables."""
        config = resolve_server_config(
            args=["--host", "192.168.1.50", "--port", "8080"],
            env={"HOST": "0.0.0.0", "PORT": "9000"}
        )
        self.assertEqual(config.host, "192.168.1.50")
        self.assertEqual(config.port, 8080)

    def test_invalid_port_in_env_falls_back_safely(self):
        """Invalid non-integer PORT in env should safely fall back to 8000."""
        config = resolve_server_config(args=[], env={"PORT": "not-a-port"})
        self.assertEqual(config.port, 8000)

    def test_dual_version_banner(self):
        """Main banner must not hardcode 'Target: 1.21.11' only; must support both versions."""
        with patch("run_web.check_port_available", return_value=True):
            with patch("uvicorn.run"):
                with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                    main(argv=["--host", "127.0.0.1", "--port", "8999"])
                    output = mock_stdout.getvalue()
                    self.assertNotIn("Target: Minecraft Java Edition 1.21.11 | Data Pack Version 94.1", output)
                    self.assertIn("1.21.11", output)
                    self.assertIn("1.21.1", output)


if __name__ == "__main__":
    unittest.main()
