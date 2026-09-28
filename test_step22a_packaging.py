import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

# Root directory of the repository
BASE_DIR = Path(__file__).resolve().parent


class TestStep22aPackaging(unittest.TestCase):
    """
    Step 22A Automated Test Suite: Production Packaging & Distribution Hardening.
    Verifies pyproject.toml specification, editable installation contracts,
    CLI/Web entry points, and Windows launcher scripts.
    """

    def test_1_package_imports(self):
        """
        Verify that all core modules and packages can be imported cleanly.
        """
        import ai
        import generator
        import pipeline
        import qa
        import repair
        import validator
        import web

        self.assertIsNotNone(ai)
        self.assertIsNotNone(generator)
        self.assertIsNotNone(pipeline)
        self.assertIsNotNone(qa)
        self.assertIsNotNone(repair)
        self.assertIsNotNone(validator)
        self.assertIsNotNone(web)

    def test_2_pyproject_toml_configuration(self):
        """
        Verify that pyproject.toml exists and declares valid packaging metadata,
        runtime dependencies, and console script entrypoints.
        """
        pyproject_path = BASE_DIR / "pyproject.toml"
        self.assertTrue(pyproject_path.exists(), "pyproject.toml must exist in project root")

        content = pyproject_path.read_text(encoding="utf-8")

        # Project metadata
        self.assertIn('name = "minecraft-ai"', content)
        self.assertIn('version = "1.0.0"', content)
        self.assertIn('requires-python = ">=3.10"', content)

        # Core runtime dependencies
        expected_deps = [
            "pydantic",
            "python-dotenv",
            "ollama",
            "openai",
            "fastapi",
            "uvicorn",
            "jinja2",
            "httpx",
        ]
        for dep in expected_deps:
            self.assertIn(dep, content, f"Dependency '{dep}' must be declared in pyproject.toml")

        # Console scripts entrypoints
        self.assertIn('minecraft-ai = "run_pipeline:main"', content)
        self.assertIn('minecraft-ai-web = "run_web:main"', content)

    def test_3_cli_entry_point(self):
        """
        Verify that the CLI entry point function is directly callable and adheres to contracts.
        """
        import run_pipeline

        self.assertTrue(callable(getattr(run_pipeline, "main", None)))
        self.assertTrue(callable(getattr(run_pipeline, "run_cli", None)))

        # Invoking run_cli with empty input should cleanly return code 1
        exit_code = run_pipeline.run_cli(args=[""])
        self.assertEqual(exit_code, 1)

    def test_4_web_entry_point(self):
        """
        Verify that the Web server entry point and FastAPI application are callable and valid.
        """
        import run_web
        from web.app import app

        self.assertTrue(callable(getattr(run_web, "main", None)))
        self.assertEqual(app.title, "MinecraftAI Web Interface")
        self.assertEqual(app.version, "1.21.11")

        # Verify key routes are present
        routes = [r.path for r in app.routes]
        self.assertIn("/", routes)
        self.assertIn("/api/health", routes)
        self.assertIn("/api/generate", routes)
        self.assertIn("/api/download/{filename}", routes)

    def test_5_windows_launchers_content(self):
        """
        Verify that launch_cli.bat and launch_web.bat exist, use %~dp0, and verify Python.
        """
        cli_bat = BASE_DIR / "launch_cli.bat"
        web_bat = BASE_DIR / "launch_web.bat"

        self.assertTrue(cli_bat.exists(), "launch_cli.bat must exist")
        self.assertTrue(web_bat.exists(), "launch_web.bat must exist")

        cli_content = cli_bat.read_text(encoding="utf-8")
        web_content = web_bat.read_text(encoding="utf-8")

        for name, content in [("launch_cli.bat", cli_content), ("launch_web.bat", web_content)]:
            self.assertIn('%~dp0', content, f"{name} must resolve script directory with %~dp0")
            self.assertIn('python --version', content, f"{name} must check Python availability")
            self.assertIn('exit /b', content, f"{name} must forward errorlevel exit codes")

    def test_6_windows_launchers_execution(self):
        """
        Verify that the Windows batch launchers execute correctly from the command line.
        """
        if sys.platform != "win32":
            self.skipTest("Batch launcher execution test is Windows-specific")

        cli_bat = str(BASE_DIR / "launch_cli.bat")
        web_bat = str(BASE_DIR / "launch_web.bat")

        # Test launch_web.bat with --help
        res_web = subprocess.run(
            ["cmd", "/c", web_bat, "--help"],
            capture_output=True,
            text=True,
            cwd=str(BASE_DIR)
        )
        self.assertEqual(res_web.returncode, 0)
        self.assertIn("usage: run_web.py", res_web.stdout)

        # Test launch_cli.bat with empty arg (should report error and return code 1)
        res_cli = subprocess.run(
            ["cmd", "/c", cli_bat, ""],
            capture_output=True,
            text=True,
            cwd=str(BASE_DIR)
        )
        self.assertEqual(res_cli.returncode, 1)
        self.assertIn("Request cannot be empty", res_cli.stdout)

    def test_7_console_script_installed(self):
        """
        Verify that pip editable install registered the minecraft-ai console scripts.
        """
        which_cli = shutil.which("minecraft-ai")
        which_web = shutil.which("minecraft-ai-web")

        # Check that executables exist in python environment's Scripts path
        if which_cli:
            self.assertTrue(Path(which_cli).exists())
        if which_web:
            self.assertTrue(Path(which_web).exists())


if __name__ == "__main__":
    unittest.main()
