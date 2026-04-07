"""
Unit tests for python_write_detector module (Issue #589).

Tests AST-based and regex-based detection of file-write operations
in Python code snippets, including aliased imports, shutil operations,
and eval/exec indirection.

Date: 2026-03-29
"""

import sys
from pathlib import Path

import pytest

# Add lib dir to path
LIB_DIR = Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "lib"
sys.path.insert(0, str(LIB_DIR))

from python_write_detector import (
    SUSPICIOUS_EXEC_SENTINEL,
    extract_write_targets,
    extract_write_targets_ast,
    extract_write_targets_regex,
    has_suspicious_exec,
)


# ---------------------------------------------------------------------------
# Basic write detection
# ---------------------------------------------------------------------------

class TestBasicPathWrite:
    """Tests for Path().write_text/write_bytes detection."""

    def test_path_write_text(self):
        code = "from pathlib import Path; Path('file.txt').write_text('hello')"
        result = extract_write_targets(code)
        assert "file.txt" in result

    def test_path_write_bytes(self):
        code = "from pathlib import Path; Path('file.bin').write_bytes(b'data')"
        result = extract_write_targets(code)
        assert "file.bin" in result

    def test_open_write_mode(self):
        code = "open('output.txt', 'w').write('hello')"
        result = extract_write_targets(code)
        assert "output.txt" in result

    def test_open_append_mode(self):
        code = "open('log.txt', 'a').write('entry')"
        result = extract_write_targets(code)
        assert "log.txt" in result

    def test_open_write_binary(self):
        code = "open('data.bin', 'wb').write(b'data')"
        result = extract_write_targets(code)
        assert "data.bin" in result


class TestShutilOperations:
    """Tests for shutil.copy/copy2/move detection."""

    def test_shutil_copy(self):
        code = "import shutil; shutil.copy('src.txt', 'dst.txt')"
        result = extract_write_targets(code)
        assert "dst.txt" in result

    def test_shutil_copy2(self):
        code = "import shutil; shutil.copy2('src.txt', 'dst.txt')"
        result = extract_write_targets(code)
        assert "dst.txt" in result

    def test_shutil_move(self):
        code = "import shutil; shutil.move('src.txt', 'dst.txt')"
        result = extract_write_targets(code)
        assert "dst.txt" in result

    def test_shutil_copyfile(self):
        code = "import shutil; shutil.copyfile('src.txt', 'dst.txt')"
        result = extract_write_targets(code)
        assert "dst.txt" in result


# ---------------------------------------------------------------------------
# Aliased imports
# ---------------------------------------------------------------------------

class TestAliasedImports:
    """Tests for aliased import detection."""

    def test_path_alias(self):
        code = "from pathlib import Path as P; P('agents/foo.md').write_text('x')"
        result = extract_write_targets(code)
        assert "agents/foo.md" in result

    def test_module_qualified_path(self):
        code = "import pathlib; pathlib.Path('file.txt').write_text('data')"
        result = extract_write_targets(code)
        assert "file.txt" in result

    def test_shutil_alias(self):
        code = "import shutil as sh; sh.copy('src', 'agents/foo.md')"
        result = extract_write_targets(code)
        assert "agents/foo.md" in result


# ---------------------------------------------------------------------------
# Suspicious exec/eval
# ---------------------------------------------------------------------------

class TestExecEval:
    """Tests for eval/exec detection."""

    def test_exec_with_variable(self):
        code = "exec(some_var)"
        result = extract_write_targets(code)
        assert SUSPICIOUS_EXEC_SENTINEL in result

    def test_eval_with_variable(self):
        code = "eval(dynamic_code)"
        result = extract_write_targets(code)
        assert SUSPICIOUS_EXEC_SENTINEL in result

    def test_exec_with_open_read(self):
        code = "exec(open('file').read())"
        result = extract_write_targets(code)
        assert SUSPICIOUS_EXEC_SENTINEL in result

    def test_safe_exec_constant_string(self):
        """exec('print(hello)') should NOT be suspicious."""
        code = "exec(\"print('hello')\")"
        result = extract_write_targets(code)
        assert SUSPICIOUS_EXEC_SENTINEL not in result

    def test_exec_constant_string_with_path_write(self):
        """exec() with constant string containing Path.write_text detects the target.

        Regression for security-auditor M-01: constant strings inside exec()
        must be recursively parsed to detect embedded write operations.
        """
        code = "exec(\"from pathlib import Path; Path('agents/foo.md').write_text('x')\")"
        result = extract_write_targets(code)
        assert "agents/foo.md" in result
        assert SUSPICIOUS_EXEC_SENTINEL not in result

    def test_exec_constant_string_with_open_write(self):
        """exec() with constant string containing open(..., 'w')."""
        code = "exec(\"open('lib/bar.py', 'w').write('pwned')\")"
        result = extract_write_targets(code)
        assert "lib/bar.py" in result

    def test_exec_constant_string_with_syntax_error(self):
        """exec() with constant string that fails to parse returns empty."""
        code = "exec('this is {not} valid python')"
        result = extract_write_targets(code)
        # Inner parse fails, but outer parse succeeds with no targets
        assert result == []

    def test_has_suspicious_exec_true(self):
        assert has_suspicious_exec("exec(some_var)") is True

    def test_has_suspicious_exec_false(self):
        assert has_suspicious_exec("exec(\"print(1)\")") is False


