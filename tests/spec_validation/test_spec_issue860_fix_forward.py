"""Spec validation tests for Issue #860: Opportunistic fix-forward.

Agents should fix pre-existing failures within reach. Adds pre-existing failure
baseline capture, classification logic, auto-filing of issues for unfixed
pre-existing failures, and guidance to implementer on handling pre-existing failures.

Acceptance criteria:
1. Implementer agent prompt includes guidance on pre-existing failures
2. Reviewer.md should NOT be modified (no dismissed pre-existing failure finding)
3. Pipeline STEP 8 distinguishes new failures vs pre-existing failures
4. Pre-existing failures that are not fixed are auto-filed as issues
5. STEP 1 captures baseline failing test IDs before implementer runs
6. The implementer 2-resolution model (Fix/Adjust) is unchanged
7. Classification logic is testable via fix_forward.py with correct behavior
8. No WARNING-level advisory text added to reviewer.md
9. All existing tests continue to pass
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LIB_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "lib"
AGENTS_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "agents"
COMMANDS_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "commands"

if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))


# ---------------------------------------------------------------------------
# Criterion 1: Implementer prompt includes pre-existing failure guidance
# ---------------------------------------------------------------------------
class TestSpecFixForward1ImplementerGuidance:
    """Implementer agent prompt includes guidance on pre-existing failures."""

    def test_spec_fix_forward_1_implementer_has_preexisting_section(self):
        content = (AGENTS_DIR / "implementer.md").read_text()
        assert "Pre-Existing Failure" in content, (
            "implementer.md must contain a section about pre-existing failures"
        )

    def test_spec_fix_forward_1_implementer_mentions_fix_forward(self):
        content = (AGENTS_DIR / "implementer.md").read_text()
        assert "fix-forward" in content.lower(), (
            "implementer.md must mention fix-forward as a concept"
        )

    def test_spec_fix_forward_1_implementer_has_forbidden_silent_ignore(self):
        content = (AGENTS_DIR / "implementer.md").read_text()
        assert "Ignoring pre-existing failures silently" in content, (
            "implementer.md must forbid silently ignoring pre-existing failures"
        )


# ---------------------------------------------------------------------------
# Criterion 2 and 8: Reviewer.md should NOT be modified
# ---------------------------------------------------------------------------
class TestSpecFixForward2ReviewerNotModified:
    """Reviewer.md has no fix-forward or pre-existing failure guidance added."""

    def test_spec_fix_forward_2_reviewer_no_dismissed_preexisting(self):
        content = (AGENTS_DIR / "reviewer.md").read_text()
        assert "dismissed pre-existing failure" not in content.lower(), (
            "reviewer.md must NOT contain dismissed pre-existing failure finding"
        )

    def test_spec_fix_forward_8_reviewer_no_fix_forward_advisory(self):
        content = (AGENTS_DIR / "reviewer.md").read_text()
        assert "fix-forward" not in content.lower(), (
            "reviewer.md must NOT contain fix-forward advisory text"
        )

    def test_spec_fix_forward_8_reviewer_no_preexisting_text(self):
        content = (AGENTS_DIR / "reviewer.md").read_text()
        assert "pre-existing" not in content.lower(), (
            "reviewer.md must NOT contain pre-existing advisory text"
        )


# ---------------------------------------------------------------------------
# Criterion 3: STEP 8 distinguishes new vs pre-existing failures
# ---------------------------------------------------------------------------
class TestSpecFixForward3Step8Classification:
    """Pipeline STEP 8 distinguishes new failures from pre-existing ones."""

    def test_spec_fix_forward_3_step8_uses_classify_failures(self):
        content = (COMMANDS_DIR / "implement.md").read_text()
        assert "classify_failures" in content, (
            "implement.md STEP 8 must use classify_failures from fix_forward"
        )

    def test_spec_fix_forward_3_step8_has_new_failures_gate(self):
        content = (COMMANDS_DIR / "implement.md").read_text()
        assert "new_failures" in content, (
            "implement.md STEP 8 must reference new_failures classification"
        )

    def test_spec_fix_forward_3_step8_has_preexisting_remaining(self):
        content = (COMMANDS_DIR / "implement.md").read_text()
        assert "pre_existing_remaining" in content, (
            "implement.md STEP 8 must reference pre_existing_remaining classification"
        )


# ---------------------------------------------------------------------------
# Criterion 4: Pre-existing failures auto-filed as issues
# ---------------------------------------------------------------------------
class TestSpecFixForward4AutoFileIssues:
    """Pre-existing failures that are not fixed are auto-filed as issues."""

    def test_spec_fix_forward_4_step8_mentions_auto_file(self):
        content = (COMMANDS_DIR / "implement.md").read_text()
        assert "gh issue create" in content, (
            "implement.md must mention gh issue create for auto-filing"
        )

    def test_spec_fix_forward_4_step8_mentions_preexisting_label(self):
        content = (COMMANDS_DIR / "implement.md").read_text()
        assert "pre-existing-failure" in content, (
            "implement.md must mention pre-existing-failure label for filed issues"
        )

    def test_spec_fix_forward_4_forbidden_silent_dismissal(self):
        content = (COMMANDS_DIR / "implement.md").read_text()
        lower = content.lower()
        assert "silently dropping pre-existing failures" in lower or "silent" in lower, (
            "implement.md must forbid silently dropping pre-existing failures"
        )


# ---------------------------------------------------------------------------
# Criterion 5: STEP 1 captures baseline failing test IDs
# ---------------------------------------------------------------------------
class TestSpecFixForward5Step1Baseline:
    """STEP 1 captures baseline failing test IDs before implementer runs."""

    def test_spec_fix_forward_5_step1_baseline_capture(self):
        content = (COMMANDS_DIR / "implement.md").read_text()
        assert "BASELINE_FAILING_FILE" in content, (
            "implement.md STEP 1 must capture BASELINE_FAILING_FILE"
        )

    def test_spec_fix_forward_5_step1_uses_parse_failing_tests(self):
        content = (COMMANDS_DIR / "implement.md").read_text()
        assert "parse_failing_tests" in content, (
            "implement.md STEP 1 must use parse_failing_tests from fix_forward"
        )

    def test_spec_fix_forward_5_step1_imports_fix_forward(self):
        content = (COMMANDS_DIR / "implement.md").read_text()
        assert "fix_forward" in content, (
            "implement.md must import from fix_forward module"
        )


# ---------------------------------------------------------------------------
# Criterion 6: 2-resolution model (Fix/Adjust) unchanged
# ---------------------------------------------------------------------------
class TestSpecFixForward6TwoResolutionModel:
    """The implementer existing 2-resolution model is unchanged."""

    def test_spec_fix_forward_6_fix_resolution_exists(self):
        content = (AGENTS_DIR / "implementer.md").read_text()
        assert "Fix it" in content, (
            "implementer.md must still contain Fix it resolution"
        )

    def test_spec_fix_forward_6_adjust_resolution_exists(self):
        content = (AGENTS_DIR / "implementer.md").read_text()
        assert "Adjust it" in content, (
            "implementer.md must still contain Adjust it resolution"
        )

    def test_spec_fix_forward_6_step8_two_resolutions(self):
        content = (COMMANDS_DIR / "implement.md").read_text()
        assert "Fix it" in content and "Adjust it" in content, (
            "implement.md must still contain both Fix/Adjust resolutions"
        )


# ---------------------------------------------------------------------------
# Criterion 7: Classification logic in fix_forward.py
# ---------------------------------------------------------------------------
class TestSpecFixForward7ClassificationLogic:
    """fix_forward.py classification logic works correctly."""

    def test_spec_fix_forward_7_parse_failing_tests_basic(self):
        from fix_forward import parse_failing_tests

        output = (
            "tests/unit/test_foo.py::test_bar FAILED\n"
            "tests/unit/test_baz.py::test_qux FAILED\n"
            "= 2 failed in 1.23s =\n"
        )
        result = parse_failing_tests(output)
        assert result == {
            "tests/unit/test_foo.py::test_bar",
            "tests/unit/test_baz.py::test_qux",
        }

    def test_spec_fix_forward_7_parse_failing_tests_empty(self):
        from fix_forward import parse_failing_tests

        result = parse_failing_tests("")
        assert result == set()

    def test_spec_fix_forward_7_parse_no_failures(self):
        from fix_forward import parse_failing_tests

        output = "5 passed in 0.50s\n"
        result = parse_failing_tests(output)
        assert result == set()

    def test_spec_fix_forward_7_classify_all_fixed(self):
        from fix_forward import classify_failures

        baseline = {"test_a", "test_b"}
        current = set()
        result = classify_failures(baseline, current)
        assert result["fixed"] == {"test_a", "test_b"}
        assert result["pre_existing_remaining"] == set()
        assert result["new_failures"] == set()

    def test_spec_fix_forward_7_classify_all_new(self):
        from fix_forward import classify_failures

        baseline = set()
        current = {"test_c", "test_d"}
        result = classify_failures(baseline, current)
        assert result["fixed"] == set()
        assert result["pre_existing_remaining"] == set()
        assert result["new_failures"] == {"test_c", "test_d"}

    def test_spec_fix_forward_7_classify_mixed(self):
        from fix_forward import classify_failures

        baseline = {"test_a", "test_b", "test_c"}
        current = {"test_b", "test_d"}
        result = classify_failures(baseline, current)
        assert result["fixed"] == {"test_a", "test_c"}
        assert result["pre_existing_remaining"] == {"test_b"}
        assert result["new_failures"] == {"test_d"}

    def test_spec_fix_forward_7_classify_no_failures(self):
        from fix_forward import classify_failures

        result = classify_failures(set(), set())
        assert result["fixed"] == set()
        assert result["pre_existing_remaining"] == set()
        assert result["new_failures"] == set()

    def test_spec_fix_forward_7_format_issue_body_contains_test_id(self):
        from fix_forward import format_issue_body

        body = format_issue_body("tests/unit/test_foo.py::test_bar")
        assert "tests/unit/test_foo.py::test_bar" in body

    def test_spec_fix_forward_7_format_issue_body_contains_context(self):
        from fix_forward import format_issue_body

        body = format_issue_body(
            "tests/unit/test_foo.py::test_bar",
            context="Discovered during pipeline run abc123",
        )
        assert "Discovered during pipeline run abc123" in body

    def test_spec_fix_forward_7_format_issue_body_markdown(self):
        from fix_forward import format_issue_body

        body = format_issue_body("tests/unit/test_foo.py::test_bar")
        assert "## Pre-Existing Test Failure" in body
        assert "pre-existing-failure" in body

    def test_spec_fix_forward_7_format_issue_body_no_context(self):
        from fix_forward import format_issue_body

        body = format_issue_body("tests/unit/test_foo.py::test_bar")
        assert "**Context**" not in body

    def test_spec_fix_forward_7_classify_returns_three_keys(self):
        from fix_forward import classify_failures

        result = classify_failures({"a"}, {"b"})
        assert set(result.keys()) == {"fixed", "pre_existing_remaining", "new_failures"}


# ---------------------------------------------------------------------------
# Criterion 9: Module importable (smoke check)
# ---------------------------------------------------------------------------
class TestSpecFixForward9ModuleImportable:
    """Verify the fix_forward module is importable and exports expected API."""

    def test_spec_fix_forward_9_module_importable(self):
        from fix_forward import classify_failures, format_issue_body, parse_failing_tests

        assert callable(parse_failing_tests)
        assert callable(classify_failures)
        assert callable(format_issue_body)
