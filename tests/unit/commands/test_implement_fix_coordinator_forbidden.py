"""Regression tests for Issue #846: Coordinator attempted direct Edit to project file after pipeline completed.

Validates that implement-fix.md contains a COORDINATOR FORBIDDEN LIST section that explicitly
prohibits direct file modifications, post-completion edits, and other coordinator bypass patterns.
"""

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
COMMANDS_DIR = PROJECT_ROOT / "plugins/autonomous-dev/commands"
IMPLEMENT_FIX_MD = COMMANDS_DIR / "implement-fix.md"
IMPLEMENT_MD = COMMANDS_DIR / "implement.md"


@pytest.fixture(scope="module")
def fix_content() -> str:
    """Read implement-fix.md once for the test module."""
    return IMPLEMENT_FIX_MD.read_text()


@pytest.fixture(scope="module")
def full_content() -> str:
    """Read implement.md once for the test module."""
    return IMPLEMENT_MD.read_text()


class TestCoordinatorForbiddenListExists:
    """Test that the Coordinator Role HARD GATE section is present."""

    def test_coordinator_forbidden_list_exists(self, fix_content: str):
        """implement-fix.md must contain a 'Coordinator Role' section.

        Regression: Issue #846 — coordinator directly edited trading_engine.py
        after the pipeline completed, bypassing all specialist agent checks.
        """
        assert "Coordinator Role" in fix_content, (
            "implement-fix.md is missing the 'Coordinator Role' section. "
            "This section prevents coordinators from acting as substitute implementers."
        )

    def test_hard_gate_label_on_coordinator_section(self, fix_content: str):
        """Coordinator Role section must be marked as a HARD GATE."""
        assert "Coordinator Role — HARD GATE" in fix_content, (
            "Coordinator Role section must be labelled 'HARD GATE' to signal "
            "it is an absolute constraint, not advisory guidance."
        )

    def test_dispatcher_role_defined(self, fix_content: str):
        """implement-fix.md must explicitly define the coordinator as a dispatcher.

        Regression: Issue #846 — the coordinator substituted its own judgment for
        specialist agent execution, editing files directly instead of delegating.
        """
        assert "dispatcher" in fix_content.lower(), (
            "implement-fix.md must define the coordinator as a dispatcher, "
            "not a substitute for specialist agents."
        )


class TestNoDirectWritesRule:
    """Test that direct file modification by the coordinator is explicitly prohibited."""

    def test_no_direct_writes_rule_present(self, fix_content: str):
        """Coordinator must be forbidden from direct file writes or edits.

        Regression: Issue #846 — coordinator issued an Edit tool call directly
        to trading_engine.py after all agents had completed, bypassing review gates.
        """
        # The section must contain language forbidding direct write/edit to project files
        assert "MUST NOT write, edit, or modify any project files directly" in fix_content, (
            "implement-fix.md must contain an explicit prohibition: "
            "'MUST NOT write, edit, or modify any project files directly'. "
            "This is the core bypass pattern from Issue #846."
        )

    def test_specialist_agents_required_for_file_modifications(self, fix_content: str):
        """File modifications must be routed through specialist agents."""
        assert "ALL file modifications MUST go through specialist agents" in fix_content, (
            "implement-fix.md must require that all file modifications go through "
            "specialist agents (implementer, doc-master), not the coordinator directly."
        )

    def test_agent_crash_retry_rule_present(self, fix_content: str):
        """When an agent crashes, coordinator must retry once then block — not substitute."""
        assert "RETRY once" in fix_content or "retry once" in fix_content, (
            "implement-fix.md must specify that when an agent crashes, the coordinator "
            "retries once then blocks — never substitutes its own file edits."
        )