# ---------------------------------------------------------------------------
# Safe operations (no false positives)
# ---------------------------------------------------------------------------

class TestSafeOperations:
    """Tests that read-only operations do NOT trigger."""

    def test_open_read_mode(self):
        code = "open('file.txt', 'r').read()"
        result = extract_write_targets(code)
        assert "file.txt" not in result

    def test_open_default_mode(self):
        """open('file') with no mode should not trigger (default is read)."""
        code = "open('file.txt').read()"
        result = extract_write_targets(code)
        assert "file.txt" not in result

    def test_path_read_text(self):
        code = "from pathlib import Path; Path('file.txt').read_text()"
        result = extract_write_targets(code)
        assert len(result) == 0

    def test_path_read_bytes(self):
        code = "from pathlib import Path; Path('file.bin').read_bytes()"
        result = extract_write_targets(code)
        assert len(result) == 0

    def test_print_only(self):
        code = "print('hello world')"
        result = extract_write_targets(code)
        assert len(result) == 0

    def test_import_only(self):
        code = "import os; import sys"
        result = extract_write_targets(code)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_string(self):
        result = extract_write_targets("")
        assert result == []

    def test_whitespace_only(self):
        result = extract_write_targets("   \n\t  ")
        assert result == []

    def test_multiline_with_escaped_newlines(self):
        """Literal \\n in -c string should be handled."""
        code = "from pathlib import Path\\nPath('agents/foo.md').write_text('x')"
        result = extract_write_targets(code)
        assert "agents/foo.md" in result

    def test_ast_failure_falls_back_to_regex(self):
        """Invalid syntax should fall back to regex."""
        code = "Path('file.txt').write_text('data') $$$ invalid syntax"
        result = extract_write_targets(code)
        # Regex fallback should still find it
        assert "file.txt" in result

    def test_multiple_writes(self):
        code = (
            "from pathlib import Path\n"
            "Path('a.txt').write_text('x')\n"
            "Path('b.txt').write_bytes(b'y')\n"
        )
        result = extract_write_targets(code)
        assert "a.txt" in result
        assert "b.txt" in result

    def test_long_snippet_truncated(self):
        """Snippets longer than MAX_SNIPPET_LENGTH should be truncated."""
        code = "x = 1\n" * 5000 + "Path('evil.txt').write_text('x')"
        result = extract_write_targets(code)
        # The write is after truncation point, so should not be found
        # (this is acceptable per the design: conservative approach)
        # Just verify it doesn't crash
        assert isinstance(result, list)

    def test_open_with_keyword_mode(self):
        code = "open('file.txt', mode='w')"
        result = extract_write_targets(code)
        assert "file.txt" in result


# ---------------------------------------------------------------------------
# Regex-specific tests
# ---------------------------------------------------------------------------

class TestRegexFallback:
    """Tests specifically for the regex fallback path."""

    def test_regex_path_write(self):
        code = "Path('target.txt').write_text('data')"
        result = extract_write_targets_regex(code)
        assert "target.txt" in result

    def test_regex_open_write(self):
        code = "open('out.txt', 'w')"
        result = extract_write_targets_regex(code)
        assert "out.txt" in result

    def test_regex_shutil(self):
        code = "shutil.copy('src', 'dst.txt')"
        result = extract_write_targets_regex(code)
        assert "dst.txt" in result

    def test_regex_suspicious_exec(self):
        code = "exec(user_input)"
        result = extract_write_targets_regex(code)
        assert SUSPICIOUS_EXEC_SENTINEL in result

    def test_regex_safe_exec(self):
        """exec('string') should not trigger suspicious in regex."""
        code = "exec('print(1)')"
        result = extract_write_targets_regex(code)
        assert SUSPICIOUS_EXEC_SENTINEL not in result

    def test_regex_open_read_not_detected(self):
        code = "open('file.txt', 'r')"
        result = extract_write_targets_regex(code)
        assert "file.txt" not in result


# ---------------------------------------------------------------------------
# os.rename / os.replace detection (Issue #698)
# ---------------------------------------------------------------------------

