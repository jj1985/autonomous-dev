"""Spec-blind behavioral validation for Issue #896.

Validates acceptance criteria for the fix of the broken list-comprehension
sys.path resolver in `plugins/autonomous-dev/commands/*.md` files.

Each test corresponds to a specific acceptance criterion (AC 1-10). Tests are
written from the acceptance criteria only — no knowledge of implementation
choice or phrasing. The tests exercise observable behavior of the resolver
snippets as executed from their command-file context.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMANDS_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "commands"
LIB_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "lib"

# The six files listed in the feature description as modified for #896.
MODIFIED_COMMAND_FILES = [
    "create-issue.md",
    "implement.md",
    "improve.md",
    "plan-to-issues.md",
    "refactor.md",
    "retrospective.md",
]

# The broken pattern that MUST be eliminated (AC 1).
BROKEN_PATTERN = re.compile(r"\[sys\.path\.insert\(0,p\) for p in")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sys_path_snapshot():
    """Snapshot sys.path and restore after test (AC 10)."""
    original = list(sys.path)
    try:
        yield original
    finally:
        sys.path[:] = original


@pytest.fixture
def tmp_cwd(tmp_path, monkeypatch):
    """Change CWD to a temp directory so relative '.claude/lib' etc. resolve there."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_python_c_snippets() -> list[tuple[str, int, str]]:
    """Extract all `python3 -c "..."` snippets from the 6 modified files that
    reference sys.path.insert and version_reader/pipeline_state. Returns a list
    of (filename, line_no, snippet_body) tuples.
    """
    snippets: list[tuple[str, int, str]] = []
    # Match: python3 -c "BODY" where BODY contains sys.path.insert
    # The body is double-quoted; escaped quotes inside are unlikely in the source.
    pat = re.compile(r'python3 -c "((?:[^"\\]|\\.)*sys\.path\.insert[^"]*)"')
    for fname in MODIFIED_COMMAND_FILES:
        fpath = COMMANDS_DIR / fname
        for i, line in enumerate(fpath.read_text().splitlines(), start=1):
            for m in pat.finditer(line):
                snippets.append((fname, i, m.group(1)))
    return snippets


def _extract_resolver_prelude(snippet_body: str) -> str:
    """Return the prelude of the snippet up to (and including) the next(...)
    resolver call — i.e., everything before the first `from <module>` import
    that depends on the resolver. Safe to exec in an arbitrary cwd.
    """
    # Split on the first `;from ` (the resolver should come right before a
    # `from <lib_module> import ...`). Keep everything up to and including the
    # next(...) call.
    idx = snippet_body.find(";from ")
    if idx == -1:
        return snippet_body
    return snippet_body[:idx]


# ---------------------------------------------------------------------------
# AC 1: Zero occurrences of the broken list-comprehension pattern
# ---------------------------------------------------------------------------


def test_ac1_no_broken_list_comprehension_in_any_command_file():
    """AC 1: Zero occurrences of `[sys.path.insert(0,p) for p in` in commands/*.md."""
    offenders: list[str] = []
    for md_path in sorted(COMMANDS_DIR.glob("*.md")):
        text = md_path.read_text()
        if BROKEN_PATTERN.search(text):
            # Record each hit with line numbers for diagnostics.
            for i, line in enumerate(text.splitlines(), start=1):
                if BROKEN_PATTERN.search(line):
                    offenders.append(f"{md_path.name}:{i}")
    assert offenders == [], (
        f"Broken list-comprehension resolver still present at: {offenders}"
    )


# ---------------------------------------------------------------------------
# AC 2: 9 resolver sites across 6 files, all using a working replacement form
# ---------------------------------------------------------------------------


def test_ac2_replacement_form_present_at_least_9_sites_across_6_files():
    """AC 2: At least 9 sys.path.insert resolver references remain across the
    6 modified files, and 0 use the broken list-comprehension form."""
    total_inserts = 0
    broken = 0
    files_with_inserts: set[str] = set()
    for fname in MODIFIED_COMMAND_FILES:
        text = (COMMANDS_DIR / fname).read_text()
        # Count every inline python3 -c resolver reference (the ones fixed by #896).
        # We count occurrences of `sys.path.insert(0,p) for p in` since both the
        # broken form and a correct `next(...)` generator form contain it.
        matches = re.findall(r"sys\.path\.insert\(0,p\) for p in", text)
        if matches:
            files_with_inserts.add(fname)
            total_inserts += len(matches)
        broken += len(BROKEN_PATTERN.findall(text))
    assert broken == 0, f"Broken list-comp form still present ({broken} occurrences)"
    assert total_inserts >= 9, (
        f"Expected >= 9 resolver sites across the 6 modified files, got {total_inserts}"
    )
    assert files_with_inserts == set(MODIFIED_COMMAND_FILES), (
        f"Expected resolver sites in all 6 files, missing: "
        f"{set(MODIFIED_COMMAND_FILES) - files_with_inserts}"
    )


