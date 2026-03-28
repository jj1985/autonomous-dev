#!/usr/bin/env python3
"""
Unit tests for unified_pre_tool.py hook.

Tests layer dispatch logic, error handling, JSON output format,
and environment variable controls (DISABLE_* flags).

Date: 2026-02-21
Agent: test-master
"""

import json
import os
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
from io import StringIO

# Add hooks directory to path
sys.path.insert(
    0,
    str(
        Path(__file__).parent.parent.parent.parent
        / "plugins"
        / "autonomous-dev"
        / "hooks"
    ),
)

import unified_pre_tool as upt


class TestCombineDecisions:
    """Test the combine_decisions logic."""

    def test_all_allow(self):
        results = [
            ("Sandbox", "allow", "ok"),
            ("MCP", "allow", "ok"),
            ("Agent", "allow", "ok"),
        ]
        decision, reason = upt.combine_decisions(results)
        assert decision == "allow"

    def test_any_deny(self):
        results = [
            ("Sandbox", "allow", "ok"),
            ("MCP", "deny", "blocked"),
            ("Agent", "allow", "ok"),
        ]
        decision, reason = upt.combine_decisions(results)
        assert decision == "deny"
        assert "blocked" in reason

    def test_multiple_deny(self):
        results = [
            ("Sandbox", "deny", "bad sandbox"),
            ("MCP", "deny", "bad mcp"),
        ]
        decision, reason = upt.combine_decisions(results)
        assert decision == "deny"
        assert "bad sandbox" in reason
        assert "bad mcp" in reason

    def test_ask_when_mixed(self):
        results = [
            ("Sandbox", "allow", "ok"),
            ("MCP", "ask", "needs approval"),
        ]
        decision, reason = upt.combine_decisions(results)
        assert decision == "ask"
        assert "needs approval" in reason

    def test_empty_results(self):
        decision, reason = upt.combine_decisions([])
        assert decision == "allow"

    def test_deny_trumps_ask(self):
        results = [
            ("A", "ask", "maybe"),
            ("B", "deny", "no"),
        ]
        decision, reason = upt.combine_decisions(results)
        assert decision == "deny"


class TestValidateSandboxLayer:
    """Test sandbox layer validation."""

    def test_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SANDBOX_ENABLED", None)
            decision, reason = upt.validate_sandbox_layer("Bash", {"command": "ls"})
            assert decision == "allow"
            assert "disabled" in reason.lower()

    def test_non_bash_tool(self):
        with patch.dict(os.environ, {"SANDBOX_ENABLED": "true"}):
            decision, reason = upt.validate_sandbox_layer("Read", {"file_path": "/tmp/x"})
            assert decision == "allow"

    def test_empty_command(self):
        with patch.dict(os.environ, {"SANDBOX_ENABLED": "true"}):
            decision, reason = upt.validate_sandbox_layer("Bash", {"command": ""})
            assert decision == "allow"

    def test_import_error_fallback(self):
        with patch.dict(os.environ, {"SANDBOX_ENABLED": "true"}):
            with patch.dict("sys.modules", {"sandbox_enforcer": None}):
                decision, reason = upt.validate_sandbox_layer("Bash", {"command": "rm -rf /"})
                # When sandbox_enforcer can't be imported, returns ask
                assert decision in ("ask", "deny")  # deny if enforcer is available, ask if not


