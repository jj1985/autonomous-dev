"""Tests for CI hook sidecar enforcement (Issue #555).

Verifies that the generate_hook_config.py --check command passes on the
current repository state, ensuring CI enforcement will not fail on PR.
"""

import subprocess
import sys
from pathlib import Path

# Detect project root from this test file's location
_TEST_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _TEST_DIR.parent.parent


def test_hook_sidecar_consistency_check() -> None:
    """CI enforcement: verify generator --check passes on current repo."""
    result = subprocess.run(
        [
            sys.executable,
            str(_PROJECT_ROOT / "scripts" / "generate_hook_config.py"),
            "--check",
            "--hooks-dir",
            str(_PROJECT_ROOT / "plugins" / "autonomous-dev" / "hooks"),
            "--manifest-path",
            str(_PROJECT_ROOT / "plugins" / "autonomous-dev" / "config" / "install_manifest.json"),
            "--settings-path",
            str(
                _PROJECT_ROOT
                / "plugins"
                / "autonomous-dev"
                / "config"
                / "global_settings_template.json"
            ),
            "--schema-path",
            str(
                _PROJECT_ROOT
                / "plugins"
                / "autonomous-dev"
                / "config"
                / "hook-metadata.schema.json"
            ),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"Hook sidecar consistency check failed:\n{result.stdout}\n{result.stderr}"
    )


def test_pre_commit_script_exists_and_executable() -> None:
    """Verify pre-commit hook script exists and is executable."""
    script = _PROJECT_ROOT / "scripts" / "pre-commit-hook-check.sh"
    assert script.is_file(), f"Pre-commit script not found: {script}"
    import os

    assert os.access(script, os.X_OK), f"Pre-commit script is not executable: {script}"


def test_ci_workflow_has_hook_validation_step() -> None:
    """Verify CI workflow includes hook sidecar validation step."""
    ci_yml = _PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
    assert ci_yml.is_file(), f"CI workflow not found: {ci_yml}"
    content = ci_yml.read_text()
    assert "Validate hook sidecar consistency" in content, (
        "CI workflow missing 'Validate hook sidecar consistency' step"
    )
    assert "generate_hook_config.py --check" in content, (
        "CI workflow missing generate_hook_config.py --check command"
    )
