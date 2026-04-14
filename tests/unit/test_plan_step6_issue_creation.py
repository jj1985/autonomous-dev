"""
Acceptance tests for Issue #854: plan.md Step 6 issue creation improvements.

These tests verify that plan.md has been updated with:
1. Step 6 heading uses conditional-mandatory language (not "(Optional)")
2. Step 6 contains a HARD GATE or FORBIDDEN list
3. Step 7 plan file template contains a "## Linked Issues" section
4. Skip logic for single-item plans with an explicit log message
5. Output section mentions `/implement --issues` when issues are created

Tests FAIL initially (implementation not done yet) — they are acceptance tests
written before implementation per the Diamond Model.
"""

from pathlib import Path

import pytest

# Portable project root detection
_current = Path.cwd()
while _current != _current.parent:
    if (_current / ".git").exists() or (_current / ".claude").exists():
        PROJECT_ROOT = _current
        break
    _current = _current.parent
else:
    PROJECT_ROOT = Path.cwd()

PLAN_MD = PROJECT_ROOT / "plugins" / "autonomous-dev" / "commands" / "plan.md"


@pytest.fixture(scope="module")
def plan_content() -> str:
    """Read plan.md once for the whole module."""
    return PLAN_MD.read_text()


@pytest.fixture(scope="module")
def step6_section(plan_content: str) -> str:
    """Extract the Step 6 section from plan.md."""
    # Split on STEP 7 to get the content of Step 6
    if "### STEP 6:" not in plan_content:
        return ""
    after_step6 = plan_content.split("### STEP 6:")[1]
    # Everything up to the next step heading
    for delimiter in ["### STEP 7:", "---\n\n### STEP 7"]:
        if delimiter in after_step6:
            return after_step6.split(delimiter)[0]
    return after_step6


@pytest.fixture(scope="module")
def step7_section(plan_content: str) -> str:
    """Extract the Step 7 section from plan.md."""
    if "### STEP 7:" not in plan_content:
        return ""
    after_step7 = plan_content.split("### STEP 7:")[1]
    for delimiter in ["### Output", "---\n\n### Output"]:
        if delimiter in after_step7:
            return after_step7.split(delimiter)[0]
    return after_step7


@pytest.fixture(scope="module")
def output_section(plan_content: str) -> str:
    """Extract the Output section from plan.md."""
    if "### Output" not in plan_content:
        return ""
    return plan_content.split("### Output")[1]


class TestStep6HeadingLanguage:
    """Issue #854 AC1: Step 6 heading must not say '(Optional)'."""

    def test_step6_heading_does_not_say_optional(self, plan_content: str) -> None:
        """Step 6 heading must use conditional-mandatory language, not '(Optional)'."""
        assert "### STEP 6:" in plan_content, "plan.md must have a STEP 6 heading"

        # Find the Step 6 heading line
        for line in plan_content.splitlines():
            if "### STEP 6:" in line:
                assert "(Optional)" not in line, (
                    "Issue #854: Step 6 heading must not say '(Optional)'. "
                    f"Got: {line!r}. "
                    "Use conditional-mandatory language instead."
                )
                break

    def test_step6_heading_uses_conditional_mandatory_language(
        self, plan_content: str
    ) -> None:
        """Step 6 heading should convey conditional-mandatory behavior."""
        assert "### STEP 6:" in plan_content, "plan.md must have a STEP 6 heading"

        for line in plan_content.splitlines():
            if "### STEP 6:" in line:
                # The heading must not be purely optional — it should indicate
                # the step is required when conditions are met
                heading_lower = line.lower()
                has_conditional_language = (
                    "when" in heading_lower
                    or "multi" in heading_lower
                    or "required" in heading_lower
                    or "if" in heading_lower
                    or "issue" in heading_lower
                )
                assert has_conditional_language, (
                    "Issue #854: Step 6 heading must use conditional-mandatory language. "
                    f"Got: {line!r}. "
                    "Expected language like 'When applicable', 'Required when multi-item', etc."
                )
                break


class TestStep6HardGate:
    """Issue #854 AC2: Step 6 must contain HARD GATE or FORBIDDEN list."""

    def test_step6_contains_hard_gate_or_forbidden(self, step6_section: str) -> None:
        """Step 6 section must have a HARD GATE or FORBIDDEN enforcement block."""
        assert step6_section, "Step 6 section must exist in plan.md"

        has_enforcement = "HARD GATE" in step6_section or "FORBIDDEN" in step6_section
        assert has_enforcement, (
            "Issue #854: Step 6 must contain 'HARD GATE' or 'FORBIDDEN' enforcement. "
            "Advisory language like 'Consider decomposing' is insufficient — "
            "add explicit enforcement language."
        )

    def test_step6_hard_gate_specifies_condition(self, step6_section: str) -> None:
        """Step 6 HARD GATE must specify when issue creation is required."""
        assert step6_section, "Step 6 section must exist in plan.md"

        # Must mention some condition that triggers mandatory issue creation
        has_condition = (
            "independent" in step6_section.lower()
            or "multiple" in step6_section.lower()
            or "multi" in step6_section.lower()
            or "separate" in step6_section.lower()
        )
        assert has_condition, (
            "Issue #854: Step 6 HARD GATE must specify the condition (e.g., multiple "
            "independent work items) that triggers mandatory issue creation."
        )