class TestValidateMcpSecurity:
    """Test MCP security layer."""

    def test_native_tool_bypass(self):
        for tool in ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "Task"]:
            decision, reason = upt.validate_mcp_security(tool, {})
            assert decision == "allow"
            assert "Native tool" in reason

    def test_disabled_via_env(self):
        with patch.dict(os.environ, {"PRE_TOOL_MCP_SECURITY": "false"}):
            decision, reason = upt.validate_mcp_security("mcp_custom_tool", {})
            assert decision == "allow"
            assert "disabled" in reason.lower()

    def test_unknown_mcp_tool_no_auto_approve(self):
        # Issue #401 refactored MCP security to default-allow when mcp_security_validator
        # is not importable (which is the case in tests). MCP_AUTO_APPROVE=false no longer
        # causes "ask" — the validator returns "allow" to avoid blocking users when the
        # optional security module is absent. Assertion changed from "ask" -> "allow".
        with patch.dict(os.environ, {"PRE_TOOL_MCP_SECURITY": "true", "MCP_AUTO_APPROVE": "false"}):
            decision, reason = upt.validate_mcp_security("mcp_custom_tool", {})
            assert decision == "allow"

    def test_unknown_mcp_tool_auto_approve_no_engine(self):
        with patch.dict(os.environ, {"PRE_TOOL_MCP_SECURITY": "true", "MCP_AUTO_APPROVE": "true"}):
            # auto_approval_engine may or may not be importable
            decision, reason = upt.validate_mcp_security("mcp_custom_tool", {})
            # If engine available: allow/ask depending on policy; if not: allow pass through
            assert decision in ("allow", "ask")

    def test_all_native_tools_listed(self):
        """Verify known native tools are in the set."""
        expected = {"Read", "Write", "Edit", "Glob", "Grep", "Bash", "Task", "TaskOutput"}
        assert expected.issubset(upt.NATIVE_TOOLS)


