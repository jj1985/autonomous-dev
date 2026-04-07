#!/usr/bin/env -S uv run --script --quiet --no-project
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
CLAUDE.md Size Guard Hook

Warns when CLAUDE.md exceeds 200 lines (Anthropic best practice).
This is a NON-BLOCKING warning-only hook — always exits 0.

What it checks:
- Whether CLAUDE.md exists in the repo root
- Whether CLAUDE.md exceeds 200 lines

If CLAUDE.md is missing, silently passes (no output).
If CLAUDE.md exceeds 200 lines, prints a warning to stderr.

Usage:
    Add to settings.local.json or settings.autonomous-dev.json PreCommit hooks:
    {
      "hooks": {
        "PreCommit": [
          {
            "type": "command",
            "command": "python \"$(git rev-parse --show-toplevel)/plugins/autonomous-dev/hooks/validate_claude_md_size.py\""
          }
        ]
      }
    }

Exit codes:
- 0: Always (non-blocking warning hook)
"""

import sys
from pathlib import Path
from typing import Tuple

MAX_LINES = 200


def get_repo_root() -> Path:
    """Find repository root by traversing up to .git directory."""
    current = Path.cwd()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return Path.cwd()


def check_claude_md_size(repo_root: Path) -> Tuple[int, str]:
    """Check CLAUDE.md size and return (line_count, warning_message).

    Args:
        repo_root: Path to the repository root directory.

    Returns:
        Tuple of (line_count, warning_message).
        line_count is 0 if CLAUDE.md not found.
        warning_message is empty string if no warning needed.
    """
    claude_md_path = repo_root / "CLAUDE.md"

    if not claude_md_path.exists():
        return 0, ""

    content = claude_md_path.read_text(encoding="utf-8")
    line_count = len(content.splitlines())

    if line_count <= MAX_LINES:
        return line_count, ""

    warning = (
        f"WARNING: CLAUDE.md is {line_count} lines "
        f"(Anthropic best practice: keep under {MAX_LINES}). "
        f"Current: {line_count}/{MAX_LINES}"
    )
    return line_count, warning


def main() -> int:
    """Run CLAUDE.md size check.

    Returns:
        Always 0 (non-blocking warning hook).
    """
    repo_root = get_repo_root()
    line_count, warning = check_claude_md_size(repo_root)

    if warning:
        print(warning, file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