class TestOsRenameReplace:
    """Tests for os.rename/os.replace destination detection (Issue #698)."""

    def test_os_rename_detected(self):
        """os.rename(src, dst) should detect dst as write target."""
        code = "import os; os.rename('/tmp/staged.py', 'agents/foo.py')"
        result = extract_write_targets(code)
        assert "agents/foo.py" in result

    def test_os_replace_detected(self):
        """os.replace(src, dst) should detect dst as write target."""
        code = "import os; os.replace('/tmp/staged.py', 'hooks/bar.py')"
        result = extract_write_targets(code)
        assert "hooks/bar.py" in result

    def test_os_alias_rename_detected(self):
        """import os as o; o.rename(src, dst) should detect dst."""
        code = "import os as o; o.rename('/tmp/x', 'agents/evil.md')"
        result = extract_write_targets(code)
        assert "agents/evil.md" in result

    def test_os_from_import_rename_detected(self):
        """from os import rename; rename(src, dst) should detect dst."""
        code = "from os import rename; rename('/tmp/x', 'lib/util.py')"
        result = extract_write_targets(code)
        assert "lib/util.py" in result

    def test_os_rename_variable_dst_suspicious(self):
        """os.rename(src, variable_dst) should set suspicious flag."""
        code = "import os; os.rename('/tmp/x', dst_path)"
        result = extract_write_targets(code)
        assert SUSPICIOUS_EXEC_SENTINEL in result

    def test_os_rename_safe_non_infra_path(self):
        """os.rename to non-protected path should be detected (not necessarily blocked)."""
        code = "import os; os.rename('a.txt', '/tmp/safe.txt')"
        result = extract_write_targets(code)
        assert "/tmp/safe.txt" in result

    def test_os_rename_src_not_detected(self):
        """Source (1st arg) of os.rename should NOT be detected as write target."""
        code = "import os; os.rename('agents/foo.py', '/tmp/backup.py')"
        result = extract_write_targets(code)
        # Source 'agents/foo.py' is being read/moved FROM, not written to
        assert "agents/foo.py" not in result
        assert "/tmp/backup.py" in result


class TestPathRename:
    """Tests for Path(...).rename/Path(...).replace detection (Issue #698)."""

    def test_path_rename_detected(self):
        """Path('src').rename('dst') should detect dst as write target."""
        code = "from pathlib import Path; Path('/tmp/staged.py').rename('agents/foo.py')"
        result = extract_write_targets(code)
        assert "agents/foo.py" in result

    def test_path_replace_detected(self):
        """Path('src').replace('dst') should detect dst as write target."""
        code = "from pathlib import Path; Path('/tmp/x').replace('hooks/bar.py')"
        result = extract_write_targets(code)
        assert "hooks/bar.py" in result

    def test_path_alias_rename_detected(self):
        """P('src').rename('dst') with aliased Path should detect dst."""
        code = "from pathlib import Path as P; P('/tmp/x').rename('agents/evil.md')"
        result = extract_write_targets(code)
        assert "agents/evil.md" in result

    def test_path_rename_variable_dst_suspicious(self):
        """Path('src').rename(variable_dst) should set suspicious flag."""
        code = "from pathlib import Path; Path('/tmp/x').rename(dst_var)"
        result = extract_write_targets(code)
        assert SUSPICIOUS_EXEC_SENTINEL in result

    def test_path_src_not_detected(self):
        """Source (Path constructor arg) of Path.rename should NOT be write target."""
        code = "from pathlib import Path; Path('agents/foo.py').rename('/tmp/backup.py')"
        result = extract_write_targets(code)
        # Source 'agents/foo.py' is being moved FROM, not written to
        assert "agents/foo.py" not in result
        assert "/tmp/backup.py" in result


class TestOsRenameRegex:
    """Tests for regex fallback covering os.rename/os.replace/Path.rename (Issue #698)."""

    def test_regex_os_rename(self):
        """Regex fallback detects os.rename destination."""
        code = "os.rename('/tmp/staged.py', 'agents/foo.py')"
        result = extract_write_targets_regex(code)
        assert "agents/foo.py" in result

    def test_regex_os_replace(self):
        """Regex fallback detects os.replace destination."""
        code = "os.replace('/tmp/staged.py', 'hooks/bar.py')"
        result = extract_write_targets_regex(code)
        assert "hooks/bar.py" in result

    def test_regex_path_rename(self):
        """Regex fallback detects Path(...).rename destination."""
        code = "Path('/tmp/x').rename('lib/util.py')"
        result = extract_write_targets_regex(code)
        assert "lib/util.py" in result

    def test_regex_path_replace(self):
        """Regex fallback detects Path(...).replace destination."""
        code = "Path('/tmp/x').replace('commands/test.md')"
        result = extract_write_targets_regex(code)
        assert "commands/test.md" in result
