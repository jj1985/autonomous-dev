#!/usr/bin/env python3
"""Unit tests for sweep_analyzer module.

Tests the SweepFinding, SweepReport, and SweepAnalyzer classes including
all three analysis modes (tests, docs, code) and error handling.
"""

import sys
from pathlib import Path
from unittest import mock
from unittest.mock import MagicMock, patch

import pytest

# Ensure lib is importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "plugins" / "autonomous-dev" / "lib"))

from sweep_analyzer import (
    SweepAnalyzer,
    SweepCategory,
    SweepFinding,
    SweepReport,
    SweepSeverity,
    _map_severity,
)


# =============================================================================
# SweepFinding Tests
# =============================================================================


class TestSweepFinding:
    """Tests for SweepFinding dataclass."""

    def test_creation_basic(self):
        """Test basic SweepFinding creation."""
        finding = SweepFinding(
            file_path="src/foo.py",
            category=SweepCategory.CODE,
            severity=SweepSeverity.HIGH,
            description="Large file detected",
            suggested_fix="Split into smaller modules",
        )
        assert finding.file_path == "src/foo.py"
        assert finding.category == SweepCategory.CODE
        assert finding.severity == SweepSeverity.HIGH
        assert finding.line is None

    def test_creation_with_line(self):
        """Test SweepFinding creation with line number."""
        finding = SweepFinding(
            file_path="tests/test_foo.py",
            category=SweepCategory.TEST,
            severity=SweepSeverity.MEDIUM,
            description="Brittle assertion",
            suggested_fix="Use >= instead",
            line=42,
        )
        assert finding.line == 42

    def test_format_without_line(self):
        """Test format() output without line number."""
        finding = SweepFinding(
            file_path="src/foo.py",
            category=SweepCategory.CODE,
            severity=SweepSeverity.HIGH,
            description="Large file",
            suggested_fix="Split it",
        )
        result = finding.format()
        assert result == "[HIGH] src/foo.py: Large file"

    def test_format_with_line(self):
        """Test format() output with line number."""
        finding = SweepFinding(
            file_path="src/foo.py",
            category=SweepCategory.CODE,
            severity=SweepSeverity.CRITICAL,
            description="Circular import",
            suggested_fix="Refactor",
            line=10,
        )
        result = finding.format()
        assert result == "[CRITICAL] src/foo.py:10: Circular import"

    def test_category_values(self):
        """Test SweepCategory enum values."""
        assert SweepCategory.TEST.value == "test"
        assert SweepCategory.DOC.value == "doc"
        assert SweepCategory.CODE.value == "code"

    def test_severity_values(self):
        """Test SweepSeverity enum values."""
        assert SweepSeverity.CRITICAL.value == "critical"
        assert SweepSeverity.HIGH.value == "high"
        assert SweepSeverity.MEDIUM.value == "medium"
        assert SweepSeverity.LOW.value == "low"


# =============================================================================
# SweepReport Tests
# =============================================================================


