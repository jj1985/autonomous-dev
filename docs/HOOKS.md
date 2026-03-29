---
covers:
  - plugins/autonomous-dev/hooks/
  - plugins/autonomous-dev/lib/hook_exit_codes.py
---

# Automation Hooks Reference

**Last Updated**: 2026-03-17
**Location**: `plugins/autonomous-dev/hooks/`

See [CLAUDE.md](../CLAUDE.md) for current counts. See [HOOK-REGISTRY.md](HOOK-REGISTRY.md) for environment variables and activation status.

---

## Overview

Hooks provide automated quality enforcement, validation, and workflow automation. They use UV single-file scripts (PEP 723) for reproducible execution with zero environment setup.

**Architecture**: Unified dispatcher pattern — consolidated hooks replace individual ones for reduced collision and easier maintenance.

---

## Exit Code Semantics

| Code | Constant | Meaning | Workflow Effect |
|------|----------|---------|-----------------|
| **0** | EXIT_SUCCESS | Passed | Continue normally |
| **1** | EXIT_WARNING | Non-critical issue | Continue with warning |
| **2** | EXIT_BLOCK | Critical issue | Block operation (PreCommit/PreSubagent only) |

**Lifecycle constraints**: PreToolUse, SubagentStop, Stop, and TaskCompleted hooks must always exit 0. Only PreCommit and PreSubagent hooks can block.

**Library**: `plugins/autonomous-dev/lib/hook_exit_codes.py` — see [LIBRARIES.md](LIBRARIES.md) for API.

---

## Active Hooks by Lifecycle

### UserPromptSubmit

| Hook | Purpose | Key Env Vars |
|------|---------|--------------|
| **unified_prompt_validator.py** | Workflow bypass detection + quality nudges | ENFORCE_WORKFLOW, QUALITY_NUDGE_ENABLED |
| **session_activity_logger.py** | Captures user prompt preview + length into session JSONL log. Pins session start date. Non-blocking. | ACTIVITY_LOGGING |

### PreToolUse

