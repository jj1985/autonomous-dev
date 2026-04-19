"""Spec validation tests for agent completeness gate bypass fix.

Bug description:
Two bypass mechanisms in unified_pre_tool.py were unreachable:
1. Inline env var (SKIP_AGENT_COMPLETENESS_GATE=1 git commit ...) -- hook reads
   os.environ but inline vars only affect child process. Fix: parse command string.
2. File-based bypass (touch /tmp/skip_agent_completeness_gate && git commit ...) --
   hook intercepts entire Bash tool call before any part executes. Fix: block message
   instructs users to run touch as a SEPARATE command first.

Testable criteria:
1. Command string containing SKIP_AGENT_COMPLETENESS_GATE=1 is detected as bypass
2. Block messages instruct users to run touch as a SEPARATE command first
3. Regression tests exist covering all bypass paths
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "hooks"
LIB_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "lib"

sys.path.insert(0, str(HOOKS_DIR))
sys.path.insert(0, str(LIB_DIR))


@pytest.fixture(autouse=True)
def _ensure_paths():
    """Ensure hooks and lib dirs are on sys.path."""
    for d in (str(HOOKS_DIR), str(LIB_DIR)):
        if d not in sys.path:
            sys.path.insert(0, d)
    yield


# ---------------------------------------------------------------------------
# Criterion 1: Inline env var in command string is detected as bypass
# ---------------------------------------------------------------------------


class TestSpec_InlineEnvVarCommandParsing:
    """The hook MUST parse the command string for SKIP_AGENT_COMPLETENESS_GATE=1
    so that inline env vars (which do not propagate to os.environ) are recognized."""

    def test_spec_bypass_1_inline_env_var_detected_in_command(self):
        """When the Bash command starts with SKIP_AGENT_COMPLETENESS_GATE=1,
        the hook recognizes it as a bypass even though os.environ does not contain it."""
        import unified_pre_tool
        import inspect
        source = inspect.getsource(unified_pre_tool)

        # The fix adds command string parsing for inline env var
        assert ('"SKIP_AGENT_COMPLETENESS_GATE=1" in command' in source or
                "'SKIP_AGENT_COMPLETENESS_GATE=1' in command" in source), \
            "Hook must parse command string for inline SKIP_AGENT_COMPLETENESS_GATE=1"

    def test_spec_bypass_2_case_insensitive_true_variant(self):
        """The command string parsing MUST also handle
        skip_agent_completeness_gate=true (case-insensitive)."""
        import unified_pre_tool
        import inspect
        source = inspect.getsource(unified_pre_tool)

        assert "skip_agent_completeness_gate=true" in source.lower(), \
            "Hook must handle skip_agent_completeness_gate=true variant"


# ---------------------------------------------------------------------------
# Criterion 2: Block messages instruct SEPARATE command for file-based bypass
# ---------------------------------------------------------------------------


class TestSpec_BlockMessageSeparateCommand:
    """Block messages MUST instruct users to run touch as a SEPARATE command first,
    since compound commands (touch ... && git commit ...) are intercepted before
    any part executes."""

    def test_spec_bypass_3_non_batch_message_says_separate(self):
        """The non-batch block message from _check_pipeline_agent_completions
        MUST contain 'SEPARATE command first'."""
        import unified_pre_tool

        mock_mod = MagicMock()
        mock_mod.verify_pipeline_agent_completions.return_value = (
            False,
            {"researcher"},
            {"implementer"},
        )

        with patch.object(unified_pre_tool, "_is_pipeline_active", return_value=True), \
             patch("importlib.util.spec_from_file_location") as mock_spec_fn, \
             patch("importlib.util.module_from_spec", return_value=mock_mod), \
             patch.object(unified_pre_tool, "_get_pipeline_mode_from_state", return_value="full"):

            mock_spec = MagicMock()
            mock_spec.loader = MagicMock()
            mock_spec_fn.return_value = mock_spec

            with patch.object(Path, "exists", return_value=True):
                result = unified_pre_tool._check_pipeline_agent_completions("test-session")

        assert result is not None, "Should return a block message when agents are missing"
        assert "SEPARATE command first" in result, (
            f"Block message must say 'SEPARATE command first' to prevent compound "
            f"command confusion, got: {result}"
        )

    def test_spec_bypass_4_batch_message_says_separate(self):
        """The batch-mode block message (Issue #853) MUST also contain
        'SEPARATE command first'."""
        import unified_pre_tool
        import inspect
        source = inspect.getsource(unified_pre_tool)

        assert "as a SEPARATE command first" in source, (
            "Batch mode block message must also say 'as a SEPARATE command first'"
        )


# ---------------------------------------------------------------------------
# Criterion 3: Regression tests exist covering all bypass paths
# ---------------------------------------------------------------------------


class TestSpec_RegressionTestsExist:
    """Regression tests MUST exist covering all bypass paths."""

    def test_spec_bypass_5_regression_test_file_exists(self):
        """A regression test file for agent completeness bypass must exist."""
        test_file = REPO_ROOT / "tests" / "unit" / "hooks" / "test_agent_completeness_bypass.py"
        assert test_file.exists(), (
            f"Regression test file must exist at {test_file}"
        )

    def test_spec_bypass_6_regression_tests_cover_inline_env_var(self):
        """Regression tests must cover the inline env var bypass path."""
        test_file = REPO_ROOT / "tests" / "unit" / "hooks" / "test_agent_completeness_bypass.py"
        content = test_file.read_text()

        assert "inline" in content.lower() or "SKIP_AGENT_COMPLETENESS_GATE=1" in content, (
            "Regression tests must cover inline env var bypass"
        )

    def test_spec_bypass_7_regression_tests_cover_file_based_bypass(self):
        """Regression tests must cover the file-based bypass path."""
        test_file = REPO_ROOT / "tests" / "unit" / "hooks" / "test_agent_completeness_bypass.py"
        content = test_file.read_text()

        assert "file" in content.lower() and "bypass" in content.lower(), (
            "Regression tests must cover file-based bypass"
        )

    def test_spec_bypass_8_regression_tests_cover_block_message(self):
        """Regression tests must verify the block message contains SEPARATE instruction."""
        test_file = REPO_ROOT / "tests" / "unit" / "hooks" / "test_agent_completeness_bypass.py"
        content = test_file.read_text()

        assert "SEPARATE" in content, (
            "Regression tests must verify block message says 'SEPARATE command first'"
        )

    def test_spec_bypass_9_regression_tests_cover_process_env_var(self):
        """Regression tests must cover the original os.environ bypass (still works)."""
        test_file = REPO_ROOT / "tests" / "unit" / "hooks" / "test_agent_completeness_bypass.py"
        content = test_file.read_text()

        assert "process" in content.lower() or "monkeypatch.setenv" in content, (
            "Regression tests must cover process environment variable bypass"
        )
