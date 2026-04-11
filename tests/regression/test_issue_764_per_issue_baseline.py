#!/usr/bin/env python3
"""
Regression tests for Issue #764: Progressive prompt shrinkage in batch mode.

Bug: In batch mode, prompt baselines persisted across issues. As context
accumulated, the coordinator produced shorter prompts for later issues.
The shrinkage gate then blocked agents (e.g., security-auditor 27.1%,
reviewer 37.4%) because the baseline was from the first issue, not the
current issue.

Root cause: get_prompt_baseline() always returned the lowest-numbered issue's
baseline. Issue #753 (first) seeded a 246-word baseline. Issue #755 (third)
sent a 154-word prompt -> 37.4% shrinkage -> BLOCKED. But the shrinkage was
from cross-issue context pressure, not within-issue prompt compression gaming.

Fix: Made baselines per-issue by adding issue_number parameter to
get_prompt_baseline(). The hook now uses PIPELINE_ISSUE_NUMBER env var for
both seeding and lookup so each issue compares only against its own baseline.
"""

import json
import sys
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

sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "autonomous-dev" / "lib"))

from prompt_integrity import (
    get_prompt_baseline,
    record_prompt_baseline,
    clear_prompt_baselines,
)


class TestPerIssueBaselineIsolation:
    """Issue #764: Per-issue baseline isolation prevents cross-issue false positives."""

    def test_issue1_baseline_does_not_affect_issue2(self, tmp_path: Path) -> None:
        """Core bug reproduction: issue #753 baseline should not block issue #755.

        Before fix: get_prompt_baseline("reviewer") returns 246 (from issue #753).
        Issue #755 sends 154 words -> 37.4% shrinkage -> BLOCKED.

        After fix: get_prompt_baseline("reviewer", issue_number=755) returns None
        (no baseline for issue #755 yet), so no shrinkage comparison happens.
        """
        # Simulate batch: issue #753 seeds baseline with 246 words
        record_prompt_baseline("reviewer", issue_number=753, word_count=246, state_dir=tmp_path)

        # Issue #755 looks up its OWN baseline (per-issue)
        baseline_for_755 = get_prompt_baseline(
            "reviewer", issue_number=755, state_dir=tmp_path
        )

        # Should be None -- issue #755 has no baseline yet
        assert baseline_for_755 is None, (
            f"Expected None for issue #755 baseline, got {baseline_for_755}. "
            f"Cross-issue contamination is still happening."
        )

    def test_within_issue_shrinkage_still_detected(self, tmp_path: Path) -> None:
        """Same issue, shorter retry -> shrinkage detected (correct behavior).

        First invocation for issue #755 seeds 200 words.
        Second invocation for issue #755 with 100 words -> 50% shrinkage.
        Per-issue lookup should return 200, allowing shrinkage detection.
        """
        # First invocation seeds baseline
        record_prompt_baseline("reviewer", issue_number=755, word_count=200, state_dir=tmp_path)

        # Second invocation checks per-issue baseline
        baseline = get_prompt_baseline(
            "reviewer", issue_number=755, state_dir=tmp_path
        )

        assert baseline == 200, (
            f"Expected 200 for issue #755 baseline, got {baseline}. "
            f"Within-issue baseline tracking is broken."
        )

    def test_backward_compat_no_issue_number(self, tmp_path: Path) -> None:
        """When issue_number is None, original behavior (lowest issue) is preserved.

        This ensures non-batch single-issue mode continues to work unchanged.
        """
        record_prompt_baseline("reviewer", issue_number=5, word_count=400, state_dir=tmp_path)
        record_prompt_baseline("reviewer", issue_number=2, word_count=500, state_dir=tmp_path)
        record_prompt_baseline("reviewer", issue_number=10, word_count=350, state_dir=tmp_path)

        # No issue_number -> backward compat -> lowest issue (#2) baseline
        baseline = get_prompt_baseline("reviewer", state_dir=tmp_path)

        assert baseline == 500, (
            f"Expected 500 (issue #2, lowest), got {baseline}. "
            f"Backward compatibility broken."
        )

    def test_baseline_seeding_uses_current_issue_number(self, tmp_path: Path) -> None:
        """Baseline seeding records under the current issue number, not hardcoded 0.

        Before fix: record_prompt_baseline(agent, issue_number=0, word_count=wc)
        After fix: record_prompt_baseline(agent, issue_number=<current_issue>, word_count=wc)
        """
        # Simulate what the hook does with PIPELINE_ISSUE_NUMBER=755
        current_issue = 755
        record_prompt_baseline(
            "security-auditor", issue_number=current_issue, word_count=180,
            state_dir=tmp_path,
        )

        # Per-issue lookup should find it
        baseline = get_prompt_baseline(
            "security-auditor", issue_number=755, state_dir=tmp_path
        )
        assert baseline == 180

        # Different issue should NOT find it
        baseline_other = get_prompt_baseline(
            "security-auditor", issue_number=753, state_dir=tmp_path
        )
        assert baseline_other is None

    def test_multiple_issues_fully_isolated(self, tmp_path: Path) -> None:
        """Each issue in a batch has its own independent baseline."""
        # Batch processes 3 issues with different prompt lengths
        record_prompt_baseline("implementer", issue_number=100, word_count=300, state_dir=tmp_path)
        record_prompt_baseline("implementer", issue_number=200, word_count=180, state_dir=tmp_path)
        record_prompt_baseline("implementer", issue_number=300, word_count=250, state_dir=tmp_path)

        # Each issue sees only its own baseline
        assert get_prompt_baseline("implementer", issue_number=100, state_dir=tmp_path) == 300
        assert get_prompt_baseline("implementer", issue_number=200, state_dir=tmp_path) == 180
        assert get_prompt_baseline("implementer", issue_number=300, state_dir=tmp_path) == 250

        # Unseen issue returns None
        assert get_prompt_baseline("implementer", issue_number=999, state_dir=tmp_path) is None

    def test_per_issue_baseline_json_structure(self, tmp_path: Path) -> None:
        """Verify JSON file structure supports per-issue baselines."""
        record_prompt_baseline("reviewer", issue_number=753, word_count=246, state_dir=tmp_path)
        record_prompt_baseline("reviewer", issue_number=755, word_count=154, state_dir=tmp_path)

        baselines_path = tmp_path / "prompt_baselines.json"
        data = json.loads(baselines_path.read_text())

        assert data == {
            "reviewer": {
                "753": 246,
                "755": 154,
            }
        }