class TestValidateAgentAuthorization:
    """Test agent authorization layer."""

    def setup_method(self):
        """Reset module state to avoid cross-test contamination."""
        upt._agent_type = ""

    def teardown_method(self):
        """Clean up module state."""
        upt._agent_type = ""

    def test_disabled_via_env(self):
        with patch.dict(os.environ, {"PRE_TOOL_AGENT_AUTH": "false"}):
            decision, reason = upt.validate_agent_authorization("Edit", {"file_path": "app.py"})
            assert decision == "allow"

    def test_pipeline_agent_allowed(self):
        with patch.dict(os.environ, {"PRE_TOOL_AGENT_AUTH": "true", "CLAUDE_AGENT_NAME": "implementer"}):
            decision, reason = upt.validate_agent_authorization("Edit", {"file_path": "app.py"})
            assert decision == "allow"
            assert "Pipeline agent" in reason

    def test_non_code_tool_allowed(self):
        with patch.dict(os.environ, {"PRE_TOOL_AGENT_AUTH": "true", "CLAUDE_AGENT_NAME": ""}, clear=False):
            os.environ.pop("PIPELINE_STATE_FILE", None)
            decision, reason = upt.validate_agent_authorization("Read", {"file_path": "app.py"})
            assert decision == "allow"

    def test_exempt_path_allowed(self):
        with patch.dict(os.environ, {"PRE_TOOL_AGENT_AUTH": "true", "CLAUDE_AGENT_NAME": "", "ENFORCEMENT_LEVEL": "block"}, clear=False):
            os.environ.pop("PIPELINE_STATE_FILE", None)
            decision, reason = upt.validate_agent_authorization(
                "Edit", {"file_path": "tests/test_foo.py", "old_string": "a", "new_string": "b"}
            )
            assert decision == "allow"

    def test_enforcement_off(self):
        with patch.dict(os.environ, {"PRE_TOOL_AGENT_AUTH": "true", "CLAUDE_AGENT_NAME": "", "ENFORCEMENT_LEVEL": "off"}, clear=False):
            os.environ.pop("PIPELINE_STATE_FILE", None)
            decision, reason = upt.validate_agent_authorization("Edit", {"file_path": "app.py"})
            assert decision == "allow"

    def test_non_code_extension_allowed(self):
        with patch.dict(os.environ, {"PRE_TOOL_AGENT_AUTH": "true", "CLAUDE_AGENT_NAME": "", "ENFORCEMENT_LEVEL": "block"}, clear=False):
            os.environ.pop("PIPELINE_STATE_FILE", None)
            decision, reason = upt.validate_agent_authorization(
                "Edit", {"file_path": "config.json", "old_string": "a", "new_string": "b"}
            )
            assert decision == "allow"

    def test_block_significant_edit(self):
        with patch.dict(os.environ, {"PRE_TOOL_AGENT_AUTH": "true", "CLAUDE_AGENT_NAME": "", "ENFORCEMENT_LEVEL": "block", "PIPELINE_STATE_FILE": "/nonexistent/state.json"}, clear=False):
            new_code = "def foo():\n    pass\ndef bar():\n    pass\ndef baz():\n    x=1\n    y=2\n    z=3\n"
            decision, reason = upt.validate_agent_authorization(
                "Edit", {"file_path": "app.py", "old_string": "", "new_string": new_code}
            )
            assert decision == "deny"

    def test_suggest_level(self):
        with patch.dict(os.environ, {"PRE_TOOL_AGENT_AUTH": "true", "CLAUDE_AGENT_NAME": "", "ENFORCEMENT_LEVEL": "suggest", "PIPELINE_STATE_FILE": "/nonexistent/state.json"}, clear=False):
            new_code = "def foo():\n    pass\ndef bar():\n    pass\ndef baz():\n    x=1\n    y=2\n    z=3\n"
            decision, reason = upt.validate_agent_authorization(
                "Edit", {"file_path": "app.py", "old_string": "", "new_string": new_code}
            )
            assert decision == "ask"
            assert "/implement" in reason

    def test_minor_edit_allowed(self):
        with patch.dict(os.environ, {"PRE_TOOL_AGENT_AUTH": "true", "CLAUDE_AGENT_NAME": "", "ENFORCEMENT_LEVEL": "block"}, clear=False):
            os.environ.pop("PIPELINE_STATE_FILE", None)
            decision, reason = upt.validate_agent_authorization(
                "Edit", {"file_path": "app.py", "old_string": "x = 1", "new_string": "x = 2"}
            )
            assert decision == "allow"

    @pytest.mark.parametrize("file_path", [
        "tests/test_foo.py",
        "docs/README.md",
        "CHANGELOG.md",
        ".claude/config/policy.json",
    ])
    def test_exempt_path_coverage(self, file_path: str):
        """Regression: _is_exempt_path must recognise test files, docs, and configs.

        Covers multiple exempt path patterns to ensure the function is robust
        against future refactoring. Each path should be allowed without entering
        significance analysis.
        """
        with patch.dict(
            os.environ,
            {
                "PRE_TOOL_AGENT_AUTH": "true",
                "CLAUDE_AGENT_NAME": "",
                "ENFORCEMENT_LEVEL": "block",
            },
            clear=False,
        ):
            os.environ.pop("PIPELINE_STATE_FILE", None)
            decision, reason = upt.validate_agent_authorization(
                "Edit",
                {"file_path": file_path, "old_string": "a", "new_string": "b"},
            )
            assert decision == "allow", (
                f"Expected 'allow' for exempt path '{file_path}', got '{decision}': {reason}"
            )

    @pytest.mark.parametrize("old_str,new_str", [
        ("version = '1.0.0'", "version = '1.0.1'"),  # single-line value change
        ("# TODO: fix this", "# Fixed: resolved the issue"),  # comment change
        ("import os", "import os  # noqa: F401"),  # import annotation change
    ])
    def test_minor_edit_various_patterns(self, old_str: str, new_str: str):
        """Regression: _has_significant_additions must treat small single-line edits as minor.

        Covers common minor-edit patterns to prevent false positives in enforcement.
        None of these should trigger significance detection.
        """
        with patch.dict(
            os.environ,
            {
                "PRE_TOOL_AGENT_AUTH": "true",
                "CLAUDE_AGENT_NAME": "",
                "ENFORCEMENT_LEVEL": "block",
            },
            clear=False,
        ):
            os.environ.pop("PIPELINE_STATE_FILE", None)
            decision, reason = upt.validate_agent_authorization(
                "Edit",
                {"file_path": "app.py", "old_string": old_str, "new_string": new_str},
            )
            assert decision == "allow", (
                f"Expected 'allow' for minor edit ({old_str!r} -> {new_str!r}), "
                f"got '{decision}': {reason}"
            )


