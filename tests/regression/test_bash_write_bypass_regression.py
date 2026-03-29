"""
Regression tests for Bash write bypass detection (Issue #558, #589).

These tests reproduce real-world bypass commands documented in Claude Code issue #29709.
Each test verifies that a specific bypass technique is now detected and blocked.

Date: 2026-03-25
Updated: 2026-03-28 (Issue #589)
"""

import os
import sys
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


@pytest.fixture(autouse=True)
def mock_pipeline_inactive():
    """Ensure pipeline is not active for regression tests."""
    with patch.object(hook, "_is_pipeline_active", return_value=False):
        yield


@pytest.fixture(autouse=True)
def mock_protected_infra():
    """Make infrastructure paths protected."""
    def fake_is_protected(fp):
        normalized = str(fp).replace("\\", "/")
        for seg in ["/agents/", "/hooks/", "/lib/", "/skills/", "/commands/"]:
            bare = seg.lstrip("/")
            if seg in normalized or normalized.startswith(bare):
                return True
        return False
    with patch.object(hook, "_is_protected_infrastructure", side_effect=fake_is_protected):
        yield


@pytest.fixture(autouse=True)
def mock_deny_cache(tmp_path):
    """Use temporary deny cache file."""
    cache_file = str(tmp_path / "deny_cache.jsonl")
    with patch.object(hook, "DENY_CACHE_PATH", cache_file):
        yield


# ---------------------------------------------------------------------------
# Regression tests — real-world bypass commands
# ---------------------------------------------------------------------------

