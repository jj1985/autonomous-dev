"""Regression test for Issue #651: session_activity_logger fails in all worktree sessions.

Bug: Hook commands in settings template files used $(git rev-parse --show-toplevel) to
resolve the repo root. In a worktree, --show-toplevel returns the worktree path (e.g.,
.worktrees/batch-XXX), NOT the main repo root where plugins/autonomous-dev/hooks/ lives.
This caused "No such file or directory" for every hook invocation in worktree sessions.

Fix: Replaced $(git rev-parse --show-toplevel) with
$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)") which:
- In normal repo: --git-common-dir returns /path/to/repo/.git -> dirname = /path/to/repo
- In worktree: --git-common-dir returns /path/to/main/.git -> dirname = /path/to/main

This correctly resolves to the main repo root in both cases.
"""

import json
import re
from pathlib import Path

import pytest

TEMPLATES_DIR = (
    Path(__file__).resolve().parents[3]
    / "plugins"
    / "autonomous-dev"
    / "templates"
)

TEMPLATE_FILES = [
    "settings.autonomous-dev.json",
    "settings.default.json",
    "settings.permission-batching.json",
    "settings.granular-bash.json",
    "settings.strict-mode.json",
    "settings.local.json",
]


def _extract_hook_commands(settings: dict) -> list[str]:
    """Extract all hook command strings from a settings dict."""
    commands = []
    hooks = settings.get("hooks", {})
    for _event, matchers in hooks.items():
        if not isinstance(matchers, list):
            continue
        for matcher_entry in matchers:
            for hook in matcher_entry.get("hooks", []):
                cmd = hook.get("command", "")
                if cmd:
                    commands.append(cmd)
    return commands


class TestIssue651WorktreeHookPaths:
    """Ensure no settings template uses --show-toplevel (breaks in worktrees)."""

    @pytest.mark.parametrize("template_name", TEMPLATE_FILES)
    def test_no_show_toplevel_in_hook_commands(self, template_name: str) -> None:
        """Hook commands must NOT use --show-toplevel (Issue #651).

        --show-toplevel returns the worktree root in worktree contexts, not
        the main repo root. Hooks must use --git-common-dir + dirname instead.
        """
        template_path = TEMPLATES_DIR / template_name
        if not template_path.exists():
            pytest.skip(f"Template {template_name} not found")

        settings = json.loads(template_path.read_text())
        commands = _extract_hook_commands(settings)

        violations = []
        for cmd in commands:
            if "--show-toplevel" in cmd:
                violations.append(cmd)

        assert not violations, (
            f"Template {template_name} still uses --show-toplevel which breaks "
            f"in git worktrees (Issue #651). Use "
            f'$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)") '
            f"instead:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    @pytest.mark.parametrize("template_name", TEMPLATE_FILES)
    def test_git_common_dir_uses_absolute_format(self, template_name: str) -> None:
        """--git-common-dir must use --path-format=absolute to avoid relative paths.

        Without --path-format=absolute, git rev-parse --git-common-dir returns
        a relative path ('.git') in the main repo, which breaks dirname resolution.
        """
        template_path = TEMPLATES_DIR / template_name
        if not template_path.exists():
            pytest.skip(f"Template {template_name} not found")

        settings = json.loads(template_path.read_text())
        commands = _extract_hook_commands(settings)

        violations = []
        for cmd in commands:
            # If using --git-common-dir, must also use --path-format=absolute
            if "--git-common-dir" in cmd and "--path-format=absolute" not in cmd:
                violations.append(cmd)

        assert not violations, (
            f"Template {template_name} uses --git-common-dir without "
            f"--path-format=absolute (Issue #651). The relative path '.git' "
            f"returned in normal repos breaks dirname resolution:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    @pytest.mark.parametrize("template_name", TEMPLATE_FILES)
    def test_worktree_safe_pattern_used(self, template_name: str) -> None:
        """Commands using git rev-parse for paths must use the worktree-safe pattern.

        The correct pattern is:
          $(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")

        This resolves to the main repo root in both normal repos and worktrees.
        """
        template_path = TEMPLATES_DIR / template_name
        if not template_path.exists():
            pytest.skip(f"Template {template_name} not found")

        settings = json.loads(template_path.read_text())
        commands = _extract_hook_commands(settings)

        # Pattern: commands that reference plugin hooks (not ~/... paths or echo)
        worktree_safe_pattern = re.compile(
            r'\$\(dirname\s+.*\$\(git\s+rev-parse\s+--path-format=absolute\s+--git-common-dir\)'
        )

        for cmd in commands:
            # Skip ~/... paths and echo commands - they don't use git rev-parse
            if cmd.startswith("echo") or "git rev-parse" not in cmd:
                continue

            assert worktree_safe_pattern.search(cmd), (
                f"Command in {template_name} uses git rev-parse but not the "
                f"worktree-safe pattern (Issue #651):\n"
                f"  Got: {cmd}\n"
                f"  Expected pattern: $(dirname \"$(git rev-parse "
                f"--path-format=absolute --git-common-dir)\")/..."
            )

    def test_home_dir_paths_not_affected(self) -> None:
        """Paths starting with ~/ must remain unchanged (already absolute)."""
        for template_name in TEMPLATE_FILES:
            template_path = TEMPLATES_DIR / template_name
            if not template_path.exists():
                continue

            settings = json.loads(template_path.read_text())
            commands = _extract_hook_commands(settings)

            for cmd in commands:
                # ~/... paths should NOT contain git rev-parse
                if "~/" in cmd and not cmd.startswith("echo"):
                    # The ~ path part itself should not be wrapped in git rev-parse
                    assert "git rev-parse" not in cmd, (
                        f"Home dir path was incorrectly modified in "
                        f"{template_name}: {cmd}"
                    )
