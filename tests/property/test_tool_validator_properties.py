"""Property-based tests for tool_validator.py classification invariants.

Tests invariants:
- Blacklisted commands always produce approved=False
- Injection patterns always produce approved=False
- If security_risk=True then approved must be False
- Native/always-allowed tools always produce approved=True
- Unknown tools always denied
"""

from pathlib import Path

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from tool_validator import ToolValidator, ValidationResult


# ---------------------------------------------------------------------------
# Inline policy for testing (no filesystem dependency)
# ---------------------------------------------------------------------------

TEST_POLICY = {
    "version": "1.0",
    "bash": {
        "whitelist": [
            "pytest*",
            "git status",
            "git diff*",
            "git log*",
            "ls*",
            "cat*",
            "echo*",
            "pwd",
        ],
        "blacklist": [
            "rm -rf*",
            "sudo*",
            "chmod 777*",
            "curl*|*bash",
            "wget*|*bash",
            "eval*",
            "exec*",
        ],
    },
    "file_paths": {
        "whitelist": ["/tmp/pytest-*", "/tmp/tmp*"],
        "blacklist": ["/etc/*", "/var/*", "/root/*", "*/.env", "*/secrets/*"],
    },
    "agents": {
        "trusted": ["researcher", "implementer", "test-master"],
        "restricted": ["reviewer"],
    },
    "tools": {
        "always_allowed": [
            "AskUserQuestion",
            "Task",
            "TaskOutput",
            "Skill",
            "SlashCommand",
            "BashOutput",
            "NotebookEdit",
            "TodoWrite",
            "EnterPlanMode",
            "ExitPlanMode",
            "AgentOutputTool",
            "KillShell",
            "LSP",
        ],
    },
}


def _make_validator() -> ToolValidator:
    """Create a ToolValidator with the inline test policy."""
    return ToolValidator(policy=TEST_POLICY)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Blacklisted command prefixes
blacklisted_prefixes = st.sampled_from([
    "rm -rf",
    "sudo",
    "chmod 777",
    "eval",
    "exec",
])

# Suffixes to append to blacklisted commands
command_suffix = st.from_regex(r"[ /a-zA-Z0-9._-]{0,50}", fullmatch=True)

# Always-allowed tool names
always_allowed_tools = st.sampled_from(TEST_POLICY["tools"]["always_allowed"])

# Random tool names that are NOT in always_allowed and NOT Bash/Read/Write/Edit/Grep/Glob/Fetch
unknown_tool_names = st.from_regex(r"[A-Z][a-zA-Z]{3,20}", fullmatch=True).filter(
    lambda t: t not in TEST_POLICY["tools"]["always_allowed"]
    and t not in ("Bash", "Read", "Write", "Edit", "Grep", "Glob", "Fetch", "WebFetch", "WebSearch")
)


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


class TestBlacklistInvariant:
    """Blacklisted commands must always produce approved=False."""

    @given(prefix=blacklisted_prefixes, suffix=command_suffix)
    @example("rm -rf", " /")
    @example("sudo", " apt-get install")
    @example("eval", " $(malicious)")
    @settings(max_examples=200)
    def test_blacklisted_commands_denied(self, prefix: str, suffix: str) -> None:
        """Commands matching blacklist patterns are always denied."""
        command = f"{prefix}{suffix}"
        validator = _make_validator()
        result = validator.validate_bash_command(command)
        assert result.approved is False, f"Blacklisted command was approved: {command}"

    @given(prefix=blacklisted_prefixes, suffix=command_suffix)
    @settings(max_examples=200)
    def test_blacklisted_commands_are_security_risk(self, prefix: str, suffix: str) -> None:
        """Blacklisted commands are flagged as security risks."""
        command = f"{prefix}{suffix}"
        validator = _make_validator()
        result = validator.validate_bash_command(command)
        assert result.security_risk is True, f"Blacklisted command not flagged: {command}"


