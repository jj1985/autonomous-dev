"""Spec validation tests for Issue #790: Spec test deletion guard.

These tests validate the acceptance criteria from the spec ONLY,
testing observable behavior without knowledge of implementation details.

Acceptance criteria:
1. Blocks deletion of spec validation tests when issue number doesn't match PIPELINE_ISSUE_NUMBER
2. Blocks deletion via Bash rm command for non-matching issue
3. Blocks deletion via Bash unlink command for non-matching issue
4. Blocks deletion via Bash os.remove for non-matching issue
5. Allows deletion when issue number matches PIPELINE_ISSUE_NUMBER
6. Moving to tests/archived/ is allowed (sanctioned archival path)
7. Escape hatch: SKIP_SPEC_DELETION_GUARD env var bypasses the guard
8. Fails open when no pipeline context (no PIPELINE_ISSUE_NUMBER)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "hooks"
LIB_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "lib"

sys.path.insert(0, str(HOOK_DIR))
sys.path.insert(0, str(LIB_DIR))

import unified_pre_tool as hook


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Reset relevant env vars for each test."""
    for key in ("SKIP_SPEC_DELETION_GUARD", "PIPELINE_ISSUE_NUMBER", "PIPELINE_STATE_FILE"):
        monkeypatch.delenv(key, raising=False)


# ---- Criterion 1: Blocks deletion when issue number doesn't match ----

@patch.object(hook, "_get_current_issue_number", return_value=800)
def test_spec_1_blocks_deletion_of_non_matching_issue_spec_test(_mock):
    """Deleting a spec test belonging to issue 761 while pipeline is on issue 800 is blocked."""
    result = hook._check_spec_test_deletion_scope(
        "tests/spec_validation/test_spec_issue761_some_feature.py"
    )
    assert result is not None, "Expected block for non-matching issue spec test"
    assert "761" in result[1], "Block reason should mention the test's issue number"


# ---- Criterion 2: Blocks deletion via Bash rm ----

def test_spec_2_bash_rm_detects_spec_test_deletion():
    """Bash rm command targeting a spec test file is detected."""
    targets = hook._extract_bash_spec_test_targets(
        "rm tests/spec_validation/test_spec_issue761_hmac_stale.py"
    )
    assert len(targets) >= 1, "rm of spec test should be detected"


def test_spec_2b_bash_rm_with_flags_detects_spec_test():
    """Bash rm -f command targeting a spec test file is detected."""
    targets = hook._extract_bash_spec_test_targets(
        "rm -rf tests/spec_validation/test_spec_issue761_hmac_stale.py"
    )
    assert len(targets) >= 1, "rm -rf of spec test should be detected"


# ---- Criterion 3: Blocks deletion via Bash unlink ----

def test_spec_3_bash_unlink_detects_spec_test_deletion():
    """Bash unlink command targeting a spec test file is detected."""
    targets = hook._extract_bash_spec_test_targets(
        "unlink tests/spec_validation/test_spec_issue764_per_issue_baseline.py"
    )
    assert len(targets) >= 1, "unlink of spec test should be detected"


# ---- Criterion 4: Blocks deletion via Bash os.remove ----

def test_spec_4_bash_os_remove_detects_spec_test_deletion():
    """Python os.remove in a Bash command targeting a spec test is detected."""
    targets = hook._extract_bash_spec_test_targets(
        "python3 -c \"import os; os.remove('tests/spec_validation/test_spec_issue764_per_issue_baseline.py')\""
    )
    assert len(targets) >= 1, "os.remove of spec test should be detected"


# ---- Criterion 5: Allows deletion when issue matches ----

@patch.object(hook, "_get_current_issue_number", return_value=761)
def test_spec_5_allows_deletion_of_matching_issue_spec_test(_mock):
    """Deleting a spec test belonging to issue 761 while pipeline is on issue 761 is allowed."""
    result = hook._check_spec_test_deletion_scope(
        "tests/spec_validation/test_spec_issue761_hmac_stale_failopen.py"
    )
    assert result is None, "Expected allow for matching issue spec test"


# ---- Criterion 6: Moving to tests/archived/ is allowed ----

def test_spec_6_mv_to_archived_not_flagged():
    """mv of a spec test to tests/archived/ is not detected as deletion."""
    targets = hook._extract_bash_spec_test_targets(
        "mv tests/spec_validation/test_spec_issue761_foo.py tests/archived/"
    )
    assert len(targets) == 0, "mv to tests/archived/ should not be flagged"


def test_spec_6b_mv_to_other_location_is_flagged():
    """mv of a spec test to a non-archived location IS detected as deletion."""
    targets = hook._extract_bash_spec_test_targets(
        "mv tests/spec_validation/test_spec_issue761_foo.py /tmp/"
    )
    assert len(targets) >= 1, "mv to non-archived location should be flagged"


# ---- Criterion 7: Escape hatch SKIP_SPEC_DELETION_GUARD ----

@patch.object(hook, "_get_current_issue_number", return_value=800)
def test_spec_7_escape_hatch_skips_guard(_mock, monkeypatch):
    """SKIP_SPEC_DELETION_GUARD=1 bypasses the deletion guard."""
    monkeypatch.setenv("SKIP_SPEC_DELETION_GUARD", "1")
    result = hook._check_spec_test_deletion_scope(
        "tests/spec_validation/test_spec_issue761_some_feature.py"
    )
    assert result is None, "Escape hatch should bypass deletion guard"


@patch.object(hook, "_get_current_issue_number", return_value=800)
def test_spec_7b_escape_hatch_true_value(_mock, monkeypatch):
    """SKIP_SPEC_DELETION_GUARD=true also bypasses the deletion guard."""
    monkeypatch.setenv("SKIP_SPEC_DELETION_GUARD", "true")
    result = hook._check_spec_test_deletion_scope(
        "tests/spec_validation/test_spec_issue761_some_feature.py"
    )
    assert result is None, "Escape hatch with 'true' should bypass deletion guard"


# ---- Criterion 8: Fails open when no pipeline context ----

@patch.object(hook, "_get_current_issue_number", return_value=0)
def test_spec_8_fails_open_when_no_pipeline_context(_mock):
    """When no pipeline context (issue number 0), deletion is allowed (fail open)."""
    result = hook._check_spec_test_deletion_scope(
        "tests/spec_validation/test_spec_issue761_some_feature.py"
    )
    assert result is None, "Should fail open when no pipeline context"
