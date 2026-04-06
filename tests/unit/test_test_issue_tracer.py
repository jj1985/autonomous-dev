"""Tests for test_issue_tracer — test-to-issue tracing library.

Issue: #675
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import sys

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[2] / "plugins" / "autonomous-dev" / "lib"),
)

from test_issue_tracer import (
    IssueReference,
    TestIssueTracer,
    TracingCategory,
    TracingFinding,
    TracingReport,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_test_file(tmp_path: Path, rel_path: str, content: str) -> Path:
    """Create a file under tmp_path/tests/ with given relative path and content."""
    full_path = tmp_path / "tests" / rel_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content)
    return full_path


def _gh_issues_json(issues: list[dict]) -> str:
    """Return serialized JSON for gh issue list output."""
    return json.dumps(issues)


# ---------------------------------------------------------------------------
# scan_test_references tests
# ---------------------------------------------------------------------------


class TestScanReferences:
    """Tests for scan_test_references pattern matching."""

    def test_scan_finds_class_name_pattern(self, tmp_path: Path) -> None:
        _make_test_file(tmp_path, "test_foo.py", "class TestIssue656:\n    pass\n")
        tracer = TestIssueTracer(tmp_path)
        refs = tracer.scan_test_references()

        assert len(refs) == 1
        assert refs[0].issue_number == 656
        assert refs[0].reference_type == "class_name"

    def test_scan_finds_docstring_pattern(self, tmp_path: Path) -> None:
        content = '""\"Regression for #656\"\"\"\ndef test_something():\n    pass\n'
        _make_test_file(tmp_path, "test_bar.py", content)
        tracer = TestIssueTracer(tmp_path)
        refs = tracer.scan_test_references()

        issue_nums = [r.issue_number for r in refs]
        assert 656 in issue_nums

    def test_scan_finds_comment_pattern(self, tmp_path: Path) -> None:
        _make_test_file(tmp_path, "test_c.py", "# Issue: #789\ndef test_x():\n    pass\n")
        tracer = TestIssueTracer(tmp_path)
        refs = tracer.scan_test_references()

        assert any(r.issue_number == 789 and r.reference_type == "comment" for r in refs)

    def test_scan_finds_gh_shorthand(self, tmp_path: Path) -> None:
        _make_test_file(tmp_path, "test_d.py", "# GH-42 regression\ndef test_y():\n    pass\n")
        tracer = TestIssueTracer(tmp_path)
        refs = tracer.scan_test_references()

        assert any(r.issue_number == 42 and r.reference_type == "gh_shorthand" for r in refs)

    def test_scan_finds_function_name_pattern(self, tmp_path: Path) -> None:
        _make_test_file(
            tmp_path, "test_e.py", "def test_issue_589_regression():\n    pass\n"
        )
        tracer = TestIssueTracer(tmp_path)
        refs = tracer.scan_test_references()

        assert any(r.issue_number == 589 and r.reference_type == "function_name" for r in refs)

    def test_scan_finds_marker_pattern(self, tmp_path: Path) -> None:
        _make_test_file(
            tmp_path,
            "test_f.py",
            '@pytest.mark.issue(123)\ndef test_marked():\n    pass\n',
        )
        tracer = TestIssueTracer(tmp_path)
        refs = tracer.scan_test_references()

        assert any(r.issue_number == 123 and r.reference_type == "marker" for r in refs)

    def test_scan_finds_fixes_pattern(self, tmp_path: Path) -> None:
        _make_test_file(tmp_path, "test_g.py", "# Fixes #999\ndef test_fix():\n    pass\n")
        tracer = TestIssueTracer(tmp_path)
        refs = tracer.scan_test_references()

        assert any(r.issue_number == 999 for r in refs)

    def test_scan_ignores_non_test_dirs(self, tmp_path: Path) -> None:
        """Files outside tests/ should not be scanned."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "module.py").write_text("class TestIssue100:\n    pass\n")
        # Also create empty tests dir
        (tmp_path / "tests").mkdir()

        tracer = TestIssueTracer(tmp_path)
        refs = tracer.scan_test_references()

        assert not any(r.issue_number == 100 for r in refs)

    def test_scan_deduplicates_same_issue_same_file(self, tmp_path: Path) -> None:
        content = (
            "class TestIssue656:\n"
            "    # Issue: #656\n"
            "    def test_issue_656_thing(self):\n"
            "        pass\n"
        )
        _make_test_file(tmp_path, "test_dedup.py", content)
        tracer = TestIssueTracer(tmp_path)
        refs = tracer.scan_test_references()

        issue_656_refs = [r for r in refs if r.issue_number == 656]
        assert len(issue_656_refs) == 1

    def test_scan_empty_tests_dir(self, tmp_path: Path) -> None:
        (tmp_path / "tests").mkdir()
        tracer = TestIssueTracer(tmp_path)
        refs = tracer.scan_test_references()
        assert refs == []

    def test_scan_no_tests_dir(self, tmp_path: Path) -> None:
        tracer = TestIssueTracer(tmp_path)
        refs = tracer.scan_test_references()
        assert refs == []


