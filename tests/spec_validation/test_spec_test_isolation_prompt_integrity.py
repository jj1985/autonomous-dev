"""
Spec validation tests for Issue #784: Fix test isolation failure in
test_prompt_integrity_enforcement.py.

Acceptance criteria:
1. test_critical_agent_allowed_outside_pipeline_when_adequate passes regardless
   of on-disk prompt baseline state.
2. The fix mocks get_prompt_baseline so that on-disk baselines do not cause
   false denials in tests that only check the minimum word count gate.
3. The fix is isolated to test code only -- no production code changes.
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add hook and lib dirs to path
REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "hooks"
LIB_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "lib"
sys.path.insert(0, str(HOOK_DIR))
sys.path.insert(0, str(LIB_DIR))

import unified_pre_tool as hook


def _make_prompt(word_count: int) -> str:
    """Generate a prompt with exactly word_count words."""
    return " ".join(f"word{i}" for i in range(word_count))


class TestSpecTestIsolationPromptIntegrity:
    """Spec validation: test isolation fix for prompt integrity enforcement."""

    def test_spec_isolation_1_adequate_prompt_allowed_with_no_baseline(self):
        """Criterion 1: A critical agent with an adequate prompt (100 words) is
        allowed when get_prompt_baseline returns None, proving no on-disk
        baseline can cause a false denial."""
        prompt = _make_prompt(100)
        with (
            patch.object(hook, "_is_pipeline_active", return_value=False),
            patch("prompt_integrity.get_prompt_baseline", return_value=None),
        ):
            decision, reason = hook.validate_prompt_integrity(
                "Agent",
                {"subagent_type": "security-auditor", "prompt": prompt},
            )
            assert decision == "allow", (
                f"Expected allow but got {decision}: {reason}"
            )

    def test_spec_isolation_2_high_baseline_causes_denial(self):
        """Criterion 2: Without baseline isolation (baseline=763), the same
        100-word prompt IS denied due to shrinkage detection. This proves
        the mock is necessary for test isolation."""
        prompt = _make_prompt(100)
        with (
            patch.object(hook, "_is_pipeline_active", return_value=False),
            patch("prompt_integrity.get_prompt_baseline", return_value=763),
        ):
            decision, reason = hook.validate_prompt_integrity(
                "Agent",
                {"subagent_type": "security-auditor", "prompt": prompt},
            )
            assert decision == "deny", (
                f"Expected deny with high baseline but got {decision}: {reason}"
            )
            assert "shrank" in reason

    def test_spec_isolation_3_no_production_code_changes(self):
        """Criterion 3: Only test files were changed -- no production code
        modifications."""
        result = subprocess.run(
            ["git", "diff", "HEAD", "--name-only"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        changed_files = [
            f for f in result.stdout.strip().splitlines() if f.strip()
        ]
        production_changes = [
            f for f in changed_files
            if not f.startswith("tests/")
            and not f.startswith("docs/")
            and not f.startswith("scripts/")
            and not f.startswith("logs/")
        ]
        # Filter to only files under plugins/ hooks/ lib/ (production code)
        hook_or_lib_changes = [
            f for f in production_changes
            if "hooks/" in f or "lib/" in f or "agents/" in f
        ]
        assert hook_or_lib_changes == [], (
            f"Production code was changed: {hook_or_lib_changes}. "
            f"The fix should be isolated to test code only."
        )

    def test_spec_isolation_4_original_test_passes(self):
        """Criterion 1 (end-to-end): Run the actual test file and confirm the
        previously-failing test passes."""
        test_file = str(
            REPO_ROOT
            / "tests"
            / "unit"
            / "hooks"
            / "test_prompt_integrity_enforcement.py"
        )
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                test_file
                + "::TestPromptIntegrityEnforcement"
                + "::test_critical_agent_allowed_outside_pipeline_when_adequate",
                "-v",
                "--no-header",
                "-p",
                "no:cacheprovider",
            ],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, (
            f"The previously-failing test did not pass.\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