class TestValidateBatchPermission:
    """Test batch permission layer."""

    def test_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PRE_TOOL_BATCH_PERMISSION", None)
            decision, reason = upt.validate_batch_permission("Edit", {})
            assert decision == "allow"
            assert "disabled" in reason.lower()

    def test_enabled_no_classifier(self):
        with patch.dict(os.environ, {"PRE_TOOL_BATCH_PERMISSION": "true"}):
            decision, reason = upt.validate_batch_permission("Edit", {})
            # If classifier available: returns based on classification; if not: allow
            assert decision in ("allow", "ask")


class TestOutputDecision:
    """Test JSON output format."""

    def test_output_format(self, capsys):
        upt.output_decision("allow", "test reason")
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
        assert output["hookSpecificOutput"]["permissionDecision"] == "allow"
        assert output["hookSpecificOutput"]["permissionDecisionReason"] == "test reason"

    def test_deny_format(self, capsys):
        upt.output_decision("deny", "blocked")
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_ask_format(self, capsys):
        upt.output_decision("ask", "needs input")
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["hookSpecificOutput"]["permissionDecision"] == "ask"


class TestHelperFunctions:
    """Test internal helper functions."""

    def test_is_exempt_path_test_file(self):
        assert upt._is_exempt_path("tests/test_foo.py") is True
        assert upt._is_exempt_path("test_foo.py") is True

    def test_is_exempt_path_docs(self):
        assert upt._is_exempt_path("README.md") is True
        assert upt._is_exempt_path("config.json") is True

    def test_is_exempt_path_code_file(self):
        assert upt._is_exempt_path("src/app.py") is False

    def test_is_exempt_path_empty(self):
        assert upt._is_exempt_path("") is False

    def test_is_exempt_path_hooks(self):
        assert upt._is_exempt_path(".claude/hooks/my_hook.py") is True

    def test_has_significant_additions_function(self):
        is_sig, reason, details = upt._has_significant_additions(
            "", "def new_func():\n    pass\n", "app.py"
        )
        assert is_sig is True
        assert "function" in reason.lower()

    def test_has_significant_additions_minor(self):
        is_sig, reason, details = upt._has_significant_additions(
            "x = 1", "x = 2", "app.py"
        )
        assert is_sig is False

    def test_has_significant_additions_lines(self):
        old = "line1\n"
        new = "line1\nline2\nline3\nline4\nline5\nline6\n"
        is_sig, reason, details = upt._has_significant_additions(old, new, "app.py")
        assert is_sig is True
        assert "lines" in details

    def test_extract_bash_file_writes_redirect(self):
        files = upt._extract_bash_file_writes("echo hello > output.py")
        assert "output.py" in files

    def test_extract_bash_file_writes_tee(self):
        files = upt._extract_bash_file_writes("echo hello | tee output.py")
        assert "output.py" in files

    def test_extract_bash_file_writes_dev_null(self):
        files = upt._extract_bash_file_writes("cmd > /dev/null")
        assert len(files) == 0

    def test_extract_bash_file_writes_no_writes(self):
        files = upt._extract_bash_file_writes("ls -la")
        assert len(files) == 0

    def test_is_protected_infrastructure_excludes_test_files(self):
        """Regression: test files under tests/unit/hooks/ must NOT be protected.

        Bug: _is_protected_infrastructure matched '/hooks/' anywhere in the path,
        so 'tests/unit/hooks/test_unified_pre_tool.py' was incorrectly blocked.
        Fix: test files (paths containing /tests/ or /test/) are excluded before
        the segment loop runs.
        """
        # These are absolute paths so _is_autonomous_dev_repo is irrelevant — we
        # test the segment-match exclusion logic directly via a relative-style path
        # that wouldn't resolve to a real repo root, which means the function returns
        # False early (not an autonomous-dev repo). The important assertion is that
        # a test file in a hooks subdir is NOT flagged even when the repo check passes.
        #
        # Patch _is_autonomous_dev_repo to return True so we can exercise the
        # exclusion logic that comes after it.
        with patch.object(upt, "_is_autonomous_dev_repo", return_value=True):
            # A test file under tests/unit/hooks/ — must NOT be protected
            assert upt._is_protected_infrastructure("tests/unit/hooks/test_unified_pre_tool.py") is False
            # A real hook file — must still be protected
            assert upt._is_protected_infrastructure("plugins/autonomous-dev/hooks/unified_pre_tool.py") is True
            # A test file that starts with test_ under hooks/ — must NOT be protected
            assert upt._is_protected_infrastructure("tests/unit/hooks/test_foo.py") is False


