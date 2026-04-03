"""
Tests for stick+carrot directive pattern in hook block messages (Issue #660).

Validates that every deny path includes:
1. Original prefix preserved (BLOCKED, WORKFLOW ENFORCEMENT, ORDERING VIOLATION)
2. "REQUIRED NEXT ACTION:" directive in permissionDecisionReason
3. system_message differs from permissionDecisionReason (shorter, user-friendly)

Date: 2026-04-04
"""

import json
import os
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

# Add hook and lib directories to path
HOOK_DIR = Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "hooks"
sys.path.insert(0, str(HOOK_DIR))

LIB_DIR = Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "lib"
sys.path.insert(0, str(LIB_DIR))

import unified_pre_tool as hook
from agent_ordering_gate import check_ordering_prerequisites


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Remove pipeline/agent env vars to ensure clean state."""
    env_keys = [
        "SANDBOX_ENABLED", "PRE_TOOL_MCP_SECURITY", "PRE_TOOL_AGENT_AUTH",
        "PRE_TOOL_BATCH_PERMISSION", "MCP_AUTO_APPROVE", "ENFORCEMENT_LEVEL",
        "CLAUDE_AGENT_NAME", "PIPELINE_STATE_FILE", "CLAUDE_SESSION_ID",
    ]
    for key in env_keys:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def no_pipeline():
    """Patch _is_pipeline_active to return False."""
    with patch.object(hook, "_is_pipeline_active", return_value=False):
        yield


@pytest.fixture
def active_pipeline():
    """Patch _is_pipeline_active to return True."""
    with patch.object(hook, "_is_pipeline_active", return_value=True):
        yield


@pytest.fixture
def no_agent():
    """Patch _get_active_agent_name to return empty string."""
    with patch.object(hook, "_get_active_agent_name", return_value=""):
        yield


@pytest.fixture
def no_issue_command():
    """Patch _is_issue_command_active to return False."""
    with patch.object(hook, "_is_issue_command_active", return_value=False):
        yield


@pytest.fixture
def no_marker(tmp_path):
    """Patch GH_ISSUE_MARKER_PATH to a non-existent file."""
    fake_path = str(tmp_path / "nonexistent_marker")
    with patch.object(hook, "GH_ISSUE_MARKER_PATH", fake_path):
        yield


# ---------------------------------------------------------------------------
# TestHelperCarrotMessages - one per helper function
# ---------------------------------------------------------------------------

class TestHelperCarrotMessages:
    """Verify each helper function includes REQUIRED NEXT ACTION in block reasons."""

    def test_detect_env_spoofing_has_carrot(self):
        """_detect_env_spoofing block messages include carrot directive."""
        result = hook._detect_env_spoofing("CLAUDE_AGENT_NAME=implementer python3 script.py")
        assert result is not None
        assert "BLOCKED" in result
        assert "REQUIRED NEXT ACTION" in result
        assert "Do NOT" in result

    def test_detect_env_spoofing_export_has_carrot(self):
        """_detect_env_spoofing export pattern includes carrot."""
        result = hook._detect_env_spoofing("export CLAUDE_AGENT_NAME=implementer")
        assert result is not None
        assert "BLOCKED" in result
        assert "REQUIRED NEXT ACTION" in result

    def test_detect_env_spoofing_env_cmd_has_carrot(self):
        """_detect_env_spoofing env command pattern includes carrot."""
        result = hook._detect_env_spoofing("env CLAUDE_AGENT_NAME=implementer python3 script.py")
        assert result is not None
        assert "BLOCKED" in result
        assert "REQUIRED NEXT ACTION" in result

    def test_check_bash_infra_writes_has_carrot(self, no_pipeline):
        """_check_bash_infra_writes block messages include carrot directive."""
        result = hook._check_bash_infra_writes(
            "sed -i 's/foo/bar/' plugins/autonomous-dev/agents/implementer.md"
        )
        assert result is not None
        file_name, reason = result
        assert "BLOCKED" in reason
        assert "REQUIRED NEXT ACTION" in reason
        assert "Do NOT" in reason

    def test_detect_gh_issue_marker_creation_has_carrot(
        self, no_pipeline, no_agent, no_issue_command
    ):
        """_detect_gh_issue_marker_creation block messages include carrot."""
        result = hook._detect_gh_issue_marker_creation(
            "touch /tmp/autonomous_dev_gh_issue_allowed.marker"
        )
        assert result is not None
        assert "BLOCKED" in result
        assert "REQUIRED NEXT ACTION" in result
        assert "Do NOT" in result

    def test_detect_gh_issue_create_has_carrot(
        self, no_pipeline, no_agent, no_marker, no_issue_command
    ):
        """_detect_gh_issue_create block messages include carrot."""
        result = hook._detect_gh_issue_create(
            'gh issue create --title "test" --body "test"'
        )
        assert result is not None
        assert "BLOCKED" in result
        assert "REQUIRED NEXT ACTION" in result

    def test_detect_settings_json_write_has_carrot(self, active_pipeline):
        """_detect_settings_json_write block messages include carrot."""
        result = hook._detect_settings_json_write("echo '{}' > settings.json")
        assert result is not None
        assert "BLOCKED" in result
        assert "REQUIRED NEXT ACTION" in result
        assert "Do NOT" in result

    def test_ordering_gate_has_carrot(self):
        """agent_ordering_gate violation includes carrot directive."""
        result = check_ordering_prerequisites(
            "implementer",
            completed_agents=set(),  # planner not completed
            validation_mode="sequential",
        )
        assert result.passed is False
        assert "ORDERING VIOLATION" in result.reason
        assert "REQUIRED NEXT ACTION" in result.reason
        assert "Do NOT" in result.reason


# ---------------------------------------------------------------------------
# TestOutputDecisionDifferentiation - verify reason != system_message
# ---------------------------------------------------------------------------

class TestOutputDecisionDifferentiation:
    """Verify output_decision produces different permissionDecisionReason vs systemMessage."""

    def _capture_output_decision(
        self, decision: str, reason: str, *, system_message: str = ""
    ) -> dict:
        """Call output_decision and capture the JSON output."""
        buf = StringIO()
        with patch("sys.stdout", buf):
            hook.output_decision(decision, reason, system_message=system_message)
        return json.loads(buf.getvalue())

    def test_infra_block_reason_differs_from_system_message(self):
        """Infrastructure block: reason contains carrot, system_message is shorter."""
        reason = (
            "BLOCKED: Direct edit to 'implementer.md' denied. "
            "Infrastructure files (agents/, commands/, hooks/, lib/, skills/) "
            "require the /implement pipeline. Run: /implement \"description\" "
            "REQUIRED NEXT ACTION: Run /implement with a description of your "
            "change. Delegate the edit to the implementer agent. "
            "Do NOT write infrastructure files directly."
        )
        sys_msg = "BLOCKED: Direct edit to 'implementer.md' denied. Use /implement to modify infrastructure files."

        output = self._capture_output_decision("deny", reason, system_message=sys_msg)
        pdr = output["hookSpecificOutput"]["permissionDecisionReason"]
        sm = output.get("systemMessage", "")

        assert pdr != sm, "permissionDecisionReason and systemMessage must differ"
        assert "REQUIRED NEXT ACTION" in pdr
        assert len(sm) < len(pdr), "systemMessage should be shorter than reason"

    def test_env_spoof_reason_differs_from_system_message(self):
        """Env spoofing block: reason contains carrot, system_message is shorter."""
        reason = (
            "BLOCKED: Inline env var spoofing detected. "
            "REQUIRED NEXT ACTION: Remove the override. Do NOT set protected vars."
        )
        sys_msg = "BLOCKED: Protected environment variable cannot be overridden."

        output = self._capture_output_decision("deny", reason, system_message=sys_msg)
        pdr = output["hookSpecificOutput"]["permissionDecisionReason"]
        sm = output.get("systemMessage", "")

        assert pdr != sm
        assert "REQUIRED NEXT ACTION" in pdr

    def test_coordinator_block_reason_differs_from_system_message(self):
        """Coordinator block: reason contains carrot, system_message is shorter."""
        reason = (
            "WORKFLOW ENFORCEMENT: /implement is active. "
            "REQUIRED NEXT ACTION: Invoke the appropriate agent. Do NOT write code directly."
        )
        sys_msg = "WORKFLOW ENFORCEMENT: Delegate code changes to pipeline agents."

        output = self._capture_output_decision("deny", reason, system_message=sys_msg)
        pdr = output["hookSpecificOutput"]["permissionDecisionReason"]
        sm = output.get("systemMessage", "")

        assert pdr != sm
        assert "REQUIRED NEXT ACTION" in pdr
        assert "WORKFLOW ENFORCEMENT" in sm


# ---------------------------------------------------------------------------
# TestCarrotInAllDenyPaths - scan source for completeness
# ---------------------------------------------------------------------------

class TestCarrotInAllDenyPaths:
    """Verify no output_decision('deny', ...) call uses system_message=block_reason."""

    def test_no_identical_system_message_in_deny_calls(self):
        """Scan unified_pre_tool.py source: no deny call should pass reason as system_message.

        Exception: ext_reason (from user-provided extensions) is allowed to be identical
        since the extension controls both the reason and the message.
        """
        source_path = HOOK_DIR / "unified_pre_tool.py"
        source = source_path.read_text()

        # Find all output_decision("deny", ...) call sites
        import re
        # Pattern: output_decision("deny", <var>, system_message=<same_var>)
        # We look for cases where system_message= references the same variable as the reason
        pattern = r'output_decision\(\s*"deny"\s*,\s*(\w+)\s*,\s*system_message\s*=\s*\1\s*\)'
        matches = re.findall(pattern, source)

        # ext_reason is exempt — extensions are user-provided and control both fields
        allowed_exceptions = {"ext_reason"}
        violations = [m for m in matches if m not in allowed_exceptions]

        assert len(violations) == 0, (
            f"Found {len(violations)} output_decision('deny') calls where "
            f"system_message is identical to the reason variable: {violations}. "
            f"Each deny call should have a distinct, shorter system_message."
        )

    def test_all_helper_block_returns_have_carrot(self):
        """All helper functions that return block strings include REQUIRED NEXT ACTION."""
        source_path = HOOK_DIR / "unified_pre_tool.py"
        source = source_path.read_text()

        # Check that BLOCKED strings in helper functions contain REQUIRED NEXT ACTION
        # Focus on the return statements in helper functions
        import re

        # Find all string literals containing "BLOCKED:" that are return values
        # We check that for each helper function's BLOCKED return, there's a
        # REQUIRED NEXT ACTION nearby
        helpers = [
            "_detect_env_spoofing",
            "_check_bash_infra_writes",
            "_detect_gh_issue_marker_creation",
            "_detect_gh_issue_create",
            "_detect_settings_json_write",
        ]

        for helper_name in helpers:
            # Extract function body
            func_pattern = rf'def {helper_name}\(.*?\n(?=def |\Z)'
            func_match = re.search(func_pattern, source, re.DOTALL)
            assert func_match is not None, f"Could not find function {helper_name}"
            func_body = func_match.group(0)

            # Count BLOCKED returns and REQUIRED NEXT ACTION occurrences
            blocked_count = func_body.count("BLOCKED")
            carrot_count = func_body.count("REQUIRED NEXT ACTION")

            assert carrot_count >= 1, (
                f"{helper_name} has {blocked_count} BLOCKED messages but "
                f"{carrot_count} REQUIRED NEXT ACTION directives"
            )