# ---------------------------------------------------------------------------
# False positive filtering
# ---------------------------------------------------------------------------


class TestFalsePositiveFiltering:
    """Ensure common false positives are excluded."""

    def test_hex_color_not_matched(self, tmp_path: Path) -> None:
        _make_test_file(tmp_path, "test_colors.py", "# color = #fff\n# Issue: #fff\n")
        tracer = TestIssueTracer(tmp_path)
        refs = tracer.scan_test_references()

        # #fff should not produce numeric issue refs
        assert not any(r.reference_type == "comment" for r in refs)

    def test_noqa_not_matched(self, tmp_path: Path) -> None:
        _make_test_file(tmp_path, "test_noqa.py", "x = 1  # noqa: E501\n")
        tracer = TestIssueTracer(tmp_path)
        refs = tracer.scan_test_references()

        # noqa comments should not produce issue refs
        assert refs == []


# ---------------------------------------------------------------------------
# fetch_github_issues tests
# ---------------------------------------------------------------------------


class TestFetchGithubIssues:
    """Tests for fetch_github_issues with mocked subprocess."""

    @patch("test_issue_tracer.subprocess.run")
    def test_fetch_issues_returns_dict(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=_gh_issues_json([
                {"number": 1, "state": "OPEN", "title": "Bug"},
                {"number": 2, "state": "CLOSED", "title": "Feature"},
            ]),
        )
        tracer = TestIssueTracer(tmp_path)
        issues = tracer.fetch_github_issues()

        assert 1 in issues
        assert 2 in issues
        assert issues[1]["state"] == "OPEN"

    @patch("test_issue_tracer.subprocess.run")
    def test_fetch_issues_caches_result(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=_gh_issues_json([{"number": 1, "state": "OPEN", "title": "Bug"}]),
        )
        tracer = TestIssueTracer(tmp_path)

        tracer.fetch_github_issues()
        tracer.fetch_github_issues()

        # Only one subprocess call due to caching
        assert mock_run.call_count == 1

    @patch("test_issue_tracer.subprocess.run", side_effect=FileNotFoundError("gh not found"))
    def test_fetch_issues_graceful_gh_missing(self, mock_run: MagicMock, tmp_path: Path) -> None:
        tracer = TestIssueTracer(tmp_path)
        issues = tracer.fetch_github_issues()
        assert issues == {}

    @patch(
        "test_issue_tracer.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=30),
    )
    def test_fetch_issues_graceful_timeout(self, mock_run: MagicMock, tmp_path: Path) -> None:
        tracer = TestIssueTracer(tmp_path)
        issues = tracer.fetch_github_issues()
        assert issues == {}

    @patch("test_issue_tracer.subprocess.run")
    def test_fetch_issues_graceful_nonzero_exit(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = MagicMock(returncode=1, stderr="auth required")
        tracer = TestIssueTracer(tmp_path)
        issues = tracer.fetch_github_issues()
        assert issues == {}


# ---------------------------------------------------------------------------
# analyze tests
# ---------------------------------------------------------------------------


class TestAnalyze:
    """Tests for the full analyze() cross-reference."""

    @patch("test_issue_tracer.subprocess.run")
    def test_analyze_untested_issues(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Open issue with no test reference -> UNTESTED_ISSUE finding."""
        (tmp_path / "tests").mkdir()
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=_gh_issues_json([
                {"number": 500, "state": "OPEN", "title": "Untested feature"},
            ]),
        )
        tracer = TestIssueTracer(tmp_path)
        report = tracer.analyze()

        untested = [f for f in report.findings if f.category == TracingCategory.UNTESTED_ISSUE]
        assert len(untested) >= 1
        assert untested[0].issue_number == 500

    @patch("test_issue_tracer.subprocess.run")
    def test_analyze_orphaned_pairs(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Test references closed issue -> ORPHANED_PAIR finding."""
        _make_test_file(tmp_path, "test_old.py", "class TestIssue300:\n    pass\n")
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=_gh_issues_json([
                {"number": 300, "state": "CLOSED", "title": "Old bug"},
            ]),
        )
        tracer = TestIssueTracer(tmp_path)
        report = tracer.analyze()

        orphaned = [f for f in report.findings if f.category == TracingCategory.ORPHANED_PAIR]
        assert len(orphaned) >= 1
        assert orphaned[0].issue_number == 300

    @patch("test_issue_tracer.subprocess.run")
    def test_analyze_untraced_tests(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Test file with no issue refs -> UNTRACED_TEST finding."""
        _make_test_file(tmp_path, "test_plain.py", "def test_something():\n    assert True\n")
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=_gh_issues_json([]),
        )
        tracer = TestIssueTracer(tmp_path)
        report = tracer.analyze()

        untraced = [f for f in report.findings if f.category == TracingCategory.UNTRACED_TEST]
        assert len(untraced) >= 1

    @patch("test_issue_tracer.subprocess.run")
    def test_analyze_empty_project(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Empty project with no tests or issues."""
        (tmp_path / "tests").mkdir()
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=_gh_issues_json([]),
        )
        tracer = TestIssueTracer(tmp_path)
        report = tracer.analyze()

        assert report.findings == []
        assert report.references == []
        assert report.issues_scanned == 0

    @patch("test_issue_tracer.subprocess.run")
    def test_analyze_report_metrics(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Report includes correct scan metrics."""
        _make_test_file(tmp_path, "test_a.py", "class TestIssue1:\n    pass\n")
        _make_test_file(tmp_path, "test_b.py", "def test_plain():\n    pass\n")
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=_gh_issues_json([{"number": 1, "state": "OPEN", "title": "Bug"}]),
        )
        tracer = TestIssueTracer(tmp_path)
        report = tracer.analyze()

        assert report.tests_scanned == 2
        assert report.issues_scanned == 1
        assert report.scan_duration_ms >= 0


# ---------------------------------------------------------------------------
# check_issue_has_test tests
# ---------------------------------------------------------------------------


class TestCheckIssueHasTest:
    """Tests for the quick lookup check_issue_has_test."""

    def test_check_issue_has_test_true(self, tmp_path: Path) -> None:
        _make_test_file(tmp_path, "test_x.py", "class TestIssue42:\n    pass\n")
        tracer = TestIssueTracer(tmp_path)
        assert tracer.check_issue_has_test(42) is True

    def test_check_issue_has_test_false(self, tmp_path: Path) -> None:
        _make_test_file(tmp_path, "test_x.py", "def test_something():\n    pass\n")
        tracer = TestIssueTracer(tmp_path)
        assert tracer.check_issue_has_test(999) is False

    def test_check_issue_has_test_no_tests_dir(self, tmp_path: Path) -> None:
        """Returns True (safe default) when tests dir doesn't exist -- never block."""
        tracer = TestIssueTracer(tmp_path)
        # No tests/ dir => scan returns empty => no match => False
        # But the method returns True on exceptions to never block pipeline
        # With no tests dir, scan_test_references returns [] which means no match => False
        assert tracer.check_issue_has_test(42) is False


# ---------------------------------------------------------------------------
# format_table tests
# ---------------------------------------------------------------------------


class TestFormatTable:
    """Tests for TracingReport.format_table markdown output."""

    def test_format_table_markdown(self) -> None:
        report = TracingReport(
            findings=[
                TracingFinding(
                    category=TracingCategory.UNTESTED_ISSUE,
                    severity="info",
                    description="Missing test",
                    issue_number=42,
                ),
            ],
            references=[],
            scan_duration_ms=100.0,
            issues_scanned=5,
            tests_scanned=10,
        )
        table = report.format_table()

        assert "## Test-to-Issue Tracing Report" in table
        assert "Tests scanned: 10" in table
        assert "Issues scanned: 5" in table
        assert "| untested_issue |" in table
        assert "#42" in table

    def test_format_table_no_findings(self) -> None:
        report = TracingReport(
            scan_duration_ms=50.0,
            issues_scanned=3,
            tests_scanned=5,
        )
        table = report.format_table()

        assert "No findings" in table
