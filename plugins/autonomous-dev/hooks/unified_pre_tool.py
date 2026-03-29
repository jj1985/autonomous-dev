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

# Defensive import of python_write_detector (Issue #589).
# Falls back to None so inline regex continues to work if import fails.
_python_write_detector = None
try:
    _hook_path = Path(__file__).resolve().parent
    _lib_candidates = [
        _hook_path.parent / "lib",           # plugins/autonomous-dev/lib
        _hook_path.parents[2] / "lib",        # fallback
    ]
    for _lib_dir in _lib_candidates:
        _detector_path = _lib_dir / "python_write_detector.py"
        if _detector_path.exists():
            import importlib.util as _ilu
            _spec = _ilu.spec_from_file_location("python_write_detector", str(_detector_path))
            if _spec and _spec.loader:
                _python_write_detector = importlib.util.module_from_spec(_spec)
                _spec.loader.exec_module(_python_write_detector)
            break
except Exception:
    _python_write_detector = None  # Fallback: inline regex in _extract_bash_file_writes

# Module-level agent_type extracted from hook stdin JSON (set in main()).
# Used by _get_active_agent_name() as primary identity source (Issue #591).
_agent_type: str = ""


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

# Agents authorized to create GitHub issues directly (Issue #599)
GH_ISSUE_AGENTS = {'continuous-improvement-analyst', 'issue-creator'}

# Marker file path for allowing gh issue create from commands (Issue #599)
GH_ISSUE_MARKER_PATH = "/tmp/autonomous_dev_gh_issue_allowed.marker"

# Environment variables protected from inline spoofing in Bash commands (Issue #557)
# Non-prefix vars that don't start with CLAUDE_ are listed individually
PROTECTED_ENV_VARS = {
    'PIPELINE_STATE_FILE', 'ENFORCEMENT_LEVEL',
}

# Prefix-based protection: any env var starting with these prefixes is protected (Issue #606)
PROTECTED_ENV_PREFIXES: "tuple[str, ...]" = ('CLAUDE_',)

# Exceptions to prefix-based protection (escape hatch for legitimate user CLAUDE_ vars)
PROTECTED_ENV_PREFIX_EXCEPTIONS: "frozenset[str]" = frozenset()

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
    # Test files are never protected — even if they live under hooks/ or lib/
    if "/tests/" in normalized or "/test/" in normalized:
        return False
    path_basename = Path(file_path).name
    if path_basename.startswith("test_") or path_basename.endswith("_test.py"):
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


def _get_active_agent_name() -> str:
    """Get the active agent name from available sources (Issue #591).

    Priority order:
    1. agent_type from hook stdin JSON (available inside subagents)
    2. CLAUDE_AGENT_NAME env var (set by Claude Code in some contexts)

    Returns:
        Lowercase agent name, or empty string if not in an agent context.
    """
    if _agent_type:
        return _agent_type.strip().lower()
    env_name = os.getenv("CLAUDE_AGENT_NAME", "").strip().lower()
    return env_name


def _is_stale_session(state: dict, state_path: "Path") -> bool:
    """Check if pipeline state belongs to a different (stale) session (Issue #592).

    Compares session_id in state file against current session's _session_id.
    If different and both are non-empty/non-unknown, state is stale -- remove file.

    Args:
        state: Parsed pipeline state dict.
        state_path: Path to the state file (for removal).

    Returns:
        True if state is stale (file removed), False if current or indeterminate.
    """
    stored_sid = state.get("session_id", "")
    current_sid = os.getenv("CLAUDE_SESSION_ID") or _session_id

    if not stored_sid or stored_sid == "unknown" or not current_sid or current_sid == "unknown":
        return False  # Cannot determine, fall through to TTL/HMAC

    if stored_sid != current_sid:
        try:
            state_path.unlink(missing_ok=True)
        except OSError:
            pass
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
    # Check agent name (Issue #591: prefer stdin agent_type over env var)
    agent_name = _get_active_agent_name()
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

            # Session staleness check (Issue #592)
            if _is_stale_session(state, state_path):
                return False

            # HMAC integrity check (Issue #557)
            if state.get("hmac") is not None:
                try:
                    from pipeline_state import verify_state_hmac
                    sid = os.getenv("CLAUDE_SESSION_ID") or _session_id
                    if not verify_state_hmac(state, sid):
                        _log_deviation("pipeline_state", "hmac_check", "pipeline_state_hmac_invalid")
                        return False  # Fail closed: tampered state = not active
                except ImportError:
                    return False  # Fail closed: HMAC present but verify library unavailable

            session_start = state.get("session_start", "")
            if session_start:
                start_time = _datetime.fromisoformat(session_start)
                elapsed = (_datetime.now() - start_time).total_seconds()
                if elapsed < 7200:  # 2 hours
                    return True
    except Exception:
        pass

    return False


def _is_explicit_implement_active() -> bool:
    """Check if /implement was explicitly invoked by the user (Issue #528).

    Reads the pipeline state file and checks for the 'explicitly_invoked' flag.
    This distinguishes user-invoked /implement from other pipeline activity,
    enabling hard blocking of coordinator code writes during explicit sessions.

    Returns:
        True if /implement was explicitly invoked and session is within TTL
    """
    pipeline_state_file = os.getenv(
        "PIPELINE_STATE_FILE", "/tmp/implement_pipeline_state.json"
    )
    try:
        state_path = Path(pipeline_state_file)
        if not state_path.exists():
            return False
        import json as _json
        from datetime import datetime as _datetime

        with open(state_path) as f:
            state = _json.load(f)

        # Session staleness check (Issue #592)
        if _is_stale_session(state, state_path):
            return False

        # HMAC integrity check (Issue #557)
        if state.get("hmac") is not None:
            try:
                from pipeline_state import verify_state_hmac
                sid = os.getenv("CLAUDE_SESSION_ID") or _session_id
                if not verify_state_hmac(state, sid):
                    _log_deviation("pipeline_state", "hmac_check", "explicit_implement_hmac_invalid")
                    return False  # Fail closed: tampered state = not active
            except ImportError:
                return False  # Fail closed: HMAC present but verify library unavailable

        # Must have explicitly_invoked flag set to true
        if not state.get("explicitly_invoked", False):
            return False
        # Check session TTL (2 hours)
        session_start = state.get("session_start", "")
        if not session_start:
            return False
        start_time = _datetime.fromisoformat(session_start)
        elapsed = (_datetime.now() - start_time).total_seconds()
        if elapsed >= 7200:  # 2 hours TTL
            return False
        return True
    except (json.JSONDecodeError, ValueError, KeyError, OSError, TypeError):
        return False


