"""
Tests for agent identity hardening in unified_pre_tool.py (Issue #557).

Validates:
1. Env var spoofing detection (_detect_env_spoofing)
2. Settings.json write protection (_detect_settings_json_write)
3. HMAC verification in _is_pipeline_active and _is_explicit_implement_active

Date: 2026-03-25
"""

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

# Add hook and lib directories to path
HOOK_DIR = Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "hooks"
sys.path.insert(0, str(HOOK_DIR))

LIB_DIR = Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "lib"
sys.path.insert(0, str(LIB_DIR))

import unified_pre_tool as hook


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    env_keys = [
        "SANDBOX_ENABLED", "PRE_TOOL_MCP_SECURITY", "PRE_TOOL_AGENT_AUTH",
        "PRE_TOOL_BATCH_PERMISSION", "MCP_AUTO_APPROVE", "ENFORCEMENT_LEVEL",
        "CLAUDE_AGENT_NAME", "PIPELINE_STATE_FILE", "CLAUDE_SESSION_ID",
    ]
    for key in env_keys:
        monkeypatch.delenv(key, raising=False)


# ---------------------------------------------------------------------------
# TestEnvSpoofingDetection
# ---------------------------------------------------------------------------

class TestEnvSpoofingDetection:
    """Tests for _detect_env_spoofing() function."""

    def test_inline_prefix_blocked(self):
        """CLAUDE_AGENT_NAME=implementer python3 ... should be blocked."""
        cmd = "CLAUDE_AGENT_NAME=implementer python3 script.py"
        result = hook._detect_env_spoofing(cmd)
        assert result is not None
        assert "CLAUDE_AGENT_NAME" in result
        assert "Issue #557" in result

    def test_export_blocked(self):
        """export CLAUDE_AGENT_NAME=implementer should be blocked."""
        cmd = "export CLAUDE_AGENT_NAME=implementer"
        result = hook._detect_env_spoofing(cmd)
        assert result is not None
        assert "CLAUDE_AGENT_NAME" in result

    def test_env_command_blocked(self):
        """env CLAUDE_AGENT_NAME=implementer python3 ... should be blocked."""
        cmd = "env CLAUDE_AGENT_NAME=implementer python3 script.py"
        result = hook._detect_env_spoofing(cmd)
        assert result is not None
        assert "CLAUDE_AGENT_NAME" in result

    def test_other_protected_vars_blocked(self):
        """All PROTECTED_ENV_VARS should be caught."""
        for var in hook.PROTECTED_ENV_VARS:
            cmd = f"{var}=spoofed_value python3 test.py"
            result = hook._detect_env_spoofing(cmd)
            assert result is not None, f"{var} should be detected as spoofing"

    def test_legitimate_env_allowed(self):
        """Normal env vars like PATH, HOME should not be blocked."""
        cmd = "PATH=/usr/bin python3 test.py"
        result = hook._detect_env_spoofing(cmd)
        assert result is None

    def test_legitimate_export_allowed(self):
        """export of non-protected vars should not be blocked."""
        cmd = "export MY_CUSTOM_VAR=hello"
        result = hook._detect_env_spoofing(cmd)
        assert result is None

    def test_quoted_value_blocked(self):
        """Quoted values should still be detected."""
        cmd = 'CLAUDE_AGENT_NAME="implementer" python3 script.py'
        result = hook._detect_env_spoofing(cmd)
        assert result is not None

    def test_single_quoted_value_blocked(self):
        """Single-quoted values should still be detected."""
        cmd = "CLAUDE_AGENT_NAME='implementer' python3 script.py"
        result = hook._detect_env_spoofing(cmd)
        assert result is not None

    def test_pipeline_state_file_blocked(self):
        """PIPELINE_STATE_FILE spoofing should be detected."""
        cmd = "PIPELINE_STATE_FILE=/tmp/fake.json python3 hook.py"
        result = hook._detect_env_spoofing(cmd)
        assert result is not None
        assert "PIPELINE_STATE_FILE" in result

    def test_enforcement_level_blocked(self):
        """ENFORCEMENT_LEVEL spoofing should be detected."""
        cmd = "export ENFORCEMENT_LEVEL=off"
        result = hook._detect_env_spoofing(cmd)
        assert result is not None
        assert "ENFORCEMENT_LEVEL" in result

    def test_empty_command_allowed(self):
        """Empty command should not be blocked."""
        result = hook._detect_env_spoofing("")
        assert result is None

    def test_command_without_env_vars(self):
        """Normal commands should not be blocked."""
        cmd = "python3 -m pytest tests/ -v"
        result = hook._detect_env_spoofing(cmd)
        assert result is None

    def test_var_in_string_not_blocked(self):
        """References to var names in strings/comments should not trigger."""
        cmd = "echo 'CLAUDE_AGENT_NAME is set by the system'"
        result = hook._detect_env_spoofing(cmd)
        assert result is None


# ---------------------------------------------------------------------------
# TestSubshellEnvSpoofingDetection (F3 remediation)
# ---------------------------------------------------------------------------