class TestSweepReport:
    """Tests for SweepReport dataclass."""

    def test_empty_report(self):
        """Test empty report properties."""
        report = SweepReport()
        assert not report.has_findings
        assert report.summary == {}
        assert report.scan_duration_ms == 0
        assert report.modes_run == []

    def test_has_findings(self):
        """Test has_findings property with findings present."""
        report = SweepReport(
            findings=[
                SweepFinding(
                    file_path="x.py",
                    category=SweepCategory.CODE,
                    severity=SweepSeverity.LOW,
                    description="test",
                    suggested_fix="fix",
                )
            ]
        )
        assert report.has_findings

    def test_summary_counts(self):
        """Test summary counts findings by category."""
        report = SweepReport(
            findings=[
                SweepFinding("a.py", SweepCategory.TEST, SweepSeverity.HIGH, "d1", "f1"),
                SweepFinding("b.py", SweepCategory.TEST, SweepSeverity.LOW, "d2", "f2"),
                SweepFinding("c.py", SweepCategory.CODE, SweepSeverity.MEDIUM, "d3", "f3"),
            ]
        )
        assert report.summary == {"test": 2, "code": 1}

    def test_format_report_empty(self):
        """Test format_report with no findings."""
        report = SweepReport()
        assert "Clean sweep" in report.format_report()

    def test_format_report_with_findings(self):
        """Test format_report with findings groups by category."""
        report = SweepReport(
            findings=[
                SweepFinding("a.py", SweepCategory.TEST, SweepSeverity.HIGH, "fail1", "fix1"),
                SweepFinding("b.py", SweepCategory.CODE, SweepSeverity.LOW, "dead", "remove"),
                SweepFinding("c.py", SweepCategory.TEST, SweepSeverity.CRITICAL, "fail2", "fix2"),
            ],
            scan_duration_ms=150,
            modes_run=["tests", "code"],
        )
        output = report.format_report()
        assert "3 findings" in output
        assert "150ms" in output
        assert "TEST (2 issues)" in output
        assert "CODE (1 issues)" in output
        # CRITICAL should appear before HIGH in TEST section
        test_section_start = output.index("TEST")
        critical_pos = output.index("CRITICAL", test_section_start)
        high_pos = output.index("HIGH", test_section_start)
        assert critical_pos < high_pos

    def test_format_report_includes_fix(self):
        """Test that format_report includes suggested fixes."""
        report = SweepReport(
            findings=[
                SweepFinding("a.py", SweepCategory.DOC, SweepSeverity.MEDIUM, "drift", "update docs"),
            ],
            modes_run=["docs"],
        )
        output = report.format_report()
        assert "Fix: update docs" in output

    def test_to_dict(self):
        """Test to_dict serialization."""
        report = SweepReport(
            findings=[
                SweepFinding("a.py", SweepCategory.TEST, SweepSeverity.HIGH, "fail", "fix", line=5),
            ],
            scan_duration_ms=100,
            modes_run=["tests"],
        )
        d = report.to_dict()
        assert d["duration_ms"] == 100
        assert d["modes_run"] == ["tests"]
        assert len(d["findings"]) == 1
        assert d["findings"][0]["file"] == "a.py"
        assert d["findings"][0]["line"] == 5
        assert d["findings"][0]["category"] == "test"
        assert d["findings"][0]["severity"] == "high"
        assert d["summary"] == {"test": 1}


# =============================================================================
# Severity Mapping Tests
# =============================================================================


class TestSeverityMapping:
    """Tests for _map_severity function."""

    def test_map_critical(self):
        from tech_debt_detector import Severity

        assert _map_severity(Severity.CRITICAL) == SweepSeverity.CRITICAL

    def test_map_high(self):
        from tech_debt_detector import Severity

        assert _map_severity(Severity.HIGH) == SweepSeverity.HIGH

    def test_map_medium(self):
        from tech_debt_detector import Severity

        assert _map_severity(Severity.MEDIUM) == SweepSeverity.MEDIUM

    def test_map_low(self):
        from tech_debt_detector import Severity

        assert _map_severity(Severity.LOW) == SweepSeverity.LOW


# =============================================================================
# SweepAnalyzer Tests
# =============================================================================