def _has_alignment_passed() -> bool:
    """Check if STEP 2 alignment has passed in the pipeline state (Issue #585).

    Reads the pipeline state file and verifies that alignment_passed is True.
    HMAC integrity is verified to prevent tampering. On any error (file missing,
    JSON invalid, HMAC fails), returns False (fail closed).

    Returns:
        True if alignment has passed and HMAC is valid
    """
    pipeline_state_file = os.getenv(
        "PIPELINE_STATE_FILE", "/tmp/implement_pipeline_state.json"
    )
    try:
        state_path = Path(pipeline_state_file)
        if not state_path.exists():
            return False
        import json as _json

        with open(state_path) as f:
            state = _json.load(f)

        # Session staleness check (Issue #592)
        if _is_stale_session(state, state_path):
            return False

        # HMAC integrity check — fail closed on any verification failure
        if state.get("hmac") is not None:
            try:
                from pipeline_state import verify_state_hmac
                sid = os.getenv("CLAUDE_SESSION_ID") or _session_id
                if not verify_state_hmac(state, sid):
                    _log_deviation(
                        "pipeline_state", "hmac_check", "alignment_gate_hmac_invalid"
                    )
                    return False
            except ImportError:
                return False  # Fail closed: HMAC present but verify library unavailable

        return state.get("alignment_passed", False) is True
    except (Exception,):
        return False  # Fail closed on any error


# Non-code file extensions exempt from explicit /implement coordinator blocking
_NON_CODE_EXTENSIONS = {
    ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini",
    ".md", ".txt", ".rst", ".csv", ".env",
}


def _is_code_file_target(tool_name: str, tool_input: Dict) -> bool:
    """Check if the tool operation targets a code file (Issue #528).

    Protected infrastructure files (agents/*.md, commands/*.md, skills/*.md)
    are treated as code targets regardless of their .md extension (Issue #623).
    The extension-based exemption only applies to regular docs and config files.

    Args:
        tool_name: Name of the tool (Write, Edit, Bash)
        tool_input: Tool input parameters

    Returns:
        True if the tool targets a code file or protected infrastructure file
    """
    if tool_name in ("Write", "Edit"):
        file_path = tool_input.get("file_path", "")
        if not file_path:
            return False
        # Issue #623: Protected infrastructure files (agents/*.md, commands/*.md,
        # skills/*.md) must be treated as code targets regardless of extension.
        if _is_protected_infrastructure(file_path):
            return True
        suffix = Path(file_path).suffix.lower()
        # Exempt non-code files (README.md, docs/*.md, config files, etc.)
        if suffix in _NON_CODE_EXTENSIONS:
            return False
        # Check against known code extensions
        return suffix in CODE_EXTENSIONS
    elif tool_name == "Bash":
        command = tool_input.get("command", "")
        if not command:
            return False
        target_files = _extract_bash_file_writes(command)
        for fp in target_files:
            # Issue #623: Infrastructure .md files in Bash redirects are code targets
            if _is_protected_infrastructure(fp):
                return True
            suffix = Path(fp).suffix.lower()
            if suffix in _NON_CODE_EXTENSIONS:
                continue
            if suffix in CODE_EXTENSIONS:
                return True
        return False
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


def _strip_quoted_segments(command: str) -> str:
    """Remove single- and double-quoted segments from a command string (Issue #590).

    This prevents false-positive env-var spoofing detection when a protected
    variable name appears inside a quoted argument (e.g., a --body flag to gh).

    Single-quoted strings in bash have no escape sequences, so the pattern is
    simple: everything between the first ``'`` and the next ``'``.

    Double-quoted strings support backslash escaping, so ``\\"`` inside a
    double-quoted segment does NOT end the string.

    On any regex error the original command is returned unchanged (fail-open for
    the stripping step, but the caller still applies the detection patterns to
    the original on error).

    Args:
        command: The raw Bash command string.

    Returns:
        Command with quoted segments replaced by empty strings.
    """
    import re

    try:
        # Remove single-quoted segments first (no escape sequences in single quotes)
        result = re.sub(r"'[^']*'", "", command)
        # Remove double-quoted segments (backslash can escape a quote inside)
        result = re.sub(r'"(?:[^"\\]|\\.)*"', "", result)
        return result
    except re.error:
        return command


def _strip_heredoc_content(command: str) -> str:
    """Remove heredoc content from a command string.

    Strips content between heredoc delimiters (<<EOF...EOF, <<'EOF'...EOF,
    <<"EOF"...EOF) to prevent false-positive detection when keywords appear
    inside heredoc bodies (e.g., commit messages passed via heredoc).

    Args:
        command: The raw Bash command string.

    Returns:
        Command with heredoc body content replaced by empty strings.
    """
    import re

    try:
        # Match heredoc start: <<EOF, <<'EOF', <<"EOF", <<-EOF, <<-'EOF', etc.
        # Capture the delimiter word, then remove everything up to the matching
        # delimiter on its own line (or end of string).
        result = re.sub(
            r"<<-?\s*['\"]?(\w+)['\"]?.*?\n(.*?\n)*?\1\b",
            "",
            command,
            flags=re.DOTALL,
        )
        return result
    except re.error:
        return command


