"""
Tests for Bash write bypass detection in unified_pre_tool.py (Issue #558).

Validates detection of:
- cat > file << 'EOF' (cat-before-heredoc)
- dd of=FILE
- Path.write_text/write_bytes in python3 -c
- python3 heredoc with open()/Path.write_text inside
- Deny cache recording and lookup

Date: 2026-03-25
"""

import json
import os
import sys
import tempfile
import time
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


@pytest.fixture
def deny_cache_file(tmp_path):
    """Provide a temporary deny cache file path."""
    cache_file = str(tmp_path / "deny_cache.jsonl")
    with patch.object(hook, "DENY_CACHE_PATH", cache_file):
        yield cache_file


# ---------------------------------------------------------------------------
# TestExtractBashFileWrites — new patterns
# ---------------------------------------------------------------------------

class TestExtractBashFileWrites:
    """Tests for _extract_bash_file_writes detecting new write patterns."""

    def test_cat_heredoc_redirect(self):
        """cat > file << 'EOF' should be detected."""
        cmd = "cat > agents/foo.md << 'EOF'\nsome content\nEOF"
        result = hook._extract_bash_file_writes(cmd)
        assert "agents/foo.md" in result

    def test_cat_append_heredoc_redirect(self):
        """cat >> file << EOF should be detected."""
        cmd = "cat >> hooks/test.py << EOF\nprint('hi')\nEOF"
        result = hook._extract_bash_file_writes(cmd)
        assert "hooks/test.py" in result

    def test_cat_heredoc_does_not_match_devnull(self):
        """cat > /dev/null << EOF should not be flagged."""
        cmd = "cat > /dev/null << EOF\ndata\nEOF"
        result = hook._extract_bash_file_writes(cmd)
        assert "/dev/null" not in result

    def test_dd_of_pattern(self):
        """dd if=/dev/zero of=hooks/test.py should be detected."""
        cmd = "dd if=/dev/zero of=hooks/test.py bs=1024 count=1"
        result = hook._extract_bash_file_writes(cmd)
        assert "hooks/test.py" in result

    def test_dd_of_with_different_order(self):
        """dd of=file if=/dev/urandom should be detected."""
        cmd = "dd of=lib/secret.py if=/dev/urandom bs=512"
        result = hook._extract_bash_file_writes(cmd)
        assert "lib/secret.py" in result

    def test_existing_redirect_still_works(self):
        """Standard > redirect should still be detected (regression)."""
        cmd = "echo 'hello' > agents/foo.md"
        result = hook._extract_bash_file_writes(cmd)
        assert "agents/foo.md" in result

    def test_existing_tee_still_works(self):
        """tee command should still be detected (regression)."""
        cmd = "echo 'data' | tee hooks/output.py"
        result = hook._extract_bash_file_writes(cmd)
        assert "hooks/output.py" in result

    def test_safe_cat_read_not_detected(self):
        """cat file (read, no redirect) should not produce write targets."""
        cmd = "cat agents/foo.md"
        result = hook._extract_bash_file_writes(cmd)
        assert "agents/foo.md" not in result

    def test_safe_dd_without_of(self):
        """dd without of= should not produce write targets."""
        cmd = "dd if=/dev/zero bs=1024 count=1"
        result = hook._extract_bash_file_writes(cmd)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# TestCheckBashInfraWrites — new bypass patterns
# ---------------------------------------------------------------------------

