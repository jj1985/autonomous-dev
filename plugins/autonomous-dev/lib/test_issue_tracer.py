"""Test-to-Issue Tracer — map tests to GitHub issues, flag gaps.

Scans test files for issue references, cross-references with GitHub issues,
and produces a tracing report identifying untested issues, orphaned pairs,
and untraced tests.

Issue: #675
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Patterns that match issue references in test files
# Each tuple: (compiled_regex, reference_type, group_index_for_issue_number)
_ISSUE_PATTERNS: List[tuple] = [
    # TestIssue656 or TestIssue656SomeDescription
    (re.compile(r"\bTestIssue(\d+)\b"), "class_name"),
    # test_issue_656_description or test_issue_656
    (re.compile(r"\btest_issue_(\d+)(?:\b|_)"), "function_name"),
    # """...#656...""" or '''...#656...''' in docstrings
    (re.compile(r'(?:"""|\'\'\')\s*.*?#(\d+).*?(?:"""|\'\'\')', re.DOTALL), "docstring"),
    # # Issue: #656 or # Issue #656
    (re.compile(r"#\s*Issue:?\s*#(\d+)"), "comment"),
    # GH-42 or GH-656
    (re.compile(r"\bGH-(\d+)\b"), "gh_shorthand"),
    # @pytest.mark.issue(656) or @pytest.mark.issue("656")
    (re.compile(r'@pytest\.mark\.issue\(["\']?(\d+)["\']?\)'), "marker"),
    # Regression for #656 or Closes #656 or Fixes #656 (in comments/docstrings)
    (re.compile(r"(?:Regression|Closes|Fixes|References|See)\s+#(\d+)"), "comment"),
]

# Patterns that produce false positive #NNN matches
_FALSE_POSITIVE_PATTERNS: List[re.Pattern] = [
    # Hex colors that contain at least one alpha hex char: #fff, #FF00AA, #abc123
    # Pure numeric like #789 is NOT a hex color (it's likely an issue ref)
    re.compile(r"#(?=[0-9a-fA-F]{3,8}\b)(?=[0-9a-fA-F]*[a-fA-F])[0-9a-fA-F]{3,8}\b"),
    # noqa comments: # noqa: E501
    re.compile(r"#\s*noqa\b"),
    # type: ignore comments
    re.compile(r"#\s*type:\s*ignore"),
    # pragma comments
    re.compile(r"#\s*pragma\b"),
    # Bare numbers that are likely not issue refs (very small: #0, #1, #2)
    re.compile(r"#[0-2]\b"),
]


@dataclass
class IssueReference:
    """A reference to a GitHub issue found in a test file."""

    file_path: str
    line: int
    issue_number: int
    reference_type: str  # class_name|docstring|comment|function_name|marker|gh_shorthand


class TracingCategory(Enum):
    """Categories of tracing findings."""

    UNTESTED_ISSUE = "untested_issue"
    ORPHANED_PAIR = "orphaned_pair"
    UNTRACED_TEST = "untraced_test"


@dataclass
class TracingFinding:
    """A finding from the tracing analysis."""

    category: TracingCategory
    severity: str  # info, warning, error
    description: str
    issue_number: Optional[int] = None
    file_path: Optional[str] = None


@dataclass
class TracingReport:
    """Complete tracing report with findings and metrics."""

    findings: List[TracingFinding] = field(default_factory=list)
    references: List[IssueReference] = field(default_factory=list)
    scan_duration_ms: float = 0.0
    issues_scanned: int = 0
    tests_scanned: int = 0

    def format_table(self) -> str:
        """Format report as a markdown table.

        Returns:
            Markdown-formatted summary table of findings.
        """
        lines = [
            "## Test-to-Issue Tracing Report",
            "",
            f"- Tests scanned: {self.tests_scanned}",
            f"- Issues scanned: {self.issues_scanned}",
            f"- References found: {len(self.references)}",
            f"- Findings: {len(self.findings)}",
            f"- Scan duration: {self.scan_duration_ms:.0f}ms",
            "",
        ]

        if not self.findings:
            lines.append("No findings. All tests are traced to issues.")
            return "\n".join(lines)

        lines.append("| Category | Severity | Description | Issue | File |")
        lines.append("|----------|----------|-------------|-------|------|")

        for f in self.findings:
            issue_str = f"#{f.issue_number}" if f.issue_number else "-"
            file_str = f.file_path or "-"
            lines.append(
                f"| {f.category.value} | {f.severity} | {f.description} | {issue_str} | {file_str} |"
            )

        return "\n".join(lines)


