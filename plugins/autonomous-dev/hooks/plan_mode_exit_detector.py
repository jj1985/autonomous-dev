#!/usr/bin/env -S uv run --script --quiet --no-project
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Plan Mode Exit Detector - Writes marker when ExitPlanMode tool is used.

Hook: PostToolUse (runs after every tool call)

When the model exits plan mode (ExitPlanMode tool), this hook writes a
marker file at `.claude/plan_mode_exit.json` containing:
- timestamp: ISO 8601 UTC timestamp
- session_id: Current session ID from environment

The marker is consumed by unified_prompt_validator.py to enforce that
the next action uses /implement or /create-issue (not raw edits).

Exit codes:
    0: Always (PostToolUse cannot block)
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


MARKER_PATH = ".claude/plan_mode_exit.json"


def main() -> int:
    """
    Main hook entry point.

    Reads stdin for PostToolUse hook input. If the tool_name is
    "ExitPlanMode", writes the plan mode exit marker file.

    Returns:
        0: Always (non-blocking hook)
    """
    try:
        input_data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, Exception):
        return 0

    tool_name = input_data.get("tool_name", "")

    if tool_name != "ExitPlanMode":
        return 0

    # Write marker file
    try:
        marker_path = Path(os.getcwd()) / MARKER_PATH
        marker_path.parent.mkdir(parents=True, exist_ok=True)

        marker_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": os.environ.get("CLAUDE_SESSION_ID", "unknown"),
        }

        marker_path.write_text(json.dumps(marker_data, indent=2))
    except Exception:
        # Never block on marker write failure
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