class TestCheckBashInfraWrites:
    """Tests for _check_bash_infra_writes detecting new bypass patterns."""

    @pytest.fixture(autouse=True)
    def _mock_pipeline_inactive(self):
        """Ensure pipeline is not active for these tests."""
        with patch.object(hook, "_is_pipeline_active", return_value=False):
            yield

    @pytest.fixture(autouse=True)
    def _mock_protected(self):
        """Make paths under agents/, hooks/, lib/, skills/, commands/ protected."""
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
    def _mock_deny_cache(self, deny_cache_file):
        """Use temporary deny cache."""
        pass

    def test_path_write_text_in_python_c(self):
        """python3 -c "Path('agents/foo.md').write_text('x')" should be blocked."""
        cmd = """python3 -c "from pathlib import Path; Path('agents/foo.md').write_text('hello')" """
        result = hook._check_bash_infra_writes(cmd)
        assert result is not None
        assert "foo.md" in result[0]
        assert "BLOCKED" in result[1]

    def test_path_write_bytes_in_python_c(self):
        """python3 -c "Path('hooks/h.py').write_bytes(b'x')" should be blocked."""
        cmd = """python3 -c "from pathlib import Path; Path('hooks/h.py').write_bytes(b'data')" """
        result = hook._check_bash_infra_writes(cmd)
        assert result is not None
        assert "h.py" in result[0]

    def test_python3_heredoc_with_open(self):
        """python3 << 'PYEOF' with open('agents/foo.md','w') should be blocked."""
        cmd = "python3 << 'PYEOF'\nopen('agents/foo.md','w').write('x')\nPYEOF"
        result = hook._check_bash_infra_writes(cmd)
        assert result is not None
        assert "foo.md" in result[0]
        assert "BLOCKED" in result[1]

    def test_python3_heredoc_with_path_write_text(self):
        """python3 << EOF with Path('lib/util.py').write_text should be blocked."""
        cmd = "python3 << EOF\nfrom pathlib import Path\nPath('lib/util.py').write_text('code')\nEOF"
        result = hook._check_bash_infra_writes(cmd)
        assert result is not None
        assert "util.py" in result[0]

    def test_python_heredoc_no_closing_marker(self):
        """python3 heredoc without closing marker still scans remaining text."""
        cmd = "python3 << PYEOF\nopen('agents/x.md','w').write('y')"
        result = hook._check_bash_infra_writes(cmd)
        assert result is not None
        assert "x.md" in result[0]

    def test_cat_heredoc_to_protected_path(self):
        """cat > agents/foo.md << 'EOF' should be blocked."""
        cmd = "cat > agents/foo.md << 'EOF'\nsome content\nEOF"
        result = hook._check_bash_infra_writes(cmd)
        assert result is not None
        assert "foo.md" in result[0]

    def test_dd_to_protected_path(self):
        """dd of=hooks/test.py should be blocked."""
        cmd = "dd if=/dev/zero of=hooks/test.py bs=1024 count=1"
        result = hook._check_bash_infra_writes(cmd)
        assert result is not None
        assert "test.py" in result[0]

    def test_safe_python_c_no_write(self):
        """python3 -c 'print(1)' should not be blocked."""
        cmd = "python3 -c 'print(1)'"
        result = hook._check_bash_infra_writes(cmd)
        assert result is None

    def test_safe_python_c_read_only(self):
        """python3 -c reading a file should not be blocked."""
        cmd = """python3 -c "open('agents/foo.md').read()" """
        result = hook._check_bash_infra_writes(cmd)
        assert result is None

    def test_safe_cat_read(self):
        """cat agents/foo.md (read only) should not be blocked."""
        cmd = "cat agents/foo.md"
        result = hook._check_bash_infra_writes(cmd)
        assert result is None

    def test_safe_echo_to_unprotected_path(self):
        """echo > /tmp/foo.txt should not be blocked."""
        cmd = "echo 'data' > /tmp/foo.txt"
        result = hook._check_bash_infra_writes(cmd)
        assert result is None

    def test_path_write_to_unprotected_path(self):
        """Path.write_text to a non-infrastructure path should not be blocked."""
        cmd = """python3 -c "from pathlib import Path; Path('/tmp/safe.txt').write_text('ok')" """
        result = hook._check_bash_infra_writes(cmd)
        assert result is None


# ---------------------------------------------------------------------------
# TestDenyCache
# ---------------------------------------------------------------------------

class TestDenyCache:
    """Tests for deny cache recording and lookup."""

    def test_update_and_check_deny_cache(self, deny_cache_file):
        """Recording a deny should be detectable within the window."""
        hook._update_deny_cache("agents/foo.md")
        result = hook._check_deny_cache("agents/foo.md", window_seconds=60)
        assert result is True

    def test_deny_cache_different_path_not_found(self, deny_cache_file):
        """A different path should not match."""
        hook._update_deny_cache("agents/foo.md")
        result = hook._check_deny_cache("hooks/bar.py", window_seconds=60)
        assert result is False

    def test_deny_cache_expired_entry(self, deny_cache_file):
        """An expired entry should not match."""
        # Write an entry with a timestamp 120 seconds ago
        old_entry = {"path": "agents/old.md", "timestamp": time.time() - 120}
        with open(deny_cache_file, "a") as f:
            f.write(json.dumps(old_entry) + "\n")
        result = hook._check_deny_cache("agents/old.md", window_seconds=60)
        assert result is False

    def test_deny_cache_missing_file(self, deny_cache_file):
        """Missing cache file should return False, not raise."""
        # deny_cache_file doesn't exist yet (tmp_path, no writes)
        result = hook._check_deny_cache("agents/any.md", window_seconds=60)
        assert result is False

    def test_deny_cache_repeated_attempt_escalation(self, deny_cache_file):
        """Repeated block should include 'repeated attempt' in message."""
        with patch.object(hook, "_is_pipeline_active", return_value=False):
            def fake_is_protected(fp):
                normalized = str(fp).replace("\\", "/")
                for seg in ["/agents/", "/hooks/", "/lib/", "/skills/", "/commands/"]:
                    bare = seg.lstrip("/")
                    if seg in normalized or normalized.startswith(bare):
                        return True
                return False
            with patch.object(hook, "_is_protected_infrastructure", side_effect=fake_is_protected):
                # First attempt — normal block
                cmd = "cat > agents/foo.md << 'EOF'\ncontent\nEOF"
                result1 = hook._check_bash_infra_writes(cmd)
                assert result1 is not None
                assert "repeated" not in result1[1].lower()

                # Second attempt — should escalate
                result2 = hook._check_bash_infra_writes(cmd)
                assert result2 is not None
                assert "repeated attempt" in result2[1].lower()