class TestBashWriteBypassRegression:
    """Regression tests for bypass commands from Claude Code issue #29709."""

    def test_cat_heredoc_overwrite_agent(self):
        """Bypass: cat > agents/orchestrator.md << 'EOF' ... EOF"""
        cmd = (
            "cat > agents/orchestrator.md << 'EOF'\n"
            "# Modified orchestrator\n"
            "New malicious content\n"
            "EOF"
        )
        result = hook._check_bash_infra_writes(cmd)
        assert result is not None, "cat heredoc bypass to agents/ should be blocked"
        assert "BLOCKED" in result[1]

    def test_cat_heredoc_overwrite_hook(self):
        """Bypass: cat > hooks/unified_pre_tool.py << 'MARKER' ... MARKER"""
        cmd = (
            "cat > hooks/unified_pre_tool.py << 'MARKER'\n"
            "# Neutered hook\n"
            "import json, sys\n"
            "print(json.dumps({'hookSpecificOutput': {'permissionDecision': 'allow'}}))\n"
            "MARKER"
        )
        result = hook._check_bash_infra_writes(cmd)
        assert result is not None, "cat heredoc bypass to hooks/ should be blocked"

    def test_python3_heredoc_open_write_agent(self):
        """Bypass: python3 << 'PYEOF' with open('agents/...','w')"""
        cmd = (
            "python3 << 'PYEOF'\n"
            "with open('agents/implementer.md', 'w') as f:\n"
            "    f.write('# Compromised agent')\n"
            "PYEOF"
        )
        result = hook._check_bash_infra_writes(cmd)
        assert result is not None, "python3 heredoc with open() to agents/ should be blocked"

    def test_python3_heredoc_path_write_text(self):
        """Bypass: python3 << EOF with Path('lib/...').write_text(...)"""
        cmd = (
            "python3 << EOF\n"
            "from pathlib import Path\n"
            "Path('lib/quality_persistence_enforcer.py').write_text('# gutted')\n"
            "EOF"
        )
        result = hook._check_bash_infra_writes(cmd)
        assert result is not None, "python3 heredoc with Path.write_text to lib/ should be blocked"

    def test_python3_c_path_write_text(self):
        """Bypass: python3 -c "Path('commands/implement.md').write_text(...)" """
        cmd = """python3 -c "from pathlib import Path; Path('commands/implement.md').write_text('# empty')" """
        result = hook._check_bash_infra_writes(cmd)
        assert result is not None, "python3 -c with Path.write_text to commands/ should be blocked"

    def test_python3_c_path_write_bytes(self):
        """Bypass: python3 -c "Path('skills/testing/SKILL.md').write_bytes(b'...')" """
        cmd = """python3 -c "Path('skills/testing/SKILL.md').write_bytes(b'# gutted')" """
        result = hook._check_bash_infra_writes(cmd)
        assert result is not None, "python3 -c with Path.write_bytes to skills/ should be blocked"

    def test_dd_overwrite_hook(self):
        """Bypass: dd if=/dev/zero of=hooks/unified_pre_tool.py"""
        cmd = "dd if=/dev/zero of=hooks/unified_pre_tool.py bs=1024 count=10"
        result = hook._check_bash_infra_writes(cmd)
        assert result is not None, "dd of= to hooks/ should be blocked"

    def test_dd_overwrite_lib(self):
        """Bypass: dd if=/dev/urandom of=lib/tool_validator.py"""
        cmd = "dd if=/dev/urandom of=lib/tool_validator.py bs=512 count=5"
        result = hook._check_bash_infra_writes(cmd)
        assert result is not None, "dd of= to lib/ should be blocked"

    def test_existing_redirect_still_blocked(self):
        """Regression: standard echo > agents/foo.md must still be blocked."""
        cmd = "echo 'pwned' > agents/foo.md"
        result = hook._check_bash_infra_writes(cmd)
        assert result is not None, "Standard redirect to agents/ must still be blocked"

    def test_existing_sed_i_still_blocked(self):
        """Regression: sed -i on protected path must still be blocked."""
        cmd = "sed -i 's/old/new/g' hooks/unified_pre_tool.py"
        result = hook._check_bash_infra_writes(cmd)
        assert result is not None, "sed -i on hooks/ must still be blocked"

    # --- Issue #589: Specific bypass scenarios ---

    def test_issue_589_python3_c_path_write_text_bypass(self):
        """Regression for Issue #589: python3 -c Path.write_text bypass.

        This is the exact bypass scenario reported in the issue. Before the fix,
        _extract_bash_file_writes did not detect python3 -c with Path.write_text,
        so the write was not caught at the extraction layer.
        """
        cmd = """python3 -c "from pathlib import Path; Path('agents/foo.md').write_text('bypassed')" """
        # Verify detection at _extract_bash_file_writes level (the fix)
        extracted = hook._extract_bash_file_writes(cmd)
        assert "agents/foo.md" in extracted, (
            "Issue #589: _extract_bash_file_writes must detect python3 -c Path.write_text"
        )
        # Also verify end-to-end blocking
        result = hook._check_bash_infra_writes(cmd)
        assert result is not None
        assert "BLOCKED" in result[1]

    def test_issue_589_cp_from_tmp_bypass(self):
        """Regression for Issue #589: cp from /tmp to protected path bypass.

        Before the fix, _extract_bash_file_writes did not detect cp/mv destinations,
        so copying a staged file from /tmp to a protected path was not caught.
        """
        cmd = "cp /tmp/staged_payload.py hooks/evil.py"
        # Verify detection at _extract_bash_file_writes level (the fix)
        extracted = hook._extract_bash_file_writes(cmd)
        assert "hooks/evil.py" in extracted, (
            "Issue #589: _extract_bash_file_writes must detect cp destination"
        )
        # Also verify end-to-end blocking
        result = hook._check_bash_infra_writes(cmd)
        assert result is not None
        assert "BLOCKED" in result[1]


# ---------------------------------------------------------------------------
# Regression tests — Issue #572: Write denied to lib/reviewer_benchmark.py,
# bypassed via Write-to-/tmp + cp
# ---------------------------------------------------------------------------