class TestInjectionPatternInvariant:
    """Command injection patterns must always produce approved=False."""

    @given(
        safe_prefix=st.sampled_from(["git status", "ls", "echo hello"]),
        injection=st.sampled_from([
            "; rm /tmp/x",
            "; sudo reboot",
            "; eval bad",
            "; exec bad",
            "; chmod stuff",
            "; chown stuff",
            "&& rm /tmp/x",
            "&& sudo reboot",
            "|| rm /tmp/x",
            "|| sudo reboot",
            "| bash",
            "| sh",
            "| zsh",
        ]),
    )
    @settings(max_examples=200)
    def test_injection_patterns_denied(self, safe_prefix: str, injection: str) -> None:
        """Injection patterns appended to safe commands are always denied."""
        command = f"{safe_prefix}{injection}"
        validator = _make_validator()
        result = validator.validate_bash_command(command)
        assert result.approved is False, f"Injection was approved: {command}"
        assert result.security_risk is True, f"Injection not flagged as risk: {command}"

    @given(data=st.data())
    @example(data=None)
    @settings(max_examples=200)
    def test_null_byte_injection_denied(self, data) -> None:
        """Commands with null bytes are always denied."""
        if data is None:
            command = "git status\x00; rm -rf /"
        else:
            prefix = data.draw(st.sampled_from(["ls", "cat", "echo"]))
            command = f"{prefix}\x00malicious"
        validator = _make_validator()
        result = validator.validate_bash_command(command)
        assert result.approved is False, f"Null byte injection approved: {command!r}"

    @given(data=st.data())
    @example(data=None)
    @settings(max_examples=200)
    def test_carriage_return_injection_denied(self, data) -> None:
        """Commands with carriage returns are always denied."""
        if data is None:
            command = "git log\rmalicious"
        else:
            prefix = data.draw(st.sampled_from(["ls", "cat", "echo"]))
            command = f"{prefix}\rinjected"
        validator = _make_validator()
        result = validator.validate_bash_command(command)
        assert result.approved is False, f"CR injection approved: {command!r}"


class TestSecurityRiskConsistency:
    """If security_risk=True then approved must be False (invariant)."""

    @given(
        command=st.from_regex(r"[a-zA-Z0-9 /_.-]{1,100}", fullmatch=True),
    )
    @settings(max_examples=200)
    def test_security_risk_implies_denied(self, command: str) -> None:
        """No ValidationResult should have security_risk=True AND approved=True."""
        validator = _make_validator()
        result = validator.validate_bash_command(command)
        if result.security_risk:
            assert result.approved is False, (
                f"security_risk=True but approved=True for: {command}"
            )


class TestAlwaysAllowedToolsInvariant:
    """Tools in the always_allowed list must always produce approved=True."""

    @given(tool=always_allowed_tools)
    @example("Task")
    @example("AskUserQuestion")
    @example("TodoWrite")
    @settings(max_examples=200)
    def test_always_allowed_tools_approved(self, tool: str) -> None:
        """Tools in always_allowed list are always approved."""
        validator = _make_validator()
        result = validator.validate_tool_call(tool, {}, agent_name="researcher")
        assert result.approved is True, f"Always-allowed tool denied: {tool}"
        assert result.security_risk is False


class TestUnknownToolsDenied:
    """Tools not in always_allowed and not Bash/Read/Write/etc must be denied."""

    @given(tool=unknown_tool_names)
    @example("RandomTool")
    @example("MaliciousExecutor")
    @example("SystemAccess")
    @settings(max_examples=200)
    def test_unknown_tools_denied(self, tool: str) -> None:
        """Unknown tools are denied by default (conservative posture)."""
        validator = _make_validator()
        result = validator.validate_tool_call(tool, {}, agent_name="researcher")
        assert result.approved is False, f"Unknown tool approved: {tool}"


class TestWhitelistApproval:
    """Commands matching whitelist patterns must be approved (if not blacklisted)."""

    @given(
        suffix=st.from_regex(r"[a-zA-Z0-9/_. -]{0,50}", fullmatch=True),
    )
    @settings(max_examples=200)
    def test_whitelisted_commands_approved(self, suffix: str) -> None:
        """Commands matching whitelist (and not blacklisted) are approved."""
        # 'pytest' is whitelisted via 'pytest*' pattern
        command = f"pytest{suffix}"
        validator = _make_validator()
        result = validator.validate_bash_command(command)
        # Should be approved unless it accidentally matches an injection pattern
        if not result.security_risk:
            assert result.approved is True, f"Whitelisted command denied: {command}"