def _is_protected_env_var(var_name: str) -> bool:
    """Check if a variable name is protected by individual listing or prefix matching.

    Args:
        var_name: The environment variable name to check.

    Returns:
        True if the variable is protected and should not be set inline.
    """
    # Check individual protected vars first
    if var_name in PROTECTED_ENV_VARS:
        return True

    # Check prefix-based protection (Issue #606)
    if var_name in PROTECTED_ENV_PREFIX_EXCEPTIONS:
        return False
    for prefix in PROTECTED_ENV_PREFIXES:
        if var_name.startswith(prefix):
            return True

    return False


def _detect_env_spoofing(command: str) -> "Optional[str]":
    """Detect inline environment variable spoofing in Bash commands (Issue #557, #606).

    Checks for patterns like:
    - CLAUDE_AGENT_NAME=implementer python3 ...
    - export CLAUDE_AGENT_NAME=implementer
    - env CLAUDE_AGENT_NAME=implementer ...
    - CLAUDE_ANY_NEW_VAR=value cmd (prefix-based, Issue #606)

    Checks variables in PROTECTED_ENV_VARS (individual) and any variable
    matching PROTECTED_ENV_PREFIXES. Legitimate env usage
    (e.g., PATH=foo, HOME=/tmp) is not blocked.

    Args:
        command: The Bash command string to inspect.

    Returns:
        Block reason string if spoofing detected, None if clean.
    """
    import re

    stripped = _strip_quoted_segments(command)

    # --- Pass 1: Check individual PROTECTED_ENV_VARS (exact match) ---
    for var in PROTECTED_ENV_VARS:
        # Pattern 1: VAR=value command (inline prefix)
        pattern1 = (
            r'(?:^|[;&|]\s*)' + re.escape(var)
            + r"""=['""]?[^\s'"";|&]*['""]?\s+\S"""
        )
        if re.search(pattern1, stripped):
            return (
                f"BLOCKED: Inline env var spoofing detected — '{var}' cannot be "
                f"set inline in Bash commands. Protected environment variables "
                f"are managed by the pipeline. (Issue #557)"
            )

        # Pattern 2: export VAR=value
        pattern2 = r'\bexport\s+' + re.escape(var) + r'\s*='
        if re.search(pattern2, stripped):
            return (
                f"BLOCKED: Export of protected env var '{var}' detected. "
                f"Protected environment variables cannot be overridden via "
                f"Bash export. (Issue #557)"
            )

        # Pattern 3: env [-flags] [--] VAR=value command
        pattern3 = r'\benv\s+(?:(?:-[a-zA-Z]+\s+(?:\S+\s+)?|--\s+)*)(?:[^\s=]+=\S+\s+)*' + re.escape(var) + r'\s*='
        if re.search(pattern3, stripped):
            return (
                f"BLOCKED: Env command spoofing detected — '{var}' cannot be "
                f"set via the env command. Protected environment variables "
                f"are managed by the pipeline. (Issue #557)"
            )

    # --- Pass 2: Prefix-based detection (Issue #606) ---
    # Find all VAR=value assignments in the stripped command
    # Pattern: word characters (var name) followed by = at assignment positions
    # Inline: VAR=value cmd  (start of command or after ; & |)
    inline_vars = re.findall(r'(?:^|[;&|]\s*)([A-Z_][A-Z0-9_]*)=', stripped, re.MULTILINE)
    # Export: export VAR=value
    export_vars = re.findall(r'\bexport\s+([A-Z_][A-Z0-9_]*)\s*=', stripped, re.MULTILINE)
    # Env command: env [-flags...] [--] VAR=value
    # Handles: env VAR=val, env -i VAR=val, env -u NAME VAR=val, env -- VAR=val
    env_cmd_vars = re.findall(
        r'\benv\s+(?:(?:-[a-zA-Z]+\s+(?:\S+\s+)?|--\s+)*)(?:[^\s=]+=\S+\s+)*([A-Z_][A-Z0-9_]*)=',
        stripped,
        re.MULTILINE,
    )

    all_assigned_vars = set(inline_vars + export_vars + env_cmd_vars)
    for var in all_assigned_vars:
        # Skip vars already checked in Pass 1
        if var in PROTECTED_ENV_VARS:
            continue
        if _is_protected_env_var(var):
            # Determine which pattern matched to give a specific message
            inline_pat = (
                r'(?:^|[;&|]\s*)' + re.escape(var)
                + r"""=['""]?[^\s'"";|&]*['""]?\s+\S"""
            )
            export_pat = r'\bexport\s+' + re.escape(var) + r'\s*='
            env_pat = r'\benv\s+(?:(?:-[a-zA-Z]+\s+(?:\S+\s+)?|--\s+)*)(?:[^\s=]+=\S+\s+)*' + re.escape(var) + r'\s*='

            if re.search(export_pat, stripped):
                return (
                    f"BLOCKED: Export of protected env var '{var}' detected. "
                    f"Variables matching protected prefix cannot be overridden "
                    f"via Bash export. (Issue #606)"
                )
            if re.search(env_pat, stripped):
                return (
                    f"BLOCKED: Env command spoofing detected — '{var}' cannot be "
                    f"set via the env command. Variables matching protected prefix "
                    f"are managed by the pipeline. (Issue #606)"
                )
            if re.search(inline_pat, stripped):
                return (
                    f"BLOCKED: Inline env var spoofing detected — '{var}' cannot be "
                    f"set inline in Bash commands. Variables matching protected prefix "
                    f"are managed by the pipeline. (Issue #606)"
                )
            # Fallback: var was found in assignment but specific pattern didn't re-match
            # (shouldn't happen, but fail safe)
            return (
                f"BLOCKED: Protected env var '{var}' assignment detected. "
                f"Variables matching protected prefix cannot be set in "
                f"Bash commands. (Issue #606)"
            )

    # Pattern 4: bash -c / sh -c subshell containing protected var assignments
    # Catches: bash -c 'CLAUDE_AGENT_NAME=x python3 ...'
    #          sh -c "export PIPELINE_STATE_FILE=/tmp/fake.json; ..."
    for subshell_match in re.finditer(r'(?:ba)?sh\s+-c\s+([\x27"])(.*?)\1', command, re.DOTALL):
        inner_cmd = subshell_match.group(2)
        # Recursively check the inner command for env spoofing
        inner_result = _detect_env_spoofing(inner_cmd)
        if inner_result:
            return (
                f"BLOCKED: Subshell env spoofing detected — protected environment "
                f"variable assignment found inside bash -c / sh -c subshell. "
                f"Inner violation: {inner_result}"
            )

    return None