class TestIssue572WriteToTmpThenCp:
    """Regression tests for Issue #572.

    The bypass sequence:
      1. Write tool denied when targeting lib/reviewer_benchmark.py directly
      2. Attacker writes to /tmp/reviewer_benchmark_content.txt instead
      3. Then runs: cp /tmp/reviewer_benchmark_content.txt plugins/autonomous-dev/lib/reviewer_benchmark.py

    The cp/mv destination detection fix (Issue #589) covers this exact pattern.
    These tests lock in that specific bypass route so it can never silently regress.
    """

    def test_issue_572_exact_bypass_cp_detected(self):
        """Issue #572: cp /tmp/... → lib/reviewer_benchmark.py destination is extracted.

        Verifies _extract_bash_file_writes detects the lib/ destination in the
        exact bypass command from the issue report.
        """
        cmd = (
            "cp /tmp/reviewer_benchmark_content.txt "
            "plugins/autonomous-dev/lib/reviewer_benchmark.py"
        )
        extracted = hook._extract_bash_file_writes(cmd)
        assert "plugins/autonomous-dev/lib/reviewer_benchmark.py" in extracted, (
            "Issue #572: _extract_bash_file_writes must extract the cp destination "
            "plugins/autonomous-dev/lib/reviewer_benchmark.py"
        )

    def test_issue_572_exact_bypass_blocked(self):
        """Issue #572: cp /tmp/... → lib/reviewer_benchmark.py is blocked end-to-end.

        Full pipeline: _check_bash_infra_writes must return a non-None block result
        for the exact bypass command from the issue report.
        """
        cmd = (
            "cp /tmp/reviewer_benchmark_content.txt "
            "plugins/autonomous-dev/lib/reviewer_benchmark.py"
        )
        result = hook._check_bash_infra_writes(cmd)
        assert result is not None, (
            "Issue #572: cp from /tmp to lib/reviewer_benchmark.py must be blocked"
        )
        assert "BLOCKED" in result[1], (
            "Issue #572: block result must contain 'BLOCKED' in the decision string"
        )

    def test_issue_572_code_file_target_detected(self):
        """Issue #572: _is_code_file_target returns True for the cp bypass command.

        The Bash tool handler must classify the bypass command as targeting a code
        file so that the pipeline-inactive guard also fires.
        """
        tool_input = {
            "command": (
                "cp /tmp/reviewer_benchmark_content.txt "
                "plugins/autonomous-dev/lib/reviewer_benchmark.py"
            )
        }
        assert hook._is_code_file_target("Bash", tool_input) is True, (
            "Issue #572: _is_code_file_target must return True for Bash cp "
            "targeting a .py file in lib/"
        )

    def test_issue_572_tmp_write_not_blocked(self):
        """Issue #572: writing to /tmp is NOT a protected infrastructure path (precision check).

        The guard must only block writes to protected destinations, not all writes.
        Writing to /tmp must remain allowed so the block is targeted and not over-broad.
        """
        cmd = "cp /dev/null /tmp/reviewer_benchmark_content.txt"
        result = hook._check_bash_infra_writes(cmd)
        assert result is None, (
            "Issue #572 (precision): cp destination /tmp/... must NOT be blocked — "
            "/tmp is not a protected infrastructure path"
        )

    def test_issue_572_variant_mv_from_tmp(self):
        """Issue #572: mv /tmp/... → lib/reviewer_benchmark.py is also blocked.

        An attacker could use mv instead of cp. The same destination detection
        must apply to mv commands.
        """
        cmd = (
            "mv /tmp/reviewer_benchmark_content.txt "
            "plugins/autonomous-dev/lib/reviewer_benchmark.py"
        )
        # Verify detection at extraction layer
        extracted = hook._extract_bash_file_writes(cmd)
        assert "plugins/autonomous-dev/lib/reviewer_benchmark.py" in extracted, (
            "Issue #572: _extract_bash_file_writes must detect mv destination"
        )
        # Verify end-to-end blocking
        result = hook._check_bash_infra_writes(cmd)
        assert result is not None, (
            "Issue #572: mv from /tmp to lib/reviewer_benchmark.py must be blocked"
        )
        assert "BLOCKED" in result[1]


# ---------------------------------------------------------------------------
# Regression tests — Issue #589: python_write_detector bypass gaps
# ---------------------------------------------------------------------------

