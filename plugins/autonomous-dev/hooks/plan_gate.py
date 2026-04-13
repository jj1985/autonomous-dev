#!/usr/bin/env -S uv run --script --quiet --no-project
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Plan Gate - Pre-implementation planning enforcement hook.

Blocks complex Write/Edit operations when no valid plan exists in
.claude/plans/. Follows stick+carrot pattern: blocks with a clear
REQUIRED NEXT ACTION directive pointing to /plan.

Detection strategy:
1. Check if tool is Write or Edit (other tools pass through)
2. Exempt documentation files (.md, CHANGELOG, README, docs/)
3. Check complexity threshold (simple edits < 100 lines pass through)
4. Validate plan exists in .claude/plans/ with required sections
5. Block if no valid plan, with actionable message

Escape hatch: SKIP_PLAN_CHECK=1 environment variable disables all checks.

Exit codes:
    0: Allow (plan valid, doc file, simple edit, or exception/fail-open)

Output: JSON to stdout with hookSpecificOutput for Claude Code hook protocol.

Part of Issue #814: Planning workflow system.
"""

import json
import os
import sys
from pathlib import Path


# Simple edit threshold -- edits with fewer lines than this are never blocked
SIMPLE_EDIT_LINE_THRESHOLD = 100

# Documentation file patterns that are always allowed
DOC_EXTENSIONS = {".md", ".rst", ".txt"}
DOC_PATHS = {"docs/", "doc/", "documentation/"}
DOC_FILENAMES = {"CHANGELOG", "README", "LICENSE", "CONTRIBUTING", "AUTHORS"}


def _output_decision(
    decision: str,
    reason: str,
    *,
    system_message: str = "",
) -> None:
    """Print hook "decision" as JSON to stdout.

    Uses the Claude Code hook protocol format with permissionDecision field.
    The "decision" value is either "allow" or "block".

    Args:
        decision: "allow" or "block"
        reason: Human-readable reason for the decision
        system_message: Optional message shown to the user
    """
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }
    if system_message:
        output["systemMessage"] = system_message
    print(json.dumps(output))


def _is_doc_file(file_path: str) -> bool:
    """Check if a file path is a documentation file (always allowed).

    Args:
        file_path: Path to check.

    Returns:
        True if the file is a documentation file.
    """
    path = Path(file_path)

    # Check extension
    if path.suffix.lower() in DOC_EXTENSIONS:
        return True

    # Check if in docs directory
    normalized = file_path.replace("\\", "/")
    for doc_path in DOC_PATHS:
        if normalized.startswith(doc_path) or f"/{doc_path}" in normalized:
            return True

    # Check filename (without extension)
    if path.stem.upper() in DOC_FILENAMES:
        return True

    return False


def _is_simple_edit(tool_name: str, tool_input: dict) -> bool:
    """Check if this is a simple edit below the complexity threshold.

    Simple edits (< 100 lines of new content) are never blocked.

    Args:
        tool_name: The tool being used (Write or Edit).
        tool_input: The tool's input parameters.

    Returns:
        True if the edit is simple enough to skip plan check.
    """
    if tool_name == "Edit":
        new_string = tool_input.get("new_string", "")
        if new_string.count("\n") < SIMPLE_EDIT_LINE_THRESHOLD:
            return True
    elif tool_name == "Write":
        content = tool_input.get("content", "")
        if content.count("\n") < SIMPLE_EDIT_LINE_THRESHOLD:
            return True
    return False


def main() -> int:
    """Main hook entry point.

    Reads PreToolUse hook input from stdin, validates plan existence,
    and outputs JSON decision to stdout.

    Returns:
        0 always (decision communicated via stdout JSON)
    """
    try:
        # Parse stdin
        try:
            input_data = json.loads(sys.stdin.read())
        except (json.JSONDecodeError, Exception):
            # Fail-open: invalid input -> allow
            _output_decision("allow", "Plan gate: invalid input, fail-open")
            return 0

        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})

        # Only check Write and Edit tools
        if tool_name not in ("Write", "Edit"):
            _output_decision("allow", f"Plan gate: tool {tool_name} not subject to plan check")
            return 0

        # SKIP_PLAN_CHECK=1 escape hatch
        if os.environ.get("SKIP_PLAN_CHECK") == "1":
            print("Plan gate: SKIP_PLAN_CHECK=1, bypassing all checks", file=sys.stderr)
            _output_decision("allow", "Plan gate: SKIP_PLAN_CHECK=1 bypass")
            return 0

        # Get file path from tool input
        file_path = tool_input.get("file_path", "") or tool_input.get("path", "")

        # Documentation files are always allowed
        if file_path and _is_doc_file(file_path):
            _output_decision("allow", f"Plan gate: doc file exemption for {file_path}")
            return 0

        # Simple edits (< threshold lines) are always allowed
        if _is_simple_edit(tool_name, tool_input):
            _output_decision("allow", "Plan gate: simple edit below threshold")
            return 0

        # Find and validate plan
        # Look for .claude/plans/ relative to git root or cwd
        plans_dir = _find_plans_dir()

        # Import plan_validator (add lib to path)
        hook_dir = Path(__file__).parent
        lib_path = hook_dir.parent / "lib"
        if lib_path.exists():
            sys.path.insert(0, str(lib_path))

        from plan_validator import find_latest_plan, validate_plan

        latest_plan = find_latest_plan(plans_dir)

        if latest_plan is None:
            # No plan file exists -- block
            block_msg = (
                "No planning document found. Complex code changes require a validated plan.\n\n"
                "REQUIRED NEXT ACTION: run /plan to create a planning document before making "
                "complex changes.\n\n"
                "The plan must contain these sections:\n"
                "  - WHY + SCOPE\n"
                "  - Existing Solutions\n"
                "  - Minimal Path\n\n"
                "Escape hatch: set SKIP_PLAN_CHECK=1 to bypass this check."
            )
            _output_decision("block", "Plan gate: no plan file found", system_message=block_msg)
            return 0

        # Validate plan contents
        result = validate_plan(latest_plan)

        if not result.valid:
            missing = ", ".join(result.missing_sections)
            block_msg = (
                f"Plan file exists but is missing required sections: {missing}\n\n"
                "REQUIRED NEXT ACTION: run /plan to update the planning document with "
                "all required sections.\n\n"
                "Required sections:\n"
                "  - WHY + SCOPE\n"
                "  - Existing Solutions\n"
                "  - Minimal Path\n\n"
                "Escape hatch: set SKIP_PLAN_CHECK=1 to bypass this check."
            )
            _output_decision(
                "block",
                f"Plan gate: plan missing sections: {missing}",
                system_message=block_msg,
            )
            return 0

        # Plan is valid -- check expiry (warn only, do not block)
        if result.expired:
            print(
                f"WARNING: Plan is {result.age_hours:.1f} hours old (>72h). "
                f"Consider refreshing with /plan.",
                file=sys.stderr,
            )

        _output_decision("allow", f"Plan gate: valid plan found at {latest_plan}")
        return 0

    except Exception as e:
        # Fail-open: any exception -> allow
        print(f"Plan gate exception (fail-open): {e}", file=sys.stderr)
        _output_decision("allow", f"Plan gate: exception occurred, fail-open: {e}")
        return 0


def _find_plans_dir() -> Path:
    """Find the .claude/plans/ directory.

    Checks cwd first, then walks up to find git root.

    Returns:
        Path to the plans directory (may not exist yet).
    """
    cwd = Path(os.getcwd())

    # Check cwd
    plans_dir = cwd / ".claude" / "plans"
    if plans_dir.exists():
        return plans_dir

    # Walk up to find git root
    current = cwd
    while current != current.parent:
        if (current / ".git").exists():
            return current / ".claude" / "plans"
        current = current.parent

    # Fallback to cwd
    return cwd / ".claude" / "plans"


if __name__ == "__main__":
    sys.exit(main())
