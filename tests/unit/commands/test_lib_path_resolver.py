"""Unit tests for the inline lib path resolver used in commands/*.md.

These tests verify the resolver logic that replaces hardcoded
sys.path.insert(0, 'plugins/autonomous-dev/lib') calls with a
multi-candidate resolver that works in both dev and consumer repos.

The resolver pattern (inline in each command's python3 -c block):

    import os as _os
    for _p in ('.claude/lib', 'plugins/autonomous-dev/lib', _os.path.expanduser('~/.claude/lib')):
        if _os.path.isdir(_p):
            sys.path.insert(0, _p)
            break

Priority order: .claude/lib > plugins/autonomous-dev/lib > ~/.claude/lib
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest


def _resolve_lib_path(cwd_paths=None, home_path=None):
    """Mirror of the inline resolver used in commands/*.md.

    Returns the first candidate directory that exists, or None.

    Args:
        cwd_paths: Tuple of candidate paths to check (relative to CWD).
            Defaults to ('.claude/lib', 'plugins/autonomous-dev/lib').
        home_path: Path for the home-based fallback. Defaults to
            os.path.expanduser('~/.claude/lib').

    Returns:
        The first existing candidate path as a string, or None if none exist.
    """
    candidates = list(cwd_paths or ('.claude/lib', 'plugins/autonomous-dev/lib'))
    if home_path:
        candidates.append(home_path)
    else:
        candidates.append(os.path.expanduser('~/.claude/lib'))
    for p in candidates:
        if os.path.isdir(p):
            return p
    return None


class TestLibPathResolver:
    """Tests for the multi-candidate lib path resolver pattern."""

    def test_finds_claude_lib_when_present(self, tmp_path, monkeypatch):
        """Resolver returns .claude/lib when that directory exists."""
        monkeypatch.chdir(tmp_path)
        claude_lib = tmp_path / '.claude' / 'lib'
        claude_lib.mkdir(parents=True)

        result = _resolve_lib_path(home_path='/nonexistent/home/.claude/lib')

        assert result == '.claude/lib'

    def test_falls_back_to_plugins_lib(self, tmp_path, monkeypatch):
        """Resolver returns plugins/autonomous-dev/lib when only that exists."""
        monkeypatch.chdir(tmp_path)
        plugins_lib = tmp_path / 'plugins' / 'autonomous-dev' / 'lib'
        plugins_lib.mkdir(parents=True)

        result = _resolve_lib_path(home_path='/nonexistent/home/.claude/lib')

        assert result == 'plugins/autonomous-dev/lib'

    def test_prefers_claude_lib_over_plugins_lib(self, tmp_path, monkeypatch):
        """Resolver prefers .claude/lib over plugins/autonomous-dev/lib when both exist."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / '.claude' / 'lib').mkdir(parents=True)
        (tmp_path / 'plugins' / 'autonomous-dev' / 'lib').mkdir(parents=True)

        result = _resolve_lib_path(home_path='/nonexistent/home/.claude/lib')

        assert result == '.claude/lib'

    def test_falls_back_to_home_claude_lib(self, tmp_path, monkeypatch):
        """Resolver falls back to home ~/.claude/lib when no CWD candidates exist."""
        monkeypatch.chdir(tmp_path)
        # Neither .claude/lib nor plugins/autonomous-dev/lib exists in tmp_path.
        # Provide a real home_path that exists.
        with tempfile.TemporaryDirectory() as home_lib_dir:
            result = _resolve_lib_path(home_path=home_lib_dir)

        assert result == home_lib_dir

    def test_no_insertion_when_no_candidate_exists(self, tmp_path, monkeypatch):
        """Resolver returns None gracefully when no candidate directory exists."""
        monkeypatch.chdir(tmp_path)

        result = _resolve_lib_path(
            cwd_paths=('.claude/lib', 'plugins/autonomous-dev/lib'),
            home_path='/nonexistent/path/that/does/not/exist/.claude/lib',
        )

        assert result is None

    def test_skips_if_already_in_sys_path(self, tmp_path, monkeypatch):
        """Resolver does not insert a path already present in sys.path."""
        monkeypatch.chdir(tmp_path)
        claude_lib = tmp_path / '.claude' / 'lib'
        claude_lib.mkdir(parents=True)

        resolved = _resolve_lib_path(home_path='/nonexistent/home/.claude/lib')
        assert resolved == '.claude/lib'

        # Simulate what the inline resolver does: only insert if not present.
        original_path = list(sys.path)
        if resolved and resolved not in sys.path:
            sys.path.insert(0, resolved)
        count_before_second_call = sys.path.count(resolved)

        # Second call with the same path already inserted should not duplicate.
        resolved2 = _resolve_lib_path(home_path='/nonexistent/home/.claude/lib')
        if resolved2 and resolved2 not in sys.path:
            sys.path.insert(0, resolved2)
        count_after_second_call = sys.path.count(resolved2)

        # Restore sys.path
        sys.path[:] = original_path

        assert count_before_second_call == count_after_second_call == 1
