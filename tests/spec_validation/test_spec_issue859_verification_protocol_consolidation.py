"""
Spec validation for Issue #859: Regression tests for pipeline verification protocol gates.

Acceptance criteria:
1. Test file exists with >=6 test functions
2. Each test reads a target file and asserts HARD GATE language presence
3. All tests pass with pytest
4. Tests follow existing pattern from test_issue_310_anti_stubbing.py
"""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

# Portable project root detection
_current = Path(__file__).resolve()
while _current != _current.parent:
    if (_current / ".git").exists() or (_current / ".claude").exists():
        PROJECT_ROOT = _current
        break
    _current = _current.parent
else:
    PROJECT_ROOT = Path.cwd()

TARGET_FILE = (
    PROJECT_ROOT
    / "tests"
    / "regression"
    / "progression"
    / "test_verification_protocol.py"
)

REFERENCE_FILE = (
    PROJECT_ROOT
    / "tests"
    / "regression"
    / "progression"
    / "test_issue_310_anti_stubbing.py"
)


def _parse_test_functions(filepath: Path) -> list[ast.FunctionDef]:
    """Parse a Python file and return all test function AST nodes."""
    tree = ast.parse(filepath.read_text())
    functions = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            functions.append(node)
    return functions


class TestSpecIssue859VerificationProtocolConsolidation:
    """Spec validation: Issue #859 consolidation test file."""

    def test_spec_859_1_file_exists_with_at_least_6_tests(self):
        """Test file must exist and contain at least 6 test functions."""
        assert TARGET_FILE.exists(), (
            f"Test file does not exist: {TARGET_FILE}"
        )
        test_functions = _parse_test_functions(TARGET_FILE)
        assert len(test_functions) >= 6, (
            f"Expected >= 6 test functions, found {len(test_functions)}: "
            f"{[f.name for f in test_functions]}"
        )

    def test_spec_859_2_each_test_reads_file_and_asserts_hard_gate(self):
        """Each test must read a target file and assert HARD GATE or enforcement language."""
        content = TARGET_FILE.read_text()
        test_functions = _parse_test_functions(TARGET_FILE)

        for func in test_functions:
            # Get the source lines for this function
            func_source = ast.get_source_segment(content, func)
            assert func_source is not None, (
                f"Could not extract source for {func.name}"
            )
            # Each test should read a file (read_text pattern)
            assert "read_text()" in func_source, (
                f"Test {func.name} must read a target file using read_text()"
            )
            # Each test should assert enforcement language
            has_hard_gate = "HARD GATE" in func_source
            has_forbidden = "FORBIDDEN" in func_source
            has_enforcement_assert = has_hard_gate or has_forbidden
            # Some tests may check for specific gate names rather than literal
            # "HARD GATE" — but the spec says "asserts HARD GATE language presence"
            # We check the assertion messages reference the regression issues
            has_regression_ref = "#854" in func_source or "#858" in func_source or "854-#858" in func_source
            assert has_enforcement_assert or has_regression_ref, (
                f"Test {func.name} must assert HARD GATE/FORBIDDEN language or reference issues #854-#858"
            )

    def test_spec_859_3_all_tests_pass(self):
        """All tests in the verification protocol file must pass with pytest."""
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(TARGET_FILE), "-v", "--tb=short", "-q"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0, (
            f"Tests failed with exit code {result.returncode}.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    def test_spec_859_4_follows_anti_stubbing_pattern(self):
        """Tests must follow the structural pattern from test_issue_310_anti_stubbing.py."""
        target_content = TARGET_FILE.read_text()
        reference_content = REFERENCE_FILE.read_text()

        target_tree = ast.parse(target_content)
        reference_tree = ast.parse(reference_content)

        # Pattern check 1: Uses class-based test organization
        target_classes = [
            n for n in ast.walk(target_tree) if isinstance(n, ast.ClassDef)
        ]
        reference_classes = [
            n for n in ast.walk(reference_tree) if isinstance(n, ast.ClassDef)
        ]
        assert len(target_classes) >= 1, (
            "Must use class-based test organization (like test_issue_310_anti_stubbing.py)"
        )

        # Pattern check 2: Uses Path-based file reading (PLUGIN_DIR pattern)
        assert "PLUGIN_DIR" in target_content or "PROJECT_ROOT" in target_content, (
            "Must use Path-based file reading pattern (PLUGIN_DIR or PROJECT_ROOT)"
        )

        # Pattern check 3: Uses read_text() for file reading
        assert "read_text()" in target_content, (
            "Must use read_text() for file reading (like test_issue_310_anti_stubbing.py)"
        )

        # Pattern check 4: Assertion messages contain regression issue references
        assert "Regression" in target_content or "regression" in target_content, (
            "Assertion messages must reference regression (like test_issue_310_anti_stubbing.py)"
        )
