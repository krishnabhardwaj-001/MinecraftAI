"""
Audit B19 Regression Tests: Dockerfile multi-stage structure, pip syntax without shell redirection,
optional JRE build arg, and B1 environment integration.
"""

import re
from pathlib import Path


def test_dockerfile_multi_stage_structure():
    """Verify Dockerfile uses true multi-stage build."""
    dockerfile = Path("Dockerfile")
    assert dockerfile.exists()
    content = dockerfile.read_text(encoding="utf-8")

    stages = re.findall(r"^FROM\s+[^\s]+\s+AS\s+([^\s]+)", content, re.MULTILINE)
    assert len(stages) >= 2, f"Expected at least 2 stages, found: {stages}"
    assert "builder" in stages
    assert "runner" in stages


def test_dockerfile_no_unquoted_redirection_pip_install():
    """Verify pip install does not contain unquoted >= which causes shell redirection."""
    dockerfile = Path("Dockerfile")
    content = dockerfile.read_text(encoding="utf-8")

    # Check for any bare unquoted package>=version lines inside RUN pip install
    for line in content.splitlines():
        if "pip install" in line:
            assert ">=" not in line or '"' in line or "'" in line, (
                f"Found unquoted version constraint causing shell redirection: {line}"
            )


def test_dockerfile_contains_jre_build_arg_and_host_defaults():
    """Verify Dockerfile supports INSTALL_JRE and sets HOST/PORT for external accessibility."""
    dockerfile = Path("Dockerfile")
    content = dockerfile.read_text(encoding="utf-8")

    assert "ARG INSTALL_JRE=" in content
    assert "HOST=0.0.0.0" in content
    assert "PORT=8000" in content
    assert 'CMD ["python", "run_web.py"]' in content
