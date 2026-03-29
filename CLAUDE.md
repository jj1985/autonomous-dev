# autonomous-dev

Plugin for autonomous development in Claude Code. AI agents, skills, automation hooks, slash commands.

## Project Overview

Autonomous development plugin that provides:
- **8-step SDLC pipeline**: alignment → research → plan → test → implement → validate → verify → git
- **Batch processing**: Process multiple features/issues with worktree isolation
- **Git automation**: AUTO_GIT_ENABLED for commit/push workflows

## Installation

```bash
bash <(curl -sSL https://raw.githubusercontent.com/akaszubski/autonomous-dev/master/install.sh)
```

Then restart Claude Code (Cmd+Q / Ctrl+Q). For subsequent updates, run `/sync` then `/reload-plugins`.

## Critical Rules

- **Direct editing is only for**: user-facing docs (README.md, CHANGELOG.md, docs/*.md), config (.json/.yaml), typos (1-2 lines).
- **NEVER direct-edit without `/implement`**: `agents/*.md`, `commands/*.md`, `hooks/*.py`, `lib/*.py`, `skills/*/SKILL.md` — these are functional infrastructure, not documentation. This rule is **hook-enforced**: `unified_pre_tool.py` blocks Write/Edit to these paths when the `/implement` pipeline is not active (Issue #483).
- **After plan mode approval → use `/implement`**: The plan IS the input to `/implement`, not a license to bypass it.
- **Run `/improve` after `/implement` sessions.** Use `--auto-file` to create GitHub issues for findings.
- **Use `/clear` after each feature.** Prevents context bloat.

## Commands

| Command | Purpose |
|---------|---------|
| `/implement` | Code changes (full pipeline, --light, --batch, --issues, --resume, --fix) |
| `/create-issue` | GitHub issue with automated research (--quick) |
| `/plan-to-issues` | Batch-convert plan into GitHub issues (--quick) |
| `/align` | Alignment check (--project, --docs, --retrofit) |
| `/audit` | Quality audit (--quick, --security, --docs, --code, --claude, --tests) |
| `/setup` | Interactive setup wizard |
| `/sync` | Update plugin (--github, --env, --marketplace, --all, --uninstall) |
| `/health-check` | Validate plugin integrity |
| `/advise` | Critical thinking analysis |
| `/worktree` | Git worktrees (--list, --status, --merge, --discard) |
| `/scaffold-genai-uat` | Scaffold LLM-as-judge tests into any repo |
| `/status` | View PROJECT.md goal progress |
| `/refactor` | Unified code, docs, test optimization (--tests, --docs, --code, --fix, --quick) |
| `/sweep` | Alias for /refactor --quick |
| `/improve` | Automation health analysis — pipeline enforcement, bypasses |
| `/retrospective` | Session drift detection — intent evolution, repeated corrections, memory rot |
| `/mem-search` | Search claude-mem persistent memory (optional) |

## Session Continuity

The `SessionStart-batch-recovery.sh` hook automatically restores batch state after `/clear` or auto-compact. Session activity is logged to `.claude/logs/activity/` by the `session_activity_logger.py` hook.

## Project Alignment

- **Goals/Scope**: See [.claude/PROJECT.md](.claude/PROJECT.md)
- **Operations**: See [.claude/local/OPERATIONS.md](.claude/local/OPERATIONS.md) (repo-specific procedures)

## Component Counts

12 agents, 17 skills, 20 active commands, 183 libraries, 25 active hooks. See [docs/ARCHITECTURE-OVERVIEW.md](docs/ARCHITECTURE-OVERVIEW.md) for details.

## Detailed Guides

| Topic | Location |
|-------|----------|
| Workflow discipline | [docs/WORKFLOW-DISCIPLINE.md](docs/WORKFLOW-DISCIPLINE.md) |
| Context management | [docs/CONTEXT-MANAGEMENT.md](docs/CONTEXT-MANAGEMENT.md) |
| Architecture | [docs/ARCHITECTURE-OVERVIEW.md](docs/ARCHITECTURE-OVERVIEW.md) |
| Batch processing | [docs/BATCH-PROCESSING.md](docs/BATCH-PROCESSING.md) |
| Git automation | [docs/GIT-AUTOMATION.md](docs/GIT-AUTOMATION.md) |
| Sandboxing | [docs/SANDBOXING.md](docs/SANDBOXING.md) |
| Libraries | [docs/LIBRARIES.md](docs/LIBRARIES.md) |
| Performance | [docs/PERFORMANCE.md](docs/PERFORMANCE.md) |
| Testing strategy | [docs/TESTING-STRATEGY.md](docs/TESTING-STRATEGY.md) |
| claude-mem integration | [docs/CLAUDE-MEM-INTEGRATION.md](docs/CLAUDE-MEM-INTEGRATION.md) |
| Troubleshooting | [plugins/autonomous-dev/docs/TROUBLESHOOTING.md](plugins/autonomous-dev/docs/TROUBLESHOOTING.md) |

**Last Updated**: 2026-03-19
