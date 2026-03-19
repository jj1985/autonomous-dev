#!/usr/bin/env -S uv run --script --quiet --no-project
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Unified PreToolUse Hook - Consolidated Permission & Security Validation

This hook consolidates four PreToolUse validators into a single dispatcher:
0. Sandbox Enforcer (sandbox_enforcer.py) - Command classification & sandboxing (Issue #171)
1. MCP Security Validator (pre_tool_use.py) - Path traversal, injection, SSRF protection
2. Agent Authorization (enforce_implementation_workflow.py) - Pipeline agent detection
3. Batch Permission Approver (batch_permission_approver.py) - Permission batching

Native Tool Fast Path:
- Native Claude Code tools (Read, Write, Edit, Bash, Task, etc.) bypass all 4 validation layers
- These tools are governed by settings.json permissions, not by this hook
- This avoids unwanted permission prompts for built-in tools
- See NATIVE_TOOLS set below for complete list

Decision Logic:
- If tool is native → skip all layers, return "allow" (settings.json governs)
- If ANY validator returns "deny" → output "deny" (block operation)
- If ALL validators return "allow" → output "allow" (approve operation)
- Otherwise → output "ask" (prompt user)

Layer Execution Order (short-circuit on deny):
0. Layer 0 (Sandbox): Command classification (SAFE → auto-approve, BLOCKED → deny, NEEDS_APPROVAL → continue)
1. Layer 1 (MCP Security): Path traversal, injection, SSRF checks
2. Layer 2 (Agent Auth): Pipeline agent detection
3. Layer 3 (Batch Permission): Permission batching

Environment Variables:
- SANDBOX_ENABLED: Enable/disable sandbox layer (default: false for opt-in)
- SANDBOX_PROFILE: Sandbox profile (default: development)
- PRE_TOOL_MCP_SECURITY: Enable/disable MCP security (default: true)
- PRE_TOOL_AGENT_AUTH: Enable/disable agent authorization (default: true)
- PRE_TOOL_BATCH_PERMISSION: Enable/disable batch permission (default: false)
- MCP_AUTO_APPROVE: Enable/disable auto-approval (default: false)

Input (stdin):
{
  "tool_name": "Bash",
  "tool_input": {"command": "pytest tests/"}
}

Output (stdout):
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow|deny|ask",
    "permissionDecisionReason": "Combined validator reasons"
  }
}

Exit code: 0 (always - let Claude Code process the decision)