class TestAnalyzeTests:
    """Tests for SweepAnalyzer.analyze_tests()."""

    @patch("sweep_analyzer.subprocess.run")
    @patch("sweep_analyzer.TechDebtDetector")
    def test_converts_pytest_failures(self, mock_detector_cls, mock_run):
        """Test that pytest FAILED lines are converted to findings."""
        mock_run.return_value = MagicMock(
            stdout="FAILED tests/test_foo.py::test_bar - AssertionError\n1 failed\n",
            stderr="",
        )
        mock_detector = MagicMock()
        mock_detector.detect_red_test_accumulation.return_value = []
        mock_detector_cls.return_value = mock_detector

        analyzer = SweepAnalyzer(Path("/tmp/fake_project"))
        # Mock internal methods to avoid filesystem access
        analyzer._detect_dead_test_imports = MagicMock(return_value=[])
        analyzer._detect_brittle_assertions = MagicMock(return_value=[])

        findings = analyzer.analyze_tests()
        failed_findings = [f for f in findings if "Failing test" in f.description]
        assert len(failed_findings) == 1
        assert failed_findings[0].severity == SweepSeverity.HIGH
        assert failed_findings[0].category == SweepCategory.TEST

    @patch("sweep_analyzer.subprocess.run")
    @patch("sweep_analyzer.TechDebtDetector")
    def test_converts_tech_debt_issues(self, mock_detector_cls, mock_run):
        """Test that TechDebtDetector red test issues are converted."""
        from tech_debt_detector import Severity, TechDebtIssue

        mock_run.return_value = MagicMock(stdout="", stderr="")

        mock_issue = TechDebtIssue(
            category="red_test",
            severity=Severity.HIGH,
            file_path="tests/test_broken.py",
            metric_value=3,
            threshold=5,
            message="3 red tests accumulated",
            recommendation="Fix failing tests",
        )
        mock_detector = MagicMock()
        mock_detector.detect_red_test_accumulation.return_value = [mock_issue]
        mock_detector_cls.return_value = mock_detector

        analyzer = SweepAnalyzer(Path("/tmp/fake_project"))
        analyzer._detect_dead_test_imports = MagicMock(return_value=[])
        analyzer._detect_brittle_assertions = MagicMock(return_value=[])

        findings = analyzer.analyze_tests()
        debt_findings = [f for f in findings if "red tests" in f.description]
        assert len(debt_findings) == 1
        assert debt_findings[0].severity == SweepSeverity.HIGH

    @patch("sweep_analyzer.subprocess.run")
    @patch("sweep_analyzer.TechDebtDetector")
    def test_handles_pytest_timeout(self, mock_detector_cls, mock_run):
        """Test graceful handling of pytest timeout."""
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="pytest", timeout=120)
        mock_detector = MagicMock()
        mock_detector.detect_red_test_accumulation.return_value = []
        mock_detector_cls.return_value = mock_detector

        analyzer = SweepAnalyzer(Path("/tmp/fake_project"))
        analyzer._detect_dead_test_imports = MagicMock(return_value=[])
        analyzer._detect_brittle_assertions = MagicMock(return_value=[])

        findings = analyzer.analyze_tests()
        timeout_findings = [f for f in findings if "TimeoutExpired" in f.description]
        assert len(timeout_findings) == 1
        assert timeout_findings[0].severity == SweepSeverity.LOW

    @patch("sweep_analyzer.subprocess.run")
    @patch("sweep_analyzer.TechDebtDetector")
    def test_handles_detector_exception(self, mock_detector_cls, mock_run):
        """Test graceful handling of TechDebtDetector exception."""
        mock_run.return_value = MagicMock(stdout="", stderr="")
        mock_detector = MagicMock()
        mock_detector.detect_red_test_accumulation.side_effect = RuntimeError("boom")
        mock_detector_cls.return_value = mock_detector

        analyzer = SweepAnalyzer(Path("/tmp/fake_project"))
        analyzer._detect_dead_test_imports = MagicMock(return_value=[])
        analyzer._detect_brittle_assertions = MagicMock(return_value=[])

        findings = analyzer.analyze_tests()
        error_findings = [f for f in findings if "Red test detection failed" in f.description]
        assert len(error_findings) == 1