| Hook | Purpose | Key Env Vars |
|------|---------|--------------|
| **unified_pre_tool.py** | Native tool fast path + 4-layer permission validation (sandbox → MCP security → agent auth → batch approval) + hook extensions. 84% reduction in permission prompts. Blocks git bypass flags (--no-verify, --force push, reset --hard, clean -f). Blocks direct Write/Edit to infrastructure files (`agents/*.md`, `commands/*.md`, `hooks/*.py`, `lib/*.py`, `skills/*/SKILL.md`) outside `/implement` pipeline — scoped to autonomous-dev repos only. Also inspects Bash command bodies for shell file-write patterns (sed -i, cp/mv, redirects, tee, python3 -c writes, cat heredoc `cat > file << EOF`, `dd of=FILE`, `Path.write_text/write_bytes` in python3 -c, python3 heredoc with open()/Path.write_text inside) to the same protected paths, closing the bypass gap where wrapping a write in Bash would evade the gate (Issue #558). Python snippet analysis (python3 -c and heredoc bodies) is backed by `python_write_detector.py` (Issue #589) using AST-based extraction with regex fallback; handles aliased `Path` imports, `shutil.copy/move` destination arguments, and `eval()`/`exec()` with dynamic arguments. Deny cache at `/tmp/.claude_deny_cache.jsonl` tracks repeated bypass attempts within a 60-second window and escalates the block message on second attempt (Issue #558). Detects inline env var spoofing in Bash commands (e.g. `VAR=value cmd` or `export VAR=value`) for protected pipeline variables (CLAUDE_AGENT_NAME, CLAUDE_AGENT_ROLE, PIPELINE_STATE_FILE, ENFORCEMENT_LEVEL, CLAUDE_SESSION_ID) — blocks attempts to forge agent identity or downgrade enforcement level. Blocks Write/Edit to `settings.json` and `settings.local.json` during active `/implement` pipeline sessions. Verifies HMAC integrity of pipeline state files to detect tampering. (Issue #557) Alignment gate: when `/implement` is active, blocks coordinator Write/Edit/Bash to code files until STEP 2 (PROJECT.md alignment) has completed — `alignment_passed: true` must be set in the pipeline state before any code changes are permitted; fails closed on HMAC failure or missing state. `alignment_passed` field included in the HMAC message to prevent tampering. (Issue #585) Blocks direct `gh issue create` in Bash outside the `/implement` pipeline, authorized issue-creation agents (`continuous-improvement-analyst`, `issue-creator`), or commands that write a fresh marker file at `/tmp/autonomous_dev_gh_issue_allowed.marker` (Issue #599). | SANDBOX_ENABLED, MCP_AUTO_APPROVE, HOOK_EXTENSIONS_ENABLED |

**unified_pre_tool.py Native Tool Fast Path** (v4.1.0+):
- Native Claude Code tools (Read, Write, Edit, Bash, Task, etc.) skip the 4-layer validation
- Governed by settings.json permissions instead
- Eliminates unwanted permission prompts for standard tools
- Hook extensions still run for native tools (extensions can block any tool)

**unified_pre_tool.py 4-Layer Architecture** (for MCP/external tools):
- **Layer 0 (Sandbox)**: Command classification (SAFE/BLOCKED/NEEDS_APPROVAL)
- **Layer 1 (MCP Security)**: Path traversal (CWE-22), injection (CWE-78), SSRF (CWE-918)
- **Layer 2 (Agent Auth)**: Pipeline agent detection, authorized agent verification
- **Layer 3 (Batch Approver)**: User consent caching, audit logging (merged into unified_pre_tool.py per Issue #348)
- **Layer 4 (Extensions)**: Project/user-specific checks from `.claude/hooks/extensions/*.py` and `~/.claude/hooks/extensions/*.py` — survives `/sync` and `/install` (see Extension Points section)

**Infrastructure Protection** (scoped to autonomous-dev repos):
- Write/Edit to `agents/*.md`, `commands/*.md`, `hooks/*.py`, `lib/*.py`, `skills/*/SKILL.md` are blocked outside the `/implement` pipeline
- Scoped to autonomous-dev repos (detected via `_is_autonomous_dev_repo()`) — does not affect user projects
- User-facing docs (`README.md`, `CHANGELOG.md`, `docs/*.md`), config files (`.json`/`.yaml`), and all non-infrastructure paths are unaffected

**GitHub Issue Creation Gate** (Issue #599):
- Direct `gh issue create` in Bash is blocked outside approved contexts to enforce the `/create-issue` pipeline (research, duplicate detection, proper formatting)
- Allow-through 1: an active `/implement` pipeline is present (`/tmp/implement_pipeline_state.json`)
- Allow-through 2: the current agent is `continuous-improvement-analyst` or `issue-creator` (authorized for direct issue creation)
- Allow-through 3: a fresh marker file exists at `GH_ISSUE_MARKER_PATH` (`/tmp/autonomous_dev_gh_issue_allowed.marker`, valid for 1 hour) — written by `/create-issue`, `/improve`, `/refactor`, and `/plan-to-issues` commands
- Block message directs the user to `/create-issue` or `/create-issue --quick`
- Fails open on any detection error to avoid blocking legitimate work

See [SANDBOXING.md](SANDBOXING.md) for complete security architecture.

### PreCommit

| Hook | Purpose | Key Env Vars |
|------|---------|--------------|
| **auto_format.py** | Code formatting (black + isort, prettier) | AUTO_FORMAT |
| **auto_test.py** | Run related test files | AUTO_TEST |
| **security_scan.py** | Secrets detection, vulnerability scanning | SECURITY_SCAN |
| **enforce_tdd.py** | TDD workflow enforcement (tests before code) | ENFORCE_TDD |
| **enforce_orchestrator.py** | PROJECT.md alignment validation | — |
| **validate_project_alignment.py** | PROJECT.md forbidden sections detection | VALIDATE_PROJECT_ALIGNMENT |
| **validate_command_file_ops.py** | Commands execute Python libs, not just describe them | — |
| **validate_session_quality.py** | Session log completeness | — |
| **auto_fix_docs.py** | Documentation consistency auto-fixes | AUTO_FIX_DOCS |

### SubagentStop

| Hook | Purpose | Key Env Vars |
|------|---------|--------------|
| **unified_session_tracker.py** | Session logging, pipeline tracking, progress updates. Reads stdin JSON from Claude Code, computes duration_ms, validates agent_transcript_path, writes JSONL for pipeline_intent_validator ghost detection. Status determination uses `CLAUDE_AGENT_STATUS` env var as authoritative signal when present; falls back to `_determine_success()` text scan only when the env var is absent (Issue #541). Session isolation: when `CLAUDE_SESSION_ID` is set, both `SessionTracker` file selection and `check_pipeline_complete()` filter to the matching session, preventing cross-session contamination when multiple batches run on the same day (Issue #594). | TRACK_SESSIONS, TRACK_PIPELINE, CLAUDE_AGENT_STATUS, CLAUDE_SESSION_ID |

### PostToolUse

| Hook | Purpose | Key Env Vars |
|------|---------|--------------|
| **plan_mode_exit_detector.py** | Detects `ExitPlanMode` tool calls and writes a marker at `.claude/plan_mode_exit.json`. Marker is consumed by `unified_prompt_validator.py` to enforce `/implement` or `/create-issue` routing before raw edits are allowed. Auto-expires after 30 minutes. Always exits 0. | — |
| **session_activity_logger.py** | Structured JSONL activity logging for continuous improvement analysis. Handles PostToolUse (tool calls) and UserPromptSubmit (user prompts). Sets `"hook": "PostToolUse"` correctly for tool-call entries. Falls back to parsing hook stdin JSON for `session_id` when `CLAUDE_SESSION_ID` env var is absent (common in PostToolUse lifecycle). Session date pinned on first activity to prevent midnight log splits. Non-blocking. | ACTIVITY_LOGGING |

### PreCompact

| Hook | Purpose | Key Env Vars |
|------|---------|--------------|
| **pre_compact_batch_saver.sh** | Saves in-progress batch state to `.claude/compaction_recovery.json` before context compaction. Captures batch_id, current_index, feature list, and RALPH checkpoint data. No-ops when no active batch. Always exits 0. | CHECKPOINT_DIR |

### PostCompact

| Hook | Purpose | Key Env Vars |
|------|---------|--------------|
| **post_compact_enricher.sh** | Enriches the compaction recovery marker with the compact_summary from stdin JSON after compaction completes. No-ops if no recovery marker present. Always exits 0. | — |

**Compaction recovery flow**: PreCompact saves state → PostCompact adds summary → UserPromptSubmit (`unified_prompt_validator.py`) detects marker on next prompt, re-injects batch context into model output, and deletes marker. This ensures batch pipelines resume correctly after `/clear` or auto-compact without requiring manual state reconstruction.

### TaskCompleted

| Hook | Purpose | Key Env Vars |
|------|---------|--------------|
| **task_completed_handler.py** | Logs task completion events (task_id, subject, description, teammate, team) to the daily activity JSONL at `.claude/logs/activity/{date}.jsonl`. Preparation handler: TaskCompleted does not currently fire in the Agent-tool pipeline but is registered so infrastructure is ready. Always exits 0. | — |

### Stop

| Hook | Purpose | Key Env Vars |
|------|---------|--------------|
| **stop_quality_gate.py** | End-of-turn quality checks (pytest, ruff, mypy). Auto-detects tools, parallel execution, 60s timeout. Always non-blocking. | ENFORCE_QUALITY_GATE |

### Utility (not lifecycle-triggered)

| Hook | Purpose |
|------|---------|
| **genai_prompts.py** | Prompt templates for GenAI-enhanced hooks |
| **genai_utils.py** | Anthropic SDK wrapper with graceful fallback |
| **setup.py** | Interactive setup wizard for plugin configuration |

---

## Standard Git Hooks

### pre-commit (`scripts/hooks/pre-commit`)

Repository structure validation, command validation, manifest sync, lib import checks, hook documentation checks, and documentation tests.

```bash
# Install
ln -sf ../../scripts/hooks/pre-commit .git/hooks/pre-commit
```

### pre-push (`scripts/hooks/pre-push`)

Fast test suite only (excludes `@pytest.mark.slow`, `@pytest.mark.genai`, `@pytest.mark.integration`). 30s vs 2-5 min full suite.

```bash
# Install
ln -sf ../../scripts/hooks/pre-push .git/hooks/pre-push
```

---

## UV Script Support

All hooks use UV (PEP 723) for reproducible execution:

```python
#!/usr/bin/env -S uv run --script --quiet --no-project
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
```

Falls back to `sys.path` if UV unavailable. Install UV: `curl -LsSf https://astral.sh/uv/install.sh | sh`

---

## Archived Hooks

61 hooks have been archived into `plugins/autonomous-dev/hooks/archived/`. These were consolidated into the unified hooks listed above.

See `plugins/autonomous-dev/hooks/archived/README.md` for:
- Complete list of archived hooks
- Migration guides (which unified hook replaced each)
- Historical rationale

---

## Agent Hooks (Experimental)

> **Status**: Proof-of-concept. Advisory only, never enforcement. See [ADR-001-agent-hooks.md](ADR-001-agent-hooks.md) for full rationale.

### type:agent vs type:command

| Property | type:command | type:agent |
|----------|-------------|------------|
| **Format** | Python script (.py) | Markdown prompt (.md) |
| **Execution** | Deterministic Python | LLM subagent (non-deterministic) |
| **Tools available** | Full system access | Read, Grep, Glob only |
| **Limits** | None | 50 tool turns, 60s timeout |
| **Use case** | Enforcement, blocking | Advisory, semantic analysis |

### Key Constraint: Advisory Only

Agent hooks **always** return `{"decision": "approve"}`. They provide informational output (e.g., "these files are missing tests") but never block operations. This is a deliberate design choice:

- LLM non-determinism makes blocking unreliable
- "Hard blocking > nudges" philosophy requires deterministic enforcement
- Advisory output adds value without disrupting workflow

### Available Agent Hooks

| Hook | Event | Purpose |
|------|-------|---------|
| **Stop-verify-test-coverage.md** | Stop | Advisory check: do modified source files have test files? |

### How to Enable (Opt-in)

Agent hooks are **not enabled by default**. To enable, add to `.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "type": "agent",
        "prompt": "plugins/autonomous-dev/hooks/Stop-verify-test-coverage.md",
        "description": "Advisory: check test coverage for modified files"
      }
    ]
  }
}
```

To disable, remove the entry. No environment variable controls activation — presence in settings.json is sufficient.

**Warning**: Agent hooks consume tokens on every invocation. Enable only when the advisory output is valuable for your workflow.

---

## Extension Points

Hook extensions allow project-specific or user-specific tool call validation without modifying the core hook files. Extensions survive `/sync` and `/install` updates.

### Extension API Contract

Each extension is a Python file (`.py`) that implements a `check` function:

```python
def check(tool_name: str, tool_input: dict) -> tuple[str, str]:
    """Validate a tool call.

    Args:
        tool_name: Name of the tool (e.g., "Bash", "Edit", "Write").
        tool_input: Tool input parameters dict.

    Returns:
        ("allow", "") to permit the tool call.
        ("deny", "reason") to block it.
    """
    # Example: block raw mlx commands
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        if "mlx" in cmd and "realign" not in cmd:
            return ("deny", "Use 'realign train' CLI instead of raw mlx commands")
    return ("allow", "")
```

### Extension Directories

Extensions are discovered from two locations (deduplicated by filename, first occurrence wins):

1. **Global**: `~/.claude/hooks/extensions/*.py` — applies to all projects
2. **Project-level**: `.claude/hooks/extensions/*.py` — project-specific rules

Extensions are loaded in **alphabetical order** within each directory. The first `("deny", reason)` return short-circuits — remaining extensions are not called.

### How Extensions Survive Updates

The `extensions/` directory is **never overwritten** by `/sync`, `/install`, or `deploy-all.sh`. All operations explicitly create or preserve the directory:

- `install.sh`: `mkdir -p ~/.claude/hooks/extensions`
- `sync_dispatcher.py`: `(hooks_dst / "extensions").mkdir(exist_ok=True)`
- `scripts/deploy-all.sh`: rsync uses `--exclude=extensions/` to prevent deletion during `--delete` syncs (Issue #560)

### Environment Variable

| Variable | Default | Effect |
|----------|---------|--------|
| `HOOK_EXTENSIONS_ENABLED` | `true` | Set to `false` to skip all extensions |

### Example Extension

**File**: `~/.claude/hooks/extensions/block_raw_mlx.py`

```python
"""Block raw mlx-lm commands — use realign train CLI instead."""

def check(tool_name: str, tool_input: dict) -> tuple[str, str]:
    if tool_name != "Bash":
        return ("allow", "")
    cmd = tool_input.get("command", "")
    if "mlx_lm" in cmd or "mlx-lm" in cmd:
        if "realign" not in cmd:
            return ("deny", "Use 'realign train' instead of raw mlx-lm commands")
    return ("allow", "")
```

### Security Notes

- **Symlinks are skipped**: Extension files that are symlinks are silently ignored to prevent symlink-based attacks.
- **Per-extension isolation**: Each extension runs in its own try/except block. A crashing extension never affects other extensions or the main hook.
- **No arbitrary code injection**: Extensions are only loaded from the two known directories listed above.

---

## See Also

- [ADR-001-agent-hooks.md](ADR-001-agent-hooks.md) — Architecture Decision Record for agent hooks
- [HOOK-REGISTRY.md](HOOK-REGISTRY.md) — Environment variables, activation status
- [SANDBOXING.md](SANDBOXING.md) — 4-layer security architecture
- [GIT-AUTOMATION.md](GIT-AUTOMATION.md) — Git automation workflow
- [hooks/archived/README.md](/plugins/autonomous-dev/hooks/archived/) — Archived hooks reference