def _track_spoofing_escalation(
    session_id: str,
    *,
    tracker_path: "Optional[str]" = None,
) -> bool:
    """Track spoofing attempts per session and detect escalation (Issue #606).

    Uses a file-based tracker to persist attempt counts across hook invocations
    (each hook invocation is a separate process). Returns True when 2+ attempts
    have occurred in the same session, indicating escalation.

    Args:
        session_id: The current session identifier.
        tracker_path: Optional override for the tracker file path (for testing).

    Returns:
        True if this is the 2nd or later attempt in the same session (escalation).
    """
    import json
    import tempfile
    from datetime import datetime

    if tracker_path is None:
        log_dir = Path(os.environ.get("HOME", "/tmp")) / ".claude" / "logs"
        tracker_file = log_dir / "spoofing_attempts.json"
    else:
        tracker_file = Path(tracker_path)

    try:
        tracker_file.parent.mkdir(parents=True, exist_ok=True)

        # Read existing tracker data
        data: "dict[str, list[str]]" = {}
        if tracker_file.exists():
            try:
                data = json.loads(tracker_file.read_text())
            except (json.JSONDecodeError, OSError):
                data = {}

        # Record this attempt
        if session_id not in data:
            data[session_id] = []
        data[session_id].append(datetime.now().isoformat())

        is_escalation = len(data[session_id]) >= 2

        # Atomic write: write to tmp file, then rename
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=str(tracker_file.parent), suffix=".tmp"
        )
        try:
            with os.fdopen(tmp_fd, "w") as f:
                json.dump(data, f)
            os.replace(tmp_path, str(tracker_file))
        except OSError:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            # Still return the escalation result based on in-memory data
            pass

        return is_escalation
    except Exception:
        # Never block on tracker failure — fail open for tracking,
        # the spoofing block itself is already applied
        return False


def _contains_gh_issue_create_bypass(command: str) -> bool:
    """Detect subprocess-wrapped 'gh issue create' bypass patterns (Issue #618).

    Checks the RAW (unstripped) command string for patterns where 'gh issue create'
    is invoked indirectly via subprocess wrappers, shell wrappers, or backtick
    substitution. These bypasses escape the normal stripped-string detection
    because the 'gh issue create' text lives inside a quoted string argument.

    Patterns detected:
    - python3 -c "... subprocess.run(['gh', 'issue', 'create'] ...)"
    - python -c "... subprocess.call(['gh', 'issue', 'create'] ...)"
    - python3 -c "... subprocess.Popen(['gh', 'issue', 'create'] ...)"
    - python3 -c "... os.system('gh issue create ...')"
    - sh -c "gh issue create ..."
    - bash -c "gh issue create ..."
    - `gh issue create ...` (backtick substitution)
    - $(gh issue create ...) (command substitution)

    Args:
        command: The raw (unstripped) Bash command string.

    Returns:
        True if a bypass pattern is detected, False otherwise.
    """
    import re

    try:
        # Pattern 1: Python subprocess wrappers — subprocess.run/call/Popen/check_output
        # with 'gh' and 'issue' and 'create' appearing as list elements or in a string.
        # We look for the subprocess family of calls followed by gh issue create nearby.
        subprocess_pattern = (
            r'subprocess\s*\.\s*(?:run|call|Popen|check_output|check_call)'
            r'[^)]*\bgh\b[^)]*\bissue\b[^)]*\bcreate\b'
        )
        if re.search(subprocess_pattern, command, re.IGNORECASE | re.DOTALL):
            return True

        # Pattern 2: os.system('gh issue create ...') or os.system("gh issue create ...")
        os_system_pattern = r'os\s*\.\s*system\s*\([^)]*\bgh\s+issue\s+create\b'
        if re.search(os_system_pattern, command, re.IGNORECASE | re.DOTALL):
            return True

        # Pattern 3: sh -c "gh issue create ..." or bash -c "gh issue create ..."
        # Also covers: /bin/sh -c, /bin/bash -c, /usr/bin/env sh -c, etc.
        shell_wrapper_pattern = (
            r'(?:^|[|;&\s])(?:/\S+/)?(?:sh|bash|zsh|dash)\s+-c\s+'
            r'["\'](?:[^"\'\\]|\\.)*\bgh\s+issue\s+create\b'
        )
        if re.search(shell_wrapper_pattern, command, re.IGNORECASE | re.DOTALL):
            return True

        # Pattern 4: Backtick command substitution: `gh issue create ...`
        # Only matches when gh issue create is the direct command inside backticks
        # (i.e., gh appears right after the opening backtick, with optional whitespace).
        backtick_pattern = r'`\s*gh\s+issue\s+create\b'
        if re.search(backtick_pattern, command, re.IGNORECASE | re.DOTALL):
            return True

        # Pattern 5: $(...) command substitution with gh issue create as the direct command
        # e.g. $(gh issue create --title "test")
        # NOT matched: $(cat <<'EOF'\ngh issue create\nEOF\n) — heredoc body, not a command
        dollar_subst_pattern = r'\$\(\s*gh\s+issue\s+create\b'
        if re.search(dollar_subst_pattern, command, re.IGNORECASE | re.DOTALL):
            return True

        return False
    except re.error:
        return False  # Fail-open on regex error