class TestStep7LinkedIssuesSection:
    """Issue #854 AC3: Step 7 plan file template must contain '## Linked Issues'."""

    def test_step7_template_contains_linked_issues_section(
        self, plan_content: str
    ) -> None:
        """The plan file template in Step 7 must include a '## Linked Issues' section."""
        assert "## Linked Issues" in plan_content, (
            "Issue #854: plan.md Step 7 template must contain '## Linked Issues' section. "
            "This section links the plan to created GitHub issues."
        )

    def test_linked_issues_section_is_in_template_block(
        self, step7_section: str
    ) -> None:
        """'## Linked Issues' must appear inside the template code block in Step 7."""
        assert step7_section, "Step 7 section must exist in plan.md"
        assert "## Linked Issues" in step7_section, (
            "Issue #854: '## Linked Issues' must appear in the Step 7 template block, "
            "not just anywhere in the file."
        )


class TestStep6SingleItemSkipLogic:
    """Issue #854 AC4: Step 6 must include explicit skip logic for single-item plans."""

    def test_step6_has_explicit_skip_logic(self, step6_section: str) -> None:
        """Step 6 must explicitly describe when to skip with a log message."""
        assert step6_section, "Step 6 section must exist in plan.md"

        has_skip_logic = "skip" in step6_section.lower() or "log" in step6_section.lower()
        assert has_skip_logic, (
            "Issue #854: Step 6 must include explicit skip logic for single-item plans. "
            "The skip condition must be clearly stated (not implied)."
        )

    def test_step6_skip_mentions_single_item_or_coherent_unit(
        self, step6_section: str
    ) -> None:
        """Step 6 skip logic must mention what constitutes a single-item plan."""
        assert step6_section, "Step 6 section must exist in plan.md"

        content_lower = step6_section.lower()
        has_single_item_reference = (
            "single" in content_lower
            or "coherent" in content_lower
            or "one item" in content_lower
            or "not multi" in content_lower
        )
        assert has_single_item_reference, (
            "Issue #854: Step 6 skip logic must reference what a single-item plan is "
            "(e.g., 'single coherent unit', 'single item'). "
            "Found section:\n" + step6_section[:300]
        )

    def test_step6_skip_includes_explicit_log_message(self, step6_section: str) -> None:
        """Step 6 must include an explicit log message when skipping."""
        assert step6_section, "Step 6 section must exist in plan.md"

        # The log message should tell the user WHY step 6 is being skipped
        has_log_message = (
            "log" in step6_section.lower()
            or "skipping" in step6_section.lower()
            or "skip" in step6_section.lower()
        ) and (
            "single" in step6_section.lower()
            or "coherent" in step6_section.lower()
            or "one item" in step6_section.lower()
        )
        assert has_log_message, (
            "Issue #854: Step 6 must include an explicit log message when skipping "
            "issue decomposition for single-item plans. "
            "Example: 'Skipping Step 6: plan is a single coherent unit.'"
        )


class TestOutputSectionImplementIssues:
    """Issue #854 AC5: Output section must mention '/implement --issues' when issues are created."""

    def test_output_section_mentions_implement_issues(
        self, output_section: str
    ) -> None:
        """Output section must reference '/implement --issues' command."""
        assert output_section, "Output section must exist in plan.md"

        assert "--issues" in output_section, (
            "Issue #854: Output section must mention '/implement --issues' command "
            "so the user knows how to proceed after issues are created. "
            "Currently only '/implement' is shown."
        )

    def test_output_section_implement_issues_is_conditional(
        self, output_section: str
    ) -> None:
        """The '/implement --issues' mention should be conditional on issues being created."""
        assert output_section, "Output section must exist in plan.md"
        assert "--issues" in output_section, (
            "Issue #854: '/implement --issues' must appear in output section"
        )

        # Check that the context around --issues suggests it's conditional
        issues_index = output_section.index("--issues")
        context_window = output_section[max(0, issues_index - 200) : issues_index + 200]

        has_conditional_context = (
            "if" in context_window.lower()
            or "when" in context_window.lower()
            or "created" in context_window.lower()
            or "issue" in context_window.lower()
        )
        assert has_conditional_context, (
            "Issue #854: '/implement --issues' in the output section should appear in "
            "conditional context (e.g., 'if issues were created'). "
            f"Context found: {context_window!r}"
        )
