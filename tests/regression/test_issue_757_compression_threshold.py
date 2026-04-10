"""Regression test: Issue #757 — progressive prompt compression false positives.

The post-hoc validator flagged reviewer prompt shrinkage of 34% (315 words -> 208 words)
as CRITICAL progressive compression. This was a false positive caused by legitimate
task-level variation between batch issues.

Fix: Increased MAX_PROMPT_SHRINKAGE_RATIO from 0.25 (25%) to 0.40 (40%) in the
post-hoc validator (pipeline_intent_validator.py). The real-time hook
(unified_pre_tool.py / prompt_integrity.py) retains the 25% per-invocation threshold.
"""
import sys
from pathlib import Path

import pytest

# Portable project root detection
_current = Path(__file__).resolve()
REPO_ROOT = _current.parents[2]

sys.path.insert(0, str(REPO_ROOT / "plugins" / "autonomous-dev" / "lib"))

from pipeline_intent_validator import (
    MAX_PROMPT_SHRINKAGE_RATIO,
    PipelineEvent,
    detect_progressive_compression,
)


def _make_event(
    *,
    subagent_type: str,
    batch_issue_number: int,
    prompt_word_count: int,
    timestamp: str = "2026-04-10T10:00:00+00:00",
) -> PipelineEvent:
    """Create a PipelineEvent for testing compression detection."""
    return PipelineEvent(
        timestamp=timestamp,
        tool="Agent",
        agent="main",
        subagent_type=subagent_type,
        pipeline_action="agent_invocation",
        batch_issue_number=batch_issue_number,
        prompt_word_count=prompt_word_count,
        result_word_count=100,
    )


class TestIssue757CompressionThreshold:
    """Regression tests for Issue #757: false positive compression detection."""

    def test_threshold_is_40_percent(self):
        """MAX_PROMPT_SHRINKAGE_RATIO must be 0.40 (not the old 0.25)."""
        assert MAX_PROMPT_SHRINKAGE_RATIO == 0.40, (
            f"Issue #757: threshold should be 0.40, got {MAX_PROMPT_SHRINKAGE_RATIO}"
        )

    def test_34_percent_shrinkage_no_finding(self):
        """Issue #757 scenario: reviewer 315->208 words (34% shrinkage) must NOT flag.

        This was the exact false positive that motivated Issue #757.
        With the old 25% threshold, this was flagged as CRITICAL.
        With the new 40% threshold, this is legitimate variation.
        """
        events = [
            _make_event(
                subagent_type="reviewer",
                batch_issue_number=750,
                prompt_word_count=315,
                timestamp="2026-04-10T10:00:00+00:00",
            ),
            _make_event(
                subagent_type="reviewer",
                batch_issue_number=751,
                prompt_word_count=208,
                timestamp="2026-04-10T10:10:00+00:00",
            ),
        ]
        findings = detect_progressive_compression(events)
        assert len(findings) == 0, (
            "Issue #757: 34% shrinkage (315->208) should NOT produce a finding "
            "with the 40% threshold"
        )

    def test_45_percent_shrinkage_produces_finding(self):
        """45% shrinkage exceeds the 40% threshold and SHOULD be flagged."""
        events = [
            _make_event(
                subagent_type="reviewer",
                batch_issue_number=750,
                prompt_word_count=315,
                timestamp="2026-04-10T10:00:00+00:00",
            ),
            _make_event(
                subagent_type="reviewer",
                batch_issue_number=751,
                prompt_word_count=173,  # ~45% shrinkage from 315
                timestamp="2026-04-10T10:10:00+00:00",
            ),
        ]
        findings = detect_progressive_compression(events)
        assert len(findings) == 1, (
            "Issue #757: 45% shrinkage (315->173) SHOULD produce a finding"
        )
        assert findings[0].severity == "CRITICAL", (
            "reviewer is a security-critical agent, severity must be CRITICAL"
        )

    def test_exactly_40_percent_shrinkage_no_finding(self):
        """Exactly 40% shrinkage (ratio = 0.60) should NOT flag.

        The check is `ratio < (1 - MAX_PROMPT_SHRINKAGE_RATIO)` = `ratio < 0.60`.
        At exactly 40% shrinkage, ratio = 0.60 which is NOT < 0.60, so no flag.
        """
        events = [
            _make_event(
                subagent_type="reviewer",
                batch_issue_number=750,
                prompt_word_count=315,
                timestamp="2026-04-10T10:00:00+00:00",
            ),
            _make_event(
                subagent_type="reviewer",
                batch_issue_number=751,
                prompt_word_count=189,  # 189/315 = 0.60 exactly
                timestamp="2026-04-10T10:10:00+00:00",
            ),
        ]
        findings = detect_progressive_compression(events)
        assert len(findings) == 0, (
            "Issue #757: exactly 40% shrinkage (ratio=0.60) should NOT flag "
            "(threshold is exclusive)"
        )