def _detect_gh_issue_marker_creation(command: str) -> "Optional[str]":
    """Detect Bash commands that directly create the gh issue marker file (Issue #627).

    The marker file ``autonomous_dev_gh_issue_allowed.marker`` is written by the
    approved /create-issue pipeline to signal that a ``gh issue create`` call is
    authorized.  Allowing arbitrary code to create the file directly would
    short-circuit the entire bypass-prevention mechanism.

    Detection anchors on the marker filename fragment
    ``autonomous_dev_gh_issue_allowed`` to catch path variations, then filters to
    write-creating operations (``touch``, redirect ``>``, ``cp``, ``mv``, ``tee``,
    Python ``Path.touch`` / ``open`` / ``write_text``).

    Read-only and delete operations (``cat``, ``ls``, ``rm``) are intentionally
    NOT blocked.

    Allow-through conditions (same guards as ``_detect_gh_issue_create``):
    1. ``_is_pipeline_active()`` — the pipeline itself writes the marker legitimately.
    2. Agent name in ``GH_ISSUE_AGENTS`` — authorised agents may also write it.
    Note: there is deliberately NO marker-file allow-through here (circular).

    Args:
        command: The raw Bash command string to inspect.

    Returns:
        Block reason string if marker creation detected and not allowed,
        None if the command is clean or allowed.
    """
    import re

    try:
        marker_anchor = r"autonomous_dev_gh_issue_allowed"

        write_patterns = [
            # touch <path containing marker name>
            rf"touch\s+.*{marker_anchor}",
            # redirect writes: > <path>, >> <path>
            rf">+\s*\S*{marker_anchor}",
            # cp <src> <dst containing marker name>
            rf"cp\s+.*{marker_anchor}",
            # mv <src> <dst containing marker name>
            rf"mv\s+.*{marker_anchor}",
            # tee <path containing marker name>
            rf"tee\s+.*{marker_anchor}",
            # Python Path(...).touch()
            rf"Path\s*\(.*{marker_anchor}.*\)\s*\.touch\s*\(",
            # Python open(<marker path>, ...) write modes
            rf"open\s*\(.*{marker_anchor}.*,\s*['\"]w",
            # Python .write_text(  near marker name in same statement
            rf"{marker_anchor}.*\.write_text\s*\(",
            rf"\.write_text\s*\(.*{marker_anchor}",
        ]

        matched = any(
            re.search(pattern, command, re.IGNORECASE) for pattern in write_patterns
        )

        if not matched:
            return None

        # Allow-through 1: Pipeline is active (writes the marker legitimately)
        if _is_pipeline_active():
            return None

        # Allow-through 2: Agent is authorised for issue creation
        agent_name = _get_active_agent_name()
        if agent_name in GH_ISSUE_AGENTS:
            return None

        return (
            "BLOCKED: Cannot create gh issue marker file directly.\n"
            "Use '/create-issue' or '/create-issue --quick' instead."
        )
    except Exception:
        return None  # Fail-open on any error


def _detect_gh_issue_create(command: str) -> "Optional[str]":
    """Detect direct 'gh issue create' usage outside approved contexts (Issue #599).

    Blocks direct GitHub issue creation via the gh CLI to enforce the
    /create-issue pipeline which includes research, duplicate detection,
    and proper formatting.

    Also detects subprocess-bypass patterns (Issue #618) where 'gh issue create'
    is wrapped inside python3 -c subprocess calls, sh/bash -c, or backtick
    substitutions to evade the normal stripped-string detection.

    Args:
        command: The raw Bash command string to inspect.

    Returns:
        Block reason string if gh issue create detected and not allowed,
        None if the command is clean or allowed.
    """
    import re

    try:
        # Strip quoted segments and heredoc content to avoid false positives
        # when 'gh issue create' appears inside commit messages, echo strings, etc.
        stripped = _strip_heredoc_content(command)
        stripped = _strip_quoted_segments(stripped)

        # Check 1: Direct 'gh issue create' in the stripped command
        direct_match = bool(re.search(r'\bgh\s+issue\s+create\b', stripped, re.IGNORECASE))

        # Check 2: Subprocess bypass patterns in the RAW command (Issue #618).
        # These wrappers embed 'gh issue create' inside quoted strings, which
        # stripping would normally remove — so we scan the original command.
        bypass_match = _contains_gh_issue_create_bypass(command)

        if not direct_match and not bypass_match:
            return None

        # Allow-through 1: Pipeline is active (implementer/test-master/doc-master)
        if _is_pipeline_active():
            return None

        # Allow-through 2: Agent is authorized for issue creation
        agent_name = _get_active_agent_name()
        if agent_name in GH_ISSUE_AGENTS:
            return None

        # Allow-through 3: Marker file exists and is fresh (< 1 hour)
        try:
            marker_path = Path(GH_ISSUE_MARKER_PATH)
            if marker_path.exists():
                import time
                age = time.time() - marker_path.stat().st_mtime
                if age < 3600:
                    return None
        except OSError:
            pass  # Marker check failed, continue to block

        return (
            "BLOCKED: Cannot create GitHub issues with 'gh issue create' directly.\n"
            "Use '/create-issue' or '/create-issue --quick' instead.\n\n"
            "/create-issue includes research, duplicate detection, and ensures "
            "proper formatting."
        )
    except Exception:
        return None  # Fail-open on any error


