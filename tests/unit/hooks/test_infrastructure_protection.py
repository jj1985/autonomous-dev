"""
Tests for infrastructure file protection in unified_pre_tool.py (Issue #483).

Validates that:
1. _is_protected_infrastructure correctly identifies protected files
2. _is_pipeline_active detects pipeline via agent name and state file
3. Main flow blocks direct edits to infrastructure files outside pipeline
4. output_decision supports systemMessage

Date: 2026-03-18
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

# Add hook's parent to path so we can import the module
HOOK_DIR = Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "hooks"
sys.path.insert(0, str(HOOK_DIR))

# Also add lib dir for any transitive imports
LIB_DIR = Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "lib"
sys.path.insert(0, str(LIB_DIR))

import unified_pre_tool as hook


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Reset relevant env vars for each test."""
    env_keys = [
        "SANDBOX_ENABLED", "PRE_TOOL_MCP_SECURITY", "PRE_TOOL_AGENT_AUTH",
        "PRE_TOOL_BATCH_PERMISSION", "MCP_AUTO_APPROVE", "ENFORCEMENT_LEVEL",
        "CLAUDE_AGENT_NAME", "PIPELINE_STATE_FILE",
    ]
    for key in env_keys:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("PRE_TOOL_MCP_SECURITY", "true")
    monkeypatch.setenv("PRE_TOOL_AGENT_AUTH", "true")


# ---------------------------------------------------------------------------
# TestIsProtectedInfrastructure
# ---------------------------------------------------------------------------

class TestIsProtectedInfrastructure:
    """Tests for _is_protected_infrastructure helper."""

    def test_agents_md_file(self):
        assert hook._is_protected_infrastructure("agents/implementer.md") is True

    def test_agents_md_with_claude_prefix(self):
        assert hook._is_protected_infrastructure(".claude/agents/implementer.md") is True

    def test_agents_md_full_path(self):
        assert hook._is_protected_infrastructure(
            "/Users/foo/.claude/agents/implementer.md"
        ) is True

    def test_agents_md_plugin_path(self):
        assert hook._is_protected_infrastructure(
            "plugins/autonomous-dev/agents/implementer.md"
        ) is True

    def test_commands_md(self):
        assert hook._is_protected_infrastructure("commands/implement.md") is True

    def test_hooks_py(self):
        assert hook._is_protected_infrastructure("hooks/unified_pre_tool.py") is True

    def test_lib_py(self):
        assert hook._is_protected_infrastructure("lib/pipeline_state.py") is True

    def test_skills_md(self):
        assert hook._is_protected_infrastructure("skills/testing-guide/SKILL.md") is True

    def test_readme_not_protected(self):
        assert hook._is_protected_infrastructure("README.md") is False

    def test_src_app_not_protected(self):
        assert hook._is_protected_infrastructure("src/app.py") is False

    def test_test_file_not_protected(self):
        assert hook._is_protected_infrastructure("tests/test_foo.py") is False

    def test_agents_json_not_protected(self):
        """JSON in agents/ is not protected (wrong extension)."""
        assert hook._is_protected_infrastructure("agents/config.json") is False

    def test_hooks_md_not_protected(self):
        """Markdown in hooks/ is not protected (wrong extension for hooks/)."""
        assert hook._is_protected_infrastructure("hooks/readme.md") is False

    def test_lib_json_not_protected(self):
        """JSON in lib/ is not protected (wrong extension for lib/)."""
        assert hook._is_protected_infrastructure("lib/data.json") is False

    def test_empty_string(self):
        assert hook._is_protected_infrastructure("") is False

    def test_backslash_paths_normalized(self):
        """Windows-style backslash paths should still match."""
        assert hook._is_protected_infrastructure(
            "C:\\Users\\foo\\.claude\\agents\\implementer.md"
        ) is True


# ---------------------------------------------------------------------------
# TestIsPipelineActive
# ---------------------------------------------------------------------------

