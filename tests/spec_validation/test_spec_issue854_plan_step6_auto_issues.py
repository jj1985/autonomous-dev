"""Spec validation tests for Issue #854: /plan Step 6 auto-creates GitHub issues.

Validates acceptance criteria:
1. /plan with >=2 work items auto-creates GitHub issues at Step 6
2. Created issue numbers are recorded in plan file under ## Linked Issues
3. Single-item plans skip issue creation with explicit log message
4. FORBIDDEN list prevents skipping issue creation when >=2 work items exist
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMANDS_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "commands"


@pytest.fixture
def plan_content() -> str:
    """Read the plan.md command file content."""
    plan_file = COMMANDS_DIR / "plan.md"
    assert plan_file.exists(), f"plan.md not found at {plan_file}"
    return plan_file.read_text()


# ---------------------------------------------------------------------------
# AC1: /plan with >=2 work items auto-creates GitHub issues at Step 6
# ---------------------------------------------------------------------------


class TestSpec854AC1AutoCreateIssues:
    """/plan Step 6 must require GitHub issue creation for >=2 work items."""

    def test_spec_854_1_step6_exists_with_hard_gate(self, plan_content: str):
        """Step 6 must exist and contain a HARD GATE for issue creation."""
        assert "### STEP 6" in plan_content, \
            "plan.md must contain a STEP 6 section"
        assert "HARD GATE" in plan_content.split("### STEP 6")[1].split("### STEP 7")[0], \
            "Step 6 must contain a HARD GATE enforcement"

    def test_spec_854_1_step6_requires_issues_for_multi_item(self, plan_content: str):
        """Step 6 must require issue creation when >=2 independent work items exist."""
        step6_content = plan_content.split("### STEP 6")[1].split("### STEP 7")[0]
        assert ">=2" in step6_content or ">= 2" in step6_content, \
            "Step 6 must reference the >=2 work items threshold"
        assert "issue creation" in step6_content.lower() or "create" in step6_content.lower(), \
            "Step 6 must describe issue creation"

    def test_spec_854_1_step6_uses_gh_cli(self, plan_content: str):
        """Step 6 must use gh issue create for creating GitHub issues."""
        step6_content = plan_content.split("### STEP 6")[1].split("### STEP 7")[0]
        assert "gh issue create" in step6_content, \
            "Step 6 must use 'gh issue create' command"

    def test_spec_854_1_step6_is_conditional_mandatory(self, plan_content: str):
        """Step 6 heading or body must indicate it is required when multi-item."""
        step6_content = plan_content.split("### STEP 6")[1].split("### STEP 7")[0]
        # Must indicate mandatory/required nature for multi-item
        has_required_language = (
            "REQUIRED" in step6_content
            or "MUST" in step6_content
            or "Required" in step6_content.split("\n")[0]  # in heading
        )
        assert has_required_language, \
            "Step 6 must indicate issue creation is REQUIRED/MUST for multi-item plans"


# ---------------------------------------------------------------------------
# AC2: Created issue numbers recorded in plan file under ## Linked Issues
# ---------------------------------------------------------------------------


class TestSpec854AC2LinkedIssuesSection:
    """Plan file template must include ## Linked Issues section."""

    def test_spec_854_2_linked_issues_section_in_template(self, plan_content: str):
        """Plan file template in Step 7 must include ## Linked Issues section."""
        step7_content = plan_content.split("### STEP 7")[1]
        assert "## Linked Issues" in step7_content, \
            "Step 7 plan file template must include '## Linked Issues' section"

    def test_spec_854_2_linked_issues_shows_issue_numbers(self, plan_content: str):
        """## Linked Issues section must show issue number format (e.g., #NNN)."""
        step7_content = plan_content.split("### STEP 7")[1]
        # Should reference issue numbers with # prefix pattern
        assert "#" in step7_content.split("## Linked Issues")[1].split("##")[0] if "## Linked Issues" in step7_content else False, \
            "Linked Issues section must show issue number format"

    def test_spec_854_2_step6_collects_issue_numbers(self, plan_content: str):
        """Step 6 must instruct collecting created issue numbers."""
        step6_content = plan_content.split("### STEP 6")[1].split("### STEP 7")[0]
        has_collection = (
            "issue number" in step6_content.lower()
            or "collect" in step6_content.lower()
            or "#" in step6_content
        )
        assert has_collection, \
            "Step 6 must instruct collecting created issue numbers"