class TestSubshellEnvSpoofingDetection:
    """Tests for bash -c subshell env spoofing detection (F3)."""

    def test_bash_c_with_inline_var_blocked(self):
        """bash -c 'CLAUDE_AGENT_NAME=x cmd' should be blocked."""
        cmd = "bash -c 'CLAUDE_AGENT_NAME=implementer python3 script.py'"
        result = hook._detect_env_spoofing(cmd)
        assert result is not None
        assert "Subshell" in result or "CLAUDE_AGENT_NAME" in result

    def test_sh_c_with_export_blocked(self):
        """sh -c 'export PIPELINE_STATE_FILE=...' should be blocked."""
        cmd = 'sh -c "export PIPELINE_STATE_FILE=/tmp/fake.json"'
        result = hook._detect_env_spoofing(cmd)
        assert result is not None
        assert "PIPELINE_STATE_FILE" in result

    def test_bash_c_with_env_command_blocked(self):
        """bash -c 'env ENFORCEMENT_LEVEL=off cmd' should be blocked."""
        cmd = "bash -c 'env ENFORCEMENT_LEVEL=off python3 hook.py'"
        result = hook._detect_env_spoofing(cmd)
        assert result is not None
        assert "ENFORCEMENT_LEVEL" in result

    def test_bash_c_with_safe_command_allowed(self):
        """bash -c 'echo hello' should be allowed."""
        cmd = "bash -c 'echo hello world'"
        result = hook._detect_env_spoofing(cmd)
        assert result is None

    def test_bash_c_with_unprotected_var_allowed(self):
        """bash -c 'PATH=/usr/bin cmd' should be allowed."""
        cmd = "bash -c 'PATH=/usr/bin python3 test.py'"
        result = hook._detect_env_spoofing(cmd)
        assert result is None

    def test_double_quoted_subshell_blocked(self):
        """bash -c with double quotes should also be caught."""
        cmd = 'bash -c "CLAUDE_SESSION_ID=fake python3 test.py"'
        result = hook._detect_env_spoofing(cmd)
        assert result is not None
        assert "CLAUDE_SESSION_ID" in result


# ---------------------------------------------------------------------------
# TestSettingsJsonProtection
# ---------------------------------------------------------------------------

class TestSettingsJsonProtection:
    """Tests for settings.json write protection during active pipeline."""

    def test_settings_json_redirect_detected(self):
        """Redirect to settings.json should be detected."""
        cmd = "echo '{}' > .claude/settings.json"
        result = hook._detect_settings_json_write(cmd)
        assert result is not None
        assert "settings.json" in result

    def test_settings_local_json_redirect_detected(self):
        """Redirect to settings.local.json should be detected."""
        cmd = "echo '{}' > .claude/settings.local.json"
        result = hook._detect_settings_json_write(cmd)
        assert result is not None
        assert "settings.local.json" in result

    def test_other_json_file_allowed(self):
        """Writing to other JSON files should be allowed."""
        cmd = "echo '{}' > config.json"
        result = hook._detect_settings_json_write(cmd)
        assert result is None

    def test_sed_settings_json_detected(self):
        """sed -i on settings.json should be detected."""
        cmd = "sed -i 's/old/new/' .claude/settings.json"
        result = hook._detect_settings_json_write(cmd)
        assert result is not None

    def test_normal_command_allowed(self):
        """Commands not targeting settings files should be allowed."""
        cmd = "python3 -m pytest tests/ -v"
        result = hook._detect_settings_json_write(cmd)
        assert result is None


# ---------------------------------------------------------------------------
# TestStateFileHmac
# ---------------------------------------------------------------------------

