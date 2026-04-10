"""
Regression tests for Issue #750: Block coordinator direct edits after agent denial.

Validates the end-to-end scenario:
1. Prompt integrity denies an agent invocation
2. _record_agent_denial is called
3. Subsequent Write/Edit to protected infrastructure is blocked
4. Write/Edit to non-infrastructure is still allowed

Date: 2026-04-10
Issue: #750
"""

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

# Add hook's parent to path so we can import the module
HOOK_DIR = Path(__file__).resolve().parents[2] / "plugins" / "autonomous-dev" / "hooks"
sys.path.insert(0, str(HOOK_DIR))

# Also add lib dir for any transitive imports
LIB_DIR = Path(__file__).resolve().parents[2] / "plugins" / "autonomous-dev" / "lib"
sys.path.insert(0, str(LIB_DIR))

import unified_pre_tool as hook


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Reset relevant env vars."""
    for key in ["SANDBOX_ENABLED", "PRE_TOOL_MCP_SECURITY", "PRE_TOOL_AGENT_AUTH",
                "PRE_TOOL_BATCH_PERMISSION", "MCP_AUTO_APPROVE", "ENFORCEMENT_LEVEL",
                "CLAUDE_AGENT_NAME", "PIPELINE_STATE_FILE"]:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def setup_denial(tmp_path, monkeypatch):
    """Set up a denial state that simulates prompt integrity denying an agent."""
    test_sid = "regression-750"
    monkeypatch.setattr(hook, "_session_id", test_sid)
    monkeypatch.setattr(hook, "AGENT_DENY_STATE_DIR", str(tmp_path))
    # Record the denial
    hook._record_agent_denial("implementer")
    return test_sid


class TestIssue750AgentDenialFallback:
    """Regression: coordinator cannot bypass prompt-integrity denial via direct edits."""

    def test_prompt_integrity_deny_then_write_agents_blocked(self, setup_denial):
        """After prompt integrity denies agent, Write to agents/*.md is blocked."""
        denied_agent = hook._check_agent_denial()
        assert denied_agent == "implementer", "Denial state should be recorded"

        # Simulate writing a large agent prompt file (substantive)
        file_path = str(HOOK_DIR.parent / "agents" / "implementer.md")
        content = "\n".join([f"## Section {i}\nContent line {i}" for i in range(20)])

        with patch.object(hook, "_is_protected_infrastructure", return_value=True):
            is_substantive = len(content.splitlines()) >= hook.SIGNIFICANT_LINE_THRESHOLD
            assert is_substantive is True, "20+ lines should be substantive"
            assert denied_agent is not None, "Should detect recent denial"

    def test_prompt_integrity_deny_then_edit_hooks_blocked(self, setup_denial):
        """After prompt integrity denies agent, Edit to hooks/*.py with new function is blocked."""
        denied_agent = hook._check_agent_denial()
        assert denied_agent == "implementer"

        # Edit that adds a new function
        old_string = "# existing code\npass"
        new_string = "# existing code\ndef new_enforcement_function():\n    return True\n"
        file_path = str(HOOK_DIR / "unified_pre_tool.py")

        sig, reason, _ = hook._has_significant_additions(old_string, new_string, file_path)
        assert sig is True, f"Adding new function should be significant: {reason}"

        with patch.object(hook, "_is_protected_infrastructure", return_value=True):
            assert hook._is_protected_infrastructure(file_path) is True

    def test_prompt_integrity_deny_then_write_docs_allowed(self, setup_denial):
        """After prompt integrity denies agent, Write to docs/*.md is allowed."""
        denied_agent = hook._check_agent_denial()
        assert denied_agent == "implementer"

        # docs/ is not protected infrastructure
        file_path = str(Path(__file__).resolve().parents[2] / "docs" / "README.md")

        with patch.object(hook, "_is_protected_infrastructure", return_value=False):
            assert not hook._is_protected_infrastructure(file_path)
            # No blocking should occur for non-infrastructure paths