class TestLoadEnv:
    """Test .env loading."""

    def test_load_env_no_file(self, tmp_path):
        with patch("os.getcwd", return_value=str(tmp_path)):
            upt.load_env()  # Should not raise

    def test_load_env_with_file(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_VAR_UNIQUE_12345=hello\n")
        with patch("os.getcwd", return_value=str(tmp_path)):
            os.environ.pop("TEST_VAR_UNIQUE_12345", None)
            upt.load_env()
            assert os.environ.get("TEST_VAR_UNIQUE_12345") == "hello"
            del os.environ["TEST_VAR_UNIQUE_12345"]

    def test_load_env_skips_comments(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("# comment\nKEY_UNIQUE_99=val\n")
        with patch("os.getcwd", return_value=str(tmp_path)):
            os.environ.pop("KEY_UNIQUE_99", None)
            upt.load_env()
            assert os.environ.get("KEY_UNIQUE_99") == "val"
            del os.environ["KEY_UNIQUE_99"]

    def test_load_env_does_not_override(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("PATH=/bad\n")
        with patch("os.getcwd", return_value=str(tmp_path)):
            original_path = os.environ["PATH"]
            upt.load_env()
            assert os.environ["PATH"] == original_path


class TestMain:
    """Test main entry point."""

    def test_invalid_json_input(self, capsys):
        with patch("sys.stdin", StringIO("not json")):
            with pytest.raises(SystemExit) as exc_info:
                upt.main()
            assert exc_info.value.code == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["hookSpecificOutput"]["permissionDecision"] == "ask"
        assert "Invalid input JSON" in output["hookSpecificOutput"]["permissionDecisionReason"]

    def test_empty_tool_name(self, capsys):
        with patch("sys.stdin", StringIO(json.dumps({"tool_name": "", "tool_input": {}}))):
            with pytest.raises(SystemExit) as exc_info:
                upt.main()
            assert exc_info.value.code == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["hookSpecificOutput"]["permissionDecision"] == "ask"

    def test_valid_native_tool(self, capsys):
        inp = json.dumps({"tool_name": "Read", "tool_input": {"file_path": "/tmp/x"}})
        with patch("sys.stdin", StringIO(inp)):
            with patch.dict(os.environ, {"PRE_TOOL_AGENT_AUTH": "true", "CLAUDE_AGENT_NAME": ""}, clear=False):
                with pytest.raises(SystemExit) as exc_info:
                    upt.main()
                assert exc_info.value.code == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["hookSpecificOutput"]["permissionDecision"] == "allow"


class TestGetActiveAgentName:
    """Test _get_active_agent_name() helper (Issue #591).

    Verifies that agent_type from hook stdin JSON is preferred over
    CLAUDE_AGENT_NAME env var, which may be absent in subprocess contexts.
    """

    def setup_method(self):
        """Reset module-level _agent_type before each test."""
        upt._agent_type = ""

    def teardown_method(self):
        """Clean up module-level _agent_type after each test."""
        upt._agent_type = ""

    def test_agent_type_from_stdin_preferred(self):
        """stdin agent_type takes priority over env var."""
        upt._agent_type = "implementer"
        with patch.dict(os.environ, {"CLAUDE_AGENT_NAME": "coordinator"}, clear=False):
            result = upt._get_active_agent_name()
        assert result == "implementer"

    def test_env_var_fallback_when_no_stdin(self):
        """Falls back to CLAUDE_AGENT_NAME when stdin agent_type is empty."""
        upt._agent_type = ""
        with patch.dict(os.environ, {"CLAUDE_AGENT_NAME": "test-master"}, clear=False):
            result = upt._get_active_agent_name()
        assert result == "test-master"

    def test_empty_when_neither_available(self):
        """Returns empty string when both sources are absent."""
        upt._agent_type = ""
        with patch.dict(os.environ, {"CLAUDE_AGENT_NAME": ""}, clear=False):
            result = upt._get_active_agent_name()
        assert result == ""

    def test_agent_type_normalized(self):
        """agent_type is stripped and lowercased."""
        upt._agent_type = "  Test-Master  "
        result = upt._get_active_agent_name()
        assert result == "test-master"


class TestStdinAgentTypeIntegration:
    """Integration tests for stdin agent_type propagation (Issue #591).

    Verifies that the agent_type from hook stdin JSON correctly flows
    through to pipeline detection, agent authorization, and coordinator
    blocking logic.
    """

    def setup_method(self):
        """Reset module-level _agent_type before each test."""
        upt._agent_type = ""

    def teardown_method(self):
        """Clean up module-level _agent_type after each test."""
        upt._agent_type = ""

    def test_pipeline_active_via_stdin_agent_type(self):
        """Pipeline detected as active when stdin agent_type is a pipeline agent."""
        upt._agent_type = "test-master"
        with patch.dict(os.environ, {"CLAUDE_AGENT_NAME": ""}, clear=False):
            os.environ.pop("PIPELINE_STATE_FILE", None)
            result = upt._is_pipeline_active()
        assert result is True

    def test_validate_agent_auth_allows_stdin_agent(self):
        """Agent authorization allows writes when stdin identifies a pipeline agent."""
        upt._agent_type = "implementer"
        with patch.dict(
            os.environ,
            {"PRE_TOOL_AGENT_AUTH": "true", "CLAUDE_AGENT_NAME": ""},
            clear=False,
        ):
            decision, reason = upt.validate_agent_authorization(
                "Write", {"file_path": "lib/foo.py", "content": "code"}
            )
        assert decision == "allow"
        assert "implementer" in reason.lower()

    def test_coordinator_block_still_works_without_agent(self):
        """Coordinator writes are still blocked when no agent identity is available."""
        upt._agent_type = ""
        with patch.dict(
            os.environ,
            {
                "PRE_TOOL_AGENT_AUTH": "true",
                "CLAUDE_AGENT_NAME": "",
                "ENFORCEMENT_LEVEL": "block",
                "PIPELINE_STATE_FILE": "/nonexistent/state.json",
            },
            clear=False,
        ):
            new_code = "def foo():\n    pass\ndef bar():\n    pass\ndef baz():\n    x=1\n    y=2\n    z=3\n"
            decision, reason = upt.validate_agent_authorization(
                "Edit", {"file_path": "app.py", "old_string": "", "new_string": new_code}
            )
        assert decision == "deny"

    def test_native_fast_path_recognizes_stdin_agent(self, capsys):
        """Native tool fast path uses stdin agent_type to avoid coordinator block."""
        upt._agent_type = "implementer"
        inp = json.dumps({
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/test.py", "content": "x = 1"},
            "agent_type": "implementer",
        })
        with patch("sys.stdin", StringIO(inp)):
            with patch.dict(
                os.environ,
                {"CLAUDE_AGENT_NAME": "", "ENFORCEMENT_LEVEL": "block"},
                clear=False,
            ):
                with pytest.raises(SystemExit) as exc_info:
                    upt.main()
                assert exc_info.value.code == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        # implementer is a pipeline agent — should NOT be blocked by coordinator check
        assert output["hookSpecificOutput"]["permissionDecision"] == "allow"
