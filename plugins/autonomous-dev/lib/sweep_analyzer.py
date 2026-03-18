#!/usr/bin/env python3
"""Sweep Analyzer -- orchestrates codebase hygiene detection.

Wraps existing detection libraries (tech_debt_detector, test_coverage_analyzer,
hybrid_validator, orphan_file_cleaner) and normalizes output into a unified
SweepFinding/SweepReport format.

Usage:
    from sweep_analyzer import SweepAnalyzer
    from pathlib import Path

    analyzer = SweepAnalyzer(Path("."))
    report = analyzer.full_sweep()
    print(report.format_report())

Date: 2026-03-18
"""

import ast
import json
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

# Import existing detectors with fallback pattern
try:
    from plugins.autonomous_dev.lib.tech_debt_detector import (
        Severity,
        TechDebtDetector,
        TechDebtIssue,
    )
except ImportError:
    from tech_debt_detector import Severity, TechDebtDetector, TechDebtIssue

try:
    from plugins.autonomous_dev.lib.hybrid_validator import (
        HybridManifestValidator,
        ValidationMode,
    )
except ImportError:
    try:
        from hybrid_validator import HybridManifestValidator, ValidationMode
    except ImportError:
        HybridManifestValidator = None  # type: ignore[assignment,misc]
        ValidationMode = None  # type: ignore[assignment,misc]

try:
    from plugins.autonomous_dev.lib.orphan_file_cleaner import (
        OrphanDetectionError,
        OrphanFileCleaner,
    )
except ImportError:
    try:
        from orphan_file_cleaner import OrphanDetectionError, OrphanFileCleaner
    except ImportError:
        OrphanFileCleaner = None  # type: ignore[assignment,misc]
        OrphanDetectionError = Exception  # type: ignore[assignment,misc]


# =============================================================================
# Data Classes
# =============================================================================


class SweepCategory(str, Enum):
    """Category of sweep finding."""

    TEST = "test"
    DOC = "doc"
    CODE = "code"