Date: 2026-01-02
Issue: GitHub #171 (Sandboxing for reduced permission prompts)
Agent: implementer
"""

import importlib.util
import json
import shlex
import sys
import os
from pathlib import Path
from typing import Dict, Tuple, List

# Module-level session_id extracted from hook stdin (set in main()).
# Logging functions fall back to this when CLAUDE_SESSION_ID env var is absent.
_session_id: str = "unknown"


def is_running_under_uv() -> bool:
    """Detect if script is running under UV."""
    return "UV_PROJECT_ENVIRONMENT" in os.environ

def find_lib_directory(hook_path: Path) -> Path | None:
    """
    Find lib directory dynamically (Issue #113).

    Checks multiple locations in order:
    1. Development: plugins/autonomous-dev/lib (relative to hook)
    2. Local install: ~/.claude/lib
    3. Marketplace: ~/.claude/plugins/autonomous-dev/lib

    Args:
        hook_path: Path to this hook script

    Returns:
        Path to lib directory if found, None otherwise (graceful failure)
    """
    # Try development location first
    dev_lib = hook_path.parent.parent / "lib"
    if dev_lib.exists() and dev_lib.is_dir():
        return dev_lib

    # Try local install
    home = Path.home()
    local_lib = home / ".claude" / "lib"
    if local_lib.exists() and local_lib.is_dir():
        return local_lib

    # Try marketplace location
    marketplace_lib = home / ".claude" / "plugins" / "autonomous-dev" / "lib"
    if marketplace_lib.exists() and marketplace_lib.is_dir():
        return marketplace_lib

    return None


# Add lib directory to path dynamically
LIB_DIR = find_lib_directory(Path(__file__))
if LIB_DIR:
    if not is_running_under_uv():
        sys.path.insert(0, str(LIB_DIR))


def load_env():
    """Load .env file from project root if it exists."""
    env_file = Path(os.getcwd()) / ".env"
    if env_file.exists():
        try:
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        if key not in os.environ:
                            os.environ[key] = value
        except Exception:
            pass  # Silently skip


# Agents authorized for code changes (pipeline agents)
# Issue #147: Consolidated to only active agents that write code/tests/docs
PIPELINE_AGENTS = [
    'implementer',
    'test-master',
    'doc-master',
]

# Code file extensions subject to workflow enforcement
CODE_EXTENSIONS = {
    '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go', '.rs',
    '.c', '.cpp', '.h', '.hpp', '.cs', '.rb', '.php', '.swift',
    '.kt', '.scala', '.sh', '.bash', '.zsh', '.vue', '.svelte',
}

# Language-specific pattern groups for code significance detection
PATTERN_GROUPS = {
    'python': {
        'extensions': {'.py'},
        'patterns': [
            (r'\bdef\s+\w+\s*\(', 'Python function'),
            (r'\basync\s+def\s+\w+\s*\(', 'Python async function'),
            (r'\bclass\s+\w+', 'Python class'),
        ]
    },
    'javascript': {
        'extensions': {'.js', '.ts', '.jsx', '.tsx', '.vue', '.svelte'},
        'patterns': [
            (r'\bfunction\s+\w+\s*\(', 'JavaScript function'),
            (r'\basync\s+function\s+\w+\s*\(', 'JavaScript async function'),
            (r'\bconst\s+\w+\s*=\s*(?:async\s*)?\(.*?\)\s*=>', 'Arrow function'),
            (r'\bexport\s+(?:default\s+)?(?:function|class|const)', 'JS export'),
            (r'\bclass\s+\w+', 'JavaScript class'),
        ]
    },
    'shell': {
        'extensions': {'.sh', '.bash', '.zsh'},
        'patterns': [
            (r'\bfunction\s+\w+', 'Shell function'),
        ]
    },
    'go': {
        'extensions': {'.go'},
        'patterns': [
            (r'\bfunc\s+(?:\(\w+\s+\*?\w+\)\s+)?\w+\s*\(', 'Go function'),
        ]
    },
    'rust': {
        'extensions': {'.rs'},
        'patterns': [
            (r'\bfn\s+\w+\s*[<(]', 'Rust function'),
            (r'\bimpl\s+', 'Rust impl block'),
        ]
    },
    'universal': {
        'extensions': None,  # None means applies to ALL code extensions
        'patterns': [
            (r'\btry:\s*\n\s+(?:from|import)\s+', 'Conditional import (try/except)'),
            (r'\bif\s+\w+.*:\s*\n(?:\s+.*\n){3,}else:', 'Multi-branch conditional'),
        ]
    }
}

SIGNIFICANT_LINE_THRESHOLD = 5

# Git subcommands where -n means --no-verify (not a count flag)
_GIT_VERIFY_SUBCOMMANDS = {"push", "commit", "merge"}

# Git subcommands where -f means --force (not something else)
_GIT_FORCE_PUSH_SUBCOMMANDS = {"push"}


def _detect_git_bypass(command: str) -> Tuple[bool, str]:
    """Detect git bypass patterns in a command string.

    Checks for --no-verify, --force on push, git reset --hard,
    git clean -f/-fd, and the -n shorthand on push/commit/merge.

    Handles pipes by only parsing the segment before the first pipe.

    Args:
        command: The shell command string to analyze.

    Returns:
        Tuple of (is_bypass, reason). If is_bypass is True, the command
        should be blocked.
    """
    # Only parse the first command in a pipeline
    pipe_idx = command.find("|")
    if pipe_idx >= 0:
        command = command[:pipe_idx]

    command = command.strip()
    if not command:
        return (False, "")

    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()

    if not tokens:
        return (False, "")

    # Find the git command and subcommand
    git_idx = None
    for i, token in enumerate(tokens):
        if token == "git" or token.endswith("/git"):
            git_idx = i
            break

    if git_idx is None:
        return (False, "")

    # Extract subcommand (first non-flag token after "git")
    subcommand = ""
    for token in tokens[git_idx + 1:]:
        if not token.startswith("-"):
            subcommand = token
            break

    remaining_tokens = tokens[git_idx + 1:]

    # Check --no-verify on any git command
    if "--no-verify" in remaining_tokens:
        return (True, f"git {subcommand} --no-verify bypasses pre-commit/pre-push hooks")

    # Check -n shorthand ONLY on push/commit/merge (not log/diff where it means count)
    if subcommand in _GIT_VERIFY_SUBCOMMANDS:
        for token in remaining_tokens:
            # Match -n as standalone flag or combined flags like -fn
            if token == "-n":
                return (True, f"git {subcommand} -n bypasses verification hooks")
            # Check combined short flags (e.g., -fn, -an) but not subcommand itself
            if token.startswith("-") and not token.startswith("--") and "n" in token and token != subcommand:
                return (True, f"git {subcommand} {token} contains -n (bypasses verification hooks)")

    # Check --force / -f ONLY on push
    if subcommand in _GIT_FORCE_PUSH_SUBCOMMANDS:
        if "--force" in remaining_tokens or "--force-with-lease" in remaining_tokens:
            return (True, f"git push --force can overwrite remote history")
        for token in remaining_tokens:
            if token == "-f":
                return (True, "git push -f can overwrite remote history")

    # Check git reset --hard
    if subcommand == "reset" and "--hard" in remaining_tokens:
        return (True, "git reset --hard discards all uncommitted changes")

    # Check git clean -f or git clean -fd
    if subcommand == "clean":
        for token in remaining_tokens:
            if token.startswith("-") and not token.startswith("--") and "f" in token:
                return (True, "git clean -f permanently deletes untracked files")
        if "--force" in remaining_tokens:
            return (True, "git clean --force permanently deletes untracked files")

    return (False, "")


def validate_sandbox_layer(tool_name: str, tool_input: Dict) -> Tuple[str, str]:
    """
    Validate sandbox layer (Layer 0) - command classification and sandboxing.

    Args:
        tool_name: Name of the tool being called
        tool_input: Tool input parameters

    Returns:
        Tuple of (decision, reason)
        - decision: "allow", "deny", or "ask"
        - reason: Human-readable reason for decision
    """
    # Check if sandbox is enabled
    enabled = os.getenv("SANDBOX_ENABLED", "false").lower() == "true"
    if not enabled:
        return ("allow", "Sandbox layer disabled - pass through")

    # Only validate Bash commands
    if tool_name != "Bash":
        return ("allow", "Sandbox layer only validates Bash commands - pass through")

    # Extract command from tool_input
    command = tool_input.get("command", "")
    if not command:
        return ("allow", "No command to validate - pass through")

    try:
        # Try to import sandbox enforcer
        try:
            from sandbox_enforcer import SandboxEnforcer, CommandClassification

            # Create enforcer
            enforcer = SandboxEnforcer(policy_path=None, profile=None)

            # Classify command
            result = enforcer.is_command_safe(command)

            if result.classification == CommandClassification.SAFE:
                # Safe command - auto-approve
                return ("allow", "Sandbox: SAFE command auto-approved")
            elif result.classification == CommandClassification.BLOCKED:
                # Blocked command - deny
                return ("deny", f"Sandbox: BLOCKED - {result.reason}")
            else:  # NEEDS_APPROVAL
                # Unknown command - continue to next layer
                return ("ask", "Sandbox: NEEDS_APPROVAL - unknown command")

        except ImportError:
            # Sandbox enforcer not available - continue to next layer
            return ("ask", "Sandbox enforcer unavailable")

    except Exception as e:
        # Error in validation - continue to next layer (don't block on errors)
        return ("ask", f"Sandbox error: {e}")


NATIVE_TOOLS = {
    "Read", "Write", "Edit", "Glob", "Grep", "Bash",
    "Task", "TaskOutput", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet", "TaskStop",
    "AskUserQuestion", "Skill", "SlashCommand", "BashOutput", "NotebookEdit",
    "TodoWrite", "EnterPlanMode", "ExitPlanMode", "AgentOutputTool", "KillShell",
    "LSP", "WebFetch", "WebSearch",
    "Agent", "EnterWorktree", "ExitWorktree", "ToolSearch",
    "CronCreate", "CronDelete", "CronList",
}

# Infrastructure file segments protected from direct edits (Issue #483)
# Maps directory path segments to allowed file extensions within that segment.
PROTECTED_INFRA_SEGMENTS = {
    '/agents/': {'.md'},
    '/commands/': {'.md'},
    '/hooks/': {'.py'},
    '/lib/': {'.py'},
    '/skills/': {'.md'},
}


def validate_mcp_security(tool_name: str, tool_input: Dict) -> Tuple[str, str]:
    """
    Validate MCP security (path traversal, injection, SSRF).

    Args:
        tool_name: Name of the tool being called
        tool_input: Tool input parameters

    Returns:
        Tuple of (decision, reason)
        - decision: "allow", "deny", or "ask"
        - reason: Human-readable reason for decision
    """
    # Native Claude Code tools skip MCP security (not MCP tools)
    if tool_name in NATIVE_TOOLS:
        return ("allow", f"Native tool '{tool_name}' - MCP security not applicable")

    # Check if MCP security is enabled
    enabled = os.getenv("PRE_TOOL_MCP_SECURITY", "true").lower() == "true"
    if not enabled:
        return ("allow", "MCP security disabled")

    try:
        # Try to import MCP security validator
        try:
            from mcp_security_validator import validate_mcp_operation

            # Validate the operation
            is_safe, reason = validate_mcp_operation(tool_name, tool_input)

            if not is_safe:
                # Security risk detected
                return ("deny", f"MCP Security: {reason}")
            else:
                return ("allow", f"MCP Security: {reason}")

        except ImportError:
            # MCP security validator not available — default to allow.
            # Previously this fell through to auto_approval_engine which used
            # an allow-list (auto_approve_policy.json). That caused recurring
            # "Not whitelisted" regressions every time Claude Code added new
            # tools. Default-allow with deny-only-on-security is simpler and
            # eliminates that entire class of regressions (Issue #401).
            return ("allow", "MCP security validator unavailable — default allow")

    except Exception as e:
        # Error in validation — default to allow (Issue #401).
        # Security validator errors should not block the user.
        return ("allow", f"MCP security error — default allow: {e}")


def _is_exempt_path(file_path: str) -> bool:
    """Check if file is exempt from workflow enforcement (tests, docs, configs)."""
    if not file_path:
        return False
    path = Path(file_path)
    path_str = str(path).lower()
    # Test files
    if ('test_' in path_str or '_test.' in path_str or '.test.' in path_str
            or path_str.startswith('tests/') or path_str.startswith('test/')):
        return True
    # Docs, configs, hooks, scripts, lib, agents, commands
    if path.suffix.lower() in {'.md', '.txt', '.rst', '.json', '.yaml', '.yml', '.toml', '.env', '.ini', '.cfg'}:
        return True
    if any(s in path_str for s in ['.claude/hooks/', 'hooks/', '/lib/', 'lib/', '.claude/agents/',
                                    '.claude/commands/', '.claude/skills/', 'scripts/']):
        return True
    return False


def _is_autonomous_dev_repo(file_path: str) -> bool:
    """Check if file is inside a repo where autonomous-dev is installed.

    Walks up from file_path looking for .claude/commands/implement.md,
    which only exists in repos with the autonomous-dev plugin installed.

    Args:
        file_path: Absolute path to check

    Returns:
        True if file is inside an autonomous-dev-managed repo
    """
    try:
        current = Path(file_path).resolve().parent
    except (OSError, ValueError):
        return False
    # Walk up at most 10 levels to find repo root
    for _ in range(10):
        marker = current / ".claude" / "commands" / "implement.md"
        if marker.exists():
            return True
        parent = current.parent
        if parent == current:
            break
        current = parent
    return False


def _is_protected_infrastructure(file_path: str) -> bool:
    """Check if file is a protected infrastructure file (agents, commands, hooks, lib, skills).

    Protected files require the /implement pipeline for edits.
    Only applies to repos where autonomous-dev is installed — other repos are unaffected.

    Args:
        file_path: Path to the file being edited

    Returns:
        True if the file is in a protected directory with matching extension
    """
    if not file_path:
        return False
    # Resolve symlinks and normalize to absolute path for security (A01)
    try:
        resolved = str(Path(file_path).resolve())
    except (OSError, ValueError):
        resolved = file_path
    # Only protect infrastructure in autonomous-dev repos (not all repos globally)
    if not _is_autonomous_dev_repo(resolved):
        return False
    # Normalize separators to forward slashes for consistent matching
    normalized = resolved.replace("\\", "/")
    # Extensions directory is user-owned — never protected
    if "/extensions/" in normalized:
        return False
    # Ensure leading slash or check for bare directory name at start
    for segment, extensions in PROTECTED_INFRA_SEGMENTS.items():
        # segment is like '/agents/' — check both embedded and path-start forms
        bare = segment.lstrip("/")  # 'agents/'
        if segment in normalized or normalized.startswith(bare):
            ext = Path(file_path).suffix.lower()
            if ext in extensions:
                return True
    return False


def _is_pipeline_active() -> bool:
    """Check if the /implement pipeline is currently active.

    Checks two sources:
    1. CLAUDE_AGENT_NAME env var against known pipeline agents
    2. Pipeline state file (valid if < 2 hours old)

    Returns:
        True if pipeline is active
    """
    # Check agent name
    agent_name = os.getenv("CLAUDE_AGENT_NAME", "").strip().lower()
    if agent_name in PIPELINE_AGENTS:
        return True

    # Check pipeline state file
    pipeline_state_file = os.getenv("PIPELINE_STATE_FILE", "/tmp/implement_pipeline_state.json")
    try:
        state_path = Path(pipeline_state_file)
        if state_path.exists():
            import json as _json
            from datetime import datetime as _datetime
            with open(state_path) as f:
                state = _json.load(f)
            session_start = state.get("session_start", "")
            if session_start:
                start_time = _datetime.fromisoformat(session_start)
                elapsed = (_datetime.now() - start_time).total_seconds()
                if elapsed < 7200:  # 2 hours
                    return True
    except Exception:
        pass

    return False


def _has_significant_additions(old_string: str, new_string: str, file_path: str = "") -> tuple:
    """Check if the edit adds significant code (new functions, classes, >5 lines)."""
    import re
    old_string = old_string or ""
    new_string = new_string or ""

    file_ext = Path(file_path).suffix.lower() if file_path else ""

    # Collect applicable patterns
    applicable_patterns = []
    for group_name, group_data in PATTERN_GROUPS.items():
        extensions = group_data['extensions']
        if extensions is None:  # universal
            applicable_patterns.extend(group_data['patterns'])
        elif not file_ext:  # no file path = backward compat, use all
            applicable_patterns.extend(group_data['patterns'])
        elif file_ext in extensions:
            applicable_patterns.extend(group_data['patterns'])

    for pattern, desc in applicable_patterns:
        old_matches = len(re.findall(pattern, old_string, re.MULTILINE))
        new_matches = len(re.findall(pattern, new_string, re.MULTILINE))
        if new_matches > old_matches:
            match = re.search(pattern, new_string)
            if match:
                return True, f"New {desc} detected", match.group(0)[:60]

    old_lines = len(old_string.strip().split('\n')) if old_string.strip() else 0
    new_lines = len(new_string.strip().split('\n')) if new_string.strip() else 0
    added = max(0, new_lines - old_lines)
    if added >= SIGNIFICANT_LINE_THRESHOLD:
        return True, "Significant code change detected", f"+{added} lines"
    return False, "", ""


def _extract_bash_file_writes(command: str) -> list:
    """Extract file paths being written to by Bash command."""
    import re
    file_paths = []

    # Redirection (>, >>) — skip stderr redirects (2>, 2>>)
    redirect_pattern = r'(?<![0-9])[>]{1,2}\s+([^\s;&|]+)'
    for match in re.finditer(redirect_pattern, command):
        fp = match.group(1).strip()
        if fp not in {'/dev/null', '/dev/stderr', '/dev/stdout', '&1', '&2'}:
            file_paths.append(fp)

    # tee command
    tee_pattern = r'\btee\s+(?:-a\s+)?([^\s;&|]+)'
    for match in re.finditer(tee_pattern, command):
        file_paths.append(match.group(1).strip())

    # Heredoc redirect
    heredoc_pattern = r'<<\s*[\'"]?\w+[\'"]?\s*[>]{1,2}\s+([^\s;&|]+)'
    for match in re.finditer(heredoc_pattern, command):
        file_paths.append(match.group(1).strip())

    return file_paths


def _log_deviation(file_name: str, tool_name: str, reason: str) -> None:
    """Append deviation to .claude/logs/deviations.jsonl for analytics."""
    try:
        import json as _json
        from datetime import datetime as _dt
        log_dir = Path(os.getcwd()) / ".claude" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": _dt.now().isoformat(),
            "file": file_name,
            "tool": tool_name,
            "reason": reason,
            "session_id": os.getenv("CLAUDE_SESSION_ID") or _session_id,
        }
        with open(log_dir / "deviations.jsonl", "a") as f:
            f.write(_json.dumps(entry) + "\n")
    except Exception:
        pass  # Never fail the hook for logging


def validate_agent_authorization(tool_name: str, tool_input: Dict) -> Tuple[str, str]:
    """
    Validate agent authorization for code changes.

    Enforces /implement workflow for significant code changes.
    Enforcement level controlled by ENFORCEMENT_LEVEL env var:
    - off: always allow
    - warn: allow + log warning (default for backward compat)
    - suggest: ask (user-visible prompt) + include /implement suggestion in reason
    - block: deny significant changes outside pipeline

    Args:
        tool_name: Name of the tool being called
        tool_input: Tool input parameters

    Returns:
        Tuple of (decision, reason)
    """
    # Check if agent authorization is enabled
    enabled = os.getenv("PRE_TOOL_AGENT_AUTH", "true").lower() == "true"
    if not enabled:
        return ("allow", "Agent authorization disabled")

    # Check if pipeline is active (agent name or state file)
    if _is_pipeline_active():
        agent_name = os.getenv("CLAUDE_AGENT_NAME", "").strip().lower()
        if agent_name in PIPELINE_AGENTS:
            return ("allow", f"Pipeline agent '{agent_name}' authorized")
        return ("allow", "Active /implement pipeline detected via state file")

    # Only check Edit, Write, and Bash tools
    if tool_name not in ("Edit", "Write", "Bash"):
        return ("allow", f"Tool '{tool_name}' not subject to workflow enforcement")

    # Get enforcement level (default: suggest - nudge toward /implement)
    level = os.getenv("ENFORCEMENT_LEVEL", "suggest").strip().lower()
    if level == "off":
        return ("allow", "Workflow enforcement disabled (level: off)")

    # Get file path and check exemptions
    file_path = tool_input.get("file_path", "")
    if _is_exempt_path(file_path):
        return ("allow", f"File exempt from workflow enforcement: {Path(file_path).name}")
    if file_path and Path(file_path).suffix.lower() not in CODE_EXTENSIONS:
        return ("allow", "Non-code file, no enforcement needed")

    # Analyze the change for significance
    if tool_name == "Edit":
        old_string = tool_input.get("old_string", "")
        new_string = tool_input.get("new_string", "")
        is_significant, reason, details = _has_significant_additions(old_string, new_string, file_path)
    elif tool_name == "Write":
        content = tool_input.get("content", "")
        is_significant, reason, details = _has_significant_additions("", content, file_path)
    elif tool_name == "Bash":
        command = tool_input.get("command", "")
        if not command:
            return ("allow", "No command to check")
        # Git bypass detection (Issue #406)
        if "git" in command:
            is_bypass, bypass_reason = _detect_git_bypass(command)
            if is_bypass:
                return ("deny", f"GIT BYPASS BLOCKED: {bypass_reason}")
        target_files = _extract_bash_file_writes(command)
        if not target_files:
            return ("allow", "No file writes detected in Bash command")
        # Check each target file for code file enforcement
        for fp in target_files:
            if _is_exempt_path(fp):
                continue
            if Path(fp).suffix.lower() not in CODE_EXTENSIONS:
                continue
            # Code file write detected via Bash
            file_name = Path(fp).name
            tip = "Tip: /implement handles testing, review, and docs automatically."
            if level == "warn":
                import sys as _sys
                _sys.stderr.write(f"WARNING: Bash file write to code file: {file_name}\n")
                _sys.stderr.flush()
                _log_deviation(file_name, tool_name, "Bash file write to code file")
                return ("allow", f"Bash file write detected ({file_name}), allowed at WARN level")
            elif level == "suggest":
                _log_deviation(file_name, tool_name, "Bash file write to code file")
                return ("ask", f"Bash file write to code file {file_name}. {tip}")
            elif level == "block":
                return ("deny", f"WORKFLOW ENFORCEMENT: Bash file write to code file {file_name}. "
                        f"Significant code changes require /implement workflow. {tip}")
        return ("allow", "Bash command writes only to non-code/exempt files")
    else:
        return ("allow", f"Tool '{tool_name}' allowed")

    if not is_significant:
        return ("allow", "Minor edit, no significant code additions detected")

    file_name = Path(file_path).name if file_path else "unknown"
    tip = "Tip: /implement handles testing, review, and docs automatically."

    if level == "warn":
        import sys as _sys
        _sys.stderr.write(f"WARNING: {reason} in {file_name}\n")
        _sys.stderr.flush()
        _log_deviation(file_name, tool_name, reason)
        return ("allow", f"{reason} in {file_name}, allowed at WARN level")

    elif level == "suggest":
        _log_deviation(file_name, tool_name, reason)
        return ("ask", f"{reason} in {file_name}. "
                f"Use /implement for this change:\n"
                f"- /implement \"description\"\n"
                f"- /implement --quick \"description\" (skip full pipeline)\n"
                f"- /implement #<issue-number>")

    elif level == "block":
        return ("deny", f"WORKFLOW ENFORCEMENT: {reason} in {file_name}. "
                f"Significant code changes require /implement workflow. "
                f"STOP coding directly and run: /implement --quick \"description\"\n"
                f"Use /implement for this change:\n"
                f"- /implement \"description\"\n"
                f"- /implement --quick \"description\" (skip full pipeline)\n"
                f"- /implement #<issue-number>")

    return ("allow", f"Tool '{tool_name}' allowed")


def validate_batch_permission(tool_name: str, tool_input: Dict) -> Tuple[str, str]:
    """
    Validate batch permission for auto-approval.

    Args:
        tool_name: Name of the tool being called
        tool_input: Tool input parameters

    Returns:
        Tuple of (decision, reason)
        - decision: "allow", "deny", or "ask"
        - reason: Human-readable reason for decision
    """
    # Check if batch permission is enabled
    enabled = os.getenv("PRE_TOOL_BATCH_PERMISSION", "false").lower() == "true"
    if not enabled:
        return ("allow", "Batch permission disabled")

    try:
        # Try to import permission classifier
        try:
            from permission_classifier import PermissionClassifier, PermissionLevel

            # Classify operation
            classifier = PermissionClassifier()
            level = classifier.classify(tool_name, tool_input)

            if level == PermissionLevel.SAFE:
                return ("allow", f"Batch permission: SAFE operation auto-approved")
            elif level == PermissionLevel.BOUNDARY:
                return ("allow", f"Batch permission: BOUNDARY operation allowed")
            else:  # PermissionLevel.SENSITIVE
                return ("ask", f"Batch permission: SENSITIVE operation requires user approval")

        except ImportError:
            # Permission classifier not available - allow (don't block)
            return ("allow", "Batch permission classifier unavailable")

    except Exception as e:
        # Error in validation - allow (don't block on errors)
        return ("allow", f"Batch permission error: {e}")


def combine_decisions(validators_results: List[Tuple[str, str, str]]) -> Tuple[str, str]:
    """
    Combine multiple validator decisions into single decision.

    Decision Logic:
    - If ANY validator returns "deny" → "deny" (block operation)
    - If ALL validators return "allow" → "allow" (approve operation)
    - Otherwise → "ask" (prompt user)

    Args:
        validators_results: List of (validator_name, decision, reason) tuples

    Returns:
        Tuple of (final_decision, combined_reason)
    """
    decisions = []
    reasons = []

    for validator_name, decision, reason in validators_results:
        decisions.append(decision)
        reasons.append(f"[{validator_name}] {reason}")

    # If ANY deny → deny
    if "deny" in decisions:
        deny_reasons = [r for v, d, r in validators_results if d == "deny"]
        return ("deny", "; ".join(deny_reasons))

    # If ALL allow → allow
    if all(d == "allow" for d in decisions):
        return ("allow", "; ".join(reasons))

    # Otherwise → ask
    ask_reasons = [r for v, d, r in validators_results if d == "ask"]
    if ask_reasons:
        return ("ask", "; ".join(ask_reasons))
    else:
        return ("ask", "; ".join(reasons))


def _log_pretool_activity(tool_name: str, tool_input: Dict, decision: str, reason: str) -> None:
    """Log PreToolUse decision to shared activity log."""
    try:
        import json as _json
        from datetime import datetime as _dt, timezone as _tz
        log_dir = Path(os.getcwd()) / ".claude" / "logs" / "activity"
        log_dir.mkdir(parents=True, exist_ok=True)
        date_str = _dt.now().strftime("%Y-%m-%d")

        # Build a compact summary of what's being done
        summary = {"tool": tool_name}
        if tool_name in ("Edit", "Write"):
            summary["file"] = tool_input.get("file_path", "")
        elif tool_name == "Bash":
            cmd = tool_input.get("command", "")
            summary["command"] = cmd[:200] if len(cmd) > 200 else cmd
        elif tool_name in ("Task", "Agent"):
            summary["subagent"] = tool_input.get("subagent_type", "")
            summary["description"] = tool_input.get("description", "")
        elif tool_name == "Skill":
            summary["skill"] = tool_input.get("skill", "")

        entry = {
            "timestamp": _dt.now(_tz.utc).isoformat(),
            "hook": "PreToolUse",
            "decision": decision,
            "reason": reason[:300],
            "session_id": os.getenv("CLAUDE_SESSION_ID") or _session_id,
            "agent": os.environ.get("CLAUDE_AGENT_NAME", "main"),
            **summary,
        }
        with open(log_dir / f"{date_str}.jsonl", "a") as f:
            f.write(_json.dumps(entry, separators=(",", ":")) + "\n")
    except Exception:
        pass


def output_decision(decision: str, reason: str, *, system_message: str = ""):
    """Output the hook decision in required format.

    Args:
        decision: Permission decision ("allow", "deny", or "ask")
        reason: Human-readable reason for the decision
        system_message: Optional message injected into model context (visible to user)
    """
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason
        }
    }
    if system_message:
        output["systemMessage"] = system_message
    print(json.dumps(output))


def _check_bash_infra_writes(command: str) -> "Optional[Tuple[str, str]]":
    """Check if a Bash command writes to protected infrastructure paths.

    Conservative detection: false negatives OK, false positives NOT OK.
    Returns None if allowed, or (file_name, block_reason) if blocked.

    Detects: sed -i, cp/mv to protected paths, shell redirects (>, >>),
    tee to protected paths, python3 -c with open(..., 'w').

    Args:
        command: The Bash command string to inspect.

    Returns:
        None if the command is allowed, or a tuple of (file_name, reason)
        if it should be blocked.
    """
    import re

    # If pipeline is active, allow everything (same as Write/Edit behavior)
    try:
        if _is_pipeline_active():
            return None
    except Exception:
        pass  # If check fails, continue with inspection

    # Collect candidate target file paths from various write patterns
    target_paths = []  # type: list

    # 1. sed -i (in-place edit)
    sed_pattern = r'\bsed\s+(?:-[^i]*)?-i[^\s]*\s+(?:[\'"][^\'"]*[\'\"]\s+)?([^\s;&|]+)'
    for match in re.finditer(sed_pattern, command):
        target_paths.append(match.group(1))

    # 2. cp / mv destination (last argument)
    # Match: cp [flags] source dest  OR  cp [flags] source1 source2 dest/
    cp_mv_pattern = r'\b(?:cp|mv)\s+(?:-[^\s]+\s+)*(?:[^\s]+\s+)+([^\s;&|]+)'
    for match in re.finditer(cp_mv_pattern, command):
        target_paths.append(match.group(1))

    # 3. Shell redirects (>, >>) — reuse existing helper
    redirect_targets = _extract_bash_file_writes(command)
    target_paths.extend(redirect_targets)

    # 4. python3 -c with open() writing — very conservative, only match explicit paths
    # Only flag if the python -c snippet contains open(...) with a protected path literal
    py_c_pattern = r'python3?\s+-c\s+[\'"]([^\'"]+)[\'"]'
    for match in re.finditer(py_c_pattern, command):
        snippet = match.group(1)
        # Look for open('path', 'w') patterns with protected paths
        open_pattern = r'open\s*\(\s*[\'"]([^\'"]+)[\'"]\s*,\s*[\'"][wa]'
        for open_match in re.finditer(open_pattern, snippet):
            target_paths.append(open_match.group(1))

    # Check each target path against protected infrastructure
    for fp in target_paths:
        fp = fp.strip().strip("'\"")
        if not fp:
            continue
        try:
            if _is_protected_infrastructure(fp):
                file_name = Path(fp).name
                block_reason = (
                    f"BLOCKED: Bash command writes to protected file '{file_name}'. "
                    f"Infrastructure files (agents/, commands/, hooks/, lib/, skills/) "
                    f"require the /implement pipeline. Run: /implement \"description\""
                )
                return (file_name, block_reason)
        except Exception:
            continue  # Skip paths that can't be resolved

    return None


def _run_extensions(tool_name: str, tool_input: Dict) -> Tuple[str, str]:
    """Run hook extension scripts that can block tool calls.

    Discovers *.py files in extensions/ directories (both alongside this hook
    and in the project's .claude/hooks/extensions/), loads each, and calls
    its ``check(tool_name, tool_input)`` function.

    Extensions survive /sync and /install — they are user-owned files in a
    directory that is never overwritten.

    Args:
        tool_name: Name of the tool being called.
        tool_input: Tool input parameters.

    Returns:
        Tuple of (decision, reason). ``("deny", reason)`` if any extension
        blocks; ``("allow", "")`` otherwise.
    """
    # Check kill-switch env var
    if os.getenv("HOOK_EXTENSIONS_ENABLED", "true").lower() == "false":
        return ("allow", "")

    # Discover extension directories
    ext_dirs: list[Path] = []

    # 1. Directory alongside this hook file (global ~/.claude/hooks/extensions/)
    hook_ext_dir = Path(__file__).parent / "extensions"
    ext_dirs.append(hook_ext_dir)

    # 2. Project-level .claude/hooks/extensions/
    project_ext_dir = Path.cwd() / ".claude" / "hooks" / "extensions"
    ext_dirs.append(project_ext_dir)

    # Collect extension files, deduplicated by filename (first occurrence wins)
    seen_names: set[str] = set()
    extension_files: list[Path] = []

    for ext_dir in ext_dirs:
        if not ext_dir.is_dir():
            continue
        try:
            py_files = sorted(ext_dir.glob("*.py"))
        except OSError:
            continue
        for py_file in py_files:
            # Skip symlinks (security)
            if py_file.is_symlink():
                continue
            if py_file.name in seen_names:
                continue
            seen_names.add(py_file.name)
            extension_files.append(py_file)

    # Execute each extension
    for ext_file in extension_files:
        try:
            module_name = f"_hook_ext_{ext_file.stem}"
            spec = importlib.util.spec_from_file_location(module_name, str(ext_file))
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            check_fn = getattr(module, "check", None)
            if check_fn is None:
                continue

            result = check_fn(tool_name, tool_input)

            # Validate return type
            if not isinstance(result, (tuple, list)) or len(result) != 2:
                continue

            decision, reason = result
            if decision == "deny":
                return ("deny", f"[ext:{ext_file.name}] {reason}")

        except Exception:
            # Per-extension isolation — never crash the hook
            continue

    return ("allow", "")


def main():
    """Main entry point - dispatch to all validators and combine decisions."""
    try:
        # Load environment variables
        load_env()

        # Read input from stdin
        try:
            input_data = json.load(sys.stdin)
        except json.JSONDecodeError as e:
            # Invalid JSON - ask user (don't block on invalid input)
            output_decision("ask", f"Invalid input JSON: {e}")
            sys.exit(0)

        # Extract session_id from hook stdin for logging functions (Issue #504).
        # The env var CLAUDE_SESSION_ID is absent in most hook contexts, so we
        # store the stdin value at module level as a fallback.
        global _session_id
        _session_id = input_data.get("session_id", "unknown")

        # Extract tool information
        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})

        if not tool_name:
            # No tool name - ask user
            output_decision("ask", "No tool name provided")
            sys.exit(0)

        # =================================================================
        # FAST PATH: Native tools skip ALL hook layers.
        # Hooks run BEFORE settings.json — returning "ask" here overrides
        # settings.json "allow" rules. Native tools are governed by
        # settings.json, not by this hook.
        # =================================================================
        if tool_name in NATIVE_TOOLS:
            # Infrastructure protection: block direct edits to agents/, commands/,
            # hooks/, lib/, skills/ unless /implement pipeline is active (Issue #483)
            # Threat model: accidental direct edits, not malicious local attacker.
            # CLAUDE_AGENT_NAME is set by Claude Code; env var trust is by design.
            # Fail-closed: if the check itself errors, block the edit (A04 remediation).
            if tool_name in ("Write", "Edit"):
                file_path = tool_input.get("file_path", "")
                try:
                    is_protected = _is_protected_infrastructure(file_path)
                    pipeline_active = _is_pipeline_active() if is_protected else False
                except Exception:
                    # Fail closed — if protection check errors, treat as protected
                    is_protected = True
                    pipeline_active = False
                if is_protected and not pipeline_active:
                    file_name = Path(file_path).name if file_path else "unknown"
                    block_reason = (
                        f"BLOCKED: Direct edit to '{file_name}' denied. "
                        f"Infrastructure files (agents/, commands/, hooks/, lib/, skills/) "
                        f"require the /implement pipeline. Run: /implement \"description\""
                    )
                    _log_deviation(file_name, tool_name, "infrastructure_protection_block")
                    _log_pretool_activity(tool_name, tool_input, "deny", block_reason)
                    output_decision("deny", block_reason, system_message=block_reason)
                    sys.exit(0)

            # Bash command inspection: detect writes to protected paths (#502)
            if tool_name == "Bash":
                command = tool_input.get("command", "")
                if command:
                    bash_block = _check_bash_infra_writes(command)
                    if bash_block is not None:
                        _log_deviation(bash_block[0], tool_name, "bash_infrastructure_protection_block")
                        _log_pretool_activity(tool_name, tool_input, "deny", bash_block[1])
                        output_decision("deny", bash_block[1], system_message=bash_block[1])
                        sys.exit(0)

            # Run extensions even for native tools
            ext_decision, ext_reason = _run_extensions(tool_name, tool_input)
            if ext_decision == "deny":
                _log_pretool_activity(tool_name, tool_input, "deny", ext_reason)
                output_decision("deny", ext_reason)
                sys.exit(0)

            reason = f"Native tool '{tool_name}' - hook bypass (settings.json governs)"
            _log_pretool_activity(tool_name, tool_input, "allow", reason)
            output_decision("allow", reason)
            sys.exit(0)

        # Run all validators in sequence (Layer 0 → Layer 1 → Layer 2 → Layer 3)
        validators_results = []

        # 0. Sandbox Layer (Layer 0) - Command classification & sandboxing
        decision, reason = validate_sandbox_layer(tool_name, tool_input)
        validators_results.append(("Sandbox", decision, reason))

        # 1. MCP Security Validator (Layer 1)
        decision, reason = validate_mcp_security(tool_name, tool_input)
        validators_results.append(("MCP Security", decision, reason))

        # 2. Agent Authorization (Layer 2)
        decision, reason = validate_agent_authorization(tool_name, tool_input)
        validators_results.append(("Agent Auth", decision, reason))

        # 3. Batch Permission Approver (Layer 3)
        decision, reason = validate_batch_permission(tool_name, tool_input)
        validators_results.append(("Batch Permission", decision, reason))

        # Layer 4: Hook extensions
        ext_decision, ext_reason = _run_extensions(tool_name, tool_input)
        if ext_decision == "deny":
            validators_results.append(("Extensions", "deny", ext_reason))

        # Combine all decisions
        final_decision, combined_reason = combine_decisions(validators_results)

        # Log the enforcement decision
        _log_pretool_activity(tool_name, tool_input, final_decision, combined_reason)

        # Output final decision
        output_decision(final_decision, combined_reason)

    except Exception as e:
        # Error in hook - ask user (don't block on hook errors)
        output_decision("ask", f"Hook error: {e}")

    # Always exit 0 - let Claude Code process the decision
    sys.exit(0)


if __name__ == "__main__":
    main()