class TestAnalyzeDocs:
    """Tests for SweepAnalyzer.analyze_docs()."""

    @patch("sweep_analyzer.HybridManifestValidator")
    def test_calls_validator_regex_only(self, mock_validator_cls):
        """Test that HybridManifestValidator is called with REGEX_ONLY mode."""
        mock_report = MagicMock()
        mock_report.issues = []
        mock_validator = MagicMock()
        mock_validator.validate.return_value = mock_report
        mock_validator_cls.return_value = mock_validator

        analyzer = SweepAnalyzer(Path("/tmp/fake_project"))
        analyzer._check_component_counts = MagicMock(return_value=[])

        findings = analyzer.analyze_docs()

        mock_validator_cls.assert_called_once()
        call_kwargs = mock_validator_cls.call_args
        # Check mode parameter
        assert call_kwargs[1]["mode"].value in ("regex-only", "regex_only")

    @patch("sweep_analyzer.HybridManifestValidator")
    def test_converts_parity_issues(self, mock_validator_cls):
        """Test that ParityIssue objects are converted to SweepFindings."""
        mock_issue = MagicMock()
        mock_issue.level.value = "ERROR"
        mock_issue.message = "Version mismatch"
        mock_issue.details = "CLAUDE.md"

        mock_report = MagicMock()
        mock_report.issues = [mock_issue]
        mock_validator = MagicMock()
        mock_validator.validate.return_value = mock_report
        mock_validator_cls.return_value = mock_validator

        analyzer = SweepAnalyzer(Path("/tmp/fake_project"))
        analyzer._check_component_counts = MagicMock(return_value=[])

        findings = analyzer.analyze_docs()
        assert len(findings) >= 1
        doc_findings = [f for f in findings if f.category == SweepCategory.DOC]
        assert len(doc_findings) >= 1
        assert doc_findings[0].severity == SweepSeverity.HIGH

    @patch("sweep_analyzer.HybridManifestValidator")
    def test_handles_validator_exception(self, mock_validator_cls):
        """Test graceful handling of validator exception."""
        mock_validator_cls.side_effect = RuntimeError("no manifest")

        analyzer = SweepAnalyzer(Path("/tmp/fake_project"))
        analyzer._check_component_counts = MagicMock(return_value=[])

        findings = analyzer.analyze_docs()
        error_findings = [f for f in findings if "Doc validation failed" in f.description]
        assert len(error_findings) == 1

    def test_handles_missing_validator(self):
        """Test graceful handling when HybridManifestValidator is None."""
        analyzer = SweepAnalyzer(Path("/tmp/fake_project"))
        analyzer._check_component_counts = MagicMock(return_value=[])

        # Temporarily set to None
        import sweep_analyzer

        original = sweep_analyzer.HybridManifestValidator
        sweep_analyzer.HybridManifestValidator = None
        try:
            findings = analyzer.analyze_docs()
            unavailable = [f for f in findings if "not available" in f.description]
            assert len(unavailable) == 1
        finally:
            sweep_analyzer.HybridManifestValidator = original


