"""Spec-validation tests for issue #894: lib path resolver in consumer repos.

Validates the acceptance criteria WITHOUT reading implementer output.

Criteria covered behaviorally:
1. /implement (commands/implement.md) — no hardcoded `sys.path.insert(0, 'plugins/autonomous-dev/lib')`.
2. /sweep — same check.
3. All listed command files contain a resolver block before `sys.path.insert(...)` for plugin lib.
4. Resolver candidate order is `.claude/lib` then `plugins/autonomous-dev/lib` then `~/.claude/lib`.
5. Resolver prefers `.claude/lib` over `plugins/autonomous-dev/lib` when both exist (simulated).
6. Symlink workaround note in TROUBLESHOOTING.md marks it optional.
7. Unit-test file exists at tests/unit/commands/test_lib_path_resolver.py.
8. Audit: no bare hardcoded `sys.path.insert(0, 'plugins/autonomous-dev/lib')` in any commands/*.md.
9. Resolver returns None when no candidate exists (graceful — no-op, later import fails naturally).
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMANDS_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "commands"
TROUBLESHOOTING = REPO_ROOT / "plugins" / "autonomous-dev" / "docs" / "TROUBLESHOOTING.md"
RESOLVER_TEST_FILE = REPO_ROOT / "tests" / "unit" / "commands" / "test_lib_path_resolver.py"

CHANGED_COMMANDS = [
    "audit.md",
    "autoresearch.md",
    "create-issue.md",
    "implement-batch.md",
    "implement.md",
    "improve.md",
    "plan-to-issues.md",
    "refactor.md",
    "retrospective.md",
    "sweep.md",
]

HARDCODED_PATTERN = re.compile(
    r"sys\.path\.insert\(\s*0\s*,\s*['\"]plugins/autonomous-dev/lib['\"]\s*\)"
)


def _inline_resolver(candidates, home_path):
    """Mirror of the inline resolver used in commands/*.md."""
    full = list(candidates) + [home_path]
    for p in full:
        if os.path.isdir(p):
            return p
    return None


# -------- Criterion 1/2/3/8: audit commands have no hardcoded path --------


@pytest.mark.parametrize("fname", CHANGED_COMMANDS)
def test_spec_issue894_1_no_hardcoded_plugin_lib_path(fname):
    """Criterion 1/2/3/8: No remaining hardcoded `sys.path.insert(0, 'plugins/autonomous-dev/lib')`."""
    path = COMMANDS_DIR / fname
    assert path.exists(), f"Expected command file missing: {path}"
    content = path.read_text()
    matches = HARDCODED_PATTERN.findall(content)
    assert not matches, (
        f"{fname} still contains hardcoded `sys.path.insert(0, 'plugins/autonomous-dev/lib')` — "
        f"found {len(matches)} occurrence(s)."
    )


# -------- Criterion 4: resolver enumerates all 3 candidates in priority order --------


@pytest.mark.parametrize("fname", CHANGED_COMMANDS)
def test_spec_issue894_2_resolver_priority_order(fname):
    """Criterion 4: each command that imports from plugin libs contains the
    multi-candidate resolver with `.claude/lib` first, `plugins/autonomous-dev/lib`
    second, and `~/.claude/lib` third.
    """
    path = COMMANDS_DIR / fname
    content = path.read_text()
    # The file must at least mention all three candidates together in some
    # ordered tuple literal if it does any sys.path manipulation for lib imports.
    # Accept both inline-loop and one-line list-comprehension variants.
    combined_regex = re.compile(
        r"['\"]\.claude/lib['\"]\s*,\s*['\"]plugins/autonomous-dev/lib['\"]\s*,\s*.*?~/\.claude/lib"
    )
    if "sys.path.insert" in content and "plugins/autonomous-dev/lib" in content:
        assert combined_regex.search(content), (
            f"{fname} does not contain the expected resolver candidate ordering "
            f"('.claude/lib', 'plugins/autonomous-dev/lib', '~/.claude/lib')."
        )


# -------- Criterion 5: resolver prefers .claude/lib over plugins/autonomous-dev/lib --------


def test_spec_issue894_3_prefers_claude_lib(tmp_path, monkeypatch):
    """Criterion 5: When both `.claude/lib` and `plugins/autonomous-dev/lib`
    exist, the resolver selects `.claude/lib`."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".claude" / "lib").mkdir(parents=True)
    (tmp_path / "plugins" / "autonomous-dev" / "lib").mkdir(parents=True)

    result = _inline_resolver(
        (".claude/lib", "plugins/autonomous-dev/lib"),
        "/nonexistent/.claude/lib",
    )
    assert result == ".claude/lib"


def test_spec_issue894_4_consumer_repo_layout_finds_claude_lib(tmp_path, monkeypatch):
    """Criterion 1/2/7: Consumer repo installed via install.sh has only
    `.claude/lib/` at repo root. Resolver must find it."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".claude" / "lib").mkdir(parents=True)

    result = _inline_resolver(
        (".claude/lib", "plugins/autonomous-dev/lib"),
        "/nonexistent/.claude/lib",
    )
    assert result == ".claude/lib"


def test_spec_issue894_5_dev_repo_layout_finds_plugins_lib(tmp_path, monkeypatch):
    """Criterion 5: Dev repo without `.claude/lib` but with
    `plugins/autonomous-dev/lib` must still resolve."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "plugins" / "autonomous-dev" / "lib").mkdir(parents=True)

    result = _inline_resolver(
        (".claude/lib", "plugins/autonomous-dev/lib"),
        "/nonexistent/.claude/lib",
    )
    assert result == "plugins/autonomous-dev/lib"


def test_spec_issue894_6_home_fallback(tmp_path, monkeypatch):
    """Criterion 4: Home `~/.claude/lib` fallback when no CWD candidate exists."""
    monkeypatch.chdir(tmp_path)
    with tempfile.TemporaryDirectory() as home_lib:
        result = _inline_resolver(
            (".claude/lib", "plugins/autonomous-dev/lib"),
            home_lib,
        )
    assert result == home_lib


def test_spec_issue894_7_graceful_none_when_nothing_exists(tmp_path, monkeypatch):
    """Criterion 9: No candidate exists -> resolver returns None (no insertion,
    no crash). The subsequent import will raise ModuleNotFoundError naturally —
    which is clearer than a cryptic path-manipulation crash."""
    monkeypatch.chdir(tmp_path)
    result = _inline_resolver(
        (".claude/lib", "plugins/autonomous-dev/lib"),
        "/nonexistent/home/.claude/lib",
    )
    assert result is None


# -------- Criterion 6: works alongside existing symlink workarounds --------


def test_spec_issue894_8_works_with_symlink_workaround(tmp_path, monkeypatch):
    """Criterion 6: A symlink at `.claude/lib -> plugins/autonomous-dev/lib`
    is still resolved (doesn't require removal)."""
    monkeypatch.chdir(tmp_path)
    real_lib = tmp_path / "plugins" / "autonomous-dev" / "lib"
    real_lib.mkdir(parents=True)
    (tmp_path / ".claude").mkdir(parents=True)
    symlink = tmp_path / ".claude" / "lib"
    symlink.symlink_to(real_lib)

    result = _inline_resolver(
        (".claude/lib", "plugins/autonomous-dev/lib"),
        "/nonexistent/.claude/lib",
    )
    # Symlink target is a directory -> should be picked up as .claude/lib.
    assert result == ".claude/lib"


# -------- Criterion 12: TROUBLESHOOTING.md updated --------


def test_spec_issue894_9_troubleshooting_notes_symlink_optional():
    """Criterion 12: TROUBLESHOOTING.md notes symlink workaround is now optional."""
    assert TROUBLESHOOTING.exists(), f"Missing: {TROUBLESHOOTING}"
    content = TROUBLESHOOTING.read_text().lower()
    # Must mention the resolver + optional/no longer required for symlink.
    assert "resolver" in content, "TROUBLESHOOTING.md does not mention the resolver."
    assert (
        "no longer required" in content
        or "optional" in content
        or "automatically finds" in content
    ), "TROUBLESHOOTING.md does not indicate symlink workaround is optional."


# -------- Criterion 10/11: unit test file exists for the resolver --------


def test_spec_issue894_10_unit_test_file_exists():
    """Criterion 10/11: tests/unit/commands/test_lib_path_resolver.py exists
    with finds/falls-back tests."""
    assert RESOLVER_TEST_FILE.exists(), f"Missing: {RESOLVER_TEST_FILE}"
    text = RESOLVER_TEST_FILE.read_text()
    assert "finds_claude_lib_when_present" in text, (
        "Resolver unit test file missing `finds_claude_lib_when_present` test "
        "(Criterion 10)."
    )
    assert "falls_back_to_plugins_lib" in text, (
        "Resolver unit test file missing `falls_back_to_plugins_lib` test "
        "(Criterion 11)."
    )
