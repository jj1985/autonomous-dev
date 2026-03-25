"""
Regression tests for Bash write bypass detection (Issue #558).

These tests reproduce real-world bypass commands documented in Claude Code issue #29709.
Each test verifies that a specific bypass technique is now detected and blocked.

Date: 2026-03-25
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