# ---------------------------------------------------------------------------
# AC 3: Priority — .claude/lib wins when both CWD candidates exist
# ---------------------------------------------------------------------------


def test_ac3_both_candidates_exist_claude_lib_wins(tmp_cwd, sys_path_snapshot):
    """AC 3: When both .claude/lib and plugins/autonomous-dev/lib exist in CWD,
    the resolver inserts exactly ONE path and it is .claude/lib."""
    (tmp_cwd / ".claude" / "lib").mkdir(parents=True)
    (tmp_cwd / "plugins" / "autonomous-dev" / "lib").mkdir(parents=True)

    # Extract the resolver prelude from implement.md:1220 (the load-bearing site).
    impl_text = (COMMANDS_DIR / "implement.md").read_text().splitlines()
    line_1220 = impl_text[1219]  # 0-indexed
    m = re.search(r'python3 -c "((?:[^"\\]|\\.)*sys\.path\.insert[^"]*)"', line_1220)
    assert m, f"Could not locate python3 -c resolver snippet at implement.md:1220"
    prelude = _extract_resolver_prelude(m.group(1))

    before = len(sys.path)
    # Execute the resolver prelude in-process so we can observe sys.path changes.
    exec(compile(prelude, "<implement.md:1220>", "exec"), {"__name__": "__main__"})
    after = len(sys.path)

    assert after - before == 1, (
        f"Expected exactly 1 sys.path insertion, got {after - before}"
    )
    inserted = sys.path[0]
    resolved = Path(inserted).resolve()
    expected = (tmp_cwd / ".claude" / "lib").resolve()
    assert resolved == expected, (
        f"Expected .claude/lib to win, but sys.path[0] resolves to {resolved} "
        f"(expected {expected})"
    )


# ---------------------------------------------------------------------------
# AC 4: Fallback — only plugins/autonomous-dev/lib exists
# ---------------------------------------------------------------------------


def test_ac4_only_plugins_lib_exists_plugins_lib_wins(tmp_cwd, sys_path_snapshot):
    """AC 4: When only plugins/autonomous-dev/lib exists, that path is inserted."""
    (tmp_cwd / "plugins" / "autonomous-dev" / "lib").mkdir(parents=True)
    # .claude/lib does NOT exist.

    impl_text = (COMMANDS_DIR / "implement.md").read_text().splitlines()
    line_1220 = impl_text[1219]
    m = re.search(r'python3 -c "((?:[^"\\]|\\.)*sys\.path\.insert[^"]*)"', line_1220)
    assert m
    prelude = _extract_resolver_prelude(m.group(1))

    before = len(sys.path)
    exec(compile(prelude, "<implement.md:1220>", "exec"), {"__name__": "__main__"})
    after = len(sys.path)

    assert after - before == 1, f"Expected 1 insertion, got {after - before}"
    resolved = Path(sys.path[0]).resolve()
    expected = (tmp_cwd / "plugins" / "autonomous-dev" / "lib").resolve()
    assert resolved == expected, (
        f"Expected plugins/autonomous-dev/lib, got {resolved}"
    )


# ---------------------------------------------------------------------------
# AC 5: Fallback — neither CWD candidate exists → ~/.claude/lib used
# ---------------------------------------------------------------------------


def test_ac5_neither_cwd_candidate_exists_home_candidate_used(
    tmp_path, monkeypatch, sys_path_snapshot
):
    """AC 5: When neither CWD candidate exists, ~/.claude/lib is used."""
    # Point HOME to a temp dir and create ~/.claude/lib there.
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    home_lib = fake_home / ".claude" / "lib"
    home_lib.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(fake_home))

    # CWD has NEITHER .claude/lib NOR plugins/autonomous-dev/lib.
    cwd = tmp_path / "empty_cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)

    impl_text = (COMMANDS_DIR / "implement.md").read_text().splitlines()
    line_1220 = impl_text[1219]
    m = re.search(r'python3 -c "((?:[^"\\]|\\.)*sys\.path\.insert[^"]*)"', line_1220)
    assert m
    prelude = _extract_resolver_prelude(m.group(1))

    before = len(sys.path)
    exec(compile(prelude, "<implement.md:1220>", "exec"), {"__name__": "__main__"})
    after = len(sys.path)

    assert after - before == 1, f"Expected 1 insertion, got {after - before}"
    resolved = Path(sys.path[0]).resolve()
    expected = home_lib.resolve()
    assert resolved == expected, (
        f"Expected ~/.claude/lib ({expected}), got {resolved}"
    )


