"""
Audit B18 Regression Tests: Repository bloat, .dockerignore, .gitignore generic rules,
and Mojang server JAR downloader setup script.
"""

import subprocess
import sys
from pathlib import Path
import pytest


def test_dockerignore_contains_essential_rules():
    """Verify .dockerignore exists and excludes git, jars, caches, and outputs."""
    dockerignore = Path(".dockerignore")
    assert dockerignore.exists(), ".dockerignore must exist"
    content = dockerignore.read_text(encoding="utf-8")

    assert ".git" in content
    assert "__pycache__" in content
    assert ".env" in content
    assert "generated/*" in content
    assert "versions/" in content
    assert "source/" in content
    assert "libraries/" in content
    assert "*.jar" in content


def test_gitignore_has_no_special_cases():
    """Verify .gitignore contains generic generated rules without hardcoded pack names."""
    gitignore = Path(".gitignore")
    assert gitignore.exists()
    content = gitignore.read_text(encoding="utf-8")

    assert "generated/*" in content
    assert "!generated/.gitkeep" in content
    # No special-case generated packs
    assert "when_it_becomes_night" not in content
    assert "when_it_is_raining" not in content


def test_download_server_jars_script_help():
    """Verify scripts/download_server_jars.py runs and provides valid CLI interface."""
    script = Path("scripts/download_server_jars.py")
    assert script.exists(), "scripts/download_server_jars.py must exist"

    res = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True)
    assert res.returncode == 0
    assert "--version" in res.stdout
    assert "--dry-run" in res.stdout
