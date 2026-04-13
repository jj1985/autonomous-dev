# autonomous-dev

Development harness for Claude Code. Deterministic enforcement, specialist agents, alignment gates — 12 elements of harness engineering.

## Critical Rules

- **NEVER direct-edit without `/implement`**: `agents/*.md`, `commands/*.md`, `hooks/*.py`, `lib/*.py`, `skills/*/SKILL.md` — these are functional infrastructure. Hook-enforced: `unified_pre_tool.py` blocks Write/Edit to these paths outside the pipeline.
- **Direct editing is only for**: user-facing docs (README.md, CHANGELOG.md, docs/*.md), config (.json/.yaml), typos (1-2 lines).
- **After plan mode approval → use `/implement`**: The plan IS the input to `/implement`, not a license to bypass it.
- **Run `/improve` after `/implement` sessions.** Use `--auto-file` to create GitHub issues.
- **Use `/clear` after each feature.** Prevents context bloat.
- **Deploy with `bash scripts/deploy-all.sh`** — never manual `cp -rf`. Script handles local, remote (Mac Studio), validation, and integrity checks.
- **Don't simplify, redesign, or consolidate agents.** The pipeline, hooks, and enforcement are validated over months of real use. The cost is tokens, not complexity. Complexity is the mechanism.

## Build & Test

Testing uses the **Diamond Model** (not traditional TDD pyramid). Acceptance criteria drive testing; unit tests are regression locks, not specifications. See [docs/TESTING-STRATEGY.md](docs/TESTING-STRATEGY.md).

```bash
# Run full deterministic suite (unit + integration + regression + security + property)
pytest --tb=short -q

# Run specific test file
pytest tests/unit/hooks/test_native_tool_auto_approval.py -v

# Run by layer
pytest tests/unit/                    # Layer 2: Unit tests (regression locks)
pytest tests/property/                # Layer 3: Property-based invariants (Hypothesis)
pytest tests/integration/             # Layer 4: Integration & contract tests
pytest tests/regression/smoke/        # Fast critical-path smoke tests
pytest tests/security/                # Security-specific tests

# GenAI tests (LLM-as-judge, probabilistic — not in default runs)
pytest tests/genai/ --genai           # Layer 5: Semantic validation (~$0.02/run)
pytest tests/genai/ --genai --strict-genai  # Strict mode (no soft failures)

# Property tests with CI thoroughness
HYPOTHESIS_PROFILE=ci pytest tests/property/  # 200 examples per test (vs 50 default)

# Coverage
pytest --cov=plugins/autonomous-dev/hooks --cov=plugins/autonomous-dev/lib --cov-report=term-missing
```

**Test directories → Diamond layers**: `tests/unit/` (L2), `tests/property/` (L3), `tests/integration/` + `tests/regression/` (L4), `tests/genai/` (L5), `tests/spec_validation/` (L5/L6).

## Architecture

- **Pipeline**: 8-step SDLC (15 internal steps) — alignment → research → plan → acceptance tests → implement → validate → verify → git
- **Enforcement**: 22 hooks with JSON `{"decision": "block"}` hard gates (not prompt-level nudges)
- **Agents**: 15 specialists with fresh context per invocation, model-tiered (Haiku/Sonnet/Opus)
- **Skills**: 17 domain packages, progressively injected per-step to prevent context bloat

Component counts: 15 agents, 17 skills, 22 commands, 22 hooks, 196 libraries.

## Commands

`/plan` | `/implement` (full, --light, --batch, --issues, --resume, --fix) | `/create-issue` (--quick) | `/plan-to-issues` (--quick) | `/align` (--project, --docs, --retrofit) | `/audit` (--quick, --security, --docs, --code, --tests) | `/setup` | `/sync` (--github, --env, --all, --uninstall) | `/health-check` | `/advise` | `/worktree` (--list, --status, --merge, --discard) | `/scaffold-genai-uat` | `/status` | `/refactor` (--tests, --docs, --code, --fix, --quick) | `/sweep` | `/improve` (--auto-file) | `/retrospective` | `/mem-search` | `/skill-eval` (--quick, --skill, --update) | `/autoresearch` (--target, --metric, --iterations, --min-improvement, --dry-run)

## Key Paths

| What | Where |
|------|-------|
| Alignment source of truth | [.claude/PROJECT.md](.claude/PROJECT.md) |
| Pipeline command | `plugins/autonomous-dev/commands/implement.md` |
| State machine | `plugins/autonomous-dev/lib/pipeline_state.py` |
| Hook enforcement | `plugins/autonomous-dev/hooks/unified_pre_tool.py` |
| Agent definitions | `plugins/autonomous-dev/agents/` |
| Test suite | `tests/` (unit, integration, regression, security, hooks, genai) |
| Activity logs | `.claude/logs/activity/` |
| Architecture details | [docs/ARCHITECTURE-OVERVIEW.md](docs/ARCHITECTURE-OVERVIEW.md) |
| Troubleshooting | [plugins/autonomous-dev/docs/TROUBLESHOOTING.md](plugins/autonomous-dev/docs/TROUBLESHOOTING.md) |

## Session Continuity

`SessionStart-batch-recovery.sh` auto-restores batch state after `/clear` or auto-compact. Activity logged to `.claude/logs/activity/` by `session_activity_logger.py`.

**Last Updated**: 2026-04-12