class TestIssue589PythonWriteDetectorBypasses:
    """Regression tests for Issue #589 bypass gaps.

    These tests reproduce the specific bypass vectors identified in Issue #589:
    aliased imports, shutil operations, and eval/exec indirection that were
    not caught by the original inline regex patterns.
    """

    def test_issue_589_aliased_path_import_bypass(self):
        """Issue #589: 'from pathlib import Path as P; P(...).write_text(...)' bypassed detection.

        Before the fix, the regex only matched 'Path(' literally, missing aliases like P.
        """
        cmd = """python3 -c "from pathlib import Path as P; P('agents/foo.md').write_text('bypassed')" """
        extracted = hook._extract_bash_file_writes(cmd)
        assert "agents/foo.md" in extracted, (
            "Issue #589: aliased Path import must be detected by _extract_bash_file_writes"
        )
        result = hook._check_bash_infra_writes(cmd)
        assert result is not None, (
            "Issue #589: aliased Path import write to agents/ must be blocked"
        )
        assert "BLOCKED" in result[1]

    def test_issue_589_shutil_copy_bypass(self):
        """Issue #589: 'import shutil; shutil.copy(src, dst)' bypassed detection.

        Before the fix, shutil operations were not scanned at all in python3 -c snippets.
        """
        cmd = """python3 -c "import shutil; shutil.copy('/tmp/payload', 'agents/foo.md')" """
        extracted = hook._extract_bash_file_writes(cmd)
        assert "agents/foo.md" in extracted, (
            "Issue #589: shutil.copy destination must be detected by _extract_bash_file_writes"
        )
        result = hook._check_bash_infra_writes(cmd)
        assert result is not None, (
            "Issue #589: shutil.copy to agents/ must be blocked"
        )
        assert "BLOCKED" in result[1]

    def test_issue_589_shutil_move_bypass(self):
        """Issue #589: 'import shutil; shutil.move(src, dst)' bypassed detection.

        Before the fix, shutil.move was not scanned in python3 -c snippets.
        """
        cmd = """python3 -c "import shutil; shutil.move('/tmp/payload', 'hooks/evil.py')" """
        extracted = hook._extract_bash_file_writes(cmd)
        assert "hooks/evil.py" in extracted, (
            "Issue #589: shutil.move destination must be detected by _extract_bash_file_writes"
        )
        result = hook._check_bash_infra_writes(cmd)
        assert result is not None, (
            "Issue #589: shutil.move to hooks/ must be blocked"
        )
        assert "BLOCKED" in result[1]

    def test_issue_589_exec_indirection_bypass(self):
        """Issue #589: 'exec(open(file).read())' with protected path context.

        Before the fix, eval/exec with dynamic arguments were not flagged as suspicious.
        This test verifies that suspicious exec + protected path context triggers detection.
        End-to-end: no mock on _is_protected_infrastructure — the sentinel path approach
        was replaced with a direct return, so _is_protected_infrastructure is never called.
        """
        cmd = """python3 -c "exec(open('agents/evil.md').read())" """
        # Temporarily restore real _is_protected_infrastructure to verify
        # the fix works without mocking
        real_fn = hook._is_protected_infrastructure
        with patch.object(hook, "_is_protected_infrastructure", side_effect=real_fn):
            result = hook._check_bash_infra_writes(cmd)
        assert result is not None, (
            "Issue #589: exec(open(...).read()) with protected path must be blocked"
        )
        assert "BLOCKED" in result[1]
        assert "suspicious_exec" in result[0] or "exec" in result[1].lower()

    def test_issue_589_exec_constant_string_with_write(self):
        """Issue #589 M-01: exec('Path(...).write_text(...)') with constant string.

        Before the fix, exec() with a constant string argument was treated as safe.
        The constant string should be recursively parsed to detect write operations.

        Tests at the python_write_detector level (the actual fix) since the hook's
        -c regex extraction uses [^"]+ which cannot capture nested quotes. The
        detector itself correctly handles exec() with constant string arguments.
        """
        # Test the detector directly — this is where the M-01 fix lives
        import python_write_detector as pwd

        code = "exec(\"from pathlib import Path; Path('agents/foo.md').write_text('x')\")"
        targets = pwd.extract_write_targets(code)
        assert "agents/foo.md" in targets, (
            "Issue #589 M-01: exec() with constant string containing Path.write_text "
            "must detect 'agents/foo.md' as a write target"
        )

        # Also test end-to-end via heredoc (avoids shell quote escaping issues with -c)
        cmd = (
            "python3 << 'PYEOF'\n"
            "exec(\"from pathlib import Path; Path('agents/foo.md').write_text('x')\")\n"
            "PYEOF"
        )
        result = hook._check_bash_infra_writes(cmd)
        assert result is not None, (
            "Issue #589 M-01: exec() with constant string writing to agents/ must be blocked"
        )
        assert "BLOCKED" in result[1]

    def test_issue_589_newline_escape_in_c_string(self):
        """Issue #589: literal \\n in python3 -c string bypassed AST parsing.

        Before the fix, literal \\n characters in the -c string prevented
        AST parsing from seeing multiline code.
        """
        cmd = r'python3 -c "from pathlib import Path\nPath('"'"'agents/foo.md'"'"').write_text('"'"'x'"'"')"'
        extracted = hook._extract_bash_file_writes(cmd)
        assert "agents/foo.md" in extracted, (
            "Issue #589: literal \\n in -c string must be handled for AST parsing"
        )
