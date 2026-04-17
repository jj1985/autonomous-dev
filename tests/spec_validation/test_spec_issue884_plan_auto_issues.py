"""Spec validation tests for Issue #884: /plan auto-runs plan-critic and /plan-to-issues on PROCEED.

Validates acceptance criteria:
1. --no-issues flag is documented in Step 0 or frontmatter
2. Step 6 contains non-blocking error handling language
3. Step 6 contains PROCEED-only guard (does not run on REVISE/BLOCKED)
4. FORBIDDEN list prevents issue creation on REVISE/BLOCKED verdicts
5. Output section references created issue URLs
6. Step 6 references gh issue create or equivalent
7. plan-to-issues.md contains note about /plan auto-running issue creation
8. Step 6 summary table row reflects auto-create description
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMANDS_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "commands"


@pytest.fixture(scope="module")
def plan_content() -> str:
    """Read plan.md once for all tests."""
    plan_cmd = COMMANDS_DIR / "plan.md"
    assert plan_cmd.exists(), f"plan.md not found at {plan_cmd}"
    return plan_cmd.read_text()


@pytest.fixture(scope="module")
def plan_to_issues_content() -> str:
    """Read plan-to-issues.md once for all tests."""
    pti_cmd = COMMANDS_DIR / "plan-to-issues.md"
    assert pti_cmd.exists(), f"plan-to-issues.md not found at {pti_cmd}"
    return pti_cmd.read_text()


# ---------------------------------------------------------------------------
# AC1: --no-issues flag documented in Step 0 or frontmatter
# ---------------------------------------------------------------------------


class TestSpec884AC1NoIssuesFlag:
    """The --no-issues flag must be documented in plan.md."""

    def test_spec_884_1_no_issues_in_frontmatter_hint(self, plan_content: str) -> None:
        """argument-hint in frontmatter must mention --no-issues."""
        assert "--no-issues" in plan_content, (
            "plan.md frontmatter argument-hint must include --no-issues flag"
        )

    def test_spec_884_1_no_issues_in_step_0(self, plan_content: str) -> None:
        """Step 0 must document --no-issues flag parsing."""
        # Find Step 0 section
        step0_idx = plan_content.find("### STEP 0:")
        assert step0_idx != -1, "plan.md must have a STEP 0 section"
        # Find next section boundary
        next_section_idx = plan_content.find("### STEP 1:", step0_idx)
        step0_text = plan_content[step0_idx:next_section_idx] if next_section_idx != -1 else plan_content[step0_idx:]
        assert "--no-issues" in step0_text, (
            "STEP 0 must document the --no-issues flag"
        )

    def test_spec_884_1_no_issues_skips_step_6(self, plan_content: str) -> None:
        """Step 6 must guard on --no-issues flag and skip issue creation."""
        step6_idx = plan_content.find("### STEP 6:")
        assert step6_idx != -1, "plan.md must have a STEP 6 section"
        next_section_idx = plan_content.find("### STEP 7:", step6_idx)
        step6_text = plan_content[step6_idx:next_section_idx] if next_section_idx != -1 else plan_content[step6_idx:]
        assert "--no-issues" in step6_text, (
            "STEP 6 must reference --no-issues flag guard"
        )


# ---------------------------------------------------------------------------
# AC2: Step 6 contains non-blocking error handling language
# ---------------------------------------------------------------------------


class TestSpec884AC2NonBlockingErrors:
    """Step 6 must use non-blocking error handling for gh failures."""

    def test_spec_884_2_step6_has_nonblocking_language(self, plan_content: str) -> None:
        """Step 6 must specify that gh failures do not block plan file creation."""
        step6_idx = plan_content.find("### STEP 6:")
        assert step6_idx != -1, "plan.md must have a STEP 6 section"
        next_section_idx = plan_content.find("### STEP 7:", step6_idx)
        step6_text = plan_content[step6_idx:next_section_idx] if next_section_idx != -1 else plan_content[step6_idx:]

        # Must contain language about not blocking
        has_nonblocking = (
            "Do NOT halt" in step6_text
            or "Do NOT block" in step6_text
            or "non-blocking" in step6_text.lower()
            or "not block" in step6_text.lower()
        )
        assert has_nonblocking, (
            "STEP 6 must contain non-blocking error handling language for gh failures"
        )

    def test_spec_884_2_step6_has_fallback_suggestion(self, plan_content: str) -> None:
        """Step 6 must suggest /plan-to-issues as fallback when gh fails."""
        step6_idx = plan_content.find("### STEP 6:")
        assert step6_idx != -1, "plan.md must have a STEP 6 section"
        next_section_idx = plan_content.find("### STEP 7:", step6_idx)
        step6_text = plan_content[step6_idx:next_section_idx] if next_section_idx != -1 else plan_content[step6_idx:]

        assert "/plan-to-issues" in step6_text, (
            "STEP 6 must suggest /plan-to-issues as fallback when gh issue create fails"
        )


# ---------------------------------------------------------------------------
# AC3: Step 6 runs ONLY after PROCEED (not REVISE or BLOCKED)
# ---------------------------------------------------------------------------


class TestSpec884AC3ProceedOnlyGuard:
    """Step 6 must only run after PROCEED verdict, not REVISE or BLOCKED."""

    def test_spec_884_3_step6_references_proceed(self, plan_content: str) -> None:
        """Step 6 must explicitly reference PROCEED verdict as the trigger."""
        step6_idx = plan_content.find("### STEP 6:")
        assert step6_idx != -1, "plan.md must have a STEP 6 section"
        next_section_idx = plan_content.find("### STEP 7:", step6_idx)
        step6_text = plan_content[step6_idx:next_section_idx] if next_section_idx != -1 else plan_content[step6_idx:]

        assert "PROCEED" in step6_text, (
            "STEP 6 must reference PROCEED verdict as the trigger condition"
        )

    def test_spec_884_3_step6_guards_against_revise(self, plan_content: str) -> None:
        """Step 6 must explicitly exclude REVISE verdict from triggering issue creation."""
        step6_idx = plan_content.find("### STEP 6:")
        assert step6_idx != -1, "plan.md must have a STEP 6 section"
        next_section_idx = plan_content.find("### STEP 7:", step6_idx)
        step6_text = plan_content[step6_idx:next_section_idx] if next_section_idx != -1 else plan_content[step6_idx:]

        assert "REVISE" in step6_text, (
            "STEP 6 must reference REVISE to guard against running after REVISE verdict"
        )

    def test_spec_884_3_step6_guards_against_blocked(self, plan_content: str) -> None:
        """Step 6 must explicitly exclude BLOCKED verdict from triggering issue creation."""
        step6_idx = plan_content.find("### STEP 6:")
        assert step6_idx != -1, "plan.md must have a STEP 6 section"
        next_section_idx = plan_content.find("### STEP 7:", step6_idx)
        step6_text = plan_content[step6_idx:next_section_idx] if next_section_idx != -1 else plan_content[step6_idx:]

        assert "BLOCKED" in step6_text, (
            "STEP 6 must reference BLOCKED to guard against running after BLOCKED verdict"
        )


# ---------------------------------------------------------------------------
# AC4: FORBIDDEN list prevents issue creation on REVISE/BLOCKED
# ---------------------------------------------------------------------------


class TestSpec884AC4ForbiddenList:
    """Step 6 FORBIDDEN list must prohibit issue creation on REVISE/BLOCKED."""

    def test_spec_884_4_forbidden_revise_in_step6(self, plan_content: str) -> None:
        """Step 6 FORBIDDEN list must explicitly disallow issue creation after REVISE."""
        step6_idx = plan_content.find("### STEP 6:")
        assert step6_idx != -1, "plan.md must have a STEP 6 section"
        next_section_idx = plan_content.find("### STEP 7:", step6_idx)
        step6_text = plan_content[step6_idx:next_section_idx] if next_section_idx != -1 else plan_content[step6_idx:]

        assert "FORBIDDEN" in step6_text, (
            "STEP 6 must contain a FORBIDDEN list"
        )
        # The FORBIDDEN section must mention REVISE verdict
        forbidden_idx = step6_text.find("FORBIDDEN")
        forbidden_area = step6_text[forbidden_idx:forbidden_idx + 500]
        assert "REVISE" in forbidden_area, (
            "STEP 6 FORBIDDEN list must mention REVISE verdict"
        )

    def test_spec_884_4_forbidden_blocked_in_step6(self, plan_content: str) -> None:
        """Step 6 FORBIDDEN list must explicitly disallow issue creation after BLOCKED."""
        step6_idx = plan_content.find("### STEP 6:")
        assert step6_idx != -1, "plan.md must have a STEP 6 section"
        next_section_idx = plan_content.find("### STEP 7:", step6_idx)
        step6_text = plan_content[step6_idx:next_section_idx] if next_section_idx != -1 else plan_content[step6_idx:]

        assert "FORBIDDEN" in step6_text, "STEP 6 must contain a FORBIDDEN list"
        forbidden_idx = step6_text.find("FORBIDDEN")
        forbidden_area = step6_text[forbidden_idx:forbidden_idx + 500]
        assert "BLOCKED" in forbidden_area, (
            "STEP 6 FORBIDDEN list must mention BLOCKED verdict"
        )


# ---------------------------------------------------------------------------
# AC5: Output section references created issue URLs
# ---------------------------------------------------------------------------


class TestSpec884AC5OutputIssueUrls:
    """Output section must show created issue URLs when issues are created."""

    def test_spec_884_5_output_section_shows_issue_urls(self, plan_content: str) -> None:
        """Output section must reference created issue URLs."""
        output_idx = plan_content.find("### Output")
        assert output_idx != -1, "plan.md must have an Output section"
        output_text = plan_content[output_idx:]

        # Should reference issue URLs in output
        has_issue_url = (
            "github.com" in output_text
            or "issues/" in output_text
            or "issue URL" in output_text.lower()
            or "Issues created" in output_text
        )
        assert has_issue_url, (
            "Output section must show created issue URLs to the user"
        )

    def test_spec_884_5_output_shows_fallback_plan_to_issues(self, plan_content: str) -> None:
        """Output section must show /plan-to-issues fallback when issues not created."""
        output_idx = plan_content.find("### Output")
        assert output_idx != -1, "plan.md must have an Output section"
        output_text = plan_content[output_idx:]

        assert "/plan-to-issues" in output_text, (
            "Output section must reference /plan-to-issues as fallback"
        )


# ---------------------------------------------------------------------------
# AC6: Step 6 references gh issue create
# ---------------------------------------------------------------------------


class TestSpec884AC6GhIssuCreate:
    """Step 6 must reference gh issue create for issue creation."""

    def test_spec_884_6_step6_references_gh_issue_create(self, plan_content: str) -> None:
        """Step 6 must use gh issue create for issue creation."""
        step6_idx = plan_content.find("### STEP 6:")
        assert step6_idx != -1, "plan.md must have a STEP 6 section"
        next_section_idx = plan_content.find("### STEP 7:", step6_idx)
        step6_text = plan_content[step6_idx:next_section_idx] if next_section_idx != -1 else plan_content[step6_idx:]

        assert "gh issue create" in step6_text, (
            "STEP 6 must reference 'gh issue create' for issue creation"
        )

    def test_spec_884_6_step6_creates_cmd_context_file(self, plan_content: str) -> None:
        """Step 6 must create /tmp/autonomous_dev_cmd_context.json before gh calls."""
        step6_idx = plan_content.find("### STEP 6:")
        assert step6_idx != -1, "plan.md must have a STEP 6 section"
        next_section_idx = plan_content.find("### STEP 7:", step6_idx)
        step6_text = plan_content[step6_idx:next_section_idx] if next_section_idx != -1 else plan_content[step6_idx:]

        assert "autonomous_dev_cmd_context.json" in step6_text, (
            "STEP 6 must create /tmp/autonomous_dev_cmd_context.json before gh calls (required by hook)"
        )


# ---------------------------------------------------------------------------
# AC7: plan-to-issues.md note about /plan auto-running issue creation
# ---------------------------------------------------------------------------


class TestSpec884AC7PlanToIssuesNote:
    """/plan-to-issues must contain a note about /plan auto-running issue creation."""

    def test_spec_884_7_plan_to_issues_has_auto_run_note(self, plan_to_issues_content: str) -> None:
        """/plan-to-issues.md must note that /plan auto-runs issue creation after PROCEED."""
        assert "/plan" in plan_to_issues_content, (
            "plan-to-issues.md must reference /plan command"
        )
        # The note should mention automatic issue creation
        has_auto_note = (
            "automatically" in plan_to_issues_content.lower()
            or "auto-creation" in plan_to_issues_content.lower()
            or "auto-runs" in plan_to_issues_content.lower()
        )
        assert has_auto_note, (
            "plan-to-issues.md must contain a note that /plan automatically runs issue creation"
        )

    def test_spec_884_7_plan_to_issues_mentions_no_issues_flag(self, plan_to_issues_content: str) -> None:
        """/plan-to-issues.md must mention --no-issues flag for skipped auto-creation."""
        assert "--no-issues" in plan_to_issues_content, (
            "plan-to-issues.md must mention --no-issues flag for cases where auto-creation was skipped"
        )


# ---------------------------------------------------------------------------
# AC8: Summary table row updated for Step 6
# ---------------------------------------------------------------------------


class TestSpec884AC8SummaryTable:
    """Summary table Step 6 row must reflect auto-create description."""

    def test_spec_884_8_summary_table_step6_updated(self, plan_content: str) -> None:
        """Summary table must show auto-create description for Step 6 row."""
        # Find the What This Does table
        table_idx = plan_content.find("## What This Does")
        assert table_idx != -1, "plan.md must have a 'What This Does' section"
        table_text = plan_content[table_idx:]

        # The Issue Decomposition row should mention auto-create or quick mode
        has_updated_description = (
            "Auto-create" in table_text
            or "auto-create" in table_text
            or "quick mode" in table_text.lower()
        )
        assert has_updated_description, (
            "Summary table Step 6 row must reflect auto-create GitHub issues description"
        )