# ---------------------------------------------------------------------------
# AC 6: Every extracted `python3 -c` snippet has valid Python syntax
# ---------------------------------------------------------------------------


def test_ac6_all_extracted_snippets_have_valid_syntax(tmp_path):
    """AC 6: All 9 extracted python3 -c snippets execute with returncode 0.

    Because the snippets import modules like `version_reader` or
    `pipeline_state` that will not be importable in a random cwd, we run each
    snippet under `bash -c "... 2>/dev/null || true"` form is NOT what we want
    (masks SyntaxError). Instead we run `python3 -c <snippet>` directly in an
    empty cwd and classify the failure: SyntaxError is unacceptable, but a
    downstream ImportError / ModuleNotFoundError is acceptable (the spec says
    so explicitly).
    """
    snippets = _extract_python_c_snippets()
    assert len(snippets) >= 9, (
        f"Expected >= 9 python3 -c resolver snippets across 6 files, found {len(snippets)}"
    )

    failures: list[str] = []
    for fname, lineno, body in snippets:
        # Run in an empty tmp dir so CWD lookups all miss → exercises the HOME
        # fallback path or fails cleanly with ImportError downstream.
        proc = subprocess.run(
            ["python3", "-c", body],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode != 0:
            stderr = proc.stderr or ""
            # SyntaxError is a hard failure; ImportError/ModuleNotFoundError
            # are acceptable per the feature description.
            if "SyntaxError" in stderr:
                failures.append(
                    f"{fname}:{lineno} SyntaxError:\n{stderr}\nSNIPPET: {body}"
                )
            elif (
                "ModuleNotFoundError" in stderr
                or "ImportError" in stderr
                or "No module named" in stderr
            ):
                # Acceptable: the resolver ran, but the downstream import failed
                # because we're not in a repo/home with the module installed.
                continue
            else:
                failures.append(
                    f"{fname}:{lineno} unexpected failure:\n{stderr}\nSNIPPET: {body}"
                )
    assert failures == [], "\n---\n".join(failures)


# ---------------------------------------------------------------------------
# AC 9: No new `_resolver.py` module in plugins/autonomous-dev/lib/
# ---------------------------------------------------------------------------


def test_ac9_no_new_resolver_module_created():
    """AC 9: No `_resolver.py` (or variants like `lib_resolver.py`) introduced."""
    forbidden_names = {
        "_resolver.py",
        "resolver.py",
        "lib_resolver.py",
        "path_resolver.py",
        "lib_path_resolver.py",
    }
    present = {p.name for p in LIB_DIR.iterdir() if p.is_file()}
    # conflict_resolver.py is pre-existing and unrelated — allowed.
    collisions = forbidden_names & present
    assert collisions == set(), (
        f"Forbidden resolver module(s) introduced: {collisions}. "
        f"Spec explicitly forbids a centralized resolver module."
    )


# ---------------------------------------------------------------------------
# AC 10: sys.path fixture actually restores between tests
# ---------------------------------------------------------------------------


def test_ac10_sys_path_fixture_restores_state(sys_path_snapshot):
    """AC 10: The sys_path_snapshot fixture restores sys.path after the test."""
    # Mutate sys.path inside the test; the fixture teardown must restore it.
    # We can only verify the snapshot captured the original state here —
    # the actual restoration happens in the fixture's finally block.
    sys.path.insert(0, "/tmp/spec_validator_sentinel_path")
    assert "/tmp/spec_validator_sentinel_path" in sys.path
    # The snapshot variable holds the pre-test sys.path — verify it's a list copy.
    assert isinstance(sys_path_snapshot, list)
    assert "/tmp/spec_validator_sentinel_path" not in sys_path_snapshot


def test_ac10_sys_path_restored_after_mutation(sys_path_snapshot):
    """AC 10 (companion): sys.path does not carry the sentinel from the
    previous test — proves the prior test's fixture restored state."""
    assert "/tmp/spec_validator_sentinel_path" not in sys.path, (
        "sys.path pollution detected — previous test's fixture did not restore."
    )