def _detect_settings_json_write(command: str) -> "Optional[str]":
    """Detect Bash commands that write to settings.json or settings.local.json.

    Only blocks during active pipeline. Called separately after pipeline check.

    Args:
        command: The Bash command string to inspect.

    Returns:
        Block reason string if settings write detected, None if clean.
    """
    import re

    settings_patterns = [
        r'settings\.json',
        r'settings\.local\.json',
    ]
    # Check redirects, tee, cp/mv targets
    write_targets = _extract_bash_file_writes(command)
    for target in write_targets:
        for pat in settings_patterns:
            if re.search(pat, target):
                return (
                    f"BLOCKED: Bash write to '{target}' during active pipeline. "
                    f"Settings files are protected during /implement sessions. (Issue #557)"
                )

    # Also check sed -i and python -c patterns
    for pat in settings_patterns:
        if re.search(r'\bsed\s+.*-i.*' + pat, command):
            return (
                f"BLOCKED: In-place edit of settings file during active pipeline. "
                f"Settings files are protected during /implement sessions. (Issue #557)"
            )

    return None


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

    # Heredoc redirect (heredoc >> file)
    heredoc_pattern = r'<<\s*[\'"]?\w+[\'"]?\s*[>]{1,2}\s+([^\s;&|]+)'
    for match in re.finditer(heredoc_pattern, command):
        file_paths.append(match.group(1).strip())

    # cat redirect before heredoc: cat > file << 'EOF' (Issue #558)
    cat_heredoc_pattern = r'\bcat\s+[>]{1,2}\s+([^\s;&|]+)\s+<<'
    for match in re.finditer(cat_heredoc_pattern, command):
        fp = match.group(1).strip()
        if fp not in {'/dev/null', '/dev/stderr', '/dev/stdout', '&1', '&2'}:
            file_paths.append(fp)

    # dd of=FILE (Issue #558)
    dd_pattern = r'\bdd\s+.*?\bof=([^\s;&|]+)'
    for match in re.finditer(dd_pattern, command):
        file_paths.append(match.group(1).strip())

    # sed -i (in-place edit) — Issue #589
    sed_pattern = r'\bsed\s+(?:-[^i]*)?-i[^\s]*\s+(?:[\'"][^\'"]*[\'"]\s+)?([^\s;&|]+)'
    for match in re.finditer(sed_pattern, command):
        file_paths.append(match.group(1).strip())

    # cp / mv destination (last argument) — Issue #589
    cp_mv_pattern = r'\b(?:cp|mv)\s+(?:-[^\s]+\s+)*(?:[^\s]+\s+)+([^\s;&|]+)'
    for match in re.finditer(cp_mv_pattern, command):
        file_paths.append(match.group(1).strip())

    # python3 -c with file writes — Issue #589 (enhanced with python_write_detector)
    py_c_patterns = [
        r'python3?\s+-c\s+"([^"]+)"',   # double-quoted
        r"python3?\s+-c\s+'([^']+)'",    # single-quoted
    ]
    py_c_snippets = []
    for py_c_pattern in py_c_patterns:
        for match in re.finditer(py_c_pattern, command):
            py_c_snippets.append(match.group(1))

    # python3 heredoc with file writes — Issue #589
    py_heredoc_pattern = r'python3?\s+.*?<<\s*[\'"]?(\w+)[\'"]?'
    for match in re.finditer(py_heredoc_pattern, command):
        marker = match.group(1)
        heredoc_start = match.end()
        remaining = command[heredoc_start:]
        _end_match = re.search(r'(?:^|\n)' + re.escape(marker) + r'(?:\n|$)', remaining)
        end_idx = _end_match.start() if _end_match else -1
        heredoc_body = remaining[:end_idx] if end_idx >= 0 else remaining
        py_c_snippets.append(heredoc_body)

    # Use python_write_detector if available, else fall back to inline regex
    for snippet in py_c_snippets:
        if _python_write_detector is not None:
            targets = _python_write_detector.extract_write_targets(snippet)
            for t in targets:
                if t != _python_write_detector.SUSPICIOUS_EXEC_SENTINEL:
                    file_paths.append(t)
        else:
            # Inline regex fallback (original patterns)
            open_pattern = r'open\s*\(\s*[\'"]([^\'"]+)[\'"]\s*,\s*[\'"][wa]'
            for open_match in re.finditer(open_pattern, snippet):
                file_paths.append(open_match.group(1))
            path_write_pattern = r"Path\s*\(\s*['\"]([^'\"]+)['\"]\s*\)\.write_(?:text|bytes)"
            for path_match in re.finditer(path_write_pattern, snippet):
                file_paths.append(path_match.group(1))
            # shutil fallback — Issue #589
            shutil_pattern = r'(?:\w+)\.(?:copy|copy2|move|copyfile)\s*\(\s*[\'"][^\'"]*[\'"]\s*,\s*[\'"]([^\'"]+)[\'"]\s*\)'
            for shutil_match in re.finditer(shutil_pattern, snippet):
                file_paths.append(shutil_match.group(1))

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
        agent_name = _get_active_agent_name()
        if agent_name in PIPELINE_AGENTS:
            return ("allow", f"Pipeline agent '{agent_name}' authorized")
        impl_active = _is_explicit_implement_active()
        # Issue #585: Block ALL code writes before alignment passes
        if impl_active and tool_name in ("Write", "Edit", "Bash"):
            if not _has_alignment_passed():
                if _is_code_file_target(tool_name, tool_input):
                    _log_deviation(
                        tool_input.get("file_path", "unknown") if tool_name != "Bash"
                        else "bash_command",
                        tool_name,
                        "alignment_gate_not_passed",
                    )
                    return ("deny", (
                        "ALIGNMENT GATE: /implement is active but STEP 2 (PROJECT.md alignment) "
                        "has not passed yet. The coordinator must complete alignment validation "
                        "before any code changes are allowed. Complete STEP 2 first."
                    ))
        # Issue #528: If /implement was explicitly invoked, block coordinator code writes
        if impl_active and tool_name in ("Write", "Edit", "Bash"):
            level = os.getenv("ENFORCEMENT_LEVEL", "block").strip().lower()
            if level != "off" and _is_code_file_target(tool_name, tool_input):
                block_reason = (
                    "WORKFLOW ENFORCEMENT: /implement is active — code changes must be "
                    "made by pipeline agents (implementer, test-master, doc-master), "
                    "not the coordinator. Delegate this work to the appropriate agent."
                )
                _log_deviation(
                    tool_input.get("file_path", "unknown") if tool_name != "Bash"
                    else "bash_command",
                    tool_name,
                    "explicit_implement_coordinator_block",
                )
                return ("deny", block_reason)
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
            "agent": _get_active_agent_name() or "main",
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


