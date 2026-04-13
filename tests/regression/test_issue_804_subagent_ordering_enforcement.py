"""Regression tests for Issue #804 — Sub-agent ordering enforcement and state file protection.

Verifies that:
1. The ordering gate uses JSON permissionDecision format (not exit code 2)
2. Ordering prerequisites are enforced during active pipeline
3. Pipeline state files are protected from deletion during active pipeline
"""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Import from unified_pre_tool
sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[2] / "plugins" / "autonomous-dev" / "hooks"),
)
import unified_pre_tool

# Import from agent_ordering_gate
sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[2] / "plugins" / "autonomous-dev" / "lib"),
)
from agent_ordering_gate import check_ordering_prerequisites


class TestOrderingGateJsonFormat:
    """Verify ordering gate output uses JSON permissionDecision, not exit code 2."""

    def test_ordering_gate_uses_json_permission_decision_format(self, capsys):
        """output_decision produces JSON with permissionDecision key."""
        unified_pre_tool.output_decision("deny", "test reason")
        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())
        assert "hookSpecificOutput" in output
        assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert output["hookSpecificOutput"]["permissionDecisionReason"] == "test reason"


class TestAgentOrderingPrerequisites:
    """Verify ordering gate blocks/allows based on prerequisites."""

    def test_agent_tool_unmet_prerequisites_denied(self):
        """Security-auditor without reviewer completed should be denied."""
        result = check_ordering_prerequisites(
            "security-auditor",
            completed_agents=set(),  # Nothing completed
            validation_mode="sequential",
        )
        assert result.passed is False
        assert "reviewer" in result.reason.lower() or len(result.missing_agents) > 0

    def test_agent_tool_met_prerequisites_allowed(self):
        """Security-auditor with all prerequisites completed should be allowed."""
        # security-auditor requires both implementer (core) and reviewer (sequential)
        result = check_ordering_prerequisites(
            "security-auditor",
            completed_agents={"implementer", "reviewer"},
            validation_mode="sequential",
        )
        assert result.passed is True


class TestPipelineStateDeletionGuard:
    """Verify _check_bash_state_deletion detects state file deletion commands."""

    def test_rm_pipeline_state_during_active_pipeline_blocked(self):
        """rm of pipeline state file must be detected."""
        result = unified_pre_tool._check_bash_state_deletion(
            "rm -f /tmp/implement_pipeline_state.json"
        )
        assert result is not None
        assert "/tmp/implement_pipeline_state.json" in result[0]

    def test_rm_pipeline_state_no_active_pipeline_detection_works(self):
        """Detection function returns non-None regardless of pipeline state.

        The pipeline-active check is done by the caller, not the function itself.
        """
        result = unified_pre_tool._check_bash_state_deletion(
            "rm /tmp/implement_pipeline_state.json"
        )
        assert result is not None

    def test_rm_unrelated_tmp_file_allowed(self):
        """rm of unrelated /tmp file must NOT trigger the guard."""
        result = unified_pre_tool._check_bash_state_deletion(
            "rm -f /tmp/something_else.txt"
        )
        assert result is None

    def test_python_os_remove_state_file_detected(self):
        """python3 -c with os.remove targeting state file must be detected."""
        cmd = 'python3 -c "import os; os.remove(\'/tmp/implement_pipeline_state.json\')"'
        result = unified_pre_tool._check_bash_state_deletion(cmd)
        assert result is not None

    def test_truncate_state_file_detected(self):
        """truncate targeting pipeline state file must be detected."""
        result = unified_pre_tool._check_bash_state_deletion(
            "truncate -s 0 /tmp/implement_pipeline_state.json"
        )
        assert result is not None

    def test_rm_deny_cache_detected(self):
        """rm of deny cache file must also be detected."""
        result = unified_pre_tool._check_bash_state_deletion(
            "rm /tmp/.claude_deny_cache.jsonl"
        )
        assert result is not None

    def test_rm_completion_state_file_detected(self):
        """rm of pipeline completion state file must be detected."""
        result = unified_pre_tool._check_bash_state_deletion(
            "rm /tmp/pipeline_completion_state_session123.json"
        )
        assert result is not None

    def test_unlink_state_file_detected(self):
        """unlink of pipeline state file must be detected."""
        result = unified_pre_tool._check_bash_state_deletion(
            "unlink /tmp/implement_pipeline_state.json"
        )
        assert result is not None
