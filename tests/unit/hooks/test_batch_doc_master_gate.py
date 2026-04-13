"""
Tests for the batch doc-master completion gate in unified_pre_tool.py.

Verifies that git commit in batch worktrees is blocked when any issue
is missing doc-master completion.

Issue: #786
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add hook and lib dirs to path
HOOK_DIR = Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "hooks"
LIB_DIR = Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "lib"
sys.path.insert(0, str(HOOK_DIR))
sys.path.insert(0, str(LIB_DIR))

import unified_pre_tool as hook


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Reset relevant env vars for each test."""
    env_keys = [
        "SKIP_BATCH_DOC_MASTER_GATE",
        "SKIP_BATCH_CIA_GATE",
        "CLAUDE_SESSION_ID",
    ]
    for key in env_keys:
        monkeypatch.delenv(key, raising=False)


class TestCheckBatchDocMasterCompletions:
    """Tests for _check_batch_doc_master_completions() helper."""

    def test_returns_none_when_all_issues_have_doc_master(self):
        """Returns None (no block) when all batch issues have doc-master."""
        with patch.object(
            hook,
            "_check_batch_doc_master_completions",
            wraps=hook._check_batch_doc_master_completions,
        ):
            # Simulate via module mock
            import importlib
            import importlib.util

            mock_mod = MagicMock()
            mock_mod.verify_batch_doc_master_completions.return_value = (True, [10, 20], [])

            with patch("importlib.util.spec_from_file_location", return_value=MagicMock(loader=MagicMock())):
                with patch("importlib.util.module_from_spec", return_value=mock_mod):
                    result = hook._check_batch_doc_master_completions("test-session")
            assert result is None

    def test_returns_block_reason_when_issues_missing_doc_master(self):
        """Returns block reason string when some issues are missing doc-master."""
        mock_mod = MagicMock()
        mock_mod.verify_batch_doc_master_completions.return_value = (False, [10], [20, 30])

        with patch("importlib.util.spec_from_file_location", return_value=MagicMock(loader=MagicMock())):
            with patch("importlib.util.module_from_spec", return_value=mock_mod):
                result = hook._check_batch_doc_master_completions("test-session")

        assert result is not None
        assert "doc-master" in result.lower()
        assert "#20" in result
        assert "#30" in result
        assert "SKIP_BATCH_DOC_MASTER_GATE" in result

    def test_returns_none_on_exception_fail_open(self):
        """Fail-open: returns None on any exception."""
        with patch("importlib.util.spec_from_file_location", side_effect=RuntimeError("boom")):
            result = hook._check_batch_doc_master_completions("test-session")
        assert result is None

    def test_returns_none_when_module_missing_function(self):
        """Returns None (fail-open) when verify function not on module."""
        mock_mod = MagicMock(spec=[])  # No attributes

        with patch("importlib.util.spec_from_file_location", return_value=MagicMock(loader=MagicMock())):
            with patch("importlib.util.module_from_spec", return_value=mock_mod):
                result = hook._check_batch_doc_master_completions("test-session")
        assert result is None

    def test_block_reason_contains_issue_786_reference(self):
        """Block reason should reference Issue #786."""
        mock_mod = MagicMock()
        mock_mod.verify_batch_doc_master_completions.return_value = (False, [], [42])

        with patch("importlib.util.spec_from_file_location", return_value=MagicMock(loader=MagicMock())):
            with patch("importlib.util.module_from_spec", return_value=mock_mod):
                result = hook._check_batch_doc_master_completions("test-session")

        assert result is not None
        assert "#786" in result

    def test_block_reason_contains_required_next_action(self):
        """Block reason should include REQUIRED NEXT ACTION directive."""
        mock_mod = MagicMock()
        mock_mod.verify_batch_doc_master_completions.return_value = (False, [], [5])

        with patch("importlib.util.spec_from_file_location", return_value=MagicMock(loader=MagicMock())):
            with patch("importlib.util.module_from_spec", return_value=mock_mod):
                result = hook._check_batch_doc_master_completions("test-session")

        assert result is not None
        assert "REQUIRED NEXT ACTION" in result

    def test_skip_env_var_bypasses_via_verify_function(self, monkeypatch):
        """SKIP_BATCH_DOC_MASTER_GATE=1 causes verify function to return True."""
        monkeypatch.setenv("SKIP_BATCH_DOC_MASTER_GATE", "1")

        # The actual verify function in the loaded module will see the env var.
        # We test via the actual pipeline_completion_state module to confirm
        # the env var escape hatch works end-to-end.
        lib_path = LIB_DIR / "pipeline_completion_state.py"
        if lib_path.exists():
            import importlib.util as ilu

            spec = ilu.spec_from_file_location("pipeline_completion_state_dm_test", str(lib_path))
            mod = ilu.module_from_spec(spec)
            spec.loader.exec_module(mod)

            all_passed, with_dm, missing_dm = mod.verify_batch_doc_master_completions("no-state-session")
            assert all_passed is True


    def test_block_reason_differentiates_never_ran_vs_no_verdict(self):
        """Block reason distinguishes 'never ran' from 'ran but no verdict'. Issue #837."""
        mock_mod = MagicMock()
        # Issues 10 and 20 are missing; we need _read_state to distinguish them
        mock_mod.verify_batch_doc_master_completions.return_value = (False, [5], [10, 20])
        # Issue 10: doc-master ran (completion=True) but no valid verdict
        # Issue 20: doc-master never ran (no completion)
        mock_mod._read_state.return_value = {
            "completions": {
                "5": {"doc-master": True, "doc-master-verdict": "PASS"},
                "10": {"doc-master": True, "doc-master-verdict": "SHALLOW"},
                "20": {"implementer": True},
            }
        }

        with patch("importlib.util.spec_from_file_location", return_value=MagicMock(loader=MagicMock())):
            with patch("importlib.util.module_from_spec", return_value=mock_mod):
                result = hook._check_batch_doc_master_completions("test-session")

        assert result is not None
        assert "never ran" in result.lower()
        assert "no valid verdict" in result.lower()
        assert "#20" in result  # never ran
        assert "#10" in result  # no verdict

    def test_block_reason_only_never_ran(self):
        """When all missing issues never ran, only 'never ran' message appears. Issue #837."""
        mock_mod = MagicMock()
        mock_mod.verify_batch_doc_master_completions.return_value = (False, [], [30])
        mock_mod._read_state.return_value = {
            "completions": {
                "30": {"implementer": True},
            }
        }

        with patch("importlib.util.spec_from_file_location", return_value=MagicMock(loader=MagicMock())):
            with patch("importlib.util.module_from_spec", return_value=mock_mod):
                result = hook._check_batch_doc_master_completions("test-session")

        assert result is not None
        assert "never ran" in result.lower()
        assert "no valid verdict" not in result.lower()

    def test_block_reason_only_no_verdict(self):
        """When all missing issues ran but have no verdict, only 'no valid verdict' appears. Issue #837."""
        mock_mod = MagicMock()
        mock_mod.verify_batch_doc_master_completions.return_value = (False, [], [40])
        mock_mod._read_state.return_value = {
            "completions": {
                "40": {"doc-master": True, "doc-master-verdict": "MISSING"},
            }
        }

        with patch("importlib.util.spec_from_file_location", return_value=MagicMock(loader=MagicMock())):
            with patch("importlib.util.module_from_spec", return_value=mock_mod):
                result = hook._check_batch_doc_master_completions("test-session")

        assert result is not None
        assert "no valid verdict" in result.lower()
        assert "never ran" not in result.lower()

    def test_block_reason_references_issue_837(self):
        """Block reason should reference Issue #837."""
        mock_mod = MagicMock()
        mock_mod.verify_batch_doc_master_completions.return_value = (False, [], [50])
        mock_mod._read_state.return_value = {
            "completions": {"50": {"implementer": True}}
        }

        with patch("importlib.util.spec_from_file_location", return_value=MagicMock(loader=MagicMock())):
            with patch("importlib.util.module_from_spec", return_value=mock_mod):
                result = hook._check_batch_doc_master_completions("test-session")

        assert result is not None
        assert "#837" in result


class TestBatchDocMasterGateIntegration:
    """Integration-style tests for the batch doc-master gate in hook flow."""

    def test_function_exists_in_hook(self):
        """_check_batch_doc_master_completions must exist in the hook module."""
        assert hasattr(hook, "_check_batch_doc_master_completions")
        assert callable(hook._check_batch_doc_master_completions)