class TestAnalyzeCode:
    """Tests for SweepAnalyzer.analyze_code()."""

    @patch("sweep_analyzer.TechDebtDetector")
    def test_converts_tech_debt_report(self, mock_detector_cls):
        """Test that TechDebtReport issues are converted to findings."""
        from tech_debt_detector import Severity, TechDebtIssue

        mock_issue = TechDebtIssue(
            category="large_file",
            severity=Severity.HIGH,
            file_path="src/big.py",
            metric_value=2000,
            threshold=1500,
            message="File exceeds 1500 LOC",
            recommendation="Split into modules",
        )
        mock_report = MagicMock()
        mock_report.issues = [mock_issue]
        mock_detector = MagicMock()
        mock_detector.analyze.return_value = mock_report
        mock_detector_cls.return_value = mock_detector

        analyzer = SweepAnalyzer(Path("/tmp/fake_project"))
        analyzer._detect_dead_imports = MagicMock(return_value=[])

        findings = analyzer.analyze_code()
        code_findings = [f for f in findings if f.category == SweepCategory.CODE]
        assert len(code_findings) >= 1
        assert code_findings[0].severity == SweepSeverity.HIGH
        assert "1500 LOC" in code_findings[0].description

    @patch("sweep_analyzer.OrphanFileCleaner")
    @patch("sweep_analyzer.TechDebtDetector")
    def test_handles_orphan_detection_error(self, mock_detector_cls, mock_cleaner_cls):
        """Test that OrphanDetectionError is silently caught (non-plugin repos)."""
        mock_report = MagicMock()
        mock_report.issues = []
        mock_detector = MagicMock()
        mock_detector.analyze.return_value = mock_report
        mock_detector_cls.return_value = mock_detector

        import sweep_analyzer as sa

        mock_cleaner = MagicMock()
        mock_cleaner.detect_orphans.side_effect = sa.OrphanDetectionError("no plugin.json")
        mock_cleaner_cls.return_value = mock_cleaner

        analyzer = SweepAnalyzer(Path("/tmp/fake_project"))
        analyzer._detect_dead_imports = MagicMock(return_value=[])

        findings = analyzer.analyze_code()
        # OrphanDetectionError should NOT produce a finding
        orphan_error_findings = [f for f in findings if "Orphan detection failed" in f.description]
        assert len(orphan_error_findings) == 0

    @patch("sweep_analyzer.OrphanFileCleaner")
    @patch("sweep_analyzer.TechDebtDetector")
    def test_converts_orphan_files(self, mock_detector_cls, mock_cleaner_cls):
        """Test that orphaned files are converted to findings."""
        mock_report = MagicMock()
        mock_report.issues = []
        mock_detector = MagicMock()
        mock_detector.analyze.return_value = mock_report
        mock_detector_cls.return_value = mock_detector

        mock_orphan = MagicMock()
        mock_orphan.path = Path("/project/.claude/commands/old.md")
        mock_orphan.category = "command"
        mock_orphan.reason = "Not listed in plugin.json commands"
        mock_cleaner = MagicMock()
        mock_cleaner.detect_orphans.return_value = [mock_orphan]
        mock_cleaner_cls.return_value = mock_cleaner

        analyzer = SweepAnalyzer(Path("/tmp/fake_project"))
        analyzer._detect_dead_imports = MagicMock(return_value=[])

        findings = analyzer.analyze_code()
        orphan_findings = [f for f in findings if "Orphaned" in f.description]
        assert len(orphan_findings) == 1
        assert orphan_findings[0].severity == SweepSeverity.MEDIUM

    @patch("sweep_analyzer.TechDebtDetector")
    def test_handles_detector_exception(self, mock_detector_cls):
        """Test graceful handling of TechDebtDetector exception."""
        mock_detector_cls.side_effect = RuntimeError("config error")

        analyzer = SweepAnalyzer(Path("/tmp/fake_project"))
        analyzer._detect_dead_imports = MagicMock(return_value=[])

        findings = analyzer.analyze_code()
        error_findings = [f for f in findings if "Tech debt analysis failed" in f.description]
        assert len(error_findings) == 1


class TestFullSweep:
    """Tests for SweepAnalyzer.full_sweep()."""

    def test_aggregates_all_modes(self):
        """Test that full_sweep combines findings from all three modes."""
        analyzer = SweepAnalyzer(Path("/tmp/fake_project"))

        test_finding = SweepFinding("t.py", SweepCategory.TEST, SweepSeverity.HIGH, "tf", "fix")
        doc_finding = SweepFinding("d.md", SweepCategory.DOC, SweepSeverity.MEDIUM, "df", "fix")
        code_finding = SweepFinding("c.py", SweepCategory.CODE, SweepSeverity.LOW, "cf", "fix")

        analyzer.analyze_tests = MagicMock(return_value=[test_finding])
        analyzer.analyze_docs = MagicMock(return_value=[doc_finding])
        analyzer.analyze_code = MagicMock(return_value=[code_finding])

        report = analyzer.full_sweep()

        assert len(report.findings) == 3
        assert report.modes_run == ["tests", "docs", "code"]
        assert report.has_findings
        assert report.summary == {"test": 1, "doc": 1, "code": 1}
        assert report.scan_duration_ms >= 0

    def test_empty_sweep(self):
        """Test full_sweep with no findings."""
        analyzer = SweepAnalyzer(Path("/tmp/fake_project"))
        analyzer.analyze_tests = MagicMock(return_value=[])
        analyzer.analyze_docs = MagicMock(return_value=[])
        analyzer.analyze_code = MagicMock(return_value=[])

        report = analyzer.full_sweep()
        assert not report.has_findings
        assert report.summary == {}
        assert report.modes_run == ["tests", "docs", "code"]

    def test_records_duration(self):
        """Test that scan_duration_ms is recorded."""
        analyzer = SweepAnalyzer(Path("/tmp/fake_project"))
        analyzer.analyze_tests = MagicMock(return_value=[])
        analyzer.analyze_docs = MagicMock(return_value=[])
        analyzer.analyze_code = MagicMock(return_value=[])

        report = analyzer.full_sweep()
        # Duration should be non-negative (may be 0 for fast mocked calls)
        assert report.scan_duration_ms >= 0