# ---------------------------------------------------------------------------
# Regression Tests — BLOCKING findings
# ---------------------------------------------------------------------------

class TestRegressionMultiSnippetPythonC:
    """Regression: stale match variable in _check_bash_infra_writes.

    Bug: 'snippet = match.group(1)' overwrote the loop variable, so multi-snippet
    commands only scanned the LAST snippet. The first (malicious) snippet was skipped.
    Fix: Removed the stale assignment so the loop variable is used directly.
    """

    @pytest.fixture(autouse=True)
    def _mock_pipeline_inactive(self):
        with patch.object(hook, "_is_pipeline_active", return_value=False):
            yield

    @pytest.fixture(autouse=True)
    def _mock_protected(self):
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
    def _mock_deny_cache(self, deny_cache_file):
        pass

    def test_multi_snippet_first_blocked(self):
        """python3 -c with protected write + python3 -c print must block (not return None).

        Before the fix, the second snippet's match.group(1) overwrote the loop variable,
        so the first snippet (with the write) was never scanned.
        """
        cmd = """python3 -c "Path('agents/foo.md').write_text('x')" && python3 -c "print(1)" """
        result = hook._check_bash_infra_writes(cmd)
        assert result is not None, (
            "Multi-snippet python3 -c command should block when first snippet writes to protected path"
        )
        assert "foo.md" in result[0]
        assert "BLOCKED" in result[1]

    def test_multi_snippet_second_blocked(self):
        """Ensure the second snippet is also scanned."""
        cmd = """python3 -c "print(1)" && python3 -c "Path('hooks/evil.py').write_text('x')" """
        result = hook._check_bash_infra_writes(cmd)
        assert result is not None
        assert "evil.py" in result[0]


class TestRegressionHeredocMarkerCollision:
    """Regression: heredoc marker collision causes premature body truncation.

    Bug: remaining.find(marker) would match the marker as a substring inside
    a variable like 'PYEOF_not_end', truncating the heredoc body prematurely
    and missing the actual write.
    Fix: Use line-start-aware regex search instead of str.find().
    """

    @pytest.fixture(autouse=True)
    def _mock_pipeline_inactive(self):
        with patch.object(hook, "_is_pipeline_active", return_value=False):
            yield

    @pytest.fixture(autouse=True)
    def _mock_protected(self):
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
    def _mock_deny_cache(self, deny_cache_file):
        pass

    def test_heredoc_marker_substring_not_truncated(self):
        """Heredoc with marker substring in body must still detect the write.

        python3 << PYEOF
        x = 'PYEOF_not_end'
        open('agents/evil.md','w').write('x')
        PYEOF

        Before the fix, remaining.find('PYEOF') matched 'PYEOF_not_end' on line 1,
        truncating the body before the open() call.
        """
        cmd = "python3 << PYEOF\nx = 'PYEOF_not_end'\nopen('agents/evil.md','w').write('x')\nPYEOF"
        result = hook._check_bash_infra_writes(cmd)
        assert result is not None, (
            "Heredoc with marker-like substring in body should still detect protected writes"
        )
        assert "evil.md" in result[0]
        assert "BLOCKED" in result[1]


class TestRegressionDenyCachePruning:
    """Regression: unbounded deny cache growth (M1).

    Fix: _update_deny_cache now prunes stale entries (>300s) every 10th write,
    capped at 500 lines.
    """

    def test_deny_cache_pruning_removes_stale(self, deny_cache_file):
        """Old entries beyond 300s should be pruned on 10th write."""
        import time as _time
        # Write 9 stale entries (>300s old)
        for i in range(9):
            old_entry = {"path": f"agents/old{i}.md", "timestamp": _time.time() - 400}
            with open(deny_cache_file, "a") as f:
                f.write(json.dumps(old_entry) + "\n")
        # 10th write triggers pruning
        hook._update_deny_cache("agents/new.md")

        # Read cache — stale entries should be gone, only the fresh one remains
        with open(deny_cache_file) as f:
            lines = [l.strip() for l in f if l.strip()]
        assert len(lines) <= 2, f"Expected stale entries pruned, got {len(lines)} lines"
        # The fresh entry must survive
        paths = [json.loads(l)["path"] for l in lines]
        assert "agents/new.md" in paths

    def test_deny_cache_cap_at_500(self, deny_cache_file):
        """Cache should be capped at 500 lines after pruning."""
        import time as _time
        # Write 510 recent entries
        now = _time.time()
        with open(deny_cache_file, "w") as f:
            for i in range(510):
                entry = {"path": f"agents/file{i}.md", "timestamp": now}
                f.write(json.dumps(entry) + "\n")
        # Trigger pruning (510 lines, 510 % 10 == 0)
        hook._update_deny_cache("agents/trigger.md")

        with open(deny_cache_file) as f:
            lines = [l.strip() for l in f if l.strip()]
        assert len(lines) <= 500, f"Cache should be capped at 500, got {len(lines)}"
