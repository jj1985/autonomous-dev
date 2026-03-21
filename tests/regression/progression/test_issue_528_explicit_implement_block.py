"""
Regression tests for Issue #528: Enforce /implement hard block when explicitly invoked.

Locks the fix that prevents the coordinator from making code changes directly
when /implement is explicitly running. The coordinator must delegate to
pipeline agents (implementer, test-master, doc-master).

Root cause: When /implement was active, validate_agent_authorization() returned
"allow" for the coordinator via the state file path, letting it bypass the
pipeline and write code directly instead of delegating.

Date fixed: 2026-03-21
Issue: #528
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

# Add hook's parent to path so we can import the module
HOOK_DIR = Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "hooks"
sys.path.insert(0, str(HOOK_DIR))

LIB_DIR = Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "lib"
sys.path.insert(0, str(LIB_DIR))

import unified_pre_tool as hook

PLUGIN_DIR = Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev"
IMPLEMENT_CMD = PLUGIN_DIR / "commands" / "implement.md"


class TestExplicitlyInvokedFlagInCommand:
    """Verify implement.md writes explicitly_invoked to state file."""

    def test_implement_md_includes_explicitly_invoked(self):
        """The implement command must write explicitly_invoked:true to state."""
        content = IMPLEMENT_CMD.read_text()
        assert '"explicitly_invoked":true' in content, (
            "implement.md must include 'explicitly_invoked:true' in pipeline state JSON"
        )


class TestCoordinatorBlockedDuringExplicitImplement:
    """The coordinator must be blocked from code writes during explicit /implement."""

    @pytest.fixture(autouse=True)
    def setup_explicit_state(self, tmp_path, monkeypatch):
        """Set up an explicit implement state file."""
        state_path = tmp_path / "implement_pipeline_state.json"
        state_path.write_text(json.dumps({
            "session_start": datetime.now().isoformat(),
            "mode": "full",
            "run_id": "regression-528",
            "explicitly_invoked": True,
        }))
        monkeypatch.setenv("PIPELINE_STATE_FILE", str(state_path))
        monkeypatch.setenv("PRE_TOOL_AGENT_AUTH", "true")
        monkeypatch.delenv("ENFORCEMENT_LEVEL", raising=False)
        monkeypatch.setenv("CLAUDE_AGENT_NAME", "")

    def test_coordinator_write_py_blocked(self):
        """Coordinator writing .py is denied with delegation message."""
        decision, reason = hook.validate_agent_authorization(
            "Write", {"file_path": "/tmp/feature.py", "content": "def main(): pass"}
        )
        assert decision == "deny"
        assert "delegate" in reason.lower()

    def test_implementer_write_py_allowed(self, monkeypatch):
        """Implementer agent writing .py is allowed."""
        monkeypatch.setenv("CLAUDE_AGENT_NAME", "implementer")
        decision, reason = hook.validate_agent_authorization(
            "Write", {"file_path": "/tmp/feature.py", "content": "def main(): pass"}
        )
        assert decision == "allow"

    def test_coordinator_write_json_allowed(self):
        """Coordinator writing .json (non-code) is allowed."""
        decision, reason = hook.validate_agent_authorization(
            "Write", {"file_path": "/tmp/config.json", "content": "{}"}
        )
        # Should not get the explicit implement deny
        assert decision != "deny" or "WORKFLOW ENFORCEMENT" not in reason
