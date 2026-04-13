#!/usr/bin/env python3
"""
Smoke tests for fix-mode pipeline validation (Issues #788, #798).

Fast critical-path regression tests verifying:
- Fix mode does not produce false CRITICAL findings about missing planner (#788)
- Security-sensitive file changes without security-auditor produce WARNING (#798)
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# Portable project root detection (tests/regression/smoke/ -> parents[2] is wrong,
# we need parents[3] from tests/regression/smoke/test_file.py)
_current = Path.cwd()
while _current != _current.parent:
    if (_current / ".git").exists() or (_current / ".claude").exists():
        PROJECT_ROOT = _current
        break
    _current = _current.parent
else:
    PROJECT_ROOT = Path.cwd()

sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "autonomous-dev" / "lib"))

from pipeline_intent_validator import (
    Finding,
    PipelineEvent,
    detect_missing_security_review,
    validate_step_ordering,
)


def _make_event(
    subagent_type: str,
    timestamp: str,
    pipeline_mode: str = "",
) -> PipelineEvent:
    """Minimal event helper for smoke tests."""
    return PipelineEvent(
        timestamp=timestamp,
        tool="Task",
        agent="main",
        subagent_type=subagent_type,
        pipeline_action="agent_invocation",
        prompt_word_count=500,
        result_word_count=2000,
        pipeline_mode=pipeline_mode,
    )


class TestIssue788FixModePlanner:
    """Regression: fix mode must not require planner step."""

    def test_issue_788_fix_mode_no_false_planner_validation(self):
        """Fix-mode implementer without planner produces no CRITICAL findings."""
        base = datetime(2026, 2, 28, 10, 0, 0)
        events = [
            _make_event("implementer", base.isoformat(), pipeline_mode="fix"),
            _make_event(
                "reviewer",
                (base + timedelta(minutes=5)).isoformat(),
                pipeline_mode="fix",
            ),
        ]
        findings = validate_step_ordering(events)
        critical = [f for f in findings if f.severity == "CRITICAL"]
        assert len(critical) == 0, (
            "Issue #788: fix mode must not produce false CRITICAL about missing planner"
        )


class TestIssue798SecurityFileReview:
    """Regression: security-sensitive file changes require security-auditor."""

    def test_issue_798_security_file_missing_auditor(self, tmp_path):
        """Hooks file change without security-auditor produces WARNING."""
        log_file = tmp_path / "session.jsonl"
        base = datetime(2026, 2, 28, 10, 0, 0)

        # Write JSONL with a Write tool entry targeting hooks/
        lines = [
            json.dumps({
                "timestamp": base.isoformat(),
                "tool": "Task",
                "input_summary": {
                    "subagent_type": "implementer",
                    "pipeline_action": "agent_invocation",
                    "prompt_word_count": 500,
                    "pipeline_mode": "--fix",
                },
                "output_summary": {"success": True, "result_word_count": 2000},
                "session_id": "smoke-test",
                "agent": "main",
            }),
            json.dumps({
                "timestamp": (base + timedelta(minutes=2)).isoformat(),
                "tool": "Write",
                "input_summary": {
                    "file_path": "plugins/autonomous-dev/hooks/unified_pre_tool.py",
                },
                "output_summary": {"success": True},
                "session_id": "smoke-test",
                "agent": "main",
            }),
        ]
        log_file.write_text("\n".join(lines) + "\n")

        events = [
            _make_event("implementer", base.isoformat(), pipeline_mode="--fix"),
            _make_event(
                "reviewer",
                (base + timedelta(minutes=5)).isoformat(),
                pipeline_mode="--fix",
            ),
        ]

        findings = detect_missing_security_review(
            log_file, events, session_id="smoke-test",
        )
        assert len(findings) == 1, (
            "Issue #798: hooks/ change without security-auditor must produce WARNING"
        )
        assert findings[0].severity == "WARNING"
        assert findings[0].pattern_id == "missing_security_review"