class TestStateFileHmac:
    """Tests for HMAC verification in pipeline active checks."""

    def _write_state_file(self, tmp_path, state_data):
        """Write a pipeline state file and return its path."""
        state_file = tmp_path / "pipeline_state.json"
        state_file.write_text(json.dumps(state_data))
        return str(state_file)

    def test_valid_hmac_state_accepted(self, tmp_path, monkeypatch):
        """State with valid HMAC should be accepted by _is_pipeline_active."""
        from pipeline_state import sign_state
        session_id = "test-session-123"
        state = {
            "session_start": datetime.now().isoformat(),
            "mode": "full",
            "run_id": "test-run",
            "explicitly_invoked": True,
        }
        sign_state(state, session_id)
        state_file = self._write_state_file(tmp_path, state)

        monkeypatch.setenv("PIPELINE_STATE_FILE", state_file)
        monkeypatch.setenv("CLAUDE_SESSION_ID", session_id)
        monkeypatch.delenv("CLAUDE_AGENT_NAME", raising=False)

        assert hook._is_pipeline_active() is True

    def test_tampered_hmac_state_rejected(self, tmp_path, monkeypatch):
        """State with tampered HMAC should be rejected by _is_pipeline_active."""
        from pipeline_state import sign_state
        session_id = "test-session-123"
        state = {
            "session_start": datetime.now().isoformat(),
            "mode": "full",
            "run_id": "test-run",
            "explicitly_invoked": True,
        }
        sign_state(state, session_id)
        state["explicitly_invoked"] = False  # Tamper after signing
        state_file = self._write_state_file(tmp_path, state)

        monkeypatch.setenv("PIPELINE_STATE_FILE", state_file)
        monkeypatch.setenv("CLAUDE_SESSION_ID", session_id)
        monkeypatch.delenv("CLAUDE_AGENT_NAME", raising=False)

        assert hook._is_pipeline_active() is False

    def test_missing_hmac_backward_compat(self, tmp_path, monkeypatch):
        """State without HMAC should be accepted (backward compat)."""
        state = {
            "session_start": datetime.now().isoformat(),
            "mode": "full",
            "run_id": "test-run",
            "explicitly_invoked": True,
        }
        state_file = self._write_state_file(tmp_path, state)

        monkeypatch.setenv("PIPELINE_STATE_FILE", state_file)
        monkeypatch.delenv("CLAUDE_AGENT_NAME", raising=False)

        assert hook._is_pipeline_active() is True

    def test_missing_session_id_with_hmac_verifies_via_secret(self, tmp_path, monkeypatch):
        """With secret-file HMAC, missing session_id still verifies via secret file.

        The HMAC key now comes from the per-run secret file, not from session_id.
        So even when CLAUDE_SESSION_ID is absent, verification succeeds as long
        as the secret file exists for the run_id.
        """
        from pipeline_state import sign_state
        state = {
            "session_start": datetime.now().isoformat(),
            "mode": "full",
            "run_id": "test-run-hmac-session",
            "explicitly_invoked": True,
        }
        sign_state(state, "original-session")
        state_file = self._write_state_file(tmp_path, state)

        monkeypatch.setenv("PIPELINE_STATE_FILE", state_file)
        monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
        monkeypatch.delenv("CLAUDE_AGENT_NAME", raising=False)
        # Secret file exists for the run_id, so HMAC verification succeeds
        assert hook._is_pipeline_active() is True

    def test_missing_secret_file_and_wrong_session_fails(self, tmp_path, monkeypatch):
        """Without secret file AND wrong session_id, verification fails closed."""
        from pipeline_state import sign_state, cleanup_pipeline_secret
        state = {
            "session_start": datetime.now().isoformat(),
            "mode": "full",
            "run_id": "test-run-no-secret",
            "explicitly_invoked": True,
        }
        sign_state(state, "original-session")
        # Remove the secret file to force session_id fallback
        cleanup_pipeline_secret("test-run-no-secret")
        state_file = self._write_state_file(tmp_path, state)

        monkeypatch.setenv("PIPELINE_STATE_FILE", state_file)
        monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
        monkeypatch.delenv("CLAUDE_AGENT_NAME", raising=False)
        # No secret file, fallback to session_id="unknown" != secret used for signing
        assert hook._is_pipeline_active() is False



# ---------------------------------------------------------------------------
# TestImportErrorFailClosed (F6 remediation)
# ---------------------------------------------------------------------------

class TestImportErrorFailClosed:
    """Tests that HMAC check fails closed when import fails (F6)."""

    def _write_state_file(self, tmp_path, state_data):
        state_file = tmp_path / "pipeline_state.json"
        state_file.write_text(json.dumps(state_data))
        return str(state_file)

    def test_pipeline_active_fails_closed_on_import_error(self, tmp_path, monkeypatch):
        """When HMAC is present but pipeline_state import fails, return False."""
        from pipeline_state import sign_state
        session_id = "test-session-f6"
        state = {
            "session_start": datetime.now().isoformat(),
            "mode": "full",
            "run_id": "test-run-f6",
            "explicitly_invoked": True,
        }
        sign_state(state, session_id)
        state_file = self._write_state_file(tmp_path, state)

        monkeypatch.setenv("PIPELINE_STATE_FILE", state_file)
        monkeypatch.setenv("CLAUDE_SESSION_ID", session_id)
        monkeypatch.delenv("CLAUDE_AGENT_NAME", raising=False)

        # Mock the import to fail inside the hook
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "pipeline_state":
                raise ImportError("Mocked import failure")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        # Should fail closed (return False) when HMAC present but import fails
        assert hook._is_pipeline_active() is False

    def test_explicit_implement_fails_closed_on_import_error(self, tmp_path, monkeypatch):
        """When HMAC present but import fails in explicit check, return False."""
        from pipeline_state import sign_state
        session_id = "test-session-f6b"
        state = {
            "session_start": datetime.now().isoformat(),
            "mode": "full",
            "run_id": "test-run-f6b",
            "explicitly_invoked": True,
        }
        sign_state(state, session_id)
        state_file = self._write_state_file(tmp_path, state)

        monkeypatch.setenv("PIPELINE_STATE_FILE", state_file)
        monkeypatch.setenv("CLAUDE_SESSION_ID", session_id)
        monkeypatch.delenv("CLAUDE_AGENT_NAME", raising=False)

        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "pipeline_state":
                raise ImportError("Mocked import failure")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        assert hook._is_explicit_implement_active() is False
