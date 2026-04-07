"""Regression test for Issue #682: doc-master verdict read race condition.

The orchestrator would grep the doc-master's transcript file before it had
fully flushed to disk, causing a false [DOC-VERDICT-MISSING] warning even
though the verdict was emitted. The fix adds explicit guidance to use the
Agent tool's return value instead of grepping transcript files, and to wait
3 seconds for filesystem flush if transcript parsing is unavoidable.

This test verifies that both implement.md and implement-batch.md contain
the race condition mitigation language.
"""

from pathlib import Path

import pytest

# Locate the commands directory relative to the repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
IMPLEMENT_MD = REPO_ROOT / "plugins" / "autonomous-dev" / "commands" / "implement.md"
IMPLEMENT_BATCH_MD = REPO_ROOT / "plugins" / "autonomous-dev" / "commands" / "implement-batch.md"


class TestIssue682DocVerdictRaceCondition:
    """Verify race condition mitigation language is present in pipeline commands."""

    def test_implement_md_exists(self) -> None:
        """Precondition: implement.md must exist."""
        assert IMPLEMENT_MD.exists(), f"implement.md not found at {IMPLEMENT_MD}"

    def test_implement_batch_md_exists(self) -> None:
        """Precondition: implement-batch.md must exist."""
        assert IMPLEMENT_BATCH_MD.exists(), f"implement-batch.md not found at {IMPLEMENT_BATCH_MD}"

    def test_implement_md_no_grep_transcript(self) -> None:
        """implement.md must instruct NOT to grep transcript files directly."""
        content = IMPLEMENT_MD.read_text()
        assert "do NOT grep transcript files directly" in content, (
            "implement.md missing 'do NOT grep transcript files directly' guidance (Issue #682)"
        )

    def test_implement_md_use_return_value(self) -> None:
        """implement.md must instruct to use Agent tool's return value."""
        content = IMPLEMENT_MD.read_text()
        assert "Agent tool's return value" in content, (
            "implement.md missing 'Agent tool's return value' guidance (Issue #682)"
        )

    def test_implement_md_flush_delay(self) -> None:
        """implement.md must mention filesystem flush delay."""
        content = IMPLEMENT_MD.read_text()
        assert "filesystem flush delay" in content, (
            "implement.md missing 'filesystem flush delay' guidance (Issue #682)"
        )

    def test_implement_md_issue_reference(self) -> None:
        """implement.md must reference Issue #682."""
        content = IMPLEMENT_MD.read_text()
        assert "Issue #682" in content, (
            "implement.md missing Issue #682 reference"
        )

    def test_implement_md_3_second_wait(self) -> None:
        """implement.md must specify 3-second wait for flush."""
        content = IMPLEMENT_MD.read_text()
        assert "3 seconds" in content or "3s" in content, (
            "implement.md missing 3-second wait specification (Issue #682)"
        )

    def test_implement_batch_md_no_grep_transcript(self) -> None:
        """implement-batch.md must instruct NOT to grep transcript files directly."""
        content = IMPLEMENT_BATCH_MD.read_text()
        assert "do NOT grep transcript files directly" in content, (
            "implement-batch.md missing 'do NOT grep transcript files directly' guidance (Issue #682)"
        )

    def test_implement_batch_md_use_return_value(self) -> None:
        """implement-batch.md must instruct to use Agent tool's return value."""
        content = IMPLEMENT_BATCH_MD.read_text()
        assert "Agent tool's return value" in content, (
            "implement-batch.md missing 'Agent tool's return value' guidance (Issue #682)"
        )

    def test_implement_batch_md_flush_delay(self) -> None:
        """implement-batch.md must mention filesystem flush delay."""
        content = IMPLEMENT_BATCH_MD.read_text()
        assert "filesystem flush delay" in content, (
            "implement-batch.md missing 'filesystem flush delay' guidance (Issue #682)"
        )

    def test_implement_batch_md_issue_reference(self) -> None:
        """implement-batch.md must reference Issue #682."""
        content = IMPLEMENT_BATCH_MD.read_text()
        assert "Issue #682" in content, (
            "implement-batch.md missing Issue #682 reference"
        )

    def test_implement_batch_md_3_second_wait(self) -> None:
        """implement-batch.md must specify 3-second wait for flush."""
        content = IMPLEMENT_BATCH_MD.read_text()
        assert "3 seconds" in content or "3s" in content, (
            "implement-batch.md missing 3-second wait specification (Issue #682)"
        )

    def test_implement_md_retry_includes_wait(self) -> None:
        """implement.md retry section must include wait before re-check.

        This is the core regression: without the wait, the retry reads
        stale filesystem state and produces a false DOC-VERDICT-MISSING.
        """
        content = IMPLEMENT_MD.read_text()
        # The retry section (point 6) must mention waiting before re-check
        assert "Wait 3 seconds for filesystem flush" in content, (
            "implement.md retry section missing 'Wait 3 seconds for filesystem flush' (Issue #682)"
        )

    def test_implement_batch_md_retry_includes_wait(self) -> None:
        """implement-batch.md retry must include wait for flush.

        Same regression as implement.md: without the wait, grep sees
        stale transcript data.
        """
        content = IMPLEMENT_BATCH_MD.read_text()
        assert "wait 3 seconds for filesystem flush" in content, (
            "implement-batch.md retry missing 'wait 3 seconds for filesystem flush' (Issue #682)"
        )