class TestIsPipelineActive:
    """Tests for _is_pipeline_active helper."""

    def test_implementer_agent(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_AGENT_NAME", "implementer")
        assert hook._is_pipeline_active() is True

    def test_test_master_agent(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_AGENT_NAME", "test-master")
        assert hook._is_pipeline_active() is True

    def test_doc_master_agent(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_AGENT_NAME", "doc-master")
        assert hook._is_pipeline_active() is True

    def test_reviewer_not_pipeline(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_AGENT_NAME", "reviewer")
        monkeypatch.setenv("PIPELINE_STATE_FILE", "/tmp/nonexistent_test_state.json")
        assert hook._is_pipeline_active() is False

    def test_no_env_var(self, monkeypatch):
        monkeypatch.delenv("CLAUDE_AGENT_NAME", raising=False)
        # Also ensure no state file
        monkeypatch.setenv("PIPELINE_STATE_FILE", "/tmp/nonexistent_test_state.json")
        assert hook._is_pipeline_active() is False

    def test_valid_state_file(self, monkeypatch):
        """Pipeline state file < 2 hours old should activate."""
        monkeypatch.delenv("CLAUDE_AGENT_NAME", raising=False)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            state = {"session_start": datetime.now().isoformat()}
            json.dump(state, f)
            f.flush()
            monkeypatch.setenv("PIPELINE_STATE_FILE", f.name)
            assert hook._is_pipeline_active() is True
        os.unlink(f.name)

    def test_stale_state_file(self, monkeypatch):
        """Pipeline state file > 2 hours old should not activate."""
        monkeypatch.delenv("CLAUDE_AGENT_NAME", raising=False)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            old_time = datetime.now() - timedelta(hours=3)
            state = {"session_start": old_time.isoformat()}
            json.dump(state, f)
            f.flush()
            monkeypatch.setenv("PIPELINE_STATE_FILE", f.name)
            assert hook._is_pipeline_active() is False
        os.unlink(f.name)

    def test_missing_state_file(self, monkeypatch):
        monkeypatch.delenv("CLAUDE_AGENT_NAME", raising=False)
        monkeypatch.setenv("PIPELINE_STATE_FILE", "/tmp/definitely_does_not_exist_12345.json")
        assert hook._is_pipeline_active() is False


# ---------------------------------------------------------------------------
# TestInfraProtectionInMainFlow
# ---------------------------------------------------------------------------

class TestInfraProtectionInMainFlow:
    """Integration tests for infrastructure protection in main() flow."""

    def _run_hook(self, tool_name: str, tool_input: dict) -> dict:
        """Run the hook's main() with given input and capture JSON output."""
        input_data = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
        captured = StringIO()

        with patch("sys.stdin", StringIO(input_data)), \
             patch("sys.stdout", captured), \
             pytest.raises(SystemExit):
            hook.main()

        output_text = captured.getvalue().strip()
        # May have multiple lines; take the last JSON line
        lines = [l for l in output_text.split("\n") if l.strip()]
        return json.loads(lines[-1]) if lines else {}

    def test_write_agents_no_pipeline_denied(self, monkeypatch):
        """Write to agents/foo.md without pipeline should be denied."""
        monkeypatch.delenv("CLAUDE_AGENT_NAME", raising=False)
        monkeypatch.setenv("PIPELINE_STATE_FILE", "/tmp/nonexistent_test_state.json")

        result = self._run_hook("Write", {"file_path": "/home/user/.claude/agents/foo.md", "content": "test"})

        decision = result["hookSpecificOutput"]["permissionDecision"]
        assert decision == "deny"
        assert "BLOCKED" in result["hookSpecificOutput"]["permissionDecisionReason"]
        assert "systemMessage" in result

    def test_edit_hooks_no_pipeline_denied(self, monkeypatch):
        """Edit to hooks/bar.py without pipeline should be denied."""
        monkeypatch.delenv("CLAUDE_AGENT_NAME", raising=False)
        monkeypatch.setenv("PIPELINE_STATE_FILE", "/tmp/nonexistent_test_state.json")

        result = self._run_hook("Edit", {
            "file_path": "/home/user/.claude/hooks/bar.py",
            "old_string": "old",
            "new_string": "new",
        })

        decision = result["hookSpecificOutput"]["permissionDecision"]
        assert decision == "deny"
        assert "BLOCKED" in result["hookSpecificOutput"]["permissionDecisionReason"]

    def test_write_agents_with_pipeline_agent_allowed(self, monkeypatch):
        """Write to agents/foo.md with implementer agent should be allowed."""
        monkeypatch.setenv("CLAUDE_AGENT_NAME", "implementer")

        result = self._run_hook("Write", {"file_path": "/home/user/.claude/agents/foo.md", "content": "test"})

        decision = result["hookSpecificOutput"]["permissionDecision"]
        assert decision == "allow"

    def test_write_agents_with_state_file_allowed(self, monkeypatch):
        """Write to agents/foo.md with valid state file should be allowed."""
        monkeypatch.delenv("CLAUDE_AGENT_NAME", raising=False)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            state = {"session_start": datetime.now().isoformat()}
            json.dump(state, f)
            f.flush()
            monkeypatch.setenv("PIPELINE_STATE_FILE", f.name)

            result = self._run_hook("Write", {"file_path": "/home/user/.claude/agents/foo.md", "content": "test"})

            decision = result["hookSpecificOutput"]["permissionDecision"]
            assert decision == "allow"
        os.unlink(f.name)

    def test_write_src_not_protected(self, monkeypatch):
        """Write to src/app.py should be allowed (not protected infra)."""
        monkeypatch.delenv("CLAUDE_AGENT_NAME", raising=False)
        monkeypatch.setenv("PIPELINE_STATE_FILE", "/tmp/nonexistent_test_state.json")

        result = self._run_hook("Write", {"file_path": "src/app.py", "content": "test"})

        decision = result["hookSpecificOutput"]["permissionDecision"]
        assert decision == "allow"

    def test_read_agents_allowed(self, monkeypatch):
        """Read from agents/foo.md should be allowed (Read not blocked)."""
        monkeypatch.delenv("CLAUDE_AGENT_NAME", raising=False)
        monkeypatch.setenv("PIPELINE_STATE_FILE", "/tmp/nonexistent_test_state.json")

        result = self._run_hook("Read", {"file_path": "/home/user/.claude/agents/foo.md"})

        decision = result["hookSpecificOutput"]["permissionDecision"]
        assert decision == "allow"


# ---------------------------------------------------------------------------
# TestOutputDecisionSystemMessage
# ---------------------------------------------------------------------------

class TestOutputDecisionSystemMessage:
    """Tests for output_decision with system_message support."""

    def test_with_system_message(self):
        captured = StringIO()
        with patch("sys.stdout", captured):
            hook.output_decision("deny", "blocked", system_message="You need /implement")

        result = json.loads(captured.getvalue())
        assert result["systemMessage"] == "You need /implement"
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_without_system_message(self):
        captured = StringIO()
        with patch("sys.stdout", captured):
            hook.output_decision("allow", "ok")

        result = json.loads(captured.getvalue())
        assert "systemMessage" not in result
        assert result["hookSpecificOutput"]["permissionDecision"] == "allow"

    def test_empty_system_message_omitted(self):
        captured = StringIO()
        with patch("sys.stdout", captured):
            hook.output_decision("allow", "ok", system_message="")

        result = json.loads(captured.getvalue())
        assert "systemMessage" not in result