class TestPostCompletionEditProhibition:
    """Test that the coordinator is prohibited from editing files after agents complete."""

    def test_post_completion_edit_prohibition(self, fix_content: str):
        """No file edits are permitted after pipeline agents complete.

        Regression: Issue #846 — coordinator performed a direct Edit call to
        trading_engine.py AFTER the implementer and reviewer had already completed,
        circumventing the review that had already been done.
        """
        assert "MUST NOT perform any file edits after agents complete" in fix_content, (
            "implement-fix.md must explicitly prohibit file edits after agents complete. "
            "Post-completion edits circumvent the review pipeline (Issue #846)."
        )

    def test_permitted_post_agent_actions_listed(self, fix_content: str):
        """The permitted post-agent actions must be explicitly enumerated."""
        # Verify the allowed post-agent actions are listed (summary, git ops, STEP F5)
        assert "final summary" in fix_content, (
            "implement-fix.md must list 'final summary' as a permitted post-agent action."
        )
        assert "git operations" in fix_content or "git add" in fix_content, (
            "implement-fix.md must list git operations as permitted post-agent actions."
        )
        assert "STEP F5" in fix_content, (
            "implement-fix.md must list launching STEP F5 as a permitted post-agent action."
        )

    def test_no_phase_parallelization_rule(self, fix_content: str):
        """Agents from different pipeline phases must not be parallelized."""
        assert "MUST NOT parallelize agents from different pipeline phases" in fix_content, (
            "implement-fix.md must prohibit parallelizing agents from different phases."
        )


class TestOutputFidelityRules:
    """Test that output fidelity constraints are present for the coordinator."""

    def test_no_paraphrase_rule_present(self, fix_content: str):
        """Coordinator must not paraphrase or condense agent output."""
        assert "MUST NOT paraphrase or condense agent output" in fix_content, (
            "implement-fix.md must prohibit the coordinator from paraphrasing "
            "or condensing agent output when passing it to the next stage."
        )

    def test_fifty_percent_word_count_rule_present(self, fix_content: str):
        """Coordinator must pass at least 50% of implementer output words to reviewer."""
        assert "50%" in fix_content, (
            "implement-fix.md must specify the 50% word count floor for passing "
            "implementer output to the reviewer."
        )


class TestParityWithFullPipeline:
    """Test that key forbidden items from implement.md are mirrored in implement-fix.md."""

    def test_parity_with_full_pipeline_skip_steps(self, fix_content: str, full_content: str):
        """Both pipelines must forbid skipping steps.

        Parity check: implement.md line ~30 has 'MUST NOT skip any STEP'.
        implement-fix.md must carry the same constraint.
        """
        assert "MUST NOT skip any STEP" in fix_content, (
            "implement-fix.md is missing parity with implement.md: "
            "'MUST NOT skip any STEP' is present in implement.md but not implement-fix.md."
        )
        assert "MUST NOT skip any STEP" in full_content, (
            "implement.md must also contain 'MUST NOT skip any STEP' (sanity check)."
        )

    def test_parity_with_full_pipeline_summarize_rule(self, fix_content: str, full_content: str):
        """Both pipelines must forbid summarizing agent output."""
        # implement.md uses "summarize agent output", implement-fix.md must have comparable text
        assert "summarize" in fix_content.lower(), (
            "implement-fix.md must prohibit summarizing agent output, "
            "matching the constraint in implement.md."
        )
        assert "summarize" in full_content.lower(), (
            "implement.md must also forbid summarizing agent output (sanity check)."
        )

    def test_parity_with_full_pipeline_dispatcher_role(self, fix_content: str, full_content: str):
        """Both pipelines must identify the coordinator as a dispatcher."""
        assert "dispatcher" in fix_content.lower(), (
            "implement-fix.md must identify the coordinator as a dispatcher."
        )
        assert "dispatcher" in full_content.lower(), (
            "implement.md must also identify the coordinator as a dispatcher (sanity check)."
        )

    def test_parity_with_full_pipeline_agent_crash_handling(
        self, fix_content: str, full_content: str
    ):
        """Both pipelines must specify agent-crash retry behaviour (retry once, then block)."""
        # implement.md: "RETRY the agent once with the same prompt. If retry also crashes, BLOCK"
        assert "RETRY" in fix_content, (
            "implement-fix.md must specify that agent crashes are handled with a RETRY, "
            "not by substituting coordinator file edits."
        )
        assert "RETRY" in full_content, (
            "implement.md must specify the RETRY pattern for agent crashes (sanity check)."
        )

    def test_parity_with_full_pipeline_no_direct_write(
        self, fix_content: str, full_content: str
    ):
        """Both pipelines must prohibit the coordinator from writing implementation code."""
        # implement.md: "MUST NOT write implementation code yourself"
        assert "MUST NOT write" in fix_content, (
            "implement-fix.md must contain 'MUST NOT write' to prohibit the coordinator "
            "from writing files directly."
        )
        assert "MUST NOT write" in full_content, (
            "implement.md must also contain 'MUST NOT write' (sanity check)."
        )
