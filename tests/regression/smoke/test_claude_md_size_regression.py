"""
Regression smoke test: CLAUDE.md must stay under 200 lines.

This test reads the actual CLAUDE.md from the repository root and asserts
it is <= 200 lines, enforcing the Anthropic best practice for CLAUDE.md size.

If this test fails, trim CLAUDE.md by removing outdated instructions,
consolidating sections, or moving detail to docs/.
"""

from pathlib import Path


def test_claude_md_does_not_exceed_200_lines() -> None:
    """CLAUDE.md in the repo root must be <= 200 lines.

    Anthropic recommends keeping CLAUDE.md concise so that Claude Code
    can efficiently load and process it. Over 200 lines indicates context
    bloat that should be trimmed or relocated to docs/.
    """
    repo_root = Path(__file__).resolve().parents[3]
    claude_md_path = repo_root / "CLAUDE.md"

    assert claude_md_path.exists(), (
        f"CLAUDE.md not found at {claude_md_path}.\n"
        f"Expected CLAUDE.md at repository root: {repo_root}"
    )

    content = claude_md_path.read_text(encoding="utf-8")
    line_count = len(content.splitlines())

    assert line_count <= 200, (
        f"CLAUDE.md is {line_count} lines — exceeds the 200-line limit.\n"
        f"\n"
        f"Anthropic best practice: keep CLAUDE.md under 200 lines for efficient\n"
        f"context loading. Current: {line_count}/200 lines.\n"
        f"\n"
        f"File: {claude_md_path}\n"
        f"\n"
        f"How to fix:\n"
        f"  1. Remove outdated or redundant instructions\n"
        f"  2. Move detailed docs to docs/ and link from CLAUDE.md\n"
        f"  3. Consolidate similar sections\n"
        f"  4. Delete sections no longer relevant to day-to-day use"
    )
