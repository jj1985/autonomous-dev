"""Unit tests for mine_git_samples.py script.

Tests keyword classification, difficulty estimation, sample building,
and git commit mining with mocked subprocess calls.

GitHub Issue: #573
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add scripts to path
sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[3] / "scripts"),
)

from mine_git_samples import (
    build_sample,
    classify_defect,
    estimate_difficulty,
    mine_clean_commits,
    mine_fix_commits,
)


class TestClassifyDefect:
    """Test classify_defect keyword-to-category mapping."""

    def test_hardcoded_keyword(self) -> None:
        result = classify_defect("", "fix hardcoded value in scorer")
        assert result == "hardcoded-value"

    def test_null_keyword(self) -> None:
        result = classify_defect("+ if value is null:", "fix null pointer")
        assert result == "null-safety"

    def test_none_keyword(self) -> None:
        result = classify_defect("+ if text is None:", "handle None input")
        assert result == "null-safety"

    def test_dispatch_keyword(self) -> None:
        result = classify_defect("", "fix wrong dispatch table entry")
        assert result == "wrong-dispatch"

    def test_stub_keyword(self) -> None:
        result = classify_defect("+ raise NotImplementedError", "remove stub")
        assert result == "stub-implementation"

    def test_race_condition_keyword(self) -> None:
        result = classify_defect("", "fix race condition in counter")
        assert result == "race-condition"

    def test_secret_keyword(self) -> None:
        result = classify_defect("+ API_KEY=sk-ant-...", "remove committed secret")
        assert result == "secrets-committed"

    def test_division_by_zero(self) -> None:
        result = classify_defect("", "fix division by zero in ratio calc")
        assert result == "division-by-zero"

    def test_no_match_returns_empty(self) -> None:
        result = classify_defect("+ x = 1", "refactor: rename variable")
        assert result == ""

    def test_match_in_diff_text(self) -> None:
        result = classify_defect("except Exception:\n    pass  # swallowed", "cleanup")
        assert result == "error-swallowed"


class TestEstimateDifficulty:
    """Test estimate_difficulty heuristic logic."""

    def test_easy_stub_category(self) -> None:
        result = estimate_difficulty("line1\nline2", 1, "stub-implementation")
        assert result == "easy"

    def test_easy_hardcoded_category(self) -> None:
        result = estimate_difficulty("small diff", 1, "hardcoded-value")
        assert result == "easy"

    def test_easy_secrets_category(self) -> None:
        result = estimate_difficulty("small diff", 1, "secrets-committed")
        assert result == "easy"

    def test_hard_race_condition(self) -> None:
        result = estimate_difficulty("line1\nline2", 1, "race-condition")
        assert result == "hard"

    def test_hard_stale_cache(self) -> None:
        result = estimate_difficulty("line1\nline2", 1, "stale-cache")
        assert result == "hard"

    def test_hard_incomplete_fix(self) -> None:
        result = estimate_difficulty("line1\nline2", 1, "incomplete-fix")
        assert result == "hard"

    def test_small_diff_single_file_easy(self) -> None:
        result = estimate_difficulty("line1\nline2\nline3", 1, "unknown-category")
        assert result == "easy"

    def test_large_diff_hard(self) -> None:
        lines = "\n".join(f"line{i}" for i in range(35))
        result = estimate_difficulty(lines, 1, "unknown-category")
        assert result == "hard"

    def test_many_files_hard(self) -> None:
        result = estimate_difficulty("line1\nline2", 3, "unknown-category")
        assert result == "hard"

    def test_medium_default(self) -> None:
        lines = "\n".join(f"line{i}" for i in range(15))
        result = estimate_difficulty(lines, 2, "unknown-category")
        assert result == "medium"


class TestBuildSample:
    """Test build_sample output schema."""

    def test_basic_sample(self) -> None:
        sample = build_sample(
            sample_id="test-001",
            source_repo="test-repo",
            diff_text="--- a/foo.py\n+++ b/foo.py",
            description="Test sample",
        )
        assert sample["sample_id"] == "test-001"
        assert sample["source_repo"] == "test-repo"
        assert sample["diff_text"] == "--- a/foo.py\n+++ b/foo.py"
        assert sample["description"] == "Test sample"
        assert sample["expected_verdict"] == "BLOCKING"
        assert sample["difficulty"] == "medium"

    def test_sample_with_all_fields(self) -> None:
        sample = build_sample(
            sample_id="test-002",
            source_repo="realign",
            diff_text="diff content",
            description="Full sample",
            expected_verdict="APPROVE",
            issue_ref="#123",
            commit_sha="abc123",
            expected_categories=["null-safety"],
            category_tags=["tag1", "tag2"],
            difficulty="hard",
            defect_category="null-safety",
        )
        assert sample["expected_verdict"] == "APPROVE"
        assert sample["issue_ref"] == "#123"
        assert sample["commit_sha"] == "abc123"
        assert sample["expected_categories"] == ["null-safety"]
        assert sample["category_tags"] == ["tag1", "tag2"]
        assert sample["difficulty"] == "hard"
        assert sample["defect_category"] == "null-safety"

    def test_sample_defaults(self) -> None:
        sample = build_sample("id", "repo", "diff", "desc")
        assert sample["issue_ref"] == ""
        assert sample["commit_sha"] == ""
        assert sample["expected_categories"] == []
        assert sample["category_tags"] == []
        assert sample["defect_category"] == ""

    def test_required_keys_present(self) -> None:
        sample = build_sample("id", "repo", "diff", "desc")
        required_keys = {
            "sample_id", "source_repo", "issue_ref", "commit_sha",
            "diff_text", "expected_verdict", "expected_categories",
            "category_tags", "description", "difficulty", "defect_category",
        }
        assert required_keys.issubset(set(sample.keys()))


class TestMineFixCommits:
    """Test mine_fix_commits with mocked subprocess."""

    @patch("mine_git_samples.subprocess.run")
    @patch("mine_git_samples.extract_diff")
    def test_mine_fix_commits_basic(self, mock_diff, mock_run) -> None:
        mock_run.return_value = MagicMock(
            stdout="abc12345|fix: handle null input\ndef67890|fix: remove hardcoded value\n",
            returncode=0,
        )
        mock_diff.side_effect = [
            "--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-old\n+new null check",
            "--- a/bar.py\n+++ b/bar.py\n@@ -1 +1 @@\n-old\n+new hardcoded fix",
        ]

        results = mine_fix_commits("/fake/repo", since="2025-01-01")
        assert len(results) == 2
        assert results[0]["source_repo"] == "repo"
        assert results[0]["expected_verdict"] == "BLOCKING"
        assert results[0]["commit_sha"] == "abc12345"

    @patch("mine_git_samples.subprocess.run")
    def test_mine_fix_commits_empty_log(self, mock_run) -> None:
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        results = mine_fix_commits("/fake/repo")
        assert results == []

    @patch("mine_git_samples.subprocess.run")
    @patch("mine_git_samples.extract_diff")
    def test_mine_fix_commits_skips_empty_diffs(self, mock_diff, mock_run) -> None:
        mock_run.return_value = MagicMock(
            stdout="abc12345|fix: something\n",
            returncode=0,
        )
        mock_diff.return_value = ""  # Empty diff
        results = mine_fix_commits("/fake/repo")
        assert results == []


class TestMineCleanCommits:
    """Test mine_clean_commits with mocked subprocess."""

    @patch("mine_git_samples.subprocess.run")
    @patch("mine_git_samples.extract_diff")
    def test_mine_clean_commits_basic(self, mock_diff, mock_run) -> None:
        mock_run.return_value = MagicMock(
            stdout="abc12345|feat: add new endpoint\n",
            returncode=0,
        )
        mock_diff.return_value = (
            "--- a/routes.py\n+++ b/routes.py\n@@ -1 +1,5 @@\n+@router.get('/api')\n+def handler():\n+    return {}"
        )

        results = mine_clean_commits("/fake/repo", since="2025-01-01")
        assert len(results) == 1
        assert results[0]["expected_verdict"] == "APPROVE"

    @patch("mine_git_samples.subprocess.run")
    @patch("mine_git_samples.extract_diff")
    def test_mine_clean_commits_skips_fix_messages(self, mock_diff, mock_run) -> None:
        mock_run.return_value = MagicMock(
            stdout="abc12345|fix: actually a fix\n",
            returncode=0,
        )
        mock_diff.return_value = "--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-old\n+new"
        results = mine_clean_commits("/fake/repo")
        assert results == []
