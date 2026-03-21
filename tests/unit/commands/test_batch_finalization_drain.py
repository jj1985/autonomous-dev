"""Tests for Issues #536, #537, #526: Batch finalization drain and logging fixes.

Validates:
1. Issue #536: implement-batch.md has pre-commit drain step (step 0) in STEP B4
2. Issue #537: Post-batch CIA launch order documented before worktree cleanup
3. Issue #526: Coordinator-side batch logging section present in STEP B3
"""

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
BATCH_CMD_PATH = PROJECT_ROOT / "plugins/autonomous-dev/commands/implement-batch.md"


@pytest.fixture
def batch_content() -> str:
    return BATCH_CMD_PATH.read_text()


class TestPreCommitDrainStep:
    """Issue #536: Doc-master fixes lost on worktree cleanup."""

    def test_step_b4_has_drain_step_zero(self, batch_content: str):
        """STEP B4 must include step 0 to drain background agents before committing."""
        assert "Drain all remaining agents and verify writes" in batch_content, (
            "STEP B4 must have a step 0 that drains all remaining agents "
            "before committing. Issue #536 fix requires this to prevent "
            "doc-master writes from being lost."
        )

    def test_drain_step_forbids_commit_during_writes(self, batch_content: str):
        """Drain step must forbid committing while background agents are writing."""
        assert "while any background agent may still be writing files" in batch_content, (
            "STEP B4 step 0 must explicitly forbid running git commit while "
            "background agents may still be writing files (Issue #536)."
        )

    def test_drain_step_requires_git_status_verification(self, batch_content: str):
        """Drain step must require git status to confirm all files are visible."""
        content_lower = batch_content.lower()
        has_git_status = "git status" in content_lower
        has_confirm = "confirm" in content_lower and "modified files" in content_lower
        assert has_git_status and has_confirm, (
            "STEP B4 step 0 must require running git status to confirm "
            "all modified files are visible before committing (Issue #536)."
        )

    def test_drain_step_forbids_worktree_delete_before_cia(self, batch_content: str):
        """Drain step must forbid deleting worktree before CIA reads session log."""
        assert "Deleting the worktree before the post-batch CIA has read the session log" in batch_content, (
            "STEP B4 must forbid deleting the worktree before the post-batch "
            "CIA has read the session log (Issue #536)."
        )

    def test_drain_step_references_issue_536(self, batch_content: str):
        """Drain step must reference Issue #536."""
        assert "Issue #536" in batch_content, (
            "STEP B4 drain step must reference Issue #536 for traceability."
        )


class TestCIALaunchOrdering:
    """Issue #537: Post-batch CIA invoked after worktree cleanup."""

    def test_step_b3_5_has_launch_order(self, batch_content: str):
        """STEP B3.5 must document the CIA launch order relative to worktree cleanup."""
        assert "STEP B3.5: Launch CIA in background" in batch_content, (
            "STEP B3.5 must document the launch order showing CIA launches "
            "before worktree cleanup (Issue #537)."
        )

    def test_cia_must_launch_before_cleanup(self, batch_content: str):
        """The CIA must be launched BEFORE worktree cleanup."""
        assert "MUST be launched BEFORE worktree cleanup" in batch_content, (
            "STEP B3.5 must state that CIA MUST be launched BEFORE "
            "worktree cleanup (Issue #537)."
        )

    def test_block_cleanup_if_cia_not_launched(self, batch_content: str):
        """If CIA not launched, worktree cleanup must be blocked."""
        assert "BLOCK worktree cleanup until CIA is launched" in batch_content, (
            "STEP B3.5 must state to BLOCK worktree cleanup if CIA "
            "has not been launched yet (Issue #537)."
        )

    def test_launch_order_sequence(self, batch_content: str):
        """Launch order must show: CIA -> commit -> merge -> cleanup."""
        cia_pos = batch_content.find("STEP B3.5: Launch CIA in background")
        commit_pos = batch_content.find("STEP B4 step 1: Commit in worktree")
        merge_pos = batch_content.find("STEP B4 step 2: Merge to master")
        cleanup_pos = batch_content.find("STEP B4 step 3: Cleanup worktree")

        assert cia_pos > 0, "CIA launch step not found in launch order"
        assert commit_pos > 0, "Commit step not found in launch order"
        assert merge_pos > 0, "Merge step not found in launch order"
        assert cleanup_pos > 0, "Cleanup step not found in launch order"

        assert cia_pos < commit_pos < merge_pos < cleanup_pos, (
            "Launch order must be: CIA -> commit -> merge -> cleanup. "
            "CIA must be launched first so it can read session logs."
        )

    def test_references_issue_537(self, batch_content: str):
        """CIA ordering section must reference Issue #537."""
        assert "Issue #537" in batch_content, (
            "CIA launch ordering must reference Issue #537 for traceability."
        )


class TestBatchCoordinatorLogging:
    """Issue #526: Session activity logger blind in batch context."""

    def test_batch_logging_section_exists(self, batch_content: str):
        """implement-batch.md must have a BatchCoordinatorLog section."""
        assert "BATCH LOGGING: Coordinator-Side Agent Completion Log" in batch_content, (
            "implement-batch.md must have a 'BATCH LOGGING' section "
            "for coordinator-side agent completion logging (Issue #526)."
        )

    def test_batch_logging_references_issue_526(self, batch_content: str):
        """Batch logging section must reference Issue #526."""
        assert "Issue #526" in batch_content, (
            "Batch logging section must reference Issue #526 for traceability."
        )

    def test_batch_logging_has_python_code(self, batch_content: str):
        """Batch logging section must include Python logging code."""
        assert "BatchCoordinatorLog" in batch_content, (
            "Batch logging section must include Python code that writes "
            "BatchCoordinatorLog entries to the activity log."
        )

    def test_batch_logging_captures_agent_type(self, batch_content: str):
        """Logging code must capture subagent_type."""
        assert "'subagent_type'" in batch_content, (
            "Batch coordinator log must capture the subagent_type "
            "to identify which agent completed."
        )

    def test_batch_logging_captures_batch_id(self, batch_content: str):
        """Logging code must capture batch_id."""
        assert "'batch_id'" in batch_content, (
            "Batch coordinator log must capture the batch_id "
            "to correlate entries with the batch run."
        )

    def test_batch_logging_captures_issue_number(self, batch_content: str):
        """Logging code must capture issue_number."""
        assert "'issue_number'" in batch_content, (
            "Batch coordinator log must capture the issue_number "
            "to correlate entries with specific issues in the batch."
        )

    def test_batch_logging_writes_to_activity_log(self, batch_content: str):
        """Logging code must write to the activity log directory."""
        assert "logs" in batch_content and "activity" in batch_content, (
            "Batch coordinator log must write to .claude/logs/activity/ "
            "to be consistent with the session_activity_logger hook."
        )

    def test_batch_logging_required_for_every_agent(self, batch_content: str):
        """Batch logging must be required for every agent completion."""
        assert "EVERY agent completion in batch mode" in batch_content, (
            "Batch coordinator log must be emitted after EVERY agent "
            "completion in batch mode (all 7-8 agents per issue)."
        )