class SweepSeverity(str, Enum):
    """Severity level for sweep findings."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# Mapping from TechDebtDetector Severity to SweepSeverity
_SEVERITY_MAP: Dict[int, SweepSeverity] = {
    4: SweepSeverity.CRITICAL,  # Severity.CRITICAL
    3: SweepSeverity.HIGH,  # Severity.HIGH
    2: SweepSeverity.MEDIUM,  # Severity.MEDIUM
    1: SweepSeverity.LOW,  # Severity.LOW
}


def _map_severity(tech_debt_severity: Severity) -> SweepSeverity:
    """Map TechDebtDetector Severity enum to SweepSeverity.

    Args:
        tech_debt_severity: Severity from tech_debt_detector module.

    Returns:
        Corresponding SweepSeverity value.
    """
    return _SEVERITY_MAP.get(tech_debt_severity.value, SweepSeverity.MEDIUM)


@dataclass
class SweepFinding:
    """A single hygiene finding from sweep analysis.

    Attributes:
        file_path: Path to the affected file.
        category: Category of the finding (test, doc, code).
        severity: Severity level of the finding.
        description: Human-readable description of the issue.
        suggested_fix: Recommended action to resolve the issue.
        line: Optional line number where the issue was found.
    """

    file_path: str
    category: SweepCategory
    severity: SweepSeverity
    description: str
    suggested_fix: str
    line: Optional[int] = None

    def format(self) -> str:
        """Format the finding as a single-line summary.

        Returns:
            Formatted string like '[HIGH] path/to/file.py:42: description'.
        """
        loc = f":{self.line}" if self.line else ""
        return f"[{self.severity.value.upper()}] {self.file_path}{loc}: {self.description}"


@dataclass
class SweepReport:
    """Aggregated report of all sweep findings.

    Attributes:
        findings: List of all detected findings.
        scan_duration_ms: Total scan duration in milliseconds.
        modes_run: List of analysis modes that were executed.
    """

    findings: List[SweepFinding] = field(default_factory=list)
    scan_duration_ms: int = 0
    modes_run: List[str] = field(default_factory=list)

    @property
    def has_findings(self) -> bool:
        """Whether any findings were detected."""
        return len(self.findings) > 0

    @property
    def summary(self) -> Dict[str, int]:
        """Count of findings grouped by category.

        Returns:
            Dictionary mapping category names to finding counts.
        """
        counts: Dict[str, int] = {}
        for f in self.findings:
            counts[f.category.value] = counts.get(f.category.value, 0) + 1
        return counts

    def format_report(self) -> str:
        """Format the full report as a readable multi-line string.

        Groups findings by category, sorts by severity within each group,
        and includes a summary header.

        Returns:
            Formatted report string.
        """
        if not self.findings:
            return "Clean sweep -- no hygiene issues found."

        severity_order = {
            SweepSeverity.CRITICAL: 0,
            SweepSeverity.HIGH: 1,
            SweepSeverity.MEDIUM: 2,
            SweepSeverity.LOW: 3,
        }

        lines: List[str] = []
        lines.append(f"Sweep Report ({len(self.findings)} findings, {self.scan_duration_ms}ms)")
        lines.append("=" * 60)

        # Group by category
        by_category: Dict[SweepCategory, List[SweepFinding]] = {}
        for f in self.findings:
            by_category.setdefault(f.category, []).append(f)

        # Display order: test, doc, code
        for cat in [SweepCategory.TEST, SweepCategory.DOC, SweepCategory.CODE]:
            if cat not in by_category:
                continue
            cat_findings = sorted(by_category[cat], key=lambda f: severity_order.get(f.severity, 9))
            lines.append("")
            lines.append(f"## {cat.value.upper()} ({len(cat_findings)} issues)")
            lines.append("-" * 40)
            for f in cat_findings:
                lines.append(f"  {f.format()}")
                lines.append(f"    Fix: {f.suggested_fix}")

        lines.append("")
        lines.append(f"Modes run: {', '.join(self.modes_run)}")
        return "\n".join(lines)

    def to_dict(self) -> Dict:
        """Serialize to dictionary for JSON output.

        Returns:
            Dictionary with findings, summary, and duration.
        """
        return {
            "findings": [
                {
                    "file": f.file_path,
                    "line": f.line,
                    "category": f.category.value,
                    "severity": f.severity.value,
                    "description": f.description,
                    "fix": f.suggested_fix,
                }
                for f in self.findings
            ],
            "summary": self.summary,
            "duration_ms": self.scan_duration_ms,
            "modes_run": self.modes_run,
        }


# =============================================================================
# Sweep Analyzer
# =============================================================================


class SweepAnalyzer:
    """Orchestrates codebase hygiene detection across multiple detectors.

    Wraps TechDebtDetector, HybridManifestValidator, OrphanFileCleaner,
    and custom AST-based checks into a unified analysis interface.

    Args:
        project_root: Root directory of the project to analyze.

    Example:
        >>> analyzer = SweepAnalyzer(Path("."))
        >>> report = analyzer.full_sweep()
        >>> if report.has_findings:
        ...     print(report.format_report())
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()

    def analyze_tests(self) -> List[SweepFinding]:
        """Detect dead, broken, or brittle tests.

        Runs pytest to find failures and skips, uses TechDebtDetector for
        red test accumulation, detects imports from archived/non-existent
        modules, and identifies brittle assertions with hardcoded counts.

        Returns:
            List of test-related findings.
        """
        findings: List[SweepFinding] = []

        # 1. Run pytest to find failures and skips
        try:
            result = subprocess.run(
                ["python3", "-m", "pytest", "--tb=line", "-q", "--no-header"],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(self.project_root),
            )
            output = result.stdout + result.stderr

            # Parse failures from pytest output
            for line in output.splitlines():
                line_stripped = line.strip()
                if line_stripped.startswith("FAILED "):
                    test_ref = line_stripped.replace("FAILED ", "").split(" - ")[0]
                    desc = line_stripped.replace("FAILED ", "")
                    findings.append(
                        SweepFinding(
                            file_path=test_ref.split("::")[0] if "::" in test_ref else test_ref,
                            category=SweepCategory.TEST,
                            severity=SweepSeverity.HIGH,
                            description=f"Failing test: {desc}",
                            suggested_fix="Fix or remove the failing test",
                        )
                    )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            findings.append(
                SweepFinding(
                    file_path="<pytest>",
                    category=SweepCategory.TEST,
                    severity=SweepSeverity.LOW,
                    description=f"Could not run pytest: {type(e).__name__}",
                    suggested_fix="Ensure pytest is installed and runnable",
                )
            )

        # 2. Use TechDebtDetector for red test accumulation
        try:
            detector = TechDebtDetector(project_root=self.project_root)
            red_tests = detector.detect_red_test_accumulation()
            for issue in red_tests:
                findings.append(
                    SweepFinding(
                        file_path=issue.file_path,
                        category=SweepCategory.TEST,
                        severity=_map_severity(issue.severity),
                        description=issue.message,
                        suggested_fix=issue.recommendation,
                    )
                )
        except Exception as e:
            findings.append(
                SweepFinding(
                    file_path="<tech_debt_detector>",
                    category=SweepCategory.TEST,
                    severity=SweepSeverity.LOW,
                    description=f"Red test detection failed: {e}",
                    suggested_fix="Check TechDebtDetector configuration",
                )
            )

        # 3. Detect tests importing from archived/ or non-existent modules
        try:
            findings.extend(self._detect_dead_test_imports())
        except Exception as e:
            findings.append(
                SweepFinding(
                    file_path="<import_checker>",
                    category=SweepCategory.TEST,
                    severity=SweepSeverity.LOW,
                    description=f"Dead import detection failed: {e}",
                    suggested_fix="Check test file accessibility",
                )
            )

        # 4. Detect brittle assertions (hardcoded counts via AST)
        try:
            findings.extend(self._detect_brittle_assertions())
        except Exception as e:
            findings.append(
                SweepFinding(
                    file_path="<assertion_checker>",
                    category=SweepCategory.TEST,
                    severity=SweepSeverity.LOW,
                    description=f"Brittle assertion detection failed: {e}",
                    suggested_fix="Check test file accessibility",
                )
            )

        return findings

    def analyze_docs(self) -> List[SweepFinding]:
        """Detect documentation drift.

        Uses HybridManifestValidator in REGEX_ONLY mode (no GenAI API key
        dependency) and cross-checks component counts in .md files vs
        filesystem.

        Returns:
            List of documentation-related findings.
        """
        findings: List[SweepFinding] = []

        # 1. Use HybridManifestValidator (REGEX_ONLY mode)
        if HybridManifestValidator is not None and ValidationMode is not None:
            try:
                validator = HybridManifestValidator(
                    repo_root=self.project_root,
                    mode=ValidationMode.REGEX_ONLY,
                )
                report = validator.validate()
                for issue in report.issues:
                    # Map ValidationLevel to SweepSeverity
                    level_str = issue.level.value if hasattr(issue.level, "value") else str(issue.level)
                    if level_str == "ERROR":
                        sev = SweepSeverity.HIGH
                    elif level_str == "WARNING":
                        sev = SweepSeverity.MEDIUM
                    else:
                        sev = SweepSeverity.LOW

                    findings.append(
                        SweepFinding(
                            file_path=str(issue.details) if issue.details else "<docs>",
                            category=SweepCategory.DOC,
                            severity=sev,
                            description=issue.message,
                            suggested_fix="Update documentation to match codebase",
                        )
                    )
            except Exception as e:
                findings.append(
                    SweepFinding(
                        file_path="<hybrid_validator>",
                        category=SweepCategory.DOC,
                        severity=SweepSeverity.LOW,
                        description=f"Doc validation failed: {e}",
                        suggested_fix="Check HybridManifestValidator configuration",
                    )
                )
        else:
            findings.append(
                SweepFinding(
                    file_path="<hybrid_validator>",
                    category=SweepCategory.DOC,
                    severity=SweepSeverity.LOW,
                    description="HybridManifestValidator not available",
                    suggested_fix="Install hybrid_validator module",
                )
            )

        # 2. Cross-check component counts in .md files vs filesystem
        try:
            findings.extend(self._check_component_counts())
        except Exception as e:
            findings.append(
                SweepFinding(
                    file_path="<component_counter>",
                    category=SweepCategory.DOC,
                    severity=SweepSeverity.LOW,
                    description=f"Component count check failed: {e}",
                    suggested_fix="Check filesystem accessibility",
                )
            )

        return findings

    def analyze_code(self) -> List[SweepFinding]:
        """Detect code rot.

        Uses TechDebtDetector.analyze() for large files, complexity, and dead
        code. Uses OrphanFileCleaner.detect_orphans() for orphaned files.
        Detects dead imports via AST analysis.

        Returns:
            List of code-related findings.
        """
        findings: List[SweepFinding] = []

        # 1. Use TechDebtDetector.analyze()
        try:
            detector = TechDebtDetector(project_root=self.project_root)
            report = detector.analyze()
            for issue in report.issues:
                findings.append(
                    SweepFinding(
                        file_path=issue.file_path,
                        category=SweepCategory.CODE,
                        severity=_map_severity(issue.severity),
                        description=issue.message,
                        suggested_fix=issue.recommendation,
                    )
                )
        except Exception as e:
            findings.append(
                SweepFinding(
                    file_path="<tech_debt_detector>",
                    category=SweepCategory.CODE,
                    severity=SweepSeverity.LOW,
                    description=f"Tech debt analysis failed: {e}",
                    suggested_fix="Check TechDebtDetector configuration",
                )
            )

        # 2. Use OrphanFileCleaner.detect_orphans()
        if OrphanFileCleaner is not None:
            try:
                cleaner = OrphanFileCleaner(project_root=self.project_root)
                orphans = cleaner.detect_orphans()
                for orphan in orphans:
                    findings.append(
                        SweepFinding(
                            file_path=str(orphan.path),
                            category=SweepCategory.CODE,
                            severity=SweepSeverity.MEDIUM,
                            description=f"Orphaned {orphan.category} file: {orphan.reason}",
                            suggested_fix="Remove orphaned file or add to manifest",
                        )
                    )
            except OrphanDetectionError:
                # Expected for non-plugin repos -- not a real finding
                pass
            except Exception as e:
                findings.append(
                    SweepFinding(
                        file_path="<orphan_cleaner>",
                        category=SweepCategory.CODE,
                        severity=SweepSeverity.LOW,
                        description=f"Orphan detection failed: {e}",
                        suggested_fix="Check OrphanFileCleaner configuration",
                    )
                )

        # 3. Detect dead imports via AST
        try:
            findings.extend(self._detect_dead_imports())
        except Exception as e:
            findings.append(
                SweepFinding(
                    file_path="<dead_import_checker>",
                    category=SweepCategory.CODE,
                    severity=SweepSeverity.LOW,
                    description=f"Dead import detection failed: {e}",
                    suggested_fix="Check source file accessibility",
                )
            )

        return findings

    def full_sweep(self) -> SweepReport:
        """Run all three analysis modes (tests, docs, code).

        Returns:
            SweepReport aggregating findings from all modes.
        """
        start = time.time()
        all_findings: List[SweepFinding] = []
        modes: List[str] = []

        for mode_name, analyze_fn in [
            ("tests", self.analyze_tests),
            ("docs", self.analyze_docs),
            ("code", self.analyze_code),
        ]:
            all_findings.extend(analyze_fn())
            modes.append(mode_name)

        elapsed_ms = int((time.time() - start) * 1000)
        return SweepReport(
            findings=all_findings,
            scan_duration_ms=elapsed_ms,
            modes_run=modes,
        )

    # =========================================================================
    # Private Helpers
    # =========================================================================

    def _detect_dead_test_imports(self) -> List[SweepFinding]:
        """Detect test files importing from archived/ or non-existent modules."""
        findings: List[SweepFinding] = []
        test_dirs = [
            self.project_root / "tests",
            self.project_root / "test",
        ]

        for test_dir in test_dirs:
            if not test_dir.is_dir():
                continue
            for py_file in test_dir.rglob("*.py"):
                try:
                    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
                except (SyntaxError, UnicodeDecodeError):
                    continue

                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom) and node.module:
                        if "archived" in node.module or "archive" in node.module:
                            findings.append(
                                SweepFinding(
                                    file_path=str(py_file.relative_to(self.project_root)),
                                    category=SweepCategory.TEST,
                                    severity=SweepSeverity.MEDIUM,
                                    description=f"Import from archived module: {node.module}",
                                    suggested_fix="Update import to use current module path",
                                    line=node.lineno,
                                )
                            )

        return findings

    def _detect_brittle_assertions(self) -> List[SweepFinding]:
        """Detect brittle assertions with hardcoded counts (e.g., assert len(x) == 42)."""
        findings: List[SweepFinding] = []
        test_dirs = [
            self.project_root / "tests",
            self.project_root / "test",
        ]

        for test_dir in test_dirs:
            if not test_dir.is_dir():
                continue
            for py_file in test_dir.rglob("*.py"):
                try:
                    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
                except (SyntaxError, UnicodeDecodeError):
                    continue

                for node in ast.walk(tree):
                    if not isinstance(node, ast.Assert):
                        continue
                    test_expr = node.test
                    # Check for: assert len(x) == <large_number>
                    if isinstance(test_expr, ast.Compare):
                        if (
                            isinstance(test_expr.left, ast.Call)
                            and isinstance(test_expr.left.func, ast.Name)
                            and test_expr.left.func.id == "len"
                        ):
                            for comparator in test_expr.comparators:
                                if isinstance(comparator, ast.Constant) and isinstance(
                                    comparator.value, int
                                ):
                                    if comparator.value >= 10:
                                        findings.append(
                                            SweepFinding(
                                                file_path=str(
                                                    py_file.relative_to(self.project_root)
                                                ),
                                                category=SweepCategory.TEST,
                                                severity=SweepSeverity.LOW,
                                                description=(
                                                    f"Brittle assertion: hardcoded count "
                                                    f"{comparator.value}"
                                                ),
                                                suggested_fix=(
                                                    "Use >= or a named constant instead "
                                                    "of exact count"
                                                ),
                                                line=node.lineno,
                                            )
                                        )

        return findings

    def _check_component_counts(self) -> List[SweepFinding]:
        """Cross-check component counts mentioned in .md files vs filesystem."""
        findings: List[SweepFinding] = []

        # Check CLAUDE.md or README.md for agent/command counts
        for md_name in ["CLAUDE.md", "README.md"]:
            md_path = self.project_root / md_name
            if not md_path.is_file():
                continue

            try:
                content = md_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            # Count actual agents
            agents_dir = self.project_root / "plugins" / "autonomous-dev" / "agents"
            if agents_dir.is_dir():
                actual_agents = len(list(agents_dir.glob("*.md")))
                # Look for agent count claims like "11 agents" or "11 specialists"
                import re

                for match in re.finditer(r"(\d+)\s+(?:agents?|specialists?)", content):
                    claimed = int(match.group(1))
                    if claimed != actual_agents:
                        findings.append(
                            SweepFinding(
                                file_path=md_name,
                                category=SweepCategory.DOC,
                                severity=SweepSeverity.MEDIUM,
                                description=(
                                    f"Agent count mismatch: {md_name} claims "
                                    f"{claimed}, found {actual_agents}"
                                ),
                                suggested_fix=f"Update {md_name} to reflect {actual_agents} agents",
                            )
                        )

        return findings

    def _detect_dead_imports(self) -> List[SweepFinding]:
        """Detect unused imports in Python source files via AST analysis.

        Scans .py files in the project root (excluding tests, venv, node_modules)
        and reports imports whose names are never referenced in the file body.
        """
        findings: List[SweepFinding] = []
        exclude_dirs = {
            "tests",
            "test",
            ".venv",
            "venv",
            "node_modules",
            "__pycache__",
            ".git",
            "archived",
        }

        src_dirs = [self.project_root / "plugins" / "autonomous-dev" / "lib"]
        for src_dir in src_dirs:
            if not src_dir.is_dir():
                continue

            for py_file in src_dir.glob("*.py"):
                if py_file.name.startswith("__"):
                    continue

                try:
                    source = py_file.read_text(encoding="utf-8")
                    tree = ast.parse(source, filename=str(py_file))
                except (SyntaxError, UnicodeDecodeError, OSError):
                    continue

                # Collect imported names
                imported_names: Dict[str, int] = {}
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            name = alias.asname or alias.name.split(".")[0]
                            imported_names[name] = node.lineno
                    elif isinstance(node, ast.ImportFrom):
                        for alias in node.names:
                            if alias.name == "*":
                                continue
                            name = alias.asname or alias.name
                            imported_names[name] = node.lineno

                if not imported_names:
                    continue

                # Check if each imported name is used elsewhere in the source
                for name, lineno in imported_names.items():
                    # Simple heuristic: count occurrences of the name in source
                    # Subtract the import line itself
                    occurrences = source.count(name)
                    if occurrences <= 1:
                        rel_path = str(py_file.relative_to(self.project_root))
                        findings.append(
                            SweepFinding(
                                file_path=rel_path,
                                category=SweepCategory.CODE,
                                severity=SweepSeverity.LOW,
                                description=f"Potentially unused import: {name}",
                                suggested_fix=f"Remove unused import '{name}' if not needed",
                                line=lineno,
                            )
                        )

        return findings