DENY_CACHE_PATH = "/tmp/.claude_deny_cache.jsonl"


def _update_deny_cache(file_path: str) -> None:
    """Record a denied file path in the deny cache for escalation tracking.

    Appends a JSON line with the path and current timestamp.
    Prunes stale entries (>300s) on every 10th write, capped at 500 lines.
    Failures are silently ignored — deny cache must never block legitimate commands.

    Args:
        file_path: The file path that was denied.
    """
    import json as _json
    import time as _time
    _PRUNE_MAX_AGE = 300  # seconds
    _PRUNE_MAX_LINES = 500
    try:
        with open(DENY_CACHE_PATH, "a") as f:
            entry = {"path": file_path, "timestamp": _time.time()}
            f.write(_json.dumps(entry) + "\n")
        # Prune on every 10th write (check line count to decide)
        cache_p = Path(DENY_CACHE_PATH)
        if cache_p.exists():
            all_lines = cache_p.read_text().splitlines()
            if len(all_lines) % 10 == 0 or len(all_lines) > _PRUNE_MAX_LINES:
                now = _time.time()
                cutoff = now - _PRUNE_MAX_AGE
                kept = []
                for raw_line in all_lines:
                    raw_line = raw_line.strip()
                    if not raw_line:
                        continue
                    try:
                        parsed = _json.loads(raw_line)
                        if parsed.get("timestamp", 0) >= cutoff:
                            kept.append(raw_line)
                    except (ValueError, KeyError):
                        continue
                # Cap at max lines (keep most recent)
                if len(kept) > _PRUNE_MAX_LINES:
                    kept = kept[-_PRUNE_MAX_LINES:]
                cache_p.write_text("\n".join(kept) + "\n" if kept else "")
    except Exception:
        pass  # Never fail the hook for cache writes