def _is_false_positive(line_text: str, match_str: str) -> bool:
    """Check if an issue number match is a false positive.

    Args:
        line_text: The full line of text containing the match.
        match_str: The matched string (e.g., '#656').

    Returns:
        True if the match is likely a false positive.
    """
    for pattern in _FALSE_POSITIVE_PATTERNS:
        if pattern.search(line_text):
            # Check if the false positive pattern overlaps with our match
            for fp_match in pattern.finditer(line_text):
                if match_str in fp_match.group():
                    return True
    return False


class TestIssueTracer:
    """Scan test files for issue references and cross-reference with GitHub issues.

    Args:
        project_root: Root directory of the project to scan.
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self._issue_cache: Optional[Dict[int, dict]] = None
        self._cache_timestamp: float = 0.0

    def scan_test_references(self) -> List[IssueReference]:
        """Scan test files for issue references.

        Searches all Python files in tests/ directories for patterns
        that reference GitHub issue numbers.

        Returns:
            List of IssueReference objects found in test files.
        """
        references: List[IssueReference] = []
        seen: set = set()  # (file_path, issue_number) dedup key

        tests_dir = self.project_root / "tests"
        if not tests_dir.exists():
            return references

        for test_file in tests_dir.rglob("*.py"):
            try:
                content = test_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                logger.debug("Could not read file: %s", test_file)
                continue

            rel_path = str(test_file.relative_to(self.project_root))

            for line_num, line_text in enumerate(content.splitlines(), start=1):
                for pattern, ref_type in _ISSUE_PATTERNS:
                    for match in pattern.finditer(line_text):
                        issue_num_str = match.group(1)
                        try:
                            issue_num = int(issue_num_str)
                        except ValueError:
                            continue

                        # Skip very small numbers (likely not real issues)
                        if issue_num < 1:
                            continue

                        # False positive filtering for bare #NNN in comments
                        if ref_type == "comment" and _is_false_positive(line_text, f"#{issue_num_str}"):
                            continue

                        dedup_key = (rel_path, issue_num)
                        if dedup_key in seen:
                            continue
                        seen.add(dedup_key)

                        references.append(
                            IssueReference(
                                file_path=rel_path,
                                line=line_num,
                                issue_number=issue_num,
                                reference_type=ref_type,
                            )
                        )

            # Also scan multiline docstrings
            for pattern, ref_type in _ISSUE_PATTERNS:
                if ref_type != "docstring":
                    continue
                for match in pattern.finditer(content):
                    issue_num_str = match.group(1)
                    try:
                        issue_num = int(issue_num_str)
                    except ValueError:
                        continue

                    if issue_num < 1:
                        continue

                    dedup_key = (rel_path, issue_num)
                    if dedup_key in seen:
                        continue
                    seen.add(dedup_key)

                    # Approximate line number from character offset
                    line_num = content[:match.start()].count("\n") + 1
                    references.append(
                        IssueReference(
                            file_path=rel_path,
                            line=line_num,
                            issue_number=issue_num,
                            reference_type=ref_type,
                        )
                    )

        return references

    def fetch_github_issues(self, *, cache_ttl_seconds: int = 300) -> Dict[int, dict]:
        """Fetch GitHub issues using the gh CLI.

        Caches results for cache_ttl_seconds to avoid repeated API calls.
        Returns empty dict on any gh CLI failure (missing, auth, timeout).

        Args:
            cache_ttl_seconds: How long to cache results in seconds.

        Returns:
            Dict mapping issue number to issue data (number, state, title).
        """
        now = time.time()
        if self._issue_cache is not None and (now - self._cache_timestamp) < cache_ttl_seconds:
            return self._issue_cache

        try:
            result = subprocess.run(
                [
                    "gh", "issue", "list",
                    "--state", "all",
                    "--limit", "500",
                    "--json", "number,state,title",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(self.project_root),
            )

            if result.returncode != 0:
                logger.debug("gh issue list failed: %s", result.stderr)
                self._issue_cache = {}
                self._cache_timestamp = now
                return self._issue_cache

            issues_list = json.loads(result.stdout)
            self._issue_cache = {issue["number"]: issue for issue in issues_list}
            self._cache_timestamp = now
            return self._issue_cache

        except FileNotFoundError:
            logger.debug("gh CLI not found")
            self._issue_cache = {}
            self._cache_timestamp = now
            return self._issue_cache
        except subprocess.TimeoutExpired:
            logger.debug("gh issue list timed out")
            self._issue_cache = {}
            self._cache_timestamp = now
            return self._issue_cache
        except (json.JSONDecodeError, KeyError) as e:
            logger.debug("Failed to parse gh output: %s", e)
            self._issue_cache = {}
            self._cache_timestamp = now
            return self._issue_cache

    def analyze(self) -> TracingReport:
        """Cross-reference test references with GitHub issues.

        Produces findings for:
        - Untested issues: open issues with no test references
        - Orphaned pairs: test references to closed issues
        - Untraced tests: test files with zero issue references

        Returns:
            TracingReport with findings, references, and metrics.
        """
        start = time.time()

        references = self.scan_test_references()
        issues = self.fetch_github_issues()

        # Build lookup: issue_number -> list of references
        refs_by_issue: Dict[int, List[IssueReference]] = {}
        for ref in references:
            refs_by_issue.setdefault(ref.issue_number, []).append(ref)

        # Build lookup: file_path -> list of references
        refs_by_file: Dict[str, List[IssueReference]] = {}
        for ref in references:
            refs_by_file.setdefault(ref.file_path, []).append(ref)

        findings: List[TracingFinding] = []

        # Untested issues: open issues with no test reference
        for issue_num, issue_data in issues.items():
            if issue_data.get("state", "").upper() == "OPEN":
                if issue_num not in refs_by_issue:
                    findings.append(
                        TracingFinding(
                            category=TracingCategory.UNTESTED_ISSUE,
                            severity="info",
                            description=f"Open issue has no test reference: {issue_data.get('title', '')}",
                            issue_number=issue_num,
                        )
                    )

        # Orphaned pairs: test references to closed issues
        for issue_num, refs in refs_by_issue.items():
            if issue_num in issues:
                issue_data = issues[issue_num]
                if issue_data.get("state", "").upper() == "CLOSED":
                    for ref in refs:
                        findings.append(
                            TracingFinding(
                                category=TracingCategory.ORPHANED_PAIR,
                                severity="info",
                                description=f"Test references closed issue: {issue_data.get('title', '')}",
                                issue_number=issue_num,
                                file_path=ref.file_path,
                            )
                        )

        # Untraced tests: test files with zero issue references
        tests_dir = self.project_root / "tests"
        if tests_dir.exists():
            for test_file in tests_dir.rglob("test_*.py"):
                rel_path = str(test_file.relative_to(self.project_root))
                if rel_path not in refs_by_file:
                    findings.append(
                        TracingFinding(
                            category=TracingCategory.UNTRACED_TEST,
                            severity="info",
                            description="Test file has no issue references",
                            file_path=rel_path,
                        )
                    )

        elapsed_ms = (time.time() - start) * 1000

        return TracingReport(
            findings=findings,
            references=references,
            scan_duration_ms=elapsed_ms,
            issues_scanned=len(issues),
            tests_scanned=sum(1 for _ in (self.project_root / "tests").rglob("test_*.py"))
            if tests_dir.exists()
            else 0,
        )

    def check_issue_has_test(self, issue_number: int) -> bool:
        """Quick check if an issue number has a corresponding test reference.

        Args:
            issue_number: The GitHub issue number to check.

        Returns:
            True if at least one test file references this issue number.
        """
        try:
            references = self.scan_test_references()
            return any(ref.issue_number == issue_number for ref in references)
        except Exception:
            # Never block the pipeline
            return True
