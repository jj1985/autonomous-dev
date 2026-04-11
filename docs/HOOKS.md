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
| **unified_prompt_validator.py** | Compaction recovery re-injection (batch and pipeline state) + workflow bypass detection + quality nudges + plan mode exit enforcement. On each prompt, checks for `.claude/compaction_recovery.json` and if present re-injects saved batch/pipeline context to stderr, then deletes the marker. Pipeline recovery validates staleness and cwd before injecting. | ENFORCE_WORKFLOW, QUALITY_NUDGE_ENABLED |
| **session_activity_logger.py** | Captures user prompt preview + length into session JSONL log. Pins session start date. Non-blocking. | ACTIVITY_LOGGING |

### PreToolUse

| Hook | Purpose | Key Env Vars |
|------|---------|--------------|
| **unified_pre_tool.py** | Native tool fast path + 4-layer permission validation (sandbox → MCP security → agent auth → batch approval) + pipeline ordering gate + hook extensions. 84% reduction in permission prompts. Blocks git bypass flags (--no-verify, --force push, reset --hard, clean -f). Blocks direct Write/Edit to infrastructure files (`agents/*.md`, `commands/*.md`, `hooks/*.py`, `lib/*.py`, `skills/*/SKILL.md`) outside `/implement` pipeline — scoped to autonomous-dev repos only. Also inspects Bash command bodies for shell file-write patterns (sed -i, cp/mv, redirects, tee, python3 -c writes, cat heredoc `cat > file << EOF`, `dd of=FILE`, `Path.write_text/write_bytes` in python3 -c, python3 heredoc with open()/Path.write_text inside) to the same protected paths, closing the bypass gap where wrapping a write in Bash would evade the gate (Issue #558). Python snippet analysis (python3 -c and heredoc bodies) is backed by `python_write_detector.py` (Issue #589) using AST-based extraction with regex fallback; handles aliased `Path` imports, `shutil.copy/move` destination arguments, and `eval()`/`exec()` with dynamic arguments. Deny cache at `/tmp/.claude_deny_cache.jsonl` tracks repeated bypass attempts within a 60-second window and escalates the block message on second attempt (Issue #558). Detects inline env var spoofing in Bash commands (e.g. `VAR=value cmd` or `export VAR=value`) for protected pipeline variables. Individual variables protected by exact match: CLAUDE_AGENT_NAME, CLAUDE_AGENT_ROLE, PIPELINE_STATE_FILE, ENFORCEMENT_LEVEL, CLAUDE_SESSION_ID. Additionally, any variable whose name starts with the `CLAUDE_` prefix is blocked by prefix-based protection (Issue #606, `PROTECTED_ENV_PREFIXES`), preventing new CLAUDE_* variables from being spoofed without requiring explicit listing. A session-scoped escalation tracker (`_track_spoofing_escalation()`) persists attempt counts to `~/.claude/logs/spoofing_attempts.json` across hook invocations; repeated spoofing attempts within the same session produce an escalated block message — blocks attempts to forge agent identity or downgrade enforcement level. Blocks Write/Edit to `settings.json` and `settings.local.json` during active `/implement` pipeline sessions. Verifies HMAC integrity of pipeline state files to detect tampering. (Issue #557) Alignment gate: when `/implement` is active, blocks coordinator Write/Edit/Bash to code files until STEP 2 (PROJECT.md alignment) has completed — `alignment_passed: true` must be set in the pipeline state before any code changes are permitted; fails closed on HMAC failure or missing state. `alignment_passed` field included in the HMAC message to prevent tampering. (Issue #585) Blocks direct `gh issue create` in Bash outside the `/implement` pipeline, authorized issue-creation agents (`continuous-improvement-analyst`, `issue-creator`), or commands that write a command context file at `/tmp/autonomous_dev_cmd_context.json` (Issue #599, #630). Realign CLI enforcement (Issue #754): in projects detected as realign repos (contain `src/realign/` or `pyproject.toml` with "realign" string), blocks Bash commands that directly invoke `python -m mlx_lm.lora`, `python -m mlx_lm.generate`, `python -m mlx_lm.fuse`, or `python -m mlx.launch`; grep/search/cat references to mlx_lm are allowed. Block message directs the user to use `realign train` or `realign generate` instead. Fails open on project-detection errors. | SANDBOX_ENABLED, MCP_AUTO_APPROVE, HOOK_EXTENSIONS_ENABLED, PRE_TOOL_PIPELINE_ORDERING |

**Hook Output Format and Visibility Semantics** (Issue #660):

The PreToolUse hook outputs a JSON object with two distinct channels that have different visibility:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow|deny|ask",
    "permissionDecisionReason": "Model-visible reason; used for REQUIRED NEXT ACTION carrots"
  },
  "systemMessage": "User-visible message injected into conversation (optional)"
}
```

- **`permissionDecisionReason`** (model-visible on deny): Read by the model when a tool call is blocked. Block messages include a `REQUIRED NEXT ACTION:` carrot directive telling the model exactly what to do next (e.g., "Run /implement", "Use /create-issue", "Wait for prerequisite agents"). This is the primary enforcement mechanism — the carrot is a model-readable instruction, not a user-facing message.
- **`systemMessage`** (user-visible): Injected into the conversation context as a system-level message visible to the human user. Used for escalated or user-facing notifications. `systemMessage` is omitted when not needed; its presence is optional.

This distinction is fundamental: nudges in `systemMessage` are user-readable but the model cannot act on them. Enforcement directives in `permissionDecisionReason` are model-readable and drive corrective behavior. See MEMORY.md entry "Critical Behavioral Issue" for why this distinction matters.

**unified_pre_tool.py Native Tool Fast Path** (v4.1.0+):
- Native Claude Code tools (Read, Write, Edit, Bash, Task, etc.) skip the 4-layer MCP validation
- Governed by settings.json permissions instead
- Eliminates unwanted permission prompts for standard tools
- **Exception — Agent/Task tools**: Pipeline ordering gate and prompt integrity gate run before extensions for Agent/Task tool calls (Issues #625, #629, #632, #695, #716). Prompt integrity minimum word count fires regardless of pipeline state; baseline shrinkage check only during active pipeline.
- Hook extensions still run for all native tools (extensions can block any tool)

**Project Detection Guard** (Issue #662 — non-native MCP tools only):
- Runs immediately after the native tool fast path, before the 4-layer enforcement stack
- Calls `repo_detector.is_autonomous_dev_repo()` on the current working directory
- Non-autonomous-dev projects: returns immediate allow, skipping all enforcement layers
- Fail-closed: when `repo_detector` is unavailable at load time, `_is_adev_project()` returns `True` so enforcement continues rather than being silently skipped
- Has no effect in autonomous-dev repos — all enforcement layers run normally

**unified_pre_tool.py 4-Layer Architecture** (for MCP/external tools in autonomous-dev repos):
- **Layer 0 (Sandbox)**: Command classification (SAFE/BLOCKED/NEEDS_APPROVAL)
- **Layer 1 (MCP Security)**: Path traversal (CWE-22), injection (CWE-78), SSRF (CWE-918)
- **Layer 2 (Agent Auth)**: Pipeline agent detection, authorized agent verification
- **Layer 3 (Batch Approver)**: User consent caching, audit logging (merged into unified_pre_tool.py per Issue #348)
- **Layer 4 (Extensions)**: Project/user-specific checks from `.claude/hooks/extensions/*.py` and `~/.claude/hooks/extensions/*.py` — survives `/sync` and `/install` (see Extension Points section)

**Pipeline Ordering Gate** (Issues #625, #629, #632, #686 — native Agent/Task tools only):
- Enforces agent invocation order during active pipeline sessions
- Records agent launch in `pipeline_completion_state.py` before checking prerequisites (Issue #686)
- Reads completion and launch state from `pipeline_completion_state.py` (completions written by `unified_session_tracker.py`)
- Delegates ordering logic to `agent_ordering_gate.py` (pure logic, no I/O)
- Blocks out-of-order agent calls (e.g., implementer before planner/test-master)
- Supports sequential mode (default) and parallel mode (`set_validation_mode()`)
- In parallel mode, distinguishes "running concurrently" (launched, not yet complete — allowed with warning) from "skipped entirely" (never launched — blocked)
- Controlled by env var `PRE_TOOL_PIPELINE_ORDERING` (default: `true`)
- Fails open — ordering check errors never block workflow

**Prompt Integrity Gate** (Issues #695, #716, #723 — native Agent/Task tools only):
- Blocks invocations of compression-critical agents (security-auditor, reviewer, doc-master, implementer, planner) when their prompt falls below the minimum word count
- Minimum word count enforcement fires **regardless of pipeline state** (Issue #716 fix) — this gate is always active for critical agents, not just during `/implement` batches
- Baseline shrinkage check (detecting > 25% compression vs first-issue baseline) fires **whenever a baseline exists** (Issue #723 — no pipeline-active gate); when no baseline exists, the hook seeds one from the **observed word count** of the current prompt at `issue_number=0` (Issue #759 fix — template-based seeding produced ~1700-word baselines that blocked legitimate ~200-400-word task-specific prompts even with a 0.70 slack factor); template-based seeding via `seed_baselines_from_templates()` is reserved for batch-mode pre-seeding at batch start with appropriate slack
- Uses `validate_prompt_integrity()` which imports `COMPRESSION_CRITICAL_AGENTS` and `MIN_CRITICAL_AGENT_PROMPT_WORDS` from `prompt_integrity.py` (minimum: 80 words)
- Shrinkage check calls `validate_prompt_word_count` with `max_shrinkage=0.25` (25%, higher than the library default of 15% to allow legitimate prompt variation at the hook level)
- Block message directs the coordinator to reconstruct the prompt with full context and use `get_agent_prompt_template()` to reload the agent base prompt from disk
- Fails open in two cases: ImportError when `prompt_integrity` module is unavailable, and any Exception raised during the baseline check

**Infrastructure Protection** (scoped to autonomous-dev repos):
- Write/Edit to `agents/*.md`, `commands/*.md`, `hooks/*.py`, `lib/*.py`, `skills/*/SKILL.md` are blocked outside the `/implement` pipeline
- Scoped to autonomous-dev repos (detected via `_is_autonomous_dev_repo()`) — does not affect user projects
- User-facing docs (`README.md`, `CHANGELOG.md`, `docs/*.md`), config files (`.json`/`.yaml`), and all non-infrastructure paths are unaffected

**Agent Denial Fallback Guard** (Issue #750):
- When the Prompt Integrity Gate denies an Agent/Task invocation due to prompt shrinkage, the orchestrator may fall back to direct Write/Edit calls to the same protected infrastructure files
- `_record_agent_denial(agent_type)` writes a session-scoped JSON state file at `AGENT_DENY_STATE_DIR` (`/tmp/adev-agent-deny-{session_id}.json`) immediately after any prompt-integrity denial
- `_check_agent_denial()` is called at the top of every Write/Edit check; if a denial record exists within `AGENT_DENY_TTL` (300 seconds) for the same session, the Write/Edit to a protected infrastructure path is blocked
- Block message includes a `REQUIRED NEXT ACTION` directive telling the orchestrator to reload the agent prompt template via `get_agent_prompt_template()` and retry the Agent call with a full-length prompt
- Non-infrastructure paths (docs, config, test files) are unaffected — the guard only activates for the same `_is_protected_infrastructure()` paths that the base infrastructure gate covers
- Fails open on all state file errors (`_record_agent_denial` swallows exceptions; `_check_agent_denial` returns `None` on any error) to avoid blocking legitimate work

**GitHub Issue Creation Gate** (Issue #599):
- Direct `gh issue create` in Bash is blocked outside approved contexts to enforce the `/create-issue` pipeline (research, duplicate detection, proper formatting)
- Allow-through 1: an active `/implement` pipeline is present (`/tmp/implement_pipeline_state.json`)
- Allow-through 2: the current agent is `continuous-improvement-analyst` or `issue-creator` (authorized for direct issue creation)
- Allow-through 3: a fresh marker file exists at `GH_ISSUE_MARKER_PATH` (`/tmp/autonomous_dev_gh_issue_allowed.marker`, valid for 1 hour) — written only by the active `/implement` pipeline (commands no longer write this file; see Issue #627)
- Allow-through 4 (Issue #630, #647, #663): a command context file exists at `GH_ISSUE_COMMAND_CONTEXT_PATH` (`/tmp/autonomous_dev_cmd_context.json`, valid for 1 hour) with a `command` field set to one of `create-issue`, `plan-to-issues`, `improve`, `refactor`, or `retrospective` — the hook auto-writes this file in the `NATIVE_TOOLS` fast path when it detects a `Skill` tool invocation for one of these commands (before any downstream Bash `gh issue create` check fires); uses file mtime for age check (harder to spoof than an embedded JSON timestamp)
- Block message directs the user to `/create-issue` or `/create-issue --quick`; also includes a FORBIDDEN clause explicitly prohibiting suggestions to run `! gh issue create` or any other bypass method (the `!` prefix runs commands outside the hook system)
- Fails open on any detection error to avoid blocking legitimate work

**Marker File Creation Guard** (Issue #627):
- Blocks direct creation of the marker file `autonomous_dev_gh_issue_allowed.marker` outside approved contexts, closing the bypass where manually writing the marker file would short-circuit the gh issue create gate
- Uses deny-by-default logic: if the substring `autonomous_dev_gh_issue_allowed` appears anywhere in the command, the command is blocked unless the operation is provably read-only or a delete — this prevents bypass via novel write methods (e.g. `python3 -c "..."`, `dd`, `install`, `os.open`) that a fixed allowlist would miss
- Allowed (not blocked): read-only verbs (`cat`, `ls`, `stat`, `test`, `head`, `tail`, `wc`, `file`, `readlink`, `[`), delete (`rm`), reference-only mentions (`grep`; `echo`/`printf` without a redirect targeting the marker file)
- Allow-through 1: active `/implement` pipeline (the pipeline legitimately writes the marker when authorizing issue creation)
- Allow-through 2: agent name in `GH_ISSUE_AGENTS` (`continuous-improvement-analyst`, `issue-creator`)
- Allow-through 3: issue-creating command is active (`_is_issue_command_active()`) — commands such as `/create-issue`, `/plan-to-issues`, `/improve`, `/refactor`, `/retrospective`
- No marker-file allow-through (circular — the guard protects the marker itself)
- Fails open on any detection error to avoid blocking legitimate work

See [SANDBOXING.md](SANDBOXING.md) for complete security architecture.

### PreCommit

| Hook | Purpose | Key Env Vars |
|------|---------|--------------|
| **auto_format.py** | Code formatting (black + isort, prettier) | AUTO_FORMAT |
| **auto_test.py** | Run related test files | AUTO_TEST |
| **security_scan.py** | Secrets detection, vulnerability scanning | SECURITY_SCAN |
| **enforce_tdd.py** | TDD workflow enforcement (tests before code) | ENFORCE_TDD |
| **enforce_regression_test.py** | Blocks `fix:`, `bugfix:`, and `hotfix:` commits when no test files are staged. Uses `bugfix_detector.is_bugfix_commit()` to detect prefixes. Fails open when `bugfix_detector` library is unavailable. Follows stick+carrot pattern: block message includes `REQUIRED NEXT ACTION` directing the committer to add a failing-then-passing regression test. Exception: pass `--no-verify` and document the covering test in the commit body when an existing test already covers the regression. (Issue #737) | — |
| **enforce_orchestrator.py** | PROJECT.md alignment validation | — |
| **validate_project_alignment.py** | PROJECT.md forbidden sections detection | VALIDATE_PROJECT_ALIGNMENT |
| **validate_command_file_ops.py** | Commands execute Python libs, not just describe them | — |
| **validate_session_quality.py** | Session log completeness | — |
| **auto_fix_docs.py** | Documentation consistency auto-fixes | AUTO_FIX_DOCS |
| **validate_claude_md_size.py** | Warns when CLAUDE.md exceeds 200 lines (Anthropic best practice). Non-blocking — always exits 0. | — |

### SubagentStop

| Hook | Purpose | Key Env Vars |
|------|---------|--------------|
| **unified_session_tracker.py** | Session logging, pipeline tracking, progress updates. Reads stdin JSON from Claude Code, computes duration_ms, validates agent_transcript_path, writes JSONL for pipeline_intent_validator ghost detection. Status determination uses `CLAUDE_AGENT_STATUS` env var as authoritative signal when present; falls back to `_determine_success()` text scan only when the env var is absent (Issue #541). Session isolation: when `CLAUDE_SESSION_ID` is set, both `SessionTracker` file selection and `check_pipeline_complete()` filter to the matching session, preventing cross-session contamination when multiple batches run on the same day (Issue #594). Each JSONL entry now includes a `plugin_version` field (e.g. `"3.50.0 (abc1234)"`) populated via `version_reader.get_plugin_version()` for diagnostics and issue triage (Issue #630). | TRACK_SESSIONS, TRACK_PIPELINE, CLAUDE_AGENT_STATUS, CLAUDE_SESSION_ID |

### PostToolUse

| Hook | Purpose | Key Env Vars |
|------|---------|--------------|
| **plan_mode_exit_detector.py** | Detects `ExitPlanMode` tool calls and writes a marker at `.claude/plan_mode_exit.json`. Marker is consumed by `unified_prompt_validator.py` to enforce `/implement` or `/create-issue` routing before raw edits are allowed. Auto-expires after 30 minutes. Always exits 0. | — |
| **session_activity_logger.py** | Structured JSONL activity logging for continuous improvement analysis. Handles PostToolUse (tool calls) and UserPromptSubmit (user prompts). Sets `"hook": "PostToolUse"` correctly for tool-call entries. Falls back to parsing hook stdin JSON for `session_id` when `CLAUDE_SESSION_ID` env var is absent (common in PostToolUse lifecycle). Session date pinned on first activity to prevent midnight log splits. For Agent/Task tool outputs, extracts `total_tokens`, `tool_uses`, and `agent_duration_ms` from `<usage>` blocks in the result text (Issue #704) — consumed by `pipeline_timing_analyzer.py` for token efficiency analysis. Worktree-aware log directory resolution (Issue #755): when the hook's CWD is inside a `.worktrees/` directory, `_find_log_dir()` runs `git rev-parse --git-common-dir` to locate the parent repo's `.claude/logs/activity/` directory, so downstream agent events written from a worktree land in the same log file as main-session events; falls through to normal walk-up resolution on any git error or when the parent `.claude/` directory does not exist. Non-blocking. | ACTIVITY_LOGGING |

### PreCompact

| Hook | Purpose | Key Env Vars |
|------|---------|--------------|
| **pre_compact_batch_saver.sh** | Saves in-progress batch and/or pipeline state to `.claude/compaction_recovery.json` before context compaction. Captures batch_id, current_index, feature list, and RALPH checkpoint data when a batch is active. Also captures `/implement` pipeline state (run_id, feature, current step, steps completed/remaining, modified files) from `/tmp/implement_pipeline_state.json` when a pipeline run is active. No-ops when neither batch nor pipeline is active. Always exits 0. | CHECKPOINT_DIR, PIPELINE_STATE_FILE, PIPELINE_STATE_DIR |

### PostCompact

| Hook | Purpose | Key Env Vars |
|------|---------|--------------|
| **post_compact_enricher.sh** | Enriches the compaction recovery marker with the compact_summary from stdin JSON after compaction completes. No-ops if no recovery marker present. Always exits 0. | — |

**Compaction recovery flow**: PreCompact saves state (batch and/or pipeline) → PostCompact adds summary → UserPromptSubmit (`unified_prompt_validator.py`) detects marker on next prompt, re-injects batch and/or pipeline context into model output, and deletes marker. Pipeline recovery validates staleness (discarded if >900 seconds old) and cwd match before injecting. This ensures both batch pipelines and single `/implement` pipeline runs resume correctly after `/clear` or auto-compact without requiring manual state reconstruction.

### TaskCompleted

| Hook | Purpose | Key Env Vars |
|------|---------|--------------|
| **task_completed_handler.py** | Logs task completion events (task_id, subject, description, teammate, team) to the daily activity JSONL at `.claude/logs/activity/{date}.jsonl`. Preparation handler: TaskCompleted does not currently fire in the Agent-tool pipeline but is registered so infrastructure is ready. Always exits 0. | — |

### Stop

| Hook | Purpose | Key Env Vars |
|------|---------|--------------|
| **stop_quality_gate.py** | End-of-turn quality checks (pytest, ruff, mypy). Auto-detects tools, parallel execution, 60s timeout. Always non-blocking. | ENFORCE_QUALITY_GATE |
| **conversation_archiver.py** | Archives complete Claude Code conversation transcripts to `~/.claude/archive/` on every Stop event for long-term pattern analysis. Writes session metadata to both `~/.claude/archive/index.jsonl` (JSONL, jq/grep compatible) and `~/.claude/archive/sessions.db` (SQLite, queryable via Python sqlite3 or DuckDB). Pure Python stdlib, non-blocking, always exits 0. Enabled via `CONVERSATION_ARCHIVE=true` env var. (Issue #773) | CONVERSATION_ARCHIVE |

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