def _check_deny_cache(file_path: str, *, window_seconds: int = 60) -> bool:
    """Check if a file path was denied within the recent time window.

    Used to detect repeated bypass attempts and escalate messaging.
    Failures return False — deny cache must never block legitimate commands.

    Args:
        file_path: The file path to check.
        window_seconds: How far back to look in seconds (default: 60).

    Returns:
        True if the path was denied within the window, False otherwise.
    """
    import json as _json
    import time as _time
    try:
        cache_path = Path(DENY_CACHE_PATH)
        if not cache_path.exists():
            return False
        now = _time.time()
        cutoff = now - window_seconds
        with open(cache_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = _json.loads(line)
                    if entry.get("path") == file_path and entry.get("timestamp", 0) >= cutoff:
                        return True
                except (ValueError, KeyError):
                    continue
    except Exception:
        pass  # Never fail the hook for cache reads
    return False


def _check_bash_infra_writes(command: str) -> "Optional[Tuple[str, str]]":
    """Check if a Bash command writes to protected infrastructure paths.

    Conservative detection: false negatives OK, false positives NOT OK.
    Returns None if allowed, or (file_name, block_reason) if blocked.

    Detects: sed -i, cp/mv to protected paths, shell redirects (>, >>),
    tee to protected paths, python3 -c with open(..., 'w'),
    cat heredoc (cat > file << EOF), dd of=FILE,
    Path.write_text/write_bytes in python3 -c,
    python3 heredoc with open()/Path.write_text inside (Issue #558).

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

    # 4. python3 -c with file writes — Issue #589 (enhanced with python_write_detector)
    py_c_patterns = [
        r'python3?\s+-c\s+"([^"]+)"',   # double-quoted: python3 -c "..."
        r"python3?\s+-c\s+'([^']+)'",   # single-quoted: python3 -c '...'
    ]
    py_c_snippets = []
    for py_c_pattern in py_c_patterns:
        for match in re.finditer(py_c_pattern, command):
            py_c_snippets.append(match.group(1))

    # 5. python3 heredoc — python3 << 'EOF' with file writes inside (Issue #558, #589)
    py_heredoc_pattern = r'python3?\s+.*?<<\s*[\'"]?(\w+)[\'"]?'
    for match in re.finditer(py_heredoc_pattern, command):
        marker = match.group(1)
        heredoc_start = match.end()
        remaining = command[heredoc_start:]
        import re as _re
        _end_match = _re.search(r'(?:^|\n)' + _re.escape(marker) + r'(?:\n|$)', remaining)
        end_idx = _end_match.start() if _end_match else -1
        heredoc_body = remaining[:end_idx] if end_idx >= 0 else remaining
        py_c_snippets.append(heredoc_body)

    # Use python_write_detector if available, else fall back to inline regex
    for snippet in py_c_snippets:
        if _python_write_detector is not None:
            targets = _python_write_detector.extract_write_targets(snippet)
            for t in targets:
                if t == _python_write_detector.SUSPICIOUS_EXEC_SENTINEL:
                    # Directly block if command references protected path segments
                    for seg in ["agents/", "hooks/", "lib/", "skills/", "commands/"]:
                        if seg in command:
                            return (
                                f"__suspicious_exec__ ({seg})",
                                f"BLOCKED: Bash command contains exec/eval with dynamic arguments "
                                f"that reference protected path '{seg}'. This pattern may be "
                                f"attempting to bypass write enforcement. "
                                f"Infrastructure files require the /implement pipeline. "
                                f"Run: /implement \"description\""
                            )
                else:
                    target_paths.append(t)
        else:
            # Inline regex fallback (original patterns)
            open_pattern = r'open\s*\(\s*[\'"]([^\'"]+)[\'"]\s*,\s*[\'"][wa]'
            for open_match in re.finditer(open_pattern, snippet):
                target_paths.append(open_match.group(1))
            path_write_pattern = r"Path\s*\(\s*['\"]([^'\"]+)['\"]\s*\)\.write_(?:text|bytes)"
            for path_match in re.finditer(path_write_pattern, snippet):
                target_paths.append(path_match.group(1))
            # shutil fallback — Issue #589
            shutil_pattern = r'(?:\w+)\.(?:copy|copy2|move|copyfile)\s*\(\s*[\'"][^\'"]*[\'"]\s*,\s*[\'"]([^\'"]+)[\'"]\s*\)'
            for shutil_match in re.finditer(shutil_pattern, snippet):
                target_paths.append(shutil_match.group(1))

    # Check each target path against protected infrastructure
    for fp in target_paths:
        fp = fp.strip().strip("'\"")
        if not fp:
            continue
        try:
            if _is_protected_infrastructure(fp):
                file_name = Path(fp).name
                # Check deny cache for escalation (Issue #558)
                repeated = _check_deny_cache(fp)
                if repeated:
                    block_reason = (
                        f"BLOCKED (repeated attempt): Bash command writes to protected "
                        f"file '{file_name}'. This path was already denied recently. "
                        f"Infrastructure files (agents/, commands/, hooks/, lib/, skills/) "
                        f"require the /implement pipeline. Run: /implement \"description\""
                    )
                else:
                    block_reason = (
                        f"BLOCKED: Bash command writes to protected file '{file_name}'. "
                        f"Infrastructure files (agents/, commands/, hooks/, lib/, skills/) "
                        f"require the /implement pipeline. Run: /implement \"description\""
                    )
                _update_deny_cache(fp)
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
        global _session_id, _agent_type
        _session_id = input_data.get("session_id", "unknown")

        # Extract agent_type from hook stdin JSON (Issue #591).
        # When fired inside a subagent, Claude Code populates agent_type in the
        # hook payload even though CLAUDE_AGENT_NAME may be absent from the
        # subprocess environment.  _get_active_agent_name() uses this as primary
        # identity source.
        _agent_type = input_data.get("agent_type", "")

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

                # Issue #557: Block settings.json writes during active pipeline
                if file_path:
                    fname = Path(file_path).name
                    if fname in ("settings.json", "settings.local.json"):
                        try:
                            if _is_pipeline_active():
                                block_reason = (
                                    f"BLOCKED: Write to '{fname}' denied during active pipeline. "
                                    f"Settings files are protected during /implement sessions. "
                                    f"(Issue #557)"
                                )
                                _log_deviation(fname, tool_name, "settings_json_write_block")
                                _log_pretool_activity(tool_name, tool_input, "deny", block_reason)
                                output_decision("deny", block_reason, system_message=block_reason)
                                sys.exit(0)
                        except Exception:
                            pass  # Don't block on check failure

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

                    # Issue #557, #606: Detect inline env var spoofing
                    spoof_reason = _detect_env_spoofing(command)
                    if spoof_reason is not None:
                        # Issue #606: Track escalation across attempts in same session
                        # Skip escalation tracking when session_id is unknown to
                        # prevent false escalation from unrelated invocations
                        session_id = os.environ.get("CLAUDE_SESSION_ID", "unknown")
                        is_escalation = (
                            _track_spoofing_escalation(session_id)
                            if session_id != "unknown"
                            else False
                        )
                        if is_escalation:
                            spoof_reason += " [CIRCUMVENTION-ESCALATION]"
                        _log_deviation("env_spoofing", tool_name, "env_var_spoofing_block")
                        _log_pretool_activity(tool_name, tool_input, "deny", spoof_reason)
                        output_decision("deny", spoof_reason, system_message=spoof_reason)
                        sys.exit(0)

                    # Issue #627: Block direct creation of gh issue marker file
                    marker_block = _detect_gh_issue_marker_creation(command)
                    if marker_block:
                        _log_deviation("gh_issue_marker", tool_name, "gh_issue_marker_creation_blocked")
                        _log_pretool_activity(tool_name, tool_input, "deny", marker_block)
                        output_decision("deny", marker_block, system_message=marker_block)
                        sys.exit(0)

                    # Issue #599: Block direct gh issue create outside approved contexts
                    gh_block = _detect_gh_issue_create(command)
                    if gh_block:
                        _log_deviation("gh_issue_create", tool_name, "gh_issue_create_blocked")
                        _log_pretool_activity(tool_name, tool_input, "deny", gh_block)
                        output_decision("deny", gh_block, system_message=gh_block)
                        sys.exit(0)

                    # Issue #557: Block settings.json writes during active pipeline
                    try:
                        if _is_pipeline_active():
                            settings_block = _detect_settings_json_write(command)
                            if settings_block is not None:
                                _log_deviation("settings.json", tool_name, "settings_json_write_block")
                                _log_pretool_activity(tool_name, tool_input, "deny", settings_block)
                                output_decision("deny", settings_block, system_message=settings_block)
                                sys.exit(0)
                    except Exception:
                        pass  # Don't block on check failure

            # Issue #528: Block coordinator code writes when /implement explicitly active
            # This is CRITICAL for external repo coverage — native tools bypass all
            # validation layers, so this check must be in the fast path.
            if tool_name in ("Write", "Edit", "Bash"):
                agent_name = _get_active_agent_name()
                impl_active = _is_explicit_implement_active()
                if (agent_name not in PIPELINE_AGENTS
                        and impl_active
                        and os.getenv("ENFORCEMENT_LEVEL", "block").strip().lower() != "off"):
                    if _is_code_file_target(tool_name, tool_input):
                        block_reason = (
                            "WORKFLOW ENFORCEMENT: /implement is active — code changes must be "
                            "made by pipeline agents (implementer, test-master, doc-master), "
                            "not the coordinator. Delegate this work to the appropriate agent."
                        )
                        _log_deviation(
                            tool_input.get("file_path", "bash_command")
                            if tool_name != "Bash" else "bash_command",
                            tool_name,
                            "explicit_implement_coordinator_block_native",
                        )
                        _log_pretool_activity(tool_name, tool_input, "deny", block_reason)
                        output_decision("deny", block_reason, system_message=block_reason)
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