# ---------------------------------------------------------------------------
# AC3: Single-item plans skip issue creation with explicit log message
# ---------------------------------------------------------------------------


class TestSpec854AC3SingleItemSkip:
    """Single-item plans must skip issue creation with explicit message."""

    def test_spec_854_3_single_item_skip_message_defined(self, plan_content: str):
        """Step 6 must define an explicit skip message for single-item plans."""
        step6_content = plan_content.split("### STEP 6")[1].split("### STEP 7")[0]
        # Must have a distinct skip path for single items
        has_skip_path = (
            "single" in step6_content.lower()
            and ("skip" in step6_content.lower() or "log" in step6_content.lower())
        )
        assert has_skip_path, \
            "Step 6 must define a skip path for single-item plans"

    def test_spec_854_3_skip_message_text_is_explicit(self, plan_content: str):
        """The skip message must be an explicit, defined string (not vague)."""
        step6_content = plan_content.split("### STEP 6")[1].split("### STEP 7")[0]
        # Should contain a concrete log message, not just a vague instruction
        assert "Skipping Step 6" in step6_content or "single coherent unit" in step6_content, \
            "Step 6 must contain an explicit, concrete skip log message"

    def test_spec_854_3_single_item_recorded_in_linked_issues(self, plan_content: str):
        """Single-item skip must record something in ## Linked Issues section."""
        # The plan should specify what to put in Linked Issues for single items
        assert "N/A" in plan_content and "single work item" in plan_content.lower(), \
            "Plan must specify 'N/A' marker for single-item plans in Linked Issues"


# ---------------------------------------------------------------------------
# AC4: FORBIDDEN list prevents skipping when >=2 work items
# ---------------------------------------------------------------------------


class TestSpec854AC4ForbiddenList:
    """FORBIDDEN list must prevent skipping issue creation for multi-item plans."""

    def test_spec_854_4_forbidden_keyword_in_step6(self, plan_content: str):
        """Step 6 must contain a FORBIDDEN section."""
        step6_content = plan_content.split("### STEP 6")[1].split("### STEP 7")[0]
        assert "FORBIDDEN" in step6_content, \
            "Step 6 must contain FORBIDDEN keyword for enforcement"

    def test_spec_854_4_forbidden_skipping_issue_creation(self, plan_content: str):
        """FORBIDDEN list must explicitly prohibit skipping issue creation."""
        step6_content = plan_content.split("### STEP 6")[1].split("### STEP 7")[0]
        # Extract FORBIDDEN section
        forbidden_text = step6_content.lower()
        has_skip_prohibition = (
            "skipping issue creation" in forbidden_text
            or "skip issue creation" in forbidden_text
        )
        assert has_skip_prohibition, \
            "FORBIDDEN list must prohibit skipping issue creation when >=2 items"

    def test_spec_854_4_forbidden_gaming_independence(self, plan_content: str):
        """FORBIDDEN list must prohibit declaring items as 'not independent' to avoid issues."""
        step6_content = plan_content.split("### STEP 6")[1].split("### STEP 7")[0]
        forbidden_text = step6_content.lower()
        has_gaming_prohibition = (
            "not independent" in forbidden_text
            or "avoid issue creation" in forbidden_text
        )
        assert has_gaming_prohibition, \
            "FORBIDDEN list must prohibit gaming independence declarations to avoid issues"

    def test_spec_854_4_forbidden_proceeding_without_action(self, plan_content: str):
        """FORBIDDEN list must prohibit proceeding to Step 7 without creating issues or logging skip."""
        step6_content = plan_content.split("### STEP 6")[1].split("### STEP 7")[0]
        forbidden_text = step6_content.lower()
        has_proceed_prohibition = (
            "proceeding to step 7" in forbidden_text
            or "proceed" in forbidden_text
        )
        assert has_proceed_prohibition, \
            "FORBIDDEN list must prohibit proceeding to Step 7 without action"
