"""Unit tests for bugfix_detector.py — Issue #737.

Tests the shared library for detecting bug-fix features, commits,
and counting test functions.
"""

import sys
from pathlib import Path

import pytest

# Add lib to path for direct import
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "plugins" / "autonomous-dev" / "lib"))

from bugfix_detector import get_test_count, is_bugfix_commit, is_bugfix_feature


# --- is_bugfix_feature tests ---


class TestIsBugfixFeature:
    """Tests for is_bugfix_feature() function."""

    def test_fix_keyword(self):
        assert is_bugfix_feature("Fix the dedup logic") is True

    def test_bug_keyword(self):
        assert is_bugfix_feature("Bug in fingerprint format") is True

    def test_broken_keyword(self):
        assert is_bugfix_feature("Broken auth flow") is True

    def test_regression_keyword(self):
        assert is_bugfix_feature("Regression in pattern matching") is True

    def test_crash_keyword(self):
        assert is_bugfix_feature("Crash on startup with empty config") is True

    def test_dedup_keyword(self):
        assert is_bugfix_feature("Dedup logic is incorrect") is True

    def test_duplicate_keyword(self):
        assert is_bugfix_feature("Duplicate entries in output") is True

    def test_label_bug(self):
        assert is_bugfix_feature("Some description", labels=["bug"]) is True

    def test_label_fix(self):
        assert is_bugfix_feature("Some description", labels=["fix"]) is True

    def test_label_bugfix_with_others(self):
        assert is_bugfix_feature("Some description", labels=["bugfix", "urgent"]) is True

    def test_label_hotfix(self):
        assert is_bugfix_feature("Some description", labels=["hotfix"]) is True

    def test_label_regression(self):
        assert is_bugfix_feature("Some description", labels=["regression"]) is True

    def test_false_for_new_feature(self):
        assert is_bugfix_feature("Add new dashboard") is False

    def test_false_for_refactor(self):
        assert is_bugfix_feature("Refactor auth module") is False

    def test_false_for_docs(self):
        assert is_bugfix_feature("Update documentation") is False

    def test_false_for_prefix_word_boundary(self):
        """'prefix' contains 'fix' but should NOT match due to word boundaries."""
        assert is_bugfix_feature("Implement prefix handling") is False

    def test_false_for_fixture_word_boundary(self):
        """'fixture' contains 'fix' but should NOT match due to word boundaries."""
        assert is_bugfix_feature("Add test fixture for auth") is False

    def test_false_for_suffix_word_boundary(self):
        """'suffix' contains 'fix' but should NOT match due to word boundaries."""
        assert is_bugfix_feature("Handle suffix correctly") is False

    def test_empty_description(self):
        assert is_bugfix_feature("") is False

    def test_none_labels(self):
        assert is_bugfix_feature("Some description", labels=None) is False

    def test_empty_labels(self):
        assert is_bugfix_feature("Some description", labels=[]) is False

    def test_case_insensitive_keyword(self):
        assert is_bugfix_feature("FIX the rendering issue") is True

    def test_case_insensitive_label(self):
        assert is_bugfix_feature("Something", labels=["BUG"]) is True


# --- is_bugfix_commit tests ---


class TestIsBugfixCommit:
    """Tests for is_bugfix_commit() function."""

    def test_fix_prefix(self):
        assert is_bugfix_commit("fix: resolve crash") is True

    def test_fix_with_scope(self):
        assert is_bugfix_commit("fix(hooks): prevent null") is True

    def test_hotfix_prefix(self):
        assert is_bugfix_commit("hotfix: urgent patch") is True

    def test_bugfix_prefix(self):
        assert is_bugfix_commit("bugfix: correct format") is True

    def test_false_for_feat(self):
        assert is_bugfix_commit("feat: new feature") is False

    def test_false_for_docs(self):
        assert is_bugfix_commit("docs: update readme") is False

    def test_false_for_refactor(self):
        assert is_bugfix_commit("refactor: clean up") is False

    def test_false_for_suffix_not_a_fix(self):
        assert is_bugfix_commit("suffix: not a fix") is False

    def test_false_for_chore(self):
        assert is_bugfix_commit("chore: update deps") is False

    def test_empty_message(self):
        assert is_bugfix_commit("") is False

    def test_fix_in_body_not_prefix(self):
        """'fix' in body but not as prefix should NOT match."""
        assert is_bugfix_commit("feat: add feature\n\nThis will fix the issue") is False

    def test_multiline_only_checks_first_line(self):
        assert is_bugfix_commit("fix: first line\n\nMore details here") is True


# --- get_test_count tests ---


class TestGetTestCount:
    """Tests for get_test_count() function."""

    def test_counts_test_functions(self, tmp_path: Path):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        test_file = tests_dir / "test_example.py"
        test_file.write_text(
            "def test_one():\n    pass\n\ndef test_two():\n    pass\n"
        )
        assert get_test_count(tmp_path) == 2

    def test_counts_across_multiple_files(self, tmp_path: Path):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_a.py").write_text("def test_a():\n    pass\n")
        (tests_dir / "test_b.py").write_text("def test_b():\n    pass\ndef test_c():\n    pass\n")
        assert get_test_count(tmp_path) == 3

    def test_ignores_non_test_functions(self, tmp_path: Path):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_example.py").write_text(
            "def test_real():\n    pass\n\ndef helper_func():\n    pass\n"
        )
        assert get_test_count(tmp_path) == 1

    def test_no_tests_dir_returns_zero(self, tmp_path: Path):
        assert get_test_count(tmp_path) == 0

    def test_empty_tests_dir_returns_zero(self, tmp_path: Path):
        (tmp_path / "tests").mkdir()
        assert get_test_count(tmp_path) == 0

    def test_nested_test_dirs(self, tmp_path: Path):
        nested = tmp_path / "tests" / "unit"
        nested.mkdir(parents=True)
        (nested / "test_deep.py").write_text("def test_deep():\n    pass\n")
        assert get_test_count(tmp_path) == 1
