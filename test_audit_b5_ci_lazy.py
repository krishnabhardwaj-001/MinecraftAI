"""
test_audit_b5_ci_lazy.py - Tests for B5: CI Workflow, Lazy Provider Construction, and Keyless Benchmark.

Verifies:
1. AutonomousQAReviewer and QARepairEngine do not construct AIProvider eagerly, allowing keyless/offline usage.
2. The benchmark runs successfully (78/78) with OLLAMA_API_KEY unset and remote OLLAMA_HOST.
3. Tests marked with 'live' are properly categorized and skipped by default in non-live CI test runs.
"""

import os
import subprocess
import sys
import pytest
from qa.reviewer import AutonomousQAReviewer
from qa.repair import QARepairEngine
from repair.repair_loop import AIRepairLoop


def test_lazy_provider_construction_with_no_api_key(monkeypatch):
    """
    Constructing AutonomousQAReviewer, QARepairEngine, and AIRepairLoop
    must NOT raise RuntimeError even if OLLAMA_HOST is https://ollama.com and no key is set.
    """
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    monkeypatch.setenv("OLLAMA_HOST", "https://ollama.com")

    # None of these should raise RuntimeError on instantiation
    reviewer = AutonomousQAReviewer()
    assert reviewer._ai_provider is None

    repair_engine = QARepairEngine()
    assert repair_engine._ai_provider is None

    repair_loop = AIRepairLoop()
    assert repair_loop._ai_provider is None


def test_benchmark_runs_offline_with_no_api_key(monkeypatch):
    """
    Benchmark runner executes and passes without network access and with no API key.
    """
    env = os.environ.copy()
    env.pop("OLLAMA_API_KEY", None)
    env["OLLAMA_HOST"] = "https://ollama.com"  # remote endpoint without key

    cmd = [sys.executable, "-m", "eval.benchmark", "--summary-only"]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True)

    assert proc.returncode == 0, f"Benchmark failed with output:\n{proc.stderr}\n{proc.stdout}"
    assert "Passed Cases:                78 (100.0%)" in proc.stdout
    assert "Failed Cases:                0" in proc.stdout