# =============================================================================
# Private Helper Tests
# =============================================================================


class TestDetectDeadTestImports:
    """Tests for _detect_dead_test_imports()."""

    def test_detects_archived_import(self, tmp_path):
        """Test detection of imports from archived modules."""
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        test_file = test_dir / "test_old.py"
        test_file.write_text("from archived.old_module import something\n")

        analyzer = SweepAnalyzer(tmp_path)
        findings = analyzer._detect_dead_test_imports()

        assert len(findings) == 1
        assert findings[0].category == SweepCategory.TEST
        assert "archived" in findings[0].description

    def test_ignores_normal_imports(self, tmp_path):
        """Test that normal imports are not flagged."""
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        test_file = test_dir / "test_normal.py"
        test_file.write_text("from pathlib import Path\nimport json\n")

        analyzer = SweepAnalyzer(tmp_path)
        findings = analyzer._detect_dead_test_imports()
        assert len(findings) == 0


class TestDetectBrittleAssertions:
    """Tests for _detect_brittle_assertions()."""

    def test_detects_large_hardcoded_count(self, tmp_path):
        """Test detection of assert len(x) == <large_number>."""
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        test_file = test_dir / "test_brittle.py"
        test_file.write_text("def test_it():\n    x = [1] * 50\n    assert len(x) == 50\n")

        analyzer = SweepAnalyzer(tmp_path)
        findings = analyzer._detect_brittle_assertions()

        assert len(findings) == 1
        assert "Brittle assertion" in findings[0].description
        assert findings[0].severity == SweepSeverity.LOW

    def test_ignores_small_counts(self, tmp_path):
        """Test that small counts (<10) are not flagged."""
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        test_file = test_dir / "test_ok.py"
        test_file.write_text("def test_it():\n    x = [1, 2]\n    assert len(x) == 2\n")

        analyzer = SweepAnalyzer(tmp_path)
        findings = analyzer._detect_brittle_assertions()
        assert len(findings) == 0


class TestDetectDeadImports:
    """Tests for _detect_dead_imports()."""

    def test_detects_unused_import(self, tmp_path):
        """Test detection of imported name used only once (the import itself)."""
        lib_dir = tmp_path / "plugins" / "autonomous-dev" / "lib"
        lib_dir.mkdir(parents=True)
        src_file = lib_dir / "example.py"
        src_file.write_text("import never_used_anywhere_xyz\n\nx = 1\n")

        analyzer = SweepAnalyzer(tmp_path)
        findings = analyzer._detect_dead_imports()

        assert len(findings) >= 1
        unused = [f for f in findings if "never_used_anywhere_xyz" in f.description]
        assert len(unused) == 1

    def test_ignores_used_import(self, tmp_path):
        """Test that imports used in the file are not flagged."""
        lib_dir = tmp_path / "plugins" / "autonomous-dev" / "lib"
        lib_dir.mkdir(parents=True)
        src_file = lib_dir / "example.py"
        src_file.write_text("import json\n\ndata = json.loads('{}')\nprint(json)\n")

        analyzer = SweepAnalyzer(tmp_path)
        findings = analyzer._detect_dead_imports()

        json_findings = [f for f in findings if "json" in f.description]
        assert len(json_findings) == 0
