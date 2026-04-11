"""Spec-validation tests for Issue #768: Python -c settings.json write bypass.

Spec: The hook blocks Edit/Write to settings.json during pipeline, but python3 -c
commands that modify settings.json via json.dump/open were not detected. Extended
_detect_settings_json_write() to catch Python inline write patterns.

Acceptance criteria:
1. Python -c commands writing to settings.json are detected and blocked
2. Read-only Python commands referencing settings.json are NOT blocked
3. Regular (non-settings) Python commands are NOT blocked
4. Existing shell-based detection still works
"""

import importlib
import sys
from pathlib import Path

# Import the hook module to access _detect_settings_json_write
_project_root = Path(__file__).resolve().parents[2]
_hook_dir = _project_root / "plugins" / "autonomous-dev" / "hooks"
sys.path.insert(0, str(_hook_dir))
hook = importlib.import_module("unified_pre_tool")

detect = hook._detect_settings_json_write


# ---------------------------------------------------------------------------
# Criterion 1: Python -c commands writing to settings.json are blocked
# ---------------------------------------------------------------------------


class TestSpec768PythonWriteBlocked:
    """Python -c commands that write to settings.json MUST be blocked."""

    def test_spec_python_settings_bypass_1a_json_dump_double_quotes(self):
        """json.dump writing to settings.json via double-quoted python -c is blocked."""
        cmd = 'python3 -c "import json; json.dump({}, open(\'settings.json\', \'w\'))"'
        result = detect(cmd)
        assert result is not None, "Expected block for json.dump to settings.json"
        assert "BLOCKED" in result

    def test_spec_python_settings_bypass_1b_json_dump_single_quotes(self):
        """json.dump writing to settings.json via single-quoted python -c is blocked."""
        cmd = "python3 -c 'import json; json.dump({}, open(\"settings.json\", \"w\"))'"
        result = detect(cmd)
        assert result is not None, "Expected block for single-quoted python -c"
        assert "BLOCKED" in result

    def test_spec_python_settings_bypass_1c_write_text(self):
        """Path.write_text targeting settings.json is blocked."""
        cmd = """python3 -c "from pathlib import Path; Path('settings.json').write_text('{}')" """
        result = detect(cmd)
        assert result is not None, "Expected block for .write_text() to settings.json"
        assert "BLOCKED" in result

    def test_spec_python_settings_bypass_1d_settings_local_json(self):
        """Python -c writing to settings.local.json is also blocked."""
        cmd = """python3 -c "import json; json.dump({}, open('settings.local.json', 'w'))" """
        result = detect(cmd)
        assert result is not None, "Expected block for settings.local.json"
        assert "BLOCKED" in result

    def test_spec_python_settings_bypass_1e_variable_indirection(self):
        """Python -c using a variable to hold the settings.json path is blocked."""
        cmd = """python3 -c "import json; p='settings.json'; json.dump({}, open(p,'w'))" """
        result = detect(cmd)
        assert result is not None, "Expected block even with variable indirection"
        assert "BLOCKED" in result

    def test_spec_python_settings_bypass_1f_python_without_3(self):
        """python (without 3) -c writing to settings.json is blocked."""
        cmd = """python -c "import json; json.dump({}, open('settings.json', 'w'))" """
        result = detect(cmd)
        assert result is not None, "Expected block for 'python' (not just 'python3')"
        assert "BLOCKED" in result

    def test_spec_python_settings_bypass_1g_shutil_copy(self):
        """shutil.copy targeting settings.json is blocked."""
        cmd = """python3 -c "import shutil; shutil.copy('tmp.json', 'settings.json')" """
        result = detect(cmd)
        assert result is not None, "Expected block for shutil operations"
        assert "BLOCKED" in result


# ---------------------------------------------------------------------------
# Criterion 2: Read-only Python commands are NOT blocked
# ---------------------------------------------------------------------------


class TestSpec768ReadOnlyAllowed:
    """Read-only Python commands referencing settings.json MUST NOT be blocked."""

    def test_spec_python_settings_bypass_2a_no_settings_reference(self):
        """Python -c writing to a non-settings file is not blocked."""
        cmd = """python3 -c "import json; json.dump({}, open('config.json', 'w'))" """
        result = detect(cmd)
        assert result is None, "Should not block writes to non-settings files"

    def test_spec_python_settings_bypass_2b_print_only(self):
        """Python -c with only print, no file writes, is not blocked."""
        cmd = """python3 -c "print('hello world')" """
        result = detect(cmd)
        assert result is None, "Should not block print-only commands"


# ---------------------------------------------------------------------------
# Criterion 3: Regular non-settings Python commands are NOT blocked
# ---------------------------------------------------------------------------


class TestSpec768RegularPythonAllowed:
    """Regular Python commands not touching settings MUST NOT be blocked."""

    def test_spec_python_settings_bypass_3a_pytest_command(self):
        """python3 -m pytest is not blocked."""
        cmd = "python3 -m pytest tests/ -v"
        result = detect(cmd)
        assert result is None, "Should not block pytest invocations"

    def test_spec_python_settings_bypass_3b_non_python_command(self):
        """Non-Python commands are not blocked."""
        cmd = "cat .claude/settings.json"
        result = detect(cmd)
        assert result is None, "Should not block cat of settings.json"

    def test_spec_python_settings_bypass_3c_grep_settings(self):
        """grep for settings.json is not blocked."""
        cmd = "grep -r 'settings.json' plugins/"
        result = detect(cmd)
        assert result is None, "Should not block grep referencing settings.json"


# ---------------------------------------------------------------------------
# Criterion 4: Existing shell-based detection still works
# ---------------------------------------------------------------------------


class TestSpec768ExistingShellDetection:
    """Existing shell write detection MUST still work after the change."""

    def test_spec_python_settings_bypass_4a_redirect_blocked(self):
        """Shell redirect to settings.json is still blocked."""
        cmd = "echo '{}' > .claude/settings.json"
        result = detect(cmd)
        assert result is not None, "Shell redirect to settings.json must be blocked"
        assert "BLOCKED" in result

    def test_spec_python_settings_bypass_4b_sed_i_blocked(self):
        """sed -i on settings.json is still blocked."""
        cmd = "sed -i 's/old/new/' .claude/settings.json"
        result = detect(cmd)
        assert result is not None, "sed -i on settings.json must be blocked"
        assert "BLOCKED" in result
